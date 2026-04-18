"""runner.py — Evidence attachment orchestration: attach_evidence, main().

Extracted from attach_evidence.py (Phase 5). Orchestrates per-file and
per-product evidence block generation and frontmatter writing.
"""
from __future__ import annotations

import sys
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from knowledge_core import Knowledge  # noqa: E402
from content_discovery import (  # noqa: E402  (R-1b: was knowledge_core)
    discover_content,
    discover_products,
    infer_product,
)
from core.markdown import parse_frontmatter  # noqa: E402  (R-2a: was knowledge_core)
from token_ops import (  # noqa: E402
    extract_tokens,
    verify_tokens,
)
from evidence.mapper import (  # noqa: E402
    _map_tokens_to_evidence,
    _detect_formats,
    _build_sections_evidence,
)
from evidence.writer import _write_evidence_to_frontmatter  # noqa: E402


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def attach_evidence(filepath, knowledge, dry_run=False, force=False) -> str:
    """Build and write evidence block for one file. Returns status string."""
    fm = parse_frontmatter(filepath)

    # Never attach evidence to draft pages — they are not live content.
    if fm.get("draft") is True:
        return "SKIP (draft)"

    existing = fm.get("evidence") or {}

    # Already up to date — idempotent skip (bypass with --force)
    if not force and isinstance(existing, dict) and \
            existing.get("model_sha") == knowledge.repo_sha:
        return "SKIP (current)"

    platform = knowledge.platform

    # Extract and verify API tokens (page-level)
    tokens = extract_tokens(filepath, platform)
    findings = verify_tokens(tokens, knowledge, filepath)
    fails = [f for f in findings if f.level == "FAIL"]
    if fails:
        _log(f"  SKIP {filepath}: {len(fails)} audit FAIL(s) — fix before attaching evidence")
        return "SKIP (audit FAILs)"

    # Map verified tokens → claim_ids via deterministic index (aggregate)
    claim_ids, api_refs = _map_tokens_to_evidence(tokens, knowledge)

    # For reference pages: inject the documented class as primary api_ref when no
    # code-block tokens yielded API refs. Reference pages document a class in
    # method/property tables (not inline code), so extract_tokens() returns nothing.
    # The class name from the title IS the authoritative evidence anchor per AGENTS.md §6:
    # "A reference page with an empty evidence.apis block is a structural gap."
    if "reference.aspose.org" in str(filepath) and not api_refs:
        title = fm.get("title", "")
        # Title format: "ClassName — Aspose.Note FOSS for Python API Reference"
        # Index pages have no "—" separator and document no single class — skip them.
        if "—" in title:
            class_candidate = title.split("—")[0].strip().split()[0]
            if class_candidate and class_candidate in knowledge.classes:
                api_refs.append(class_candidate)
                cid = knowledge.api_to_claim.get(class_candidate)
                if cid and cid not in claim_ids:
                    claim_ids.append(cid)

    # Detect format references (page-level aggregate)
    formats = _detect_formats(filepath, knowledge)

    # Build per-section evidence breakdown
    sections = _build_sections_evidence(filepath, knowledge)

    evidence = {
        "model_sha": knowledge.repo_sha,
        "model_version": knowledge.version,
        "claims": sorted(set(claim_ids)),
        "apis": sorted(set(api_refs)),
    }
    if formats:
        evidence["formats"] = formats
    if sections:
        evidence["sections"] = sections

    if dry_run:
        _log(f"  DRY-RUN {filepath}:")
        _log(f"    claims: {len(evidence['claims'])}, apis: {len(evidence['apis'])}, "
             f"formats: {len(formats)}, sections: {len(sections)}")
        for sec in sections:
            _log(f"      [{sec['line']}] {sec['heading']}: "
                 f"claims={len(sec['claims'])}, apis={len(sec['apis'])}")
        return "DRY-RUN"

    ok = _write_evidence_to_frontmatter(filepath, evidence)
    if ok:
        # Auto-grade: pages reaching here have 0 FAILs (line 58 returns on FAILs).
        from content_eval.models import compute_grade, Page  # noqa: E402
        from content_eval import EVALUATOR_LOGIC_VERSION  # noqa: E402
        from grade_writer import write_grade  # noqa: E402
        warn_count = sum(1 for f in findings if f.level == "WARN")
        fail_count = 0
        evaluator_tier = "audit"

        # For reference pages: also run description_completeness to catch empty
        # description tables. attach_evidence normally uses only verify_tokens()
        # (audit tier), which checks API accuracy but not content completeness.
        # Without this, pages with 100% empty description cells grade A because
        # verify_tokens() finds 0 FAILs when all API names are structurally correct.
        if "reference.aspose.org" in str(filepath):
            try:
                from content_eval.evaluators.description_completeness import (  # noqa: E402
                    DescriptionCompletenessEvaluator,
                )
                page = Page.load(Path(filepath))
                dc_findings = DescriptionCompletenessEvaluator().evaluate(page, knowledge)
                fail_count += sum(1 for f in dc_findings if f.level == "FAIL")
                warn_count += sum(1 for f in dc_findings if f.level == "WARN")
                if dc_findings:
                    evaluator_tier = "audit,description_completeness"
            except Exception:
                pass  # never block evidence writing on evaluator errors

        grade = compute_grade(fail_count, warn_count)
        write_grade(filepath, grade, model_sha=knowledge.repo_sha,
                    evaluator_tier=evaluator_tier, logic_version=EVALUATOR_LOGIC_VERSION)
    return "UPDATED" if ok else "ERROR"


def attach_product(family, platform, dry_run=False, force=False) -> dict:
    """Attach evidence to all content files for a product."""
    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        _log(f"  SKIP {family}/{platform}: no knowledge model")
        return {}

    files = discover_content(family, platform)
    if not files:
        _log(f"  SKIP {family}/{platform}: no content files")
        return {}

    _log(f"  {family}/{platform}: {len(files)} files")
    counts = {"UPDATED": 0, "SKIP (current)": 0, "SKIP (draft)": 0,
              "SKIP (audit FAILs)": 0, "DRY-RUN": 0, "ERROR": 0}
    for f in files:
        status = attach_evidence(f, knowledge, dry_run=dry_run, force=force)
        counts[status] = counts.get(status, 0) + 1

    _log(f"    -> {counts}")
    return counts


def attach_files(file_paths, dry_run=False, force=False) -> dict:
    """Attach evidence to specific files."""
    knowledge_cache = {}
    counts = {}
    for fp in file_paths:
        fp = Path(fp)
        if not fp.exists():
            _log(f"  SKIP {fp}: not found")
            continue
        family, platform = infer_product(fp)
        if not family:
            _log(f"  SKIP {fp}: cannot infer product")
            continue
        key = (family, platform)
        if key not in knowledge_cache:
            knowledge_cache[key] = Knowledge(family, platform)
        knowledge = knowledge_cache[key]
        if not knowledge.available:
            _log(f"  SKIP {fp}: no knowledge for {family}/{platform}")
            continue
        status = attach_evidence(fp, knowledge, dry_run=dry_run, force=force)
        counts[status] = counts.get(status, 0) + 1
    _log(f"  -> {counts}")
    return counts


def _auto_refresh(family, platform):
    """Run refresh_knowledge.py for a product if --auto-refresh is set."""
    import subprocess
    script = Path(__file__).parent.parent / "refresh_knowledge.py"
    if not script.exists():
        _log(f"  WARNING: refresh_knowledge.py not found, skipping auto-refresh")
        return
    _log(f"  Auto-refreshing knowledge for {family}/{platform}...")
    result = subprocess.run(
        [sys.executable, str(script), family, platform],
        cwd=str(Path(__file__).resolve().parents[3]),
    )
    if result.returncode != 0:
        _log(f"  WARNING: refresh_knowledge.py failed (exit {result.returncode}), "
             "continuing with existing knowledge")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args
    files_mode = "--files" in args
    auto_refresh = "--auto-refresh" in args
    args = [a for a in args if not a.startswith("--")]

    if files_mode:
        _log("Attaching evidence to specified files...")
        attach_files(args, dry_run=dry_run, force=force)
    elif len(args) >= 2:
        family, platform = args[0], args[1]
        if auto_refresh:
            _auto_refresh(family, platform)
        _log(f"Attaching evidence for {family}/{platform}...")
        attach_product(family, platform, dry_run=dry_run, force=force)
    elif len(args) == 1 and args[0] == "all":
        products = discover_products()
        _log(f"Attaching evidence for {len(products)} products...")
        total = {}
        for family, platform in products:
            if auto_refresh:
                _auto_refresh(family, platform)
            counts = attach_product(family, platform, dry_run=dry_run, force=force)
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
        _log(f"\nTotal: {total}")
    else:
        import attach_evidence as _ae
        print(_ae.__doc__)
        sys.exit(1)

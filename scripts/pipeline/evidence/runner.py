"""runner.py — Evidence attachment orchestration: attach_evidence, main().

Extracted from attach_evidence.py (Phase 5). Orchestrates per-file and
per-product evidence block generation and frontmatter writing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from knowledge_core import Knowledge  # noqa: E402
from content_discovery import (  # noqa: E402  (R-1b: was knowledge_core)
    discover_content,
    discover_products,
    infer_product,
    _infer_subdomain,
)
from core.markdown import parse_frontmatter  # noqa: E402  (R-2a: was knowledge_core)
from token_ops import (  # noqa: E402
    extract_tokens,
    verify_tokens,
)
from evidence.mapper import (  # noqa: E402
    _map_tokens_to_evidence,
    _api_name_fallback_match,
    _detect_formats,
    _build_sections_evidence,
    _semantic_match_claims,
)
from evidence.writer import _write_evidence_to_frontmatter  # noqa: E402


# ---------------------------------------------------------------------------
# configure() seam — T1/T2 compliance (AGENTS.md §16.2)
# ---------------------------------------------------------------------------

_cfg_extract_tokens_fn = None
_cfg_verify_tokens_fn = None
_cfg_map_tokens_fn = None
_cfg_detect_formats_fn = None
_cfg_build_sections_fn = None
_cfg_write_evidence_fn = None
_cfg_infer_product_fn = None
_cfg_knowledge_fn = None
_cfg_write_grade_fn = None
_cfg_compute_grade_fn = None
_cfg_evaluator_logic_version = None
_cfg_semantic_evidence = False


def configure(
    extract_tokens_fn=None,
    verify_tokens_fn=None,
    map_tokens_fn=None,
    detect_formats_fn=None,
    build_sections_fn=None,
    write_evidence_fn=None,
    infer_product_fn=None,
    knowledge_fn=None,
    write_grade_fn=None,
    compute_grade_fn=None,
    evaluator_logic_version=None,
    semantic_evidence=False,
) -> None:
    """Inject test dependencies. Call configure() with no args to reset."""
    global _cfg_extract_tokens_fn, _cfg_verify_tokens_fn, _cfg_map_tokens_fn
    global _cfg_detect_formats_fn, _cfg_build_sections_fn, _cfg_write_evidence_fn
    global _cfg_infer_product_fn, _cfg_knowledge_fn
    global _cfg_write_grade_fn, _cfg_compute_grade_fn, _cfg_evaluator_logic_version
    global _cfg_semantic_evidence
    _cfg_extract_tokens_fn = extract_tokens_fn
    _cfg_verify_tokens_fn = verify_tokens_fn
    _cfg_map_tokens_fn = map_tokens_fn
    _cfg_detect_formats_fn = detect_formats_fn
    _cfg_build_sections_fn = build_sections_fn
    _cfg_write_evidence_fn = write_evidence_fn
    _cfg_infer_product_fn = infer_product_fn
    _cfg_knowledge_fn = knowledge_fn
    _cfg_write_grade_fn = write_grade_fn
    _cfg_compute_grade_fn = compute_grade_fn
    _cfg_evaluator_logic_version = evaluator_logic_version
    _cfg_semantic_evidence = semantic_evidence


_KNOWN_SUBDOMAINS = frozenset(
    name for name, _ in
    # avoid importing SITE_PATHS at module level since content_discovery may not
    # be on sys.path yet during import; resolved lazily in attach_product()
    [
        ("products.aspose.org", ""),
        ("reference.aspose.org", ""),
        ("docs.aspose.org", ""),
        ("blog.aspose.org", ""),
        ("kb.aspose.org", ""),
    ]
)


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def _append_skip_record(records: list, filepath, reason: str, existing_claims=None):
    """Append a SKIP record to a dry_run_records accumulator."""
    from pathlib import Path as _Path
    records.append({
        "filepath": str(filepath),
        "subdomain": _infer_subdomain(_Path(filepath)),
        "action": "SKIP",
        "existing_claims": sorted(existing_claims or []),
        "proposed_claims": [],
        "added_claims": [],
        "stale_claims": [],
        "skip_reason": reason,
        "token_matches": [],
    })


def _build_audit_grade_reasons(
    grade: str,
    fail_count: int,
    warn_count: int,
    findings: list,
    extra_findings: list | None = None,
) -> list[str]:
    """Build grade_reasons for audit-tier grading in evidence runner.

    Simpler than EvalReport.grade_reasons() because the evidence runner only
    runs audit-tier checks (verify_tokens) plus optionally
    description_completeness and content_substance for reference pages.

    Only accesses .level, .line_no, .message on findings — attributes common
    to both token_ops.Finding and content_eval.models.Finding.
    """
    reasons: list[str] = []
    if fail_count == 0 and warn_count == 0:
        reasons.append("No findings -> grade A")
        return reasons

    all_findings = list(findings) + (extra_findings or [])
    if fail_count > 0:
        reasons.append(f"{fail_count} FAIL finding(s) [audit] -> base grade {grade}")
        fails = [f for f in all_findings if f.level == "FAIL"]
        if fails:
            loc = f" (line {fails[0].line_no})" if fails[0].line_no else ""
            reasons.append(f"audit FAIL: {fails[0].message}{loc}")
    elif warn_count > 0:
        reasons.append(f"{warn_count} WARN finding(s) [audit] -> base grade {grade}")

    return reasons


def attach_evidence(filepath, knowledge, dry_run=False, force=False,
                    dry_run_records=None) -> str:
    """Build and write evidence block for one file. Returns status string.

    Args:
        dry_run_records: When not None, append a ClaimPlan record dict to this
            list instead of (or in addition to) writing. Used by --dry-run-json.
    """
    fm = parse_frontmatter(filepath)

    # Never attach evidence to draft pages — they are not live content.
    if fm.get("draft") is True:
        if dry_run_records is not None:
            _append_skip_record(dry_run_records, filepath, "draft")
        return "SKIP (draft)"

    existing = fm.get("evidence") or {}

    # Already up to date — idempotent skip (bypass with --force)
    # Also surface WOULD_UPDATE_METADATA when claims_hash differs (GAP-14 Phase 1).
    # Guard: only skip when claims is not None. claims=None means evidence was never
    # fully attached (e.g. manual `claims: null` in YAML after partial run); re-attach.
    # claims=[] is a valid complete state for pages with no API claims; still skip.
    _existing_claims_not_null = (
        isinstance(existing, dict) and existing.get("claims") is not None
    )
    if not force and isinstance(existing, dict) and \
            existing.get("model_sha") == knowledge.repo_sha and \
            _existing_claims_not_null:
        page_claims_hash = existing.get("claims_hash", "")
        if dry_run_records is not None:
            knowledge_claims_hash = getattr(knowledge, "claims_hash", "")
            if page_claims_hash and knowledge_claims_hash and \
                    page_claims_hash != knowledge_claims_hash:
                # claims.json changed but SHA unchanged — report as WOULD_UPDATE_METADATA
                dry_run_records.append({
                    "filepath": str(filepath),
                    "subdomain": _infer_subdomain(Path(filepath)),
                    "action": "WOULD_UPDATE_METADATA",
                    "existing_claims": sorted(existing.get("claims", [])),
                    "proposed_claims": [],
                    "added_claims": [],
                    "stale_claims": [],
                    "skip_reason": "model_sha current but claims_hash differs",
                    "token_matches": [],
                    "current_claims_hash": page_claims_hash,
                    "knowledge_claims_hash": knowledge_claims_hash,
                })
            else:
                _append_skip_record(dry_run_records, filepath, "current",
                                    existing_claims=existing.get("claims", []))
        return "SKIP (current)"

    platform = knowledge.platform

    # Extract and verify API tokens (page-level)
    _eff_extract_tokens = _cfg_extract_tokens_fn if _cfg_extract_tokens_fn is not None else extract_tokens
    _eff_verify_tokens = _cfg_verify_tokens_fn if _cfg_verify_tokens_fn is not None else verify_tokens
    tokens = _eff_extract_tokens(filepath, platform)
    findings = _eff_verify_tokens(tokens, knowledge, filepath)
    fails = [f for f in findings if f.level == "FAIL"]
    if fails:
        _log(f"  SKIP {filepath}: {len(fails)} audit FAIL(s) — fix before attaching evidence")
        if dry_run_records is not None:
            _append_skip_record(dry_run_records, filepath, f"audit FAILs ({len(fails)})",
                                existing_claims=existing.get("claims", []))
        return "SKIP (audit FAILs)"

    # Map verified tokens → claim_ids via deterministic index (aggregate)
    _eff_map_tokens = _cfg_map_tokens_fn if _cfg_map_tokens_fn is not None else _map_tokens_to_evidence
    claim_ids, api_refs = _eff_map_tokens(tokens, knowledge)

    # CLAIM-EXTRACT-001: fallback for modified APIs mentioned in prose but not code blocks.
    # Scans body text for modified_apis from knowledge_delta.json; avoids double-counting
    # refs already captured by code-block token extraction above.
    already_matched = set(api_refs) | {r.split(".")[0] for r in api_refs}
    fb_claims, fb_refs = _api_name_fallback_match(filepath, knowledge, already_matched)
    for cid in fb_claims:
        if cid not in claim_ids:
            claim_ids.append(cid)
    for ref in fb_refs:
        if ref not in api_refs:
            api_refs.append(ref)

    # TC-EVID-001: Semantic evidence matching — supplement keyword matches with
    # TF-IDF cosine-based claim matching on prose text (outside code blocks).
    if _cfg_semantic_evidence and hasattr(knowledge, "claims"):
        try:
            page_text = filepath.read_text(encoding="utf-8")
            # Strip frontmatter
            if page_text.startswith("---"):
                end_fm = page_text.find("\n---", 3)
                if end_fm != -1:
                    page_text = page_text[end_fm + 4:]
            # Strip code blocks to get prose only
            prose_only = re.sub(r"```[\s\S]*?```", " ", page_text)
            sem_claims = _semantic_match_claims(prose_only, knowledge.claims)
            for cid in sem_claims:
                if cid not in claim_ids:
                    claim_ids.append(cid)
        except (OSError, AttributeError):
            pass  # Graceful degradation

    # Convert Token objects to class_name strings for JSON serialization
    token_matches = [
        t.class_name if hasattr(t, "class_name") else str(t)
        for t in tokens if t
    ]

    # For reference pages: inject the documented class as primary api_ref when no
    # code-block tokens yielded API refs. Reference pages document a class in
    # method/property tables (not inline code), so extract_tokens() returns nothing.
    # The class name from the title IS the authoritative evidence anchor per AGENTS.md §6:
    # "A reference page with an empty evidence.apis block is a structural gap."
    if "reference.aspose.org" in str(filepath) and not api_refs:
        title = fm.get("title", "")
        # Extract the class name: supports both "ClassName — Product Reference" and
        # plain "ClassName" title formats.  The first word before any "—" (or the
        # full title when no separator exists) is the class candidate.
        # Index pages are safely excluded because their titles (e.g. "cells Java
        # Reference") do not appear in knowledge.classes.
        class_candidate = title.split("—")[0].strip().split()[0] if title else ""
        if class_candidate and class_candidate in knowledge.classes:
            api_refs.append(class_candidate)
            cid = knowledge.api_to_claim.get(class_candidate)
            if cid and cid not in claim_ids:
                claim_ids.append(cid)

    # Detect format references (page-level aggregate)
    _eff_detect_formats = _cfg_detect_formats_fn if _cfg_detect_formats_fn is not None else _detect_formats
    formats = _eff_detect_formats(filepath, knowledge)

    # Build per-section evidence breakdown
    _eff_build_sections = _cfg_build_sections_fn if _cfg_build_sections_fn is not None else _build_sections_evidence
    sections = _eff_build_sections(filepath, knowledge)

    evidence = {
        "model_sha": knowledge.repo_sha,
        "model_version": knowledge.version,
        "claims": sorted(set(claim_ids)),
        "apis": sorted(set(api_refs)),
    }
    if hasattr(knowledge, "claim_ids"):
        evidence["_valid_claim_ids"] = set(knowledge.claim_ids)
    if formats:
        evidence["formats"] = formats
    if sections:
        evidence["sections"] = sections

    existing_claims = existing.get("claims", []) if isinstance(existing, dict) else []
    proposed_claims = evidence["claims"]
    added_claims = [c for c in proposed_claims if c not in existing_claims]

    # Append ClaimPlan record when dry_run_records accumulator is provided
    if dry_run_records is not None:
        from evidence.claim_policy import ClaimPolicy, PolicyContext  # noqa: E402
        policy = ClaimPolicy()
        subdomain = _infer_subdomain(Path(filepath))
        claim_records = []
        for cid in proposed_claims:
            ctx = PolicyContext(
                filepath=Path(filepath),
                subdomain=subdomain or "",
                page_role=fm.get("page_role"),
                claim_id=cid,
                claim_kind=None,
                claim_page_role=None,
                claim_source=None,
                token_match_context=None,
            )
            decision = policy.evaluate(ctx)
            claim_records.append({
                "claim_id": cid,
                "policy_status": decision.action,
                "policy_reason": decision.reason,
            })
        knowledge_claims_hash = getattr(knowledge, "claims_hash", "")
        page_claims_hash = existing.get("claims_hash", "") if isinstance(existing, dict) else ""
        dry_run_records.append({
            "filepath": str(filepath),
            "subdomain": subdomain,
            "action": "WOULD_UPDATE",
            "existing_claims": sorted(existing_claims),
            "proposed_claims": claim_records,
            "added_claims": sorted(added_claims),
            "stale_claims": [],
            "skip_reason": None,
            "token_matches": sorted(set(token_matches)),
            "current_claims_hash": page_claims_hash,
            "knowledge_claims_hash": knowledge_claims_hash,
        })

    if dry_run:
        _log(f"  DRY-RUN {filepath}:")
        _log(f"    claims: {len(evidence['claims'])}, apis: {len(evidence['apis'])}, "
             f"formats: {len(formats)}, sections: {len(sections)}")
        for sec in sections:
            _log(f"      [{sec['line']}] {sec['heading']}: "
                 f"claims={len(sec['claims'])}, apis={len(sec['apis'])}")
        return "DRY-RUN"

    _eff_write_evidence = _cfg_write_evidence_fn if _cfg_write_evidence_fn is not None else _write_evidence_to_frontmatter
    ok = _eff_write_evidence(filepath, evidence)
    if ok:
        # Auto-grade: pages reaching here have 0 FAILs (line 58 returns on FAILs).
        from content_eval.models import compute_grade as _cg_default, Page  # noqa: E402
        from content_eval import EVALUATOR_LOGIC_VERSION as _elv_default  # noqa: E402
        from grade_writer import write_grade as _wg_default  # noqa: E402
        compute_grade = _cfg_compute_grade_fn if _cfg_compute_grade_fn is not None else _cg_default
        EVALUATOR_LOGIC_VERSION = _cfg_evaluator_logic_version if _cfg_evaluator_logic_version is not None else _elv_default
        write_grade = _cfg_write_grade_fn if _cfg_write_grade_fn is not None else _wg_default
        warn_count = sum(1 for f in findings if f.level == "WARN")
        fail_count = 0
        evaluator_tier = "audit"
        extra_findings: list = []

        # For reference pages: also run description_completeness and content_substance
        # to catch empty description tables and stub pages. attach_evidence normally uses
        # only verify_tokens() (audit tier), which checks API accuracy but not completeness.
        # Without description_completeness: pages with 100% empty description cells grade A.
        # Without content_substance: pages with <50 prose words silently grade A.
        if "reference.aspose.org" in str(filepath):
            try:
                from content_eval.evaluators.description_completeness import (  # noqa: E402
                    DescriptionCompletenessEvaluator,
                )
                from content_eval.evaluators.content_substance import (  # noqa: E402
                    ContentSubstanceEvaluator,
                )
                page = Page.load(Path(filepath))
                dc_findings = DescriptionCompletenessEvaluator().evaluate(page, knowledge)
                cs_findings = ContentSubstanceEvaluator().evaluate(page, knowledge)
                extra = dc_findings + cs_findings
                extra_findings = extra
                fail_count += sum(1 for f in extra if f.level == "FAIL")
                warn_count += sum(1 for f in extra if f.level == "WARN")
                tiers = ["audit"]
                if dc_findings:
                    tiers.append("description_completeness")
                if cs_findings:
                    tiers.append("content_substance")
                if len(tiers) > 1:
                    evaluator_tier = ",".join(tiers)
            except Exception:
                pass  # never block evidence writing on evaluator errors

        grade = compute_grade(fail_count, warn_count)
        reasons = _build_audit_grade_reasons(
            grade, fail_count, warn_count, findings, extra_findings,
        )
        write_grade(filepath, grade, model_sha=knowledge.repo_sha,
                    evaluator_tier=evaluator_tier, logic_version=EVALUATOR_LOGIC_VERSION,
                    grade_reasons=reasons)
    return "UPDATED" if ok else "ERROR"


def attach_product(family, platform, dry_run=False, force=False,
                   subdomain=None, all_subdomains=False,
                   dry_run_records=None) -> dict:
    """Attach evidence to all content files for a product.

    Args:
        subdomain: When set, restrict to files under this subdomain only.
            Must be a canonical subdomain name (e.g. "reference.aspose.org").
            Raises ValueError for unknown subdomain names.
        all_subdomains: When True with no subdomain, suppresses the Phase 1
            unscoped-write WARN. Use with --confirm-all-subdomains.
        dry_run_records: When not None, ClaimPlan records are accumulated here
            instead of writing. Enables --dry-run-json output.
    """
    if subdomain is not None and subdomain not in _KNOWN_SUBDOMAINS:
        raise ValueError(
            f"Unknown subdomain {subdomain!r}. "
            f"Known: {sorted(_KNOWN_SUBDOMAINS)}"
        )

    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        _log(f"  SKIP {family}/{platform}: no knowledge model")
        return {}

    files = discover_content(family, platform)
    if not files:
        _log(f"  SKIP {family}/{platform}: no content files")
        return {}

    # Apply subdomain filter
    if subdomain is not None:
        files = [f for f in files if _infer_subdomain(f) == subdomain]
        if not files:
            _log(f"  WARN: no files found for subdomain={subdomain!r}")
            return {}
    elif not dry_run and not all_subdomains:
        # Phase 1: warn when running unscoped write across all subdomains
        _log("  WARN: running across all subdomains; use --subdomain to restrict")

    _log(f"  {family}/{platform}: {len(files)} files"
         + (f" (subdomain={subdomain})" if subdomain else ""))
    counts = {"UPDATED": 0, "SKIP (current)": 0, "SKIP (draft)": 0,
              "SKIP (audit FAILs)": 0, "DRY-RUN": 0, "ERROR": 0}
    for f in files:
        status = attach_evidence(f, knowledge, dry_run=dry_run, force=force,
                                 dry_run_records=dry_run_records)
        counts[status] = counts.get(status, 0) + 1

    _log(f"    -> {counts}")
    return counts


def attach_files(file_paths, dry_run=False, force=False,
                 dry_run_records=None) -> dict:
    """Attach evidence to specific files."""
    _eff_infer_product = _cfg_infer_product_fn if _cfg_infer_product_fn is not None else infer_product
    _eff_knowledge = _cfg_knowledge_fn if _cfg_knowledge_fn is not None else Knowledge
    knowledge_cache = {}
    counts = {}
    for fp in file_paths:
        fp = Path(fp)
        if not fp.exists():
            _log(f"  SKIP {fp}: not found")
            continue
        family, platform = _eff_infer_product(fp)
        if not family:
            _log(f"  SKIP {fp}: cannot infer product")
            continue
        key = (family, platform)
        if key not in knowledge_cache:
            knowledge_cache[key] = _eff_knowledge(family, platform)
        knowledge = knowledge_cache[key]
        if not knowledge.available:
            _log(f"  SKIP {fp}: no knowledge for {family}/{platform}")
            continue
        status = attach_evidence(fp, knowledge, dry_run=dry_run, force=force,
                                 dry_run_records=dry_run_records)
        counts[status] = counts.get(status, 0) + 1
    _log(f"  -> {counts}")
    return counts


def _auto_refresh(family, platform):
    """Run refresh_knowledge.py for a product if --auto-refresh is set."""
    import subprocess
    script = Path(__file__).parent.parent / "commands" / "knowledge" / "refresh_knowledge.py"
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
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(
        prog="attach_evidence",
        description="Deterministic evidence block generator for content pages.",
    )
    parser.add_argument("args", nargs="*",
                        help="family platform | all | (used with --files: file paths)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes; no writes")
    parser.add_argument("--dry-run-json", metavar="OUTFILE",
                        help="Write machine-readable ClaimPlan JSON to OUTFILE (implies dry-run)")
    parser.add_argument("--force", action="store_true",
                        help="Re-attach even if model_sha matches")
    parser.add_argument("--files", action="store_true",
                        help="Positional args are file paths, not family/platform")
    parser.add_argument("--subdomain", metavar="SUBDOMAIN",
                        help="Restrict to files under this subdomain only "
                             "(e.g. reference.aspose.org)")
    parser.add_argument("--all-subdomains", action="store_true",
                        help="Explicitly target all subdomains (must pair with "
                             "--confirm-all-subdomains for write commands)")
    parser.add_argument("--confirm-all-subdomains", action="store_true",
                        help="Suppress unscoped-write WARN when --all-subdomains is set")
    parser.add_argument("--auto-refresh", action="store_true",
                        help="Run refresh_knowledge.py before attaching")
    parser.add_argument("--detect-stale-claims", action="store_true",
                        help="Report stale/orphan claim IDs (read-only, no writes)")
    parser.add_argument("--report-json", metavar="OUTFILE",
                        help="Write stale-claim report JSON to OUTFILE "
                             "(used with --detect-stale-claims)")
    parser.add_argument("--apply-claim-plan", metavar="PLAN_FILE",
                        help="Apply a previously generated --dry-run-json ClaimPlan")
    parser.add_argument("--confirm-apply", action="store_true",
                        help="Required safety flag when using --apply-claim-plan")
    parser.add_argument("--max-files", type=int, default=20,
                        help="Maximum files to write per apply run (default: 20)")

    parsed = parser.parse_args()

    dry_run = parsed.dry_run or (parsed.dry_run_json is not None)
    force = parsed.force
    files_mode = parsed.files
    auto_refresh = parsed.auto_refresh
    subdomain = parsed.subdomain
    all_subdomains = parsed.all_subdomains and parsed.confirm_all_subdomains
    positional = parsed.args
    detect_stale = parsed.detect_stale_claims

    # --apply-claim-plan: gated apply from a pre-generated plan
    if parsed.apply_claim_plan:
        if not parsed.confirm_apply:
            _log("ERROR: --apply-claim-plan requires --confirm-apply flag")
            sys.exit(1)
        from evidence.apply_gate import (  # noqa: E402
            apply_plan, write_ledger_entry, _build_ledger_entry, ApplyGateError,
        )
        plan_path = Path(parsed.apply_claim_plan)
        if not plan_path.exists():
            _log(f"ERROR: plan file not found: {plan_path}")
            sys.exit(1)
        plan = _json.loads(plan_path.read_text(encoding="utf-8"))
        max_files = parsed.max_files
        repo_root = Path(__file__).resolve().parents[3]  # scripts/pipeline/evidence/ -> repo root
        from content_discovery import KNOWLEDGE_ROOT as _KR  # noqa: E402
        knowledge_root = _KR.parent  # knowledge/ parent = repo root / knowledge -> parent is repo root
        # Actually knowledge_root for apply_gate is the knowledge/ directory root (families live inside)
        knowledge_root = _KR
        try:
            result = apply_plan(plan, knowledge_root, max_files, repo_root)
        except ApplyGateError as e:
            _log(f"APPLY GATE REFUSED: {e}")
            sys.exit(2)
        # Write run ledger entry
        ledger_path = repo_root / "runs" / "ledger" / "claim-apply-ledger.json"
        entry = _build_ledger_entry(plan, result, f"attach_evidence --apply-claim-plan {plan_path}",
                                    dry_run_json_path=str(plan_path))
        write_ledger_entry(entry, ledger_path)
        _log(f"  Apply result: {result.apply_status} "
             f"(written={result.files_written}, skipped={result.files_skipped}, "
             f"warns={result.warn_count}, blocked={result.blocked_count})")
        _log(f"  Ledger entry written to {ledger_path}")
        if result.apply_status == "FAIL":
            for err in result.errors:
                _log(f"  ERROR: {err}")
            sys.exit(1)
        sys.exit(0)

    # --detect-stale-claims: read-only stale report, no writes
    if detect_stale:
        from evidence.claim_validator import report_stale_claims  # noqa: E402
        if len(positional) >= 2:
            family, platform = positional[0], positional[1]
        elif len(positional) == 1 and positional[0] != "all":
            _log("ERROR: --detect-stale-claims requires family platform arguments")
            sys.exit(1)
        else:
            _log("ERROR: --detect-stale-claims requires 'family platform' arguments")
            sys.exit(1)
        report = report_stale_claims(family, platform, subdomain=subdomain)
        report_json_str = _json.dumps(report, indent=2, sort_keys=True)
        if parsed.report_json:
            outfile = Path(parsed.report_json)
            outfile.parent.mkdir(parents=True, exist_ok=True)
            outfile.write_text(report_json_str, encoding="utf-8")
            _log(f"  Stale-claim report written to {outfile}")
        else:
            print(report_json_str)
        _log(f"  Files scanned: {report['total_files_scanned']}, "
             f"files with stale claims: {report['files_with_stale_claims']}, "
             f"total stale: {report['total_stale_claims']}")
        sys.exit(0)

    # Accumulate ClaimPlan records when --dry-run-json requested
    dry_run_records = [] if parsed.dry_run_json else None

    if files_mode:
        _log("Attaching evidence to specified files...")
        attach_files(positional, dry_run=dry_run, force=force,
                     dry_run_records=dry_run_records)
    elif len(positional) >= 2:
        family, platform = positional[0], positional[1]
        if auto_refresh:
            _auto_refresh(family, platform)
        _log(f"Attaching evidence for {family}/{platform}...")
        attach_product(family, platform, dry_run=dry_run, force=force,
                       subdomain=subdomain, all_subdomains=all_subdomains,
                       dry_run_records=dry_run_records)
    elif len(positional) == 1 and positional[0] == "all":
        products = discover_products()
        _log(f"Attaching evidence for {len(products)} products...")
        total = {}
        for family, platform in products:
            if auto_refresh:
                _auto_refresh(family, platform)
            counts = attach_product(family, platform, dry_run=dry_run, force=force,
                                    subdomain=subdomain, all_subdomains=all_subdomains,
                                    dry_run_records=dry_run_records)
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
        _log(f"\nTotal: {total}")
    else:
        parser.print_help()
        sys.exit(1)

    # Write ClaimPlan JSON output
    if dry_run_records is not None and parsed.dry_run_json:
        outfile = Path(parsed.dry_run_json)
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(
            _json.dumps(dry_run_records, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _log(f"  ClaimPlan written to {outfile} ({len(dry_run_records)} records)")

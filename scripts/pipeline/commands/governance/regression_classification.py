"""regression_classification.py — S-114 implemented as real code (HARDEN-A10).

CONTRACT: scripts/pipeline/commands/governance/regression_classification.py
  purpose: For every page whose grade regressed between a baseline git ref and
           the working tree, classify JUSTIFIED (the regression is explained by
           a documented knowledge change) vs UNJUSTIFIED (no such evidence — a
           likely pipeline defect) vs NEEDS_HUMAN_REVIEW (ambiguous), with a
           citation for every verdict. This was previously ONLY a prose skill
           procedure (skills/regression-classification.md) with no backing
           script — its own "write every item, never a sample" completeness
           guarantee was therefore unenforceable; this script enforces it in
           code via a hard assertion, not a design note.
  inputs:  family, platform, baseline_ref (git ref to diff grades against,
           default origin/main)
  outputs: reports/regression_classification/{family}-{platform}-{run_id}.json
           — one row per regressed page (schema below), COMPLETE.
  deterministic_or_llm: hybrid. Evidence gathering (grade comparison,
           evidence.apis/claims vs knowledge_delta.json intersection) is fully
           deterministic. An optional --llm-judge pass (routed through
           llm_output_cache.py, namespace "regression_classification") resolves
           cases the deterministic check can't — REQUIRED to cite the specific
           evidence line it used; if it can't produce a citation, the item is
           NEEDS_HUMAN_REVIEW, never guessed.
  completeness: main() asserts len(output_rows) == len(regressed_pages) and
           exits non-zero if not — the exact guarantee the prose skill could
           never verify.
  output row schema (matches the more complete of two prior ad hoc manual-run
           shapes found in this repo's gitignored reports/regression_classification/):
    {path, family, platform, site, prior_grade, current_grade,
     citation_grade_reasons: [...], classification, rationale,
     remediation_priority, remediation_route}
  classification values: JUSTIFIED | UNJUSTIFIED_CANDIDATE | UNJUSTIFIED |
           NEEDS_HUMAN_REVIEW
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _PIPELINE_ROOT.parent.parent
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from grade_writer import read_grade  # noqa: E402
from content_discovery import discover_content  # noqa: E402
from core.markdown import parse_frontmatter  # noqa: E402

_GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
_CONSUMER_USEFULNESS_RE = re.compile(r"\bconsumer_usefulness\b")


def _grade_rank(grade: str | None) -> int | None:
    return _GRADE_RANK.get(grade) if grade else None


def _site_for_path(path: Path) -> str:
    parts = path.as_posix().split("/")
    if "content" in parts:
        idx = parts.index("content")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _grade_from_ref(path: Path, ref: str) -> tuple[str | None, list[str]]:
    """Read grade + grade_reasons from `path` as it existed at git ref `ref`."""
    try:
        rel = path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    try:
        content = subprocess.check_output(
            ["git", "show", f"{ref}:{rel}"], stderr=subprocess.DEVNULL,
            cwd=str(_REPO_ROOT), encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return None, []  # file didn't exist at ref — no prior grade to compare
    except (UnicodeDecodeError, OSError) as exc:
        # R4: don't crash the whole batch over one unreadable baseline blob —
        # treat this single page as unresolvable at baseline, same as "didn't
        # exist," and keep processing the rest.
        print(f"WARNING: could not read {rel} at {ref}: {exc}", file=sys.stderr)
        return None, []
    with NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        result = read_grade(tmp)
        if not result:
            return None, []
        return result.get("grade"), list(result.get("grade_reasons") or [])
    finally:
        tmp.unlink(missing_ok=True)


def _resolve_baseline_ref(ref: str, repo_root: Path) -> bool:
    """R2: True if `ref` resolves to a real git object. A bad ref (typo,
    force-pushed/rewritten history, wrong remote) must not silently produce
    'zero regressions found' — that's indistinguishable from a genuinely
    clean baseline and defeats the whole point of this classifier."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            capture_output=True, cwd=str(repo_root), timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _load_knowledge_delta(family: str, platform: str) -> dict:
    path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "knowledge_delta.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _page_evidence(path: Path) -> dict:
    try:
        fm = parse_frontmatter(path)
    except Exception:
        return {}
    evidence = fm.get("evidence") if isinstance(fm, dict) else None
    return evidence if isinstance(evidence, dict) else {}


def _deterministic_citation(evidence: dict, delta: dict) -> list[str]:
    """Intersect a page's cited apis/claims against knowledge_delta's changed
    sets. A non-empty result is direct, checkable evidence the regression
    traces to a real, documented knowledge change."""
    changed_apis = set(delta.get("removed_apis") or []) | set(delta.get("modified_apis") or [])
    changed_claims = set(delta.get("removed_claims") or []) | set(delta.get("modified_claims") or [])
    page_apis = set(evidence.get("apis") or [])
    page_claims = set(evidence.get("claims") or [])
    hits = sorted((page_apis & changed_apis) | (page_claims & changed_claims))
    return hits


def _is_consumer_usefulness_only(grade_reasons: list[str]) -> bool:
    """True if every FINDING-category line (the actual grade drivers) names
    consumer_usefulness. Non-finding lines (e.g. a separate "US ceiling
    applied" cap rule, which reports a consequence, not a finding category)
    are ignored — they don't introduce a second, non-consumer_usefulness
    driver on their own."""
    finding_lines = [r for r in grade_reasons if "finding(s)" in r.lower()]
    if not finding_lines:
        return False
    return all(_CONSUMER_USEFULNESS_RE.search(r) for r in finding_lines)


def classify_page(
    path: Path,
    family: str,
    platform: str,
    prior_grade: str,
    current_grade: str,
    current_reasons: list[str],
    delta: dict,
    *,
    llm_judge=None,
) -> dict:
    """Classify one regressed page. Pure function except for the optional
    llm_judge callable (injected for testability — see test file)."""
    evidence = _page_evidence(path)
    citation = _deterministic_citation(evidence, delta)

    if citation:
        return {
            "classification": "JUSTIFIED",
            "citation_grade_reasons": current_reasons,
            "rationale": f"regression traces to documented knowledge changes: {', '.join(citation)}",
            "remediation_priority": "NONE",
            "remediation_route": "none — grade correctly reflects current knowledge",
        }

    if _is_consumer_usefulness_only(current_reasons):
        return {
            "classification": "UNJUSTIFIED_CANDIDATE",
            "citation_grade_reasons": current_reasons,
            "rationale": "grade driven solely by consumer_usefulness findings with no "
                         "corresponding knowledge_delta evidence — likely a prose/generation "
                         "defect, not a legitimate content change",
            "remediation_priority": "NORMAL",
            "remediation_route": "re-run body-refresh (post RPR-E-01) then re-grade",
        }

    if llm_judge is not None:
        verdict = llm_judge(path=path, family=family, platform=platform,
                            prior_grade=prior_grade, current_grade=current_grade,
                            grade_reasons=current_reasons, delta=delta)
        if verdict and verdict.get("citation"):
            return {
                "classification": verdict.get("classification", "NEEDS_HUMAN_REVIEW"),
                "citation_grade_reasons": current_reasons,
                "rationale": f"LLM judgment: {verdict['rationale']} (cites: {verdict['citation']})",
                "remediation_priority": verdict.get("remediation_priority", "NORMAL"),
                "remediation_route": verdict.get("remediation_route",
                                                 "re-run body-refresh then re-grade"),
            }
        # LLM ran but could not produce a citation — escalate, never guess.

    return {
        "classification": "NEEDS_HUMAN_REVIEW",
        "citation_grade_reasons": current_reasons,
        "rationale": "no deterministic evidence found in knowledge_delta.json, and no "
                     "confident LLM citation available — cannot classify without guessing",
        "remediation_priority": "HIGH",
        "remediation_route": "human governance review (skills/regression-classification.md "
                              "stop_conditions)",
    }


def run(
    family: str,
    platform: str,
    *,
    baseline_ref: str = "origin/main",
    llm_judge=None,
    repo_root: Path | None = None,
) -> dict:
    """Discover regressed pages, classify every one, return the complete report
    dict (also written to disk by main()). Never returns a partial list.

    Raises ValueError if baseline_ref doesn't resolve (R2) — a bad ref must
    fail loudly, not silently produce a false "zero regressions" report
    indistinguishable from a genuinely clean baseline.
    """
    root = repo_root or _REPO_ROOT
    if not _resolve_baseline_ref(baseline_ref, root):
        raise ValueError(
            f"baseline_ref {baseline_ref!r} does not resolve to a commit in {root} — "
            f"refusing to run (a bad ref would silently report zero regressions, "
            f"indistinguishable from a genuinely clean baseline)"
        )

    pages = discover_content(family, platform, skip_drafts=True)
    delta = _load_knowledge_delta(family, platform)

    # R3: detection is tracked independently of row construction/classification
    # below, so the completeness check at the end of this function (and the
    # one main() repeats) verifies something real — that classification didn't
    # silently drop a page the detection pass found — rather than comparing a
    # list's length against itself (which can never disagree).
    detected_paths: list[str] = []
    regressions: list[dict] = []
    for page in pages:
        current = read_grade(page)
        current_grade = current.get("grade") if current else None
        current_reasons = list((current or {}).get("grade_reasons") or [])
        prior_grade, _prior_reasons = _grade_from_ref(page, baseline_ref)

        cur_rank = _grade_rank(current_grade)
        prior_rank = _grade_rank(prior_grade)

        try:
            rel = page.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = page.as_posix()

        # R1: a page that WAS graded at baseline but is now ungradeable (grade
        # field missing/corrupted) is the single worst case this classifier
        # exists to catch — not a "not a regression, skip" case. Treating it
        # identically to "brand-new page" let both regressions_found and
        # len(items) shrink together, defeating the completeness assertion.
        if prior_rank is not None and cur_rank is None:
            detected_paths.append(rel)
            row = {
                "path": rel, "family": family, "platform": platform,
                "site": _site_for_path(page),
                "prior_grade": prior_grade, "current_grade": None,
                "classification": "UNGRADEABLE_REGRESSION",
                "citation_grade_reasons": current_reasons,
                "rationale": f"page was graded {prior_grade!r} at {baseline_ref} but has no "
                             f"readable grade now — content, frontmatter, or the grading "
                             f"pipeline itself may be broken",
                "remediation_priority": "HIGH",
                "remediation_route": "investigate immediately — this is a stronger signal "
                                      "than an ordinary grade drop",
            }
            regressions.append(row)
            continue

        if cur_rank is None or prior_rank is None or cur_rank >= prior_rank:
            continue  # not a regression (new page, unreadable at baseline, or improved/unchanged)

        detected_paths.append(rel)
        row = {
            "path": rel,
            "family": family,
            "platform": platform,
            "site": _site_for_path(page),
            "prior_grade": prior_grade,
            "current_grade": current_grade,
        }
        row.update(classify_page(
            page, family, platform, prior_grade, current_grade, current_reasons,
            delta, llm_judge=llm_judge,
        ))
        regressions.append(row)

    # R3: real completeness check — detected_paths was populated at the exact
    # moment each page was determined to be a regression, independent of how
    # `regressions` rows got built. A future refactor that classifies but
    # forgets to append (or appends the wrong row) would make this disagree.
    classified_paths = [row["path"] for row in regressions]
    if sorted(detected_paths) != sorted(classified_paths):
        missing = set(detected_paths) - set(classified_paths)
        raise RuntimeError(
            f"regression_classification internal completeness failure: "
            f"{len(detected_paths)} pages detected as regressed but "
            f"{len(classified_paths)} classified — missing: {sorted(missing)}"
        )

    report = {
        "family": family,
        "platform": platform,
        "baseline_ref": baseline_ref,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages_scanned": len(pages),
        "regressions_found": len(detected_paths),
        "items": regressions,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S-114 regression-classification — real, completeness-enforced implementation.")
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--baseline-ref", default="origin/main",
                        help="git ref to diff prior grades against (default: origin/main)")
    parser.add_argument("--run-id", default=None,
                        help="Output filename stem (default: {family}-{platform}-{timestamp})")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = run(args.family, args.platform, baseline_ref=args.baseline_ref)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # HARDEN-A10 completeness guarantee, enforced in code, not prose:
    # every regressed page found MUST appear exactly once in the output.
    scanned_regressed_paths = {row["path"] for row in report["items"]}
    if len(scanned_regressed_paths) != len(report["items"]):
        print("COMPLETENESS_VIOLATION: duplicate path(s) in output — refusing to write",
              file=sys.stderr)
        return 1
    if report["regressions_found"] != len(report["items"]):
        print(f"COMPLETENESS_VIOLATION: found {report['regressions_found']} regressions "
              f"but classified {len(report['items'])} — refusing to write partial output",
              file=sys.stderr)
        return 1

    run_id = args.run_id or f"{args.family}-{args.platform}-{report['generated_at'].replace(':', '')}"
    out_dir = _REPO_ROOT / "reports" / "regression_classification"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"regression_classification: {args.family}/{args.platform} "
              f"(baseline {args.baseline_ref})")
        print(f"  pages scanned      : {report['pages_scanned']}")
        print(f"  regressions found  : {report['regressions_found']}")
        by_class: dict[str, int] = {}
        for row in report["items"]:
            by_class[row["classification"]] = by_class.get(row["classification"], 0) + 1
        for cls, count in sorted(by_class.items()):
            print(f"  {cls:22s}: {count}")
        print(f"  written to         : {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

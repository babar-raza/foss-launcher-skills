#!/usr/bin/env python3
"""refresh_review.py — Per-page decision logging and coverage reporting for post-refresh review.

CONTRACT: scripts/pipeline/commands/ops/refresh_review.py
  purpose: Record per-page content review decisions (BODY_UPDATED / EVIDENCE_ONLY /
           NOT_AFFECTED / RETIRED) and generate a per-subdomain coverage report after
           a product refresh cycle.
  inputs:  page_decisions.json (written by this module's record_decision())
           content pages (all 5 subdomains) for the given family/platform
  outputs: reports/refresh_review/{family}/{platform}/page_decisions.json
           reports/refresh_review/{family}/{platform}/coverage_report.md
  idempotent: yes — record_decision() appends/updates; --report overwrites coverage_report.md

Decision values:
  BODY_UPDATED   — page body content was modified (delta signals found and applied)
  EVIDENCE_ONLY  — only evidence.model_sha was updated; body content unchanged
  NOT_AFFECTED   — PIA scored LOW_IMPACT/NOT_AFFECTED; no body changes warranted
  RETIRED        — page was set to draft:true (retired)

Usage:
    # Record a per-page decision (called by skills during S-20 and S-84):
    .venv/Scripts/python scripts/pipeline/commands/ops/refresh_review.py {family} {platform} \\
        --record-decision --path {file_path} --decision BODY_UPDATED \\
        --reason "modified_claims CLM-abc cited in paragraph 2" --body-changed

    # Generate coverage report after all decisions recorded:
    .venv/Scripts/python scripts/pipeline/commands/ops/refresh_review.py {family} {platform} --report
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REVIEW_ROOT = _REPO_ROOT / "reports" / "refresh_review"

VALID_DECISIONS = frozenset({
    # Core page-update decisions
    "BODY_UPDATED", "EVIDENCE_ONLY", "NOT_AFFECTED", "RETIRED",
    # delta-dispatch decisions (bypass page-update)
    "GENERATED",
    # Semantic guard verdicts (post-update, S-84 Step 11.5)
    "SEMANTIC_NOOP_PROVEN",
    "REFRESH_BLOCKED_UNPROVEN_NOOP",
    "CLAIM_EXTRACTION_MISSED_DELTA",
    "PAGE_MAPPING_MISSED_IMPACT",
    # Guard v2 body-update quality verdicts (S-84 Step 11.5 w/ page_impact.json)
    "GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT",
    "EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED",
    # Grade remediation decisions (S-84 Step 9.6 / S-96)
    "GRADING_REPAIRED",
    "GRADING_BLOCKED",
    "TASKCARD_CREATED",
})

_SUBDOMAIN_ORDER = ["docs", "kb", "blog", "products", "reference", "unknown"]


def _decisions_path(family: str, platform: str, *, review_root: Path | None = None) -> Path:
    root = review_root or _REVIEW_ROOT
    return root / family / platform / "page_decisions.json"


def _load_decisions(family: str, platform: str, *, review_root: Path | None = None) -> dict:
    """Load page_decisions.json; return skeleton dict if absent."""
    p = _decisions_path(family, platform, review_root=review_root)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {
        "family": family,
        "platform": platform,
        "generated_at": None,
        "refresh_sha": None,
        "pages": {},
    }


_PAGE_DECISIONS_SCHEMA_VERSION = 2


def _save_decisions(
    family: str,
    platform: str,
    data: dict,
    *,
    review_root: Path | None = None,
) -> None:
    # RPR-J-08: stamp every write so a reader can tell "recorded, under a shape
    # this code understands" apart from "recorded under an old/incompatible
    # shape" -- see post_refresh_verify.py's _artifact_schema_state.
    data["schema_version"] = _PAGE_DECISIONS_SCHEMA_VERSION
    p = _decisions_path(family, platform, review_root=review_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:
        print(f"WARN: could not write page_decisions.json: {exc}", file=sys.stderr)
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _build_coverage_ledger_entry(
    path: str,
    decision: str,
    reason: str,
    *,
    decision_source: str,
    body_diff_hash_before: str | None,
    body_diff_hash_after: str | None,
    frontmatter_only: bool,
    blocking: bool,
    evidence_claims_checked: list[str],
    evidence_apis_checked: list[str],
) -> dict:
    """Construct a schema-5c page-coverage-ledger entry for validation (RPR-D-03)."""
    return {
        "page_id": path,
        "decision": decision,
        "decision_reason": reason,
        "decision_source": decision_source,
        "evidence_claims_checked": evidence_claims_checked,
        "evidence_apis_checked": evidence_apis_checked,
        "body_diff_hash_before": body_diff_hash_before,
        "body_diff_hash_after": body_diff_hash_after,
        "frontmatter_only": frontmatter_only,
        "blocking": blocking,
    }


def record_decision(
    family: str,
    platform: str,
    path: str,
    decision: str,
    reason: str,
    *,
    body_hash_changed: bool = False,
    decision_source: str = "manual",
    body_diff_hash_before: str | None = None,
    body_diff_hash_after: str | None = None,
    frontmatter_only: bool = False,
    blocking: bool = False,
    evidence_claims_checked: list[str] | None = None,
    evidence_apis_checked: list[str] | None = None,
    review_root: Path | None = None,
) -> None:
    """Record a per-page content review decision.

    RPR-D-03: every write is now validated against the schema-5c page-coverage-ledger
    contract (`validate_page_coverage_ledger_entry`) BEFORE it touches disk — a
    non-conformant entry raises instead of silently landing. The strict cross-field
    invariants (a BODY_UPDATED decision cannot have identical before/after body hashes,
    nor frontmatter_only=True) only bite when the caller actually populates those fields;
    the legacy simple-shape call (path/decision/reason[/body_hash_changed]) keeps working
    because the hash fields default to None (which the invariant treats as "not applicable").

    Args:
        family, platform:   Product identity.
        path:               Relative file path.
        decision:           A VALID_DECISIONS value.
        reason:             Human-readable explanation (maps to schema decision_reason).
        body_hash_changed:  Legacy flag; retained in the stored entry for backward compat.
        decision_source:    RPR-D-01 provenance: pia_per_page_citation | oracle | manual | triage_confirm.
        body_diff_hash_before/after: content hashes; when both set + equal + decision=BODY_UPDATED, rejected.
        frontmatter_only:   when True + decision=BODY_UPDATED, rejected (the PDF-NET-REFRESH-001 bug shape).
        blocking:           whether this decision must be justified before commit.
        evidence_claims_checked/apis_checked: the cited IDs PIA actually read (proves citation-based).
        review_root:        Override for reports/refresh_review/ base (tests only).
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Invalid decision '{decision}'. Must be one of {sorted(VALID_DECISIONS)}")

    claims_checked = evidence_claims_checked or []
    apis_checked = evidence_apis_checked or []

    # RPR-D-03: validate the schema-5c projection before writing. Raise on failure —
    # this is a write-time gate, not a report-time WARN (plan §2.3: Check 6 previously
    # accepted any decision, including a malformed one, as "covered").
    ledger_entry = _build_coverage_ledger_entry(
        path, decision, reason,
        decision_source=decision_source,
        body_diff_hash_before=body_diff_hash_before,
        body_diff_hash_after=body_diff_hash_after,
        frontmatter_only=frontmatter_only,
        blocking=blocking,
        evidence_claims_checked=claims_checked,
        evidence_apis_checked=apis_checked,
    )
    try:
        from lib.schema_validators import validate_page_coverage_ledger_entry
    except ImportError:  # pragma: no cover — lib always importable in this repo
        validate_page_coverage_ledger_entry = None
    if validate_page_coverage_ledger_entry is not None:
        errors = validate_page_coverage_ledger_entry(ledger_entry)
        if errors:
            raise ValueError(
                f"page_decisions entry for {path} is not schema-conformant, refusing to write: {errors}"
            )

    data = _load_decisions(family, platform, review_root=review_root)
    # Stored entry keeps the legacy fields (consumed by post_refresh_verify.py /
    # generate_coverage_report) AND carries the richer schema-5c fields.
    data.setdefault("pages", {})[path] = {
        "decision": decision,
        "reason": reason,
        "body_hash_changed": body_hash_changed,
        "decision_source": decision_source,
        "body_diff_hash_before": body_diff_hash_before,
        "body_diff_hash_after": body_diff_hash_after,
        "frontmatter_only": frontmatter_only,
        "blocking": blocking,
        "evidence_claims_checked": claims_checked,
        "evidence_apis_checked": apis_checked,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    _save_decisions(family, platform, data, review_root=review_root)


def validate_decisions_file(
    family: str,
    platform: str,
    *,
    review_root: Path | None = None,
) -> list[str]:
    """RPR-D-03 `--dry-run-validate`: check an existing page_decisions.json against
    schema 5c without a full re-run. Returns a list of human-readable problem strings
    (empty = all entries conformant). Historical files written before RPR-D-03 lack the
    richer fields, so missing-field problems are reported but treated as advisory (the
    entry predates the schema) — only a genuinely contradictory entry (e.g. a stored
    BODY_UPDATED with identical hashes) is a hard problem.
    """
    data = _load_decisions(family, platform, review_root=review_root)
    problems: list[str] = []
    try:
        from lib.schema_validators import validate_page_coverage_ledger_entry
    except ImportError:  # pragma: no cover
        return ["lib.schema_validators unavailable"]
    for path, entry in (data.get("pages") or {}).items():
        projected = _build_coverage_ledger_entry(
            path,
            entry.get("decision", ""),
            entry.get("reason", ""),
            decision_source=entry.get("decision_source", "manual"),
            body_diff_hash_before=entry.get("body_diff_hash_before"),
            body_diff_hash_after=entry.get("body_diff_hash_after"),
            frontmatter_only=bool(entry.get("frontmatter_only", False)),
            blocking=bool(entry.get("blocking", False)),
            evidence_claims_checked=entry.get("evidence_claims_checked", []),
            evidence_apis_checked=entry.get("evidence_apis_checked", []),
        )
        for err in validate_page_coverage_ledger_entry(projected):
            problems.append(f"{path}: {err}")
    return problems


def _infer_subdomain(path: str) -> str:
    """Infer subdomain label from a content page path string."""
    _MAP = {
        "docs.aspose.org": "docs",
        "kb.aspose.org": "kb",
        "products.aspose.org": "products",
        "reference.aspose.org": "reference",
        "blog.aspose.org": "blog",
    }
    for key, label in _MAP.items():
        if key in path:
            return label
    return "unknown"


def generate_coverage_report(
    family: str,
    platform: str,
    *,
    review_root: Path | None = None,
) -> str:
    """Generate a markdown coverage report from page_decisions.json.

    Returns the report text.  Also writes coverage_report.md to the review dir.
    """
    data = _load_decisions(family, platform, review_root=review_root)
    pages = data.get("pages", {})

    # Build per-subdomain counts
    counts: dict[str, dict[str, int]] = {}
    for path, entry in pages.items():
        sub = _infer_subdomain(path)
        if sub not in counts:
            counts[sub] = {d: 0 for d in VALID_DECISIONS}
            counts[sub]["total"] = 0
        decision = entry.get("decision", "UNKNOWN")
        if decision in VALID_DECISIONS:
            counts[sub][decision] += 1
        counts[sub]["total"] += 1

    # Build report lines
    lines = [
        f"# Coverage Report: {family}/{platform}",
        "",
        f"Generated: {data.get('generated_at', 'unknown')}",
        f"Refresh SHA: {data.get('refresh_sha', 'unknown')}",
        f"Total pages decided: {len(pages)}",
        "",
        "| Subdomain | Total | BODY_UPDATED | EVIDENCE_ONLY | NOT_AFFECTED | RETIRED |",
        "|-----------|-------|--------------|---------------|--------------|---------|",
    ]

    grand_total = {d: 0 for d in VALID_DECISIONS}
    grand_total["total"] = 0

    for sub in _SUBDOMAIN_ORDER:
        if sub not in counts:
            continue
        c = counts[sub]
        lines.append(
            f"| {sub} | {c['total']} | {c.get('BODY_UPDATED', 0)} "
            f"| {c.get('EVIDENCE_ONLY', 0)} | {c.get('NOT_AFFECTED', 0)} "
            f"| {c.get('RETIRED', 0)} |"
        )
        for d in VALID_DECISIONS:
            grand_total[d] += c.get(d, 0)
        grand_total["total"] += c["total"]

    # Add any extra subdomains not in the ordered list
    for sub in sorted(counts):
        if sub not in _SUBDOMAIN_ORDER:
            c = counts[sub]
            lines.append(
                f"| {sub} | {c['total']} | {c.get('BODY_UPDATED', 0)} "
                f"| {c.get('EVIDENCE_ONLY', 0)} | {c.get('NOT_AFFECTED', 0)} "
                f"| {c.get('RETIRED', 0)} |"
            )
            for d in VALID_DECISIONS:
                grand_total[d] += c.get(d, 0)
            grand_total["total"] += c["total"]

    lines.extend([
        f"| **TOTAL** | **{grand_total['total']}** | **{grand_total.get('BODY_UPDATED', 0)}** "
        f"| **{grand_total.get('EVIDENCE_ONLY', 0)}** | **{grand_total.get('NOT_AFFECTED', 0)}** "
        f"| **{grand_total.get('RETIRED', 0)}** |",
        "",
    ])

    report = "\n".join(lines)

    # Write to file
    root = review_root or _REVIEW_ROOT
    out_dir = root / family / platform
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage_report.md").write_text(report, encoding="utf-8")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="refresh_review",
        description="Per-page decision logging and coverage reporting for post-refresh review",
    )
    parser.add_argument("family", help="Product family (e.g. cells)")
    parser.add_argument("platform", help="Platform (e.g. net)")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record-decision", action="store_true",
                      help="Record a per-page decision")
    mode.add_argument("--report", action="store_true",
                      help="Generate coverage_report.md from accumulated decisions")
    mode.add_argument("--status", action="store_true",
                      help="Print current page_decisions.json summary")
    mode.add_argument("--dry-run-validate", action="store_true",
                      help="Validate an existing page_decisions.json against schema 5c "
                           "without a re-run (RPR-D-03); exit 1 if any entry is non-conformant")

    parser.add_argument("--path", metavar="FILE_PATH",
                        help="Content page path (required for --record-decision)")
    parser.add_argument("--decision", metavar="DECISION",
                        choices=sorted(VALID_DECISIONS),
                        help="Decision value (required for --record-decision)")
    parser.add_argument("--reason", metavar="REASON", default="",
                        help="Human-readable reason for the decision")
    parser.add_argument("--body-changed", action="store_true",
                        help="Flag that body content changed (use with BODY_UPDATED)")
    parser.add_argument("--review-root", type=Path, default=None,
                        help="Override base dir for reports/refresh_review/ (tests/diagnostics)")

    args = parser.parse_args(argv)
    rr = args.review_root

    if args.record_decision:
        if not args.path or not args.decision:
            print("ERROR: --record-decision requires --path and --decision", file=sys.stderr)
            return 1
        record_decision(
            args.family, args.platform,
            path=args.path,
            decision=args.decision,
            reason=args.reason,
            body_hash_changed=args.body_changed,
            review_root=rr,
        )
        print(f"Decision recorded: {args.path} → {args.decision}")
        return 0

    if getattr(args, "dry_run_validate", False):
        problems = validate_decisions_file(args.family, args.platform, review_root=rr)
        if problems:
            print(f"NON-CONFORMANT: {len(problems)} problem(s) in {args.family}/{args.platform} page_decisions.json:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"OK: {args.family}/{args.platform} page_decisions.json is schema-conformant")
        return 0

    if args.report:
        report = generate_coverage_report(args.family, args.platform, review_root=rr)
        print(report)
        root = rr or _REVIEW_ROOT
        print(f"\nCoverage report written to: {root / args.family / args.platform / 'coverage_report.md'}")
        return 0

    if args.status:
        data = _load_decisions(args.family, args.platform, review_root=rr)
        pages = data.get("pages", {})
        print(f"Page decisions for {args.family}/{args.platform}: {len(pages)} recorded")
        counts: dict[str, int] = {}
        for entry in pages.values():
            d = entry.get("decision", "UNKNOWN")
            counts[d] = counts.get(d, 0) + 1
        for decision, count in sorted(counts.items()):
            print(f"  {decision}: {count}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

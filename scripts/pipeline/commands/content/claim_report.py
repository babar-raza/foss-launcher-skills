"""claim_report.py — WARN-only CI claim report for non-reference subdomains.

TC-CLAIM-11: Read-only report. Never blocks. Never writes content files.

Checks (all WARN-only in Sprint 1):
  - Unknown claims: claim ID not in merged/claims.json
  - Stale claims: same check via ClaimValidator
  - Duplicate claims: same claim ID listed twice
  - Malformed claim IDs: does not match CLM- or ERC- patterns
  - Page-role mismatches: ERC with page_role != subdomain type (via ClaimPolicy)

Output:
  - Summary table printed to stdout
  - Optional JSON artifact via --output-json OUTFILE
  - Exit code 0 always (WARN-only; does not block pipeline)

Usage:
    python scripts/pipeline/commands/content/claim_report.py cells java
    python scripts/pipeline/commands/content/claim_report.py cells java --subdomain blog.aspose.org
    python scripts/pipeline/commands/content/claim_report.py cells java --output-json report.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

# Claim ID format patterns
_CLM_RE = re.compile(r"^CLM-[a-zA-Z0-9]+-[0-9a-f]{4,}$")
_ERC_RE = re.compile(r"^ERC-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[0-9a-f]{8}$")


def _is_valid_claim_format(cid: str) -> bool:
    return bool(_CLM_RE.match(cid) or _ERC_RE.match(cid))


def scan_files(
    files: list[Path],
    knowledge,
    subdomain: str | None = None,
) -> dict:
    """Scan files for claim issues. Returns structured report dict.

    Never writes. Never raises on individual file errors.
    """
    from core.markdown import parse_frontmatter  # noqa: E402
    from evidence.claim_policy import ClaimPolicy, PolicyContext  # noqa: E402
    from content_discovery import _infer_subdomain  # noqa: E402

    known_ids = knowledge.claim_ids
    policy = ClaimPolicy()

    issues: list[dict] = []
    total_files = 0
    files_with_issues = 0

    for f in files:
        try:
            fm = parse_frontmatter(f)
        except Exception:
            continue

        evidence = fm.get("evidence") or {}
        if not isinstance(evidence, dict):
            continue
        claims = evidence.get("claims", [])
        if not isinstance(claims, list):
            continue

        total_files += 1
        file_issues: list[dict] = []
        seen_in_file: set[str] = set()
        file_subdomain = _infer_subdomain(f) or subdomain or ""
        page_role = fm.get("page_role")

        for cid in claims:
            if not isinstance(cid, str):
                continue

            # Malformed
            if not _is_valid_claim_format(cid):
                file_issues.append({
                    "claim_id": cid,
                    "issue": "MALFORMED_CLAIM_ID",
                    "severity": "WARN",
                    "message": f"Claim ID does not match CLM- or ERC- format: {cid!r}",
                })

            # Duplicate
            if cid in seen_in_file:
                file_issues.append({
                    "claim_id": cid,
                    "issue": "DUPLICATE_CLAIM",
                    "severity": "WARN",
                    "message": f"Duplicate claim ID: {cid!r}",
                })
            seen_in_file.add(cid)

            # Unknown / stale
            if cid not in known_ids:
                file_issues.append({
                    "claim_id": cid,
                    "issue": "UNKNOWN_CLAIM",
                    "severity": "WARN",
                    "message": f"Claim ID not in knowledge model: {cid!r}",
                })
                continue

            # Page-role mismatch (via ClaimPolicy)
            ctx = PolicyContext(
                filepath=f,
                subdomain=file_subdomain,
                page_role=page_role,
                claim_id=cid,
                claim_kind=None,
                claim_page_role=None,
                claim_source=None,
                token_match_context=None,
            )
            decision = policy.evaluate(ctx)
            if decision.action == "WARN":
                file_issues.append({
                    "claim_id": cid,
                    "issue": "PAGE_ROLE_MISMATCH",
                    "severity": "WARN",
                    "message": decision.reason,
                })

        if file_issues:
            files_with_issues += 1
            issues.append({
                "filepath": str(f),
                "subdomain": file_subdomain,
                "issues": file_issues,
            })

    return {
        "family": knowledge.family,
        "platform": knowledge.platform,
        "subdomain_filter": subdomain,
        "total_files_scanned": total_files,
        "files_with_issues": files_with_issues,
        "total_issues": sum(len(r["issues"]) for r in issues),
        "warn_count": sum(
            1 for r in issues for i in r["issues"] if i["severity"] == "WARN"
        ),
        "records": issues,
    }


def _print_summary(report: dict) -> None:
    print(f"\n=== Claim Report: {report['family']}/{report['platform']} ===")
    if report.get("subdomain_filter"):
        print(f"Subdomain filter: {report['subdomain_filter']}")
    print(f"Files scanned:    {report['total_files_scanned']}")
    print(f"Files with issues: {report['files_with_issues']}")
    print(f"Total warnings:    {report['warn_count']}")
    if report["records"]:
        print("\nIssues found:")
        for rec in report["records"][:20]:  # print up to 20
            print(f"  {rec['filepath']}")
            for issue in rec["issues"]:
                print(f"    [{issue['severity']}] {issue['issue']}: {issue['message']}")
    print()


def main(argv=None):
    import argparse
    from knowledge_core import Knowledge  # noqa: E402
    from content_discovery import discover_content  # noqa: E402

    parser = argparse.ArgumentParser(
        prog="claim_report",
        description="WARN-only CI claim report for non-reference subdomains.",
    )
    parser.add_argument("family", help="Product family (e.g. cells)")
    parser.add_argument("platform", help="Product platform (e.g. java)")
    parser.add_argument("--subdomain", metavar="SUBDOMAIN",
                        help="Restrict to this subdomain only")
    parser.add_argument("--output-json", metavar="OUTFILE",
                        help="Write full JSON report to OUTFILE")

    parsed = parser.parse_args(argv)

    knowledge = Knowledge(parsed.family, parsed.platform)
    if not knowledge.available:
        print(f"WARN: no knowledge model for {parsed.family}/{parsed.platform}; "
              "report may be incomplete")

    files = discover_content(parsed.family, parsed.platform)
    if parsed.subdomain:
        from content_discovery import _infer_subdomain  # noqa: E402
        files = [f for f in files if _infer_subdomain(f) == parsed.subdomain]

    report = scan_files(files, knowledge, subdomain=parsed.subdomain)
    _print_summary(report)

    if parsed.output_json:
        out = Path(parsed.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Report written to {out}")

    # Always exit 0 — WARN-only, never blocks pipeline
    sys.exit(0)


if __name__ == "__main__":
    main()

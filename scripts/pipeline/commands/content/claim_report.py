"""claim_report.py -- WARN-only CI claim report for non-reference subdomains.

TC-CLAIM-11: Read-only report. Never blocks. Never writes content files.

Ported/adapted from aspose.org scripts/pipeline/commands/content/claim_report.py.
Adaptations:
  - Uses foss knowledge_core.Knowledge, discover_content, parse_frontmatter
  - ClaimPolicy replaced with simple format-check stub (evidence.claim_policy not available)
  - content_discovery replaced with knowledge_core.discover_content + _infer_subdomain

Checks (all WARN-only):
  - Unknown claims: claim ID not in knowledge model
  - Duplicate claims: same claim ID listed twice
  - Malformed claim IDs: does not match CLM- or ERC- patterns

Output:
  - Summary table printed to stdout
  - Optional JSON artifact via --output-json OUTFILE
  - Exit code 0 always (WARN-only; does not block pipeline)

Usage:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/content/claim_report.py cells java
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/content/claim_report.py cells java --subdomain blog
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/content/claim_report.py cells java --output-json report.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Claim ID format patterns
_CLM_RE = re.compile(r"^CLM-[a-zA-Z0-9]+-[0-9a-f]{4,}$")
_ERC_RE = re.compile(r"^ERC-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[0-9a-f]{8}$")


def _is_valid_claim_format(cid: str) -> bool:
    return bool(_CLM_RE.match(cid) or _ERC_RE.match(cid))


def _infer_subdomain(filepath: Path) -> str:
    """Infer subdomain from a content file path.

    Expects paths like: content/{subdomain}.aspose.org/en/{family}/{platform}/...
    or: content/{subdomain}/{family}/{platform}/...
    """
    parts = filepath.parts
    try:
        ci = next(i for i, p in enumerate(parts) if p == "content")
    except StopIteration:
        return ""
    if len(parts) <= ci + 1:
        return ""
    sub = parts[ci + 1]
    # Strip .aspose.org suffix if present
    if ".aspose.org" in sub:
        sub = sub.split(".")[0]
    return sub


def _infer_family_platform(filepath: Path) -> tuple[str, str]:
    """Infer (family, platform) from a content file path."""
    parts = filepath.parts
    try:
        ci = next(i for i, p in enumerate(parts) if p == "content")
    except StopIteration:
        return "", ""
    if len(parts) < ci + 5:
        return "", ""
    family = parts[ci + 3]
    platform = parts[ci + 4]
    return family, platform


def scan_files(
    files: list,
    knowledge,
    subdomain: str | None = None,
) -> dict:
    """Scan files for claim issues. Returns structured report dict.

    Never writes. Never raises on individual file errors.
    """
    from knowledge_core import parse_frontmatter  # noqa: E402

    known_ids: set = set()
    if knowledge is not None and hasattr(knowledge, "claim_ids"):
        known_ids = set(getattr(knowledge, "claim_ids", []) or [])

    issues: list[dict] = []
    total_files = 0
    files_with_issues = 0

    for f in files:
        try:
            fm = parse_frontmatter(Path(f))
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
        file_subdomain = _infer_subdomain(Path(f)) or subdomain or ""

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

            # Unknown / stale (only checked if we have a knowledge model)
            if known_ids and cid not in known_ids:
                file_issues.append({
                    "claim_id": cid,
                    "issue": "UNKNOWN_CLAIM",
                    "severity": "WARN",
                    "message": f"Claim ID not in knowledge model: {cid!r}",
                })

        if file_issues:
            files_with_issues += 1
            issues.append({
                "filepath": str(f),
                "subdomain": file_subdomain,
                "issues": file_issues,
            })

    family = getattr(knowledge, "family", "") if knowledge else ""
    platform = getattr(knowledge, "platform", "") if knowledge else ""

    return {
        "family": family,
        "platform": platform,
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
    print(f"Files scanned:     {report['total_files_scanned']}")
    print(f"Files with issues: {report['files_with_issues']}")
    print(f"Total warnings:    {report['warn_count']}")
    if report["records"]:
        print("\nIssues found:")
        for rec in report["records"][:20]:
            print(f"  {rec['filepath']}")
            for issue in rec["issues"]:
                print(f"    [{issue['severity']}] {issue['issue']}: {issue['message']}")
    print()


def main(argv=None):
    import argparse
    from knowledge_core import Knowledge, discover_content  # noqa: E402

    parser = argparse.ArgumentParser(
        prog="claim_report",
        description="WARN-only CI claim report for non-reference subdomains.",
    )
    parser.add_argument("family", nargs="?", default="",
                        help="Product family (e.g. cells)")
    parser.add_argument("platform", nargs="?", default="",
                        help="Product platform (e.g. java)")
    parser.add_argument("--files", nargs="+", metavar="FILE",
                        help="Specific files to scan (CI mode)")
    parser.add_argument("--subdomain", metavar="SUBDOMAIN",
                        help="Restrict to this subdomain only")
    parser.add_argument("--output-json", "--json-out", metavar="OUTFILE",
                        dest="output_json",
                        help="Write full JSON report to OUTFILE")
    parser.add_argument("--warn-annotations", action="store_true",
                        help="Emit GitHub Actions ::warning:: annotations")

    parsed = parser.parse_args(argv)

    if parsed.files:
        files = [Path(f) for f in parsed.files]
        family, platform = parsed.family, parsed.platform
        if not family or not platform:
            family, platform = _infer_family_platform(files[0])
    else:
        family, platform = parsed.family, parsed.platform
        if not family or not platform:
            parser.error("family and platform are required when --files is not given")
        files = None

    knowledge = None
    if family and platform:
        try:
            knowledge = Knowledge(family, platform)
            if not knowledge.available:
                print(f"WARN: no knowledge model for {family}/{platform}; "
                      "UNKNOWN_CLAIM detection may be incomplete")
        except Exception as e:
            print(f"WARN: could not load knowledge model: {e}")

    if files is None:
        files = discover_content(family, platform)
        if parsed.subdomain:
            files = [f for f in files if _infer_subdomain(Path(f)) == parsed.subdomain]

    report = scan_files(files, knowledge, subdomain=parsed.subdomain)
    _print_summary(report)

    if parsed.warn_annotations:
        for rec in report.get("records", []):
            for issue in rec.get("issues", []):
                fp = rec["filepath"]
                msg = f"[{issue['issue']}] {issue['message']}"
                print(f"::warning file={fp}::{msg}")

    if parsed.output_json:
        out = Path(parsed.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Report written to {out}")

    # Always exit 0 -- WARN-only, never blocks pipeline
    sys.exit(0)


if __name__ == "__main__":
    main()

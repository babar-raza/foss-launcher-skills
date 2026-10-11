#!/usr/bin/env python3
"""grade_remediation_check.py — Scan for pages needing grade remediation.

CONTRACT: scripts/pipeline/commands/ops/grade_remediation_check.py
  purpose: Scan content pages for D/F grades and stale grades (graded_content_hash mismatch).
           Used in S-84 Step 9.6 and S-96 (grade-remediate).
  inputs:  family, platform, --grade-filter (default: D,F), --stale-grades, --list
  outputs: reports/refresh_review/{family}/{platform}/grade_remediation_report.json
  idempotent: yes — overwrites on re-run

Exit codes:
  0 = no grade issues found (or --list produced report; no action needed)
  1 = grade issues found (D/F pages or stale grades)
  2 = scan error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


def _compute_body_hash(file_path: Path) -> str:
    """Compute sha256 of the body content (after frontmatter)."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    # Strip YAML frontmatter (between --- delimiters)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:].lstrip("\n")
        else:
            body = text
    else:
        body = text
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _get_grade_info(file_path: Path) -> dict | None:
    """
    Read grade frontmatter from a markdown file.

    Returns dict with 'grade', 'graded_content_hash' (if present), or None if no grade block.
    """
    try:
        lib_dir = str(_REPO_ROOT / "scripts" / "pipeline")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from lib.grade_writer import read_grade  # type: ignore
        return read_grade(file_path)
    except Exception:
        return None


def scan(
    family: str,
    platform: str,
    *,
    grade_filter: list[str] | None = None,
    check_stale: bool = False,
    repo_root: Path | None = None,
    out_path: Path | None = None,
) -> tuple[list[dict], int]:
    """
    Scan content pages for grade issues.

    Returns (issues_list, exit_code).
    Each issue dict: {path, grade, issue_type, graded_content_hash, current_body_hash}.
    """
    root = repo_root or _REPO_ROOT
    if grade_filter is None:
        grade_filter = ["D", "F"]

    if out_path is None:
        out_path = (
            root / "reports" / "refresh_review" / family / platform
            / "grade_remediation_report.json"
        )

    issues: list[dict] = []
    scanned = 0
    errors = 0

    for site in ["docs.aspose.org", "kb.aspose.org"]:
        site_dir = root / "content" / site / "en" / family / platform
        if not site_dir.is_dir():
            continue
        for md_file in sorted(site_dir.rglob("*.md")):
            scanned += 1
            try:
                grade_info = _get_grade_info(md_file)
                if not grade_info:
                    continue

                grade = grade_info.get("grade", "")
                graded_hash = grade_info.get("graded_content_hash", "")
                rel_path = str(md_file.relative_to(root))

                if grade in grade_filter:
                    issues.append({
                        "path": rel_path,
                        "grade": grade,
                        "issue_type": "GRADE_FILTER_MATCH",
                        "graded_content_hash": graded_hash,
                        "current_body_hash": "",
                        "grade_reasons": grade_info.get("grade_reasons", []),
                    })
                elif check_stale and graded_hash:
                    current_hash = _compute_body_hash(md_file)
                    if current_hash != graded_hash:
                        issues.append({
                            "path": rel_path,
                            "grade": grade,
                            "issue_type": "STALE_GRADE",
                            "graded_content_hash": graded_hash,
                            "current_body_hash": current_hash,
                            "grade_reasons": grade_info.get("grade_reasons", []),
                        })

            except Exception as e:
                errors += 1

    report = {
        "family": family,
        "platform": platform,
        "grade_filter": grade_filter,
        "stale_check": check_stale,
        "scanned_count": scanned,
        "issue_count": len(issues),
        "error_count": errors,
        "issues": issues,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    exit_code = 1 if issues else 0
    return issues, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan for D/F grades and stale grades in content pages"
    )
    parser.add_argument("family", help="Product family (e.g. cells)")
    parser.add_argument("platform", help="Platform (e.g. java)")
    parser.add_argument(
        "--grade-filter", default="D,F",
        help="Comma-separated grades to flag (default: D,F)"
    )
    parser.add_argument(
        "--stale-grades", action="store_true",
        help="Also flag pages where graded_content_hash != current body hash"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Print issue list to stdout (always exits 0 for use in pipelines)"
    )
    parser.add_argument("--out", default=None, help="Output path for grade_remediation_report.json")
    parser.add_argument("--repo-root", default=None, help="Override repository root")
    args = parser.parse_args(argv)

    grade_filter = [g.strip().upper() for g in args.grade_filter.split(",") if g.strip()]
    repo_root = Path(args.repo_root) if args.repo_root else None
    out_path = Path(args.out) if args.out else None

    issues, exit_code = scan(
        args.family, args.platform,
        grade_filter=grade_filter,
        check_stale=args.stale_grades,
        repo_root=repo_root,
        out_path=out_path,
    )

    if args.list:
        if issues:
            print(f"Found {len(issues)} grade issue(s) for {args.family}/{args.platform}:")
            for issue in issues:
                print(f"  [{issue['grade']}] {issue['issue_type']}: {issue['path']}")
        else:
            print(f"No grade issues found for {args.family}/{args.platform}")
        return 0

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

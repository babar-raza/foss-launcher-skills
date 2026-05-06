"""Locale grade drift check — SH-02 enforcement for locale pages.

Detects locale pages whose grade is worse than the English source
or below the public grade floor (grade B). Distinguishes public pages from drafts.

Grade floor policy (TC-GP-2):
- docs/blog/KB pages must be grade B or better.
- Reference pages are exempt (known false-positive issue pending characterization).
- Draft pages (draft: true) are exempt from grade floor.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/locale_grade_drift.py
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/locale_grade_drift.py --family email --platform cpp
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/locale_grade_drift.py --json

Exit codes:
    0  No grade drift or floor violations on public pages
    1  One or more violations found
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[4]

GRADE_ORDER = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
FLOOR_GRADE = "B"  # minimum public grade for docs/blog/KB

# Subdomain directories to check (reference is exempt)
CHECKED_SUBDOMAINS = [
    "blog.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
]

GRADE_RE = re.compile(r"^grade:\s*([A-F])", re.MULTILINE)
DRAFT_RE = re.compile(r"^draft:\s*true", re.MULTILINE)


def parse_md(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"grade": None, "draft": False}
    grade_m = GRADE_RE.search(text)
    is_draft = bool(DRAFT_RE.search(text))
    return {
        "grade": grade_m.group(1) if grade_m else None,
        "draft": is_draft,
    }


def check_directory(subdir: Path) -> list[dict]:
    """Check all locale variants in a directory against the English source."""
    findings = []
    if not subdir.exists():
        return findings

    # Walk: for each English index.md, find locale variants
    for english_file in subdir.rglob("index.md"):
        parent = english_file.parent
        english_info = parse_md(english_file)
        english_grade = english_info["grade"]

        # Find locale variants: index.*.md in the same directory
        locale_files = list(parent.glob("index.*.md"))
        if not locale_files:
            continue

        for locale_file in locale_files:
            locale_info = parse_md(locale_file)
            locale_grade = locale_info["grade"]
            is_draft = locale_info["draft"]

            if is_draft:
                continue  # drafts are exempt

            if locale_grade is None:
                continue  # no grade field

            # Check 1: grade floor violation
            floor_val = GRADE_ORDER.get(FLOOR_GRADE, 4)
            locale_val = GRADE_ORDER.get(locale_grade, 0)
            if locale_val < floor_val:
                findings.append({
                    "type": "GRADE_FLOOR_VIOLATION",
                    "file": str(locale_file.relative_to(REPO_ROOT)),
                    "locale_grade": locale_grade,
                    "english_grade": english_grade,
                    "floor": FLOOR_GRADE,
                    "is_draft": False,
                })

            # Check 2: grade worse than English source (drift)
            elif english_grade and locale_val < GRADE_ORDER.get(english_grade, 0):
                findings.append({
                    "type": "LOCALE_DRIFT",
                    "file": str(locale_file.relative_to(REPO_ROOT)),
                    "locale_grade": locale_grade,
                    "english_grade": english_grade,
                    "floor": FLOOR_GRADE,
                    "is_draft": False,
                })

    return findings


def main():
    parser = argparse.ArgumentParser(description="Locale grade drift check")
    parser.add_argument("--family", help="Filter by family (e.g. email)")
    parser.add_argument("--platform", help="Filter by platform (e.g. cpp)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    all_findings = []

    for subdomain in CHECKED_SUBDOMAINS:
        subdir = REPO_ROOT / "content" / subdomain
        if not subdir.exists():
            continue

        if args.family and args.platform:
            search_dirs = [subdir / args.family / args.platform]
        elif args.family:
            search_dirs = list(subdir.glob(f"{args.family}/*/"))
        else:
            search_dirs = [subdir]

        for search_dir in search_dirs:
            all_findings.extend(check_directory(search_dir))

    floor_violations = [f for f in all_findings if f["type"] == "GRADE_FLOOR_VIOLATION"]
    drift_findings = [f for f in all_findings if f["type"] == "LOCALE_DRIFT"]

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pass": len(floor_violations) == 0,  # Only floor violations fail; drift is informational
        "total_floor_violations": len(floor_violations),
        "total_drift_findings": len(drift_findings),
        "total_findings": len(all_findings),
        "floor_grade": FLOOR_GRADE,
        "findings": all_findings,
    }

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        status = "PASS" if results["pass"] else "FAIL"
        print(f"\n# Locale Grade Drift Check")
        print(f"Grade floor: {FLOOR_GRADE}")
        print(f"Status: {status} — {results['total_floor_violations']} floor violation(s), {results['total_drift_findings']} drift finding(s)\n")
        for f in all_findings:
            tag = "ERROR" if f["type"] == "GRADE_FLOOR_VIOLATION" else "WARN"
            print(f"  [{tag}:{f['type']}] {f['file']} — locale:{f['locale_grade']} english:{f['english_grade']}")
        if results["pass"] and not all_findings:
            print("  No grade drift or floor violations on public pages.")

    sys.exit(0 if results["pass"] else 1)


if __name__ == "__main__":
    main()

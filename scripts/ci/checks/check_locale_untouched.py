# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""Assert no locale (non-English) files were touched during launch.

Used as a validation gate in launch-product workflows.
Checks both session ledger and git diff for locale file changes.

Usage:
    python scripts/ci/checks/check_locale_untouched.py cells java
    python scripts/ci/checks/check_locale_untouched.py cells java --report reports/refresh_state/cells/java/translation-skip-report.json

Exit codes:
    0 — PASS: no locale files touched
    1 — FAIL: locale files found in session or git diff
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configurable site domain
SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "aspose.org")

# Locale path patterns for content
LOCALE_PATTERNS = [
    f"content/docs.{SITE_DOMAIN}/{{lang}}/cells/java/",
    f"content/kb.{SITE_DOMAIN}/{{lang}}/cells/java/",
    f"content/reference.{SITE_DOMAIN}/{{lang}}/cells/java/",
    f"content/blog.{SITE_DOMAIN}/cells/java/",  # locale files are index.{lang}.md
]

# English paths (these are OK)
EN_PREFIXES = [
    f"content/docs.{SITE_DOMAIN}/en/",
    f"content/kb.{SITE_DOMAIN}/en/",
    f"content/products.{SITE_DOMAIN}/en/",
    f"content/reference.{SITE_DOMAIN}/en/",
]


def is_locale_file(path: str, family: str, platform: str) -> bool:
    """Determine if a path is a locale (non-English) content file for the given product."""
    # Blog locale files: index.{lang}.md (not index.md)
    if f"content/blog.{SITE_DOMAIN}/{family}/{platform}/" in path:
        if path.endswith(".md") and not path.endswith("/index.md"):
            return True

    # Docs/KB/Reference: non-/en/ paths
    for prefix in EN_PREFIXES:
        if path.startswith(prefix):
            return False

    # Check if it's a content file in a non-English locale
    if path.startswith("content/") and f"/{family}/{platform}/" in path:
        if "/en/" not in path and path.endswith(".md"):
            return True

    return False


def check_git_diff(family: str, platform: str) -> list[str]:
    """Check git diff for locale file changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, check=True,
        )
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        files = []

    return [f for f in files if is_locale_file(f, family, platform)]


def check_staged(family: str, platform: str) -> list[str]:
    """Check staged files for locale content."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, check=True,
        )
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        files = []

    return [f for f in files if is_locale_file(f, family, platform)]


def check_untracked(family: str, platform: str) -> list[str]:
    """Check untracked files for locale content in target paths."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        lines = []

    untracked = [line[3:] for line in lines if line.startswith("?? ")]
    return [f for f in untracked if is_locale_file(f, family, platform)]


def main():
    parser = argparse.ArgumentParser(description="Assert no locale files touched during launch")
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--report", "-r", help="Output report JSON path")
    args = parser.parse_args()

    locale_in_diff = check_git_diff(args.family, args.platform)
    locale_in_staged = check_staged(args.family, args.platform)
    locale_untracked = check_untracked(args.family, args.platform)

    all_locale_files = list(set(locale_in_diff + locale_in_staged + locale_untracked))
    passed = len(all_locale_files) == 0

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "family": args.family,
        "platform": args.platform,
        "locale_files_in_diff": locale_in_diff,
        "locale_files_staged": locale_in_staged,
        "locale_files_untracked_in_target": locale_untracked,
        "total_locale_files_found": len(all_locale_files),
        "verdict": "PASS" if passed else "FAIL",
        "translation_skipped": passed,
    }

    if args.report:
        out_path = Path(args.report)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if passed:
        print(f"PASS: No locale files touched for {args.family}/{args.platform}")
        sys.exit(0)
    else:
        print(f"FAIL: {len(all_locale_files)} locale files found:", file=sys.stderr)
        for f in all_locale_files[:10]:
            print(f"  {f}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check report freshness — anti-stale-evidence guardrail.

Scans reports/*.md and reports/**/*.md for modification age.
Warns on reports older than 30 days. Exit 0 always (advisory only).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "reports"
STALE_DAYS = int(os.environ.get("REPORT_STALE_DAYS", "30"))


def main() -> int:
    if not REPORTS_DIR.is_dir():
        print("SKIP: reports/ directory not found")
        return 0

    now = time.time()
    threshold = now - (STALE_DAYS * 86400)
    fresh = 0
    stale = 0
    total = 0

    for md in sorted(REPORTS_DIR.rglob("*.md")):
        if "__pycache__" in str(md):
            continue
        total += 1
        mtime = md.stat().st_mtime
        age_days = int((now - mtime) / 86400)
        if mtime < threshold:
            stale += 1
            rel = md.relative_to(REPO_ROOT)
            print(f"  WARN: {rel} — {age_days} days old")
        else:
            fresh += 1

    print(f"OK: {fresh} fresh, {stale} stale, {total} total reports (threshold: {STALE_DAYS} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

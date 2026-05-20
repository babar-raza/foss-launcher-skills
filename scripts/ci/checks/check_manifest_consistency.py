#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_manifest_consistency.py — GUARD-04: Manifest/frontmatter grade consistency.

Compares the grade letter in frontmatter with the grade in grade_manifest.json
for each changed .md file.  Warns (does not block) when the two disagree for
the same content_hash.

Usage (CI):
    python scripts/ci/checks/check_manifest_consistency.py <file1.md> [file2.md ...]

Exit codes:
    0  — all consistent (or no manifest / no grade)
    1  — inconsistency found (blocking — MIG-01 transition complete SR-05 2026-04-25)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_FM_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
_GRADE_RE = re.compile(r"^grade:\s*([A-F])\s*$", re.MULTILINE)
_HASH_RE = re.compile(r'^graded_content_hash:\s*"?(\S+?)"?\s*$', re.MULTILINE)

MANIFEST_PATH = Path("reports") / "grade_manifest.json"


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _check_file(filepath: str, manifest: dict) -> str | None:
    """Return a warning string if inconsistency found, else None."""
    try:
        text = Path(filepath).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm_m = _FM_RE.match(text)
    if not fm_m:
        return None

    fm_text = fm_m.group(1)
    grade_m = _GRADE_RE.search(fm_text)
    if not grade_m:
        return None  # No grade in frontmatter

    fm_grade = grade_m.group(1)
    hash_m = _HASH_RE.search(fm_text)
    fm_hash = hash_m.group(1) if hash_m else ""

    # Normalize path key
    key = filepath.replace("\\", "/")
    entry = manifest.get(key)
    if not entry:
        return None  # No manifest entry — nothing to compare

    manifest_grade = entry.get("grade", "")
    manifest_hash = entry.get("content_hash", "")

    # Only compare when content_hash matches — different hashes mean
    # one side is stale, which is expected during transition
    if fm_hash and manifest_hash and fm_hash != manifest_hash:
        return None  # Different content versions — acceptable

    if fm_grade != manifest_grade:
        return (
            f"{filepath}: frontmatter grade={fm_grade} vs manifest grade={manifest_grade} "
            f"(same content_hash={fm_hash[:16]}...)"
        )
    return None


def main(argv: list[str] | None = None) -> int:
    files = argv or sys.argv[1:]
    if not files:
        print("No files to check.")
        return 0

    manifest = _load_manifest()
    if not manifest:
        print("No grade manifest found — skipping consistency check.")
        return 0

    warnings = []
    for f in files:
        if not f.endswith(".md"):
            continue
        warn = _check_file(f, manifest)
        if warn:
            warnings.append(warn)

    if warnings:
        print(f"GUARD-04: {len(warnings)} manifest/frontmatter inconsistency(ies):")
        for w in warnings:
            print(f"  FAIL: {w}")
        # MIG-01 transition complete (SR-05: 2026-04-25). Now blocking (exit 1).
        return 1

    print(f"GUARD-04: {len([f for f in files if f.endswith('.md')])} file(s) checked — all consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""Standalone full-tree scanner for duplicate or malformed grade frontmatter keys.

Role: on-demand audit tool for the whole content tree. Run after backfills,
product launches, or any batch operation that writes grade metadata. Not a CI
gate — for the per-PR CI gate, see scripts/pipeline/commands/governance/check_grade_integrity.py.

Checks:
    - Duplicate grade-related keys in a single frontmatter block
    - Non-consecutive (orphaned) grade keys
    - Invalid grade values (not A-F)
    - ``graded_at`` present without ``grade`` (residual metadata)

Exit codes:
    0 — clean (no errors; warnings still print)
    1 — one or more ERROR-severity findings

Usage:
    python scripts/ci/checks/scan_grade_duplicates.py [content_dir]

Defaults to scanning ``content/`` relative to the repo root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Grade-related frontmatter keys
_GRADE_KEYS = {"grade", "graded_at", "graded_model_sha", "graded_evaluators"}
_GRADE_KEY_LINE_RE = re.compile(
    r"^(grade|graded_at|graded_model_sha|graded_evaluators):", re.MULTILINE
)
_VALID_GRADES = {"A", "B", "C", "D", "F"}


def _extract_frontmatter(text: str) -> str | None:
    """Return frontmatter content between --- delimiters, or None."""
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end < 0:
        return None
    return text[3:end]


def scan_file(filepath: Path) -> list[dict]:
    """Scan a single file for grade frontmatter defects.

    Returns a list of finding dicts with keys: path, severity, message.
    """
    findings: list[dict] = []
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings

    fm = _extract_frontmatter(text)
    if fm is None:
        return findings

    # Count each grade-related key
    key_counts: dict[str, int] = {}
    for m in _GRADE_KEY_LINE_RE.finditer(fm):
        key = m.group(1)
        key_counts[key] = key_counts.get(key, 0) + 1

    if not key_counts:
        return findings  # No grade keys at all

    # Check for duplicate keys
    for key, count in key_counts.items():
        if count > 1:
            findings.append({
                "path": str(filepath),
                "severity": "ERROR",
                "message": f"Duplicate `{key}:` — found {count} occurrences",
            })

    # Check for non-consecutive grade keys (orphans)
    lines = fm.splitlines()
    grade_line_indices: list[int] = []
    for i, line in enumerate(lines):
        if _GRADE_KEY_LINE_RE.match(line):
            grade_line_indices.append(i)

    if len(grade_line_indices) >= 2:
        is_consecutive = all(
            grade_line_indices[j + 1] - grade_line_indices[j] == 1
            for j in range(len(grade_line_indices) - 1)
        )
        if not is_consecutive:
            findings.append({
                "path": str(filepath),
                "severity": "WARN",
                "message": f"Non-consecutive grade keys at lines {grade_line_indices} — possible orphan",
            })

    # Check grade value validity
    for line in lines:
        if line.startswith("grade:"):
            value = line.split(":", 1)[1].strip().strip('"').strip("'")
            if value and value not in _VALID_GRADES:
                findings.append({
                    "path": str(filepath),
                    "severity": "ERROR",
                    "message": f"Invalid grade value: `{value}` (expected A-F)",
                })
            break

    # Check for graded_at without grade
    if "graded_at" in key_counts and "grade" not in key_counts:
        findings.append({
            "path": str(filepath),
            "severity": "WARN",
            "message": "`graded_at:` present without `grade:` — residual metadata",
        })

    return findings


def scan_directory(content_dir: Path) -> list[dict]:
    """Scan all .md files under content_dir."""
    all_findings: list[dict] = []
    for filepath in sorted(content_dir.rglob("*.md")):
        all_findings.extend(scan_file(filepath))
    return all_findings


def main() -> int:
    content_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("content")
    if not content_dir.is_dir():
        print(f"Error: {content_dir} is not a directory", file=sys.stderr)
        return 1

    findings = scan_directory(content_dir)

    errors = [f for f in findings if f["severity"] == "ERROR"]
    warns = [f for f in findings if f["severity"] == "WARN"]

    if not findings:
        file_count = sum(1 for _ in content_dir.rglob("*.md"))
        print(f"Clean: scanned {file_count} files, 0 grade defects found.")
        return 0

    for f in findings:
        prefix = "ERROR" if f["severity"] == "ERROR" else "WARN"
        print(f"[{prefix}] {f['path']}: {f['message']}")

    print(f"\nSummary: {len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

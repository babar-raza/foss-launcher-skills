#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""Verify that all §-references to AGENTS.md resolve to defined sections.

Scans CLAUDE.md, CODEX.md, governance.md (kilocode), skill files, docs/,
and scripts/ for §N patterns and checks each against the section index
defined in AGENTS.md.

Usage:
    python scripts/ci/checks/check_anchor_compatibility.py
    python scripts/ci/checks/check_anchor_compatibility.py --json

Exit codes:
    0  All references resolve
    1  One or more dangling references found
"""
from __future__ import annotations

import json
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
AGENTS_MD = REPO_ROOT / "AGENTS.md"

# Files and directories to scan for §-references
SCAN_FILES = [
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "CODEX.md",
    REPO_ROOT / "OPERATOR_GUIDE.md",
    REPO_ROOT / "RUNBOOK.md",
    REPO_ROOT / ".kilocode" / "rules-code" / "governance.md",
]
SCAN_DIRS = [
    (REPO_ROOT / "skills", "*.md"),
    (REPO_ROOT / "docs", "**/*.md"),
    (REPO_ROOT / "scripts", "**/*.py"),
    (REPO_ROOT / "scripts", "**/*.sh"),
    (REPO_ROOT / ".claude" / "commands", "*.md"),
    (REPO_ROOT / ".agents" / "skills", "**/*.md"),
    (REPO_ROOT / ".kilocode" / "skills", "**/*.md"),
]

# Match §N, §Na, §Nab patterns (e.g. §5, §6a, §6f, §10b, §7c)
_SECTION_REF_RE = re.compile(r"§(\d+[a-z]*)")

# Match heading declarations: ## N. or ## Na. patterns in AGENTS.md
_HEADING_RE = re.compile(r"^##+ (?:§?)(\d+[a-z]*)[.\s:—–-]", re.MULTILINE)

# Also parse the section index table: | §6f | ...
_INDEX_ROW_RE = re.compile(r"^\|\s*§(\d+[a-z]*)\s*\|", re.MULTILINE)

# Patterns that indicate a §-ref is NOT to AGENTS.md (false positive filters)
_FALSE_POSITIVE_PATTERNS = [
    # Reference to a non-AGENTS .md file's section: "RUNBOOK.md §3d", "plan.md §15"
    # Uses negative lookbehind to exclude "AGENTS.md" matches
    re.compile(r"(?<!AGENTS)\.md\b[^§]{0,40}§\d+", re.IGNORECASE),
    # Internal "Part N §N.N" numbering within a document
    re.compile(r"Part\s+\d+\s+§\d+", re.IGNORECASE),
    # Provenance headers: "# Source: AGENTS.md §6d" (historical extraction record)
    re.compile(r"^#\s*Source:\s*AGENTS\.md\s+§", re.MULTILINE),
]


def load_defined_sections() -> frozenset[str]:
    """Extract all section IDs defined in AGENTS.md (headings + index table)."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    sections: set[str] = set()
    for m in _HEADING_RE.finditer(text):
        sections.add(m.group(1))
    for m in _INDEX_ROW_RE.finditer(text):
        sections.add(m.group(1))
    return frozenset(sections)


def _is_false_positive(line: str) -> bool:
    """Check if a line's §-reference is clearly not to AGENTS.md."""
    return any(pat.search(line) for pat in _FALSE_POSITIVE_PATTERNS)


def scan_file(filepath: Path) -> list[tuple[int, str]]:
    """Return [(line_number, section_id)] for all §-references in a file."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    refs = []
    for i, line in enumerate(text.splitlines(), 1):
        if _is_false_positive(line):
            continue
        for m in _SECTION_REF_RE.finditer(line):
            refs.append((i, m.group(1)))
    return refs


def main() -> int:
    as_json = "--json" in sys.argv

    defined = load_defined_sections()
    if not defined:
        print("ERROR: Could not parse any section IDs from AGENTS.md", file=sys.stderr)
        return 1

    issues: list[dict] = []

    # Collect all files to scan
    files_to_scan: list[Path] = []
    for f in SCAN_FILES:
        if f.exists():
            files_to_scan.append(f)
    for dir_path, glob_pattern in SCAN_DIRS:
        if dir_path.exists():
            files_to_scan.extend(sorted(dir_path.glob(glob_pattern)))

    # Don't scan AGENTS.md itself (it defines the sections) or this script (contains §-refs in regex patterns)
    self_path = Path(__file__).resolve()
    files_to_scan = [f for f in files_to_scan if f.resolve() not in (AGENTS_MD.resolve(), self_path)]

    for filepath in files_to_scan:
        refs = scan_file(filepath)
        for line_num, section_id in refs:
            if section_id not in defined:
                rel = filepath.relative_to(REPO_ROOT)
                issues.append({
                    "file": str(rel),
                    "line": line_num,
                    "ref": f"§{section_id}",
                    "detail": f"{rel}:{line_num}: dangling reference §{section_id} (not defined in AGENTS.md)",
                })

    if as_json:
        result = {
            "defined_sections": sorted(defined),
            "files_scanned": len(files_to_scan),
            "issue_count": len(issues),
            "issues": issues,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"Defined sections in AGENTS.md: {sorted(defined)}")
        print(f"Files scanned: {len(files_to_scan)}")
        if issues:
            print(f"\nDANGLING REFERENCES: {len(issues)}\n")
            for issue in issues:
                print(f"  {issue['detail']}")
            print(f"\nFAIL: {len(issues)} dangling §-reference(s)")
        else:
            print("\nPASS: all §-references resolve to defined AGENTS.md sections")

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

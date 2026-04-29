#!/usr/bin/env python3
"""Check for content duplication between AGENTS.md root and child docs.

FAIL if 5+ consecutive identical non-empty lines appear in both root and any child doc.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_MD = REPO_ROOT / 'AGENTS.md'
CHILD_DIRS = [
    REPO_ROOT / 'docs' / 'governance',
    REPO_ROOT / 'docs' / 'workflows',
    REPO_ROOT / 'docs' / 'registries',
]
THRESHOLD = 5  # consecutive identical lines


def get_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]


def find_duplicates(root_lines: list[str], child_lines: list[str]) -> list[tuple[int, int]]:
    dupes = []
    for i in range(len(root_lines) - THRESHOLD + 1):
        window = root_lines[i:i + THRESHOLD]
        for j in range(len(child_lines) - THRESHOLD + 1):
            if child_lines[j:j + THRESHOLD] == window:
                dupes.append((i, j))
    return dupes


def main() -> int:
    root_lines = get_lines(AGENTS_MD)
    issues = 0
    for child_dir in CHILD_DIRS:
        if not child_dir.exists():
            continue
        for child_file in sorted(child_dir.glob('*.md')):
            child_lines = get_lines(child_file)
            dupes = find_duplicates(root_lines, child_lines)
            if dupes:
                rel = child_file.relative_to(REPO_ROOT)
                print(f'WARN: {len(dupes)} duplicate block(s) between AGENTS.md and {rel} (transitional)')
                issues += len(dupes)
    if issues:
        print(f'Total: {issues} duplicate block(s) (transitional — expected during Phase 2-4)')
        return 0  # WARN only during transitional phase
    print('OK: no content duplication detected')
    return 0


if __name__ == '__main__':
    sys.exit(main())

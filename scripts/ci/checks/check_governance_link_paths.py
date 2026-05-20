# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
"""Verify markdown links in governance child docs resolve to existing files.

Checks all [text](path) links in docs/governance/ and docs/workflows/ files.
FAIL if any target path does not exist.
"""
from __future__ import annotations
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parents[3])))
CHILD_DIRS = [
    REPO_ROOT / 'docs' / 'governance',
    REPO_ROOT / 'docs' / 'workflows',
    REPO_ROOT / 'docs' / 'registries',
]
LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def main() -> int:
    issues = 0
    for child_dir in CHILD_DIRS:
        if not child_dir.exists():
            continue
        for md_file in sorted(child_dir.glob('*.md')):
            content = md_file.read_text(encoding='utf-8')
            for match in LINK_RE.finditer(content):
                link_path = match.group(2)
                # Skip URLs, anchors, and protocol links
                if link_path.startswith(('http://', 'https://', '#', 'mailto:')):
                    continue
                # Strip anchor from path
                link_path = link_path.split('#')[0]
                if not link_path:
                    continue
                # Resolve relative to repo root (links in child docs are repo-relative)
                target = REPO_ROOT / link_path
                if not target.exists():
                    rel = md_file.relative_to(REPO_ROOT)
                    print(f'FAIL: {rel}: broken link -> {link_path}')
                    issues += 1
    if issues:
        print(f'Total: {issues} broken link(s)')
        return 1
    print('OK: all governance child doc links resolve')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Check AGENTS.md line count — anti-regrowth guardrail.

Post-refactor thresholds: WARN >480, FAIL >550.
Constitutional verbatim sections (§5, §6f, §7, §7b, §7c, §8, §11, §13)
account for ~300 lines; stubs+routing for moved sections add ~160.
"""
from __future__ import annotations
import sys
from pathlib import Path

AGENTS_MD = Path(__file__).resolve().parents[3] / 'AGENTS.md'
WARN_THRESHOLD = 480
FAIL_THRESHOLD = 550


def main() -> int:
    lines = AGENTS_MD.read_text(encoding='utf-8').splitlines()
    count = len(lines)
    if count > FAIL_THRESHOLD:
        print(f'FAIL: AGENTS.md has {count} lines (threshold: {FAIL_THRESHOLD})')
        return 1
    if count > WARN_THRESHOLD:
        print(f'WARN: AGENTS.md has {count} lines (threshold: {WARN_THRESHOLD})')
        return 0
    print(f'OK: AGENTS.md has {count} lines')
    return 0


if __name__ == '__main__':
    sys.exit(main())

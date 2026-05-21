#!/usr/bin/env python3
"""Reconcile skill counts in README files after adding or removing a skill.

Run this after adding a new skill file:
    python scripts/ci/fix_skill_counts.py

The script counts *.md files in skills/ (excluding README.md), then updates
every "N registered skills" occurrence in the four README files that track
the count. Does NOT touch AGENTS.md (machine-validated by check_skill_registry.py).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

SKILLS_DIR = REPO / "skills"

FILES_WITH_COUNT = [
    REPO / "skills" / "README.md",
    REPO / ".agents" / "skills" / "README.md",
    REPO / ".kilocode" / "skills" / "README.md",
    REPO / ".claude" / "commands" / "README.md",
]

_REGISTERED_RE = re.compile(r'(\b)(\d+)(\b)(?= registered skills)')


def main() -> int:
    skill_files = sorted(p for p in SKILLS_DIR.glob("*.md") if p.stem != "README")
    actual = len(skill_files)

    changed = []
    for fpath in FILES_WITH_COUNT:
        if not fpath.exists():
            print(f"SKIP (not found): {fpath.relative_to(REPO)}")
            continue
        text = fpath.read_text(encoding="utf-8")
        new_text = _REGISTERED_RE.sub(lambda m: m.group(1) + str(actual) + m.group(3), text)
        if new_text != text:
            fpath.write_text(new_text, encoding="utf-8")
            changed.append(str(fpath.relative_to(REPO)))

    if changed:
        print(f"Updated count to {actual} in:")
        for f in changed:
            print(f"  {f}")
    else:
        print(f"OK: all files already show {actual} registered skills.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

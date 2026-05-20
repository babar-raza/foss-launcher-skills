# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""validate_skill_ids.py — Verify that skill IDs exist in the AGENTS.md §12 registry.

Called by the commit-msg hook and CI workflow to validate "Skills invoked:" declarations.

Usage:
  python scripts/ci/checks/validate_skill_ids.py S-01 S-23 S-48
  echo "Skills invoked: [S-01, S-48]" | python scripts/ci/checks/validate_skill_ids.py --stdin

Exit codes:
  0  All IDs are valid (or no IDs provided)
  1  One or more IDs are not in the AGENTS.md §12 registry
"""
from __future__ import annotations

import logging
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
AGENTS_MD = REPO_ROOT / "AGENTS.md"
SKILLS_CHILD_DOC = REPO_ROOT / "docs" / "registries" / "skills.md"

# Regex to extract skill registry rows: | skill-name | S-nn | description |
_ROW_RE = re.compile(r"^\|\s*[\w\-]+\s*\|\s*(S-\d+)\s*\|", re.MULTILINE)
# Regex to extract S-nn patterns from arbitrary text
_ID_RE = re.compile(r"S-\d+", re.IGNORECASE)


def load_registry() -> frozenset[str]:
    """Parse §12 skill table. Dual-read: prefer child doc, fall back to AGENTS.md."""
    if SKILLS_CHILD_DOC.exists():
        text = SKILLS_CHILD_DOC.read_text(encoding="utf-8")
    elif AGENTS_MD.exists():
        logging.warning("FALLBACK: reading Skills reference from AGENTS.md — child doc missing")
        text = AGENTS_MD.read_text(encoding="utf-8")
    else:
        return frozenset()
    return frozenset(m.group(1).upper() for m in _ROW_RE.finditer(text))


def validate_ids(ids: list[str], registry: frozenset[str]) -> list[str]:
    """Return list of IDs that are not in the registry."""
    return [id_.upper() for id_ in ids if id_.upper() not in registry]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--stdin" in args:
        text = sys.stdin.read()
        ids = _ID_RE.findall(text)
    else:
        ids = [a for a in args if _ID_RE.fullmatch(a.upper())]

    if not ids:
        print("No skill IDs to validate.")
        return 0

    registry = load_registry()
    if not registry:
        print("WARNING: Could not load skill registry from AGENTS.md — skipping ID validation.", file=sys.stderr)
        return 0  # Fail open if AGENTS.md is unavailable (bootstrap scenarios)

    unknown = validate_ids(ids, registry)
    if unknown:
        print(f"BLOCKED: Unknown skill ID(s) in 'Skills invoked:' declaration: {unknown}")
        print(f"  Valid IDs per governance docs §12: {sorted(registry)}")
        print("  Fix: use only IDs listed in the §12 skill registry table.")
        return 1

    print(f"Skill IDs validated OK: {sorted(set(id_.upper() for id_ in ids))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

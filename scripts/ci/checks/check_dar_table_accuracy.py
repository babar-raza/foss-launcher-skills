#!/usr/bin/env python3
"""check_dar_table_accuracy.py — RPR-G-02: DAR-table skill IDs must match skills.md.

docs/governance/dar-table.md maps each skill command to a skill ID, e.g.
``| `/refresh-product` (S-84) | ...``. Those IDs drifted from the authoritative
docs/registries/skills.md over time — a full audit (RPR-A-04) found 8 wrong IDs
(e.g. /refresh-product labeled S-80 when S-80 is coverage-reconcile). This check
asserts every ``(S-NN)`` in dar-table.md matches skills.md's ``| name | S-NN |``
mapping, so the drift cannot recur.

Exit codes:
  0 — every DAR-table skill ID matches skills.md
  1 — one or more mismatches
  2 — a source file is missing/unparseable
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DAR_TABLE = REPO_ROOT / "docs" / "governance" / "dar-table.md"
SKILLS_MD = REPO_ROOT / "docs" / "registries" / "skills.md"

# dar-table rows: | `/skill-name` (S-NN) | ... |
_DAR_ROW = re.compile(r"\|\s*`?/([a-z0-9-]+)`?\s*\((S-[A-Z0-9-]+)\)")
# skills.md rows: | skill-name | S-NN | purpose |
_SKILLS_ROW = re.compile(r"\|\s*`?([a-z0-9-]+)`?\s*\|\s*(S-[A-Z0-9-]+)\s*\|")


def load_skills_map(skills_md: Path) -> dict[str, str]:
    """name -> canonical skill ID from skills.md."""
    text = skills_md.read_text(encoding="utf-8")
    mapping = {}
    for m in _SKILLS_ROW.finditer(text):
        name, sid = m.group(1).strip(), m.group(2).strip()
        # Skip the header/separator rows.
        if name.lower() in ("skill", "id", "---"):
            continue
        mapping[name] = sid
    return mapping


def find_mismatches(dar_table: Path, skills_map: dict[str, str]) -> list[dict]:
    """Return DAR-table rows whose (S-NN) disagrees with skills.md for that name."""
    text = dar_table.read_text(encoding="utf-8")
    mismatches = []
    for m in _DAR_ROW.finditer(text):
        name, dar_id = m.group(1).strip(), m.group(2).strip()
        canonical = skills_map.get(name)
        if canonical is None:
            continue  # name not in skills.md (e.g. /knowledge-bootstrap, /change-guard) — skip
        if dar_id != canonical:
            mismatches.append({"name": name, "dar_id": dar_id, "canonical_id": canonical})
    return mismatches


def main(argv=None) -> int:
    if not DAR_TABLE.is_file() or not SKILLS_MD.is_file():
        print("ERROR: dar-table.md or skills.md missing", file=sys.stderr)
        return 2
    try:
        skills_map = load_skills_map(SKILLS_MD)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not parse skills.md: {exc}", file=sys.stderr)
        return 2

    mismatches = find_mismatches(DAR_TABLE, skills_map)
    if mismatches:
        print(f"DAR-TABLE DRIFT: {len(mismatches)} skill ID(s) disagree with skills.md:")
        for mm in mismatches:
            print(f"  /{mm['name']}: dar-table says {mm['dar_id']}, skills.md says {mm['canonical_id']}")
        return 1
    print(f"OK: all DAR-table skill IDs match skills.md ({len(skills_map)} skills known).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

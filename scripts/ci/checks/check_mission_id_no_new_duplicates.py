#!/usr/bin/env python3
"""check_mission_id_no_new_duplicates.py — ST-194: mission-id duplicate-number
regression gate.

Groups every entry in scripts/pipeline/config/mission-ids.jsonl by its
`number` field. Any number claimed by more than one distinct `mission_id` is
a duplicate -- the same defect class as the confirmed MT018 double-mint
(ST-157) and the 19 further historical instances found and disclosed by
ST-194 (2026-09-11).

Per the disclose-not-rename decision (ST-194, matching the original MT018
precedent), historical duplicates are never renamed -- they stay in the
ledger as disclosed history. This check is a ratchet, not a rename-enforcer:
duplicates listed in scripts/pipeline/config/mission-id-known-duplicates.json
are reported as known/accepted, but any duplicate number NOT in that baseline
is a real regression and fails even in --strict mode.

Landed ADVISORY (matching check_mission_id_ledger_coverage.py's and
check_master_plan_index_completeness.py's own first-landing posture, both
its siblings in this same ST-157/ST-194 family): promote to blocking once
this has run clean against real CI traffic for a while.

Usage:
    python scripts/ci/checks/check_mission_id_no_new_duplicates.py
    python scripts/ci/checks/check_mission_id_no_new_duplicates.py --root PATH
    python scripts/ci/checks/check_mission_id_no_new_duplicates.py --strict

Exit codes:
    0 — no new duplicates (known/baseline duplicates, if any, reported as info)
    1 — a duplicate number not in the baseline exists AND --strict given
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PIPELINE_DIR = _REPO_ROOT / "scripts" / "pipeline"
_LIB_DIR = _PIPELINE_DIR / "lib"
for _p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mission_id_ledger import MissionIdLedger  # noqa: E402

_BASELINE_PATH = _PIPELINE_DIR / "config" / "mission-id-known-duplicates.json"


def _load_baseline(root: Path) -> set[int]:
    path = root / "scripts" / "pipeline" / "config" / "mission-id-known-duplicates.json"
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("known_duplicate_numbers", []))


def find_duplicate_numbers(root: Path) -> dict[int, list[str]]:
    """Return {number: [mission_id, ...]} for every number claimed by more
    than one distinct mission_id in the ledger."""
    ledger = MissionIdLedger(repo_root=root)
    by_number: dict[int, list[str]] = defaultdict(list)
    for entry in ledger.history():
        number = entry.get("number")
        mission_id = entry.get("mission_id")
        if isinstance(number, int) and mission_id and mission_id not in by_number[number]:
            by_number[number].append(mission_id)
    return {n: ids for n, ids in by_number.items() if len(ids) > 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="Repo root override (for tests)")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any NEW finding instead of advisory-only")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _REPO_ROOT
    duplicates = find_duplicate_numbers(root)
    baseline = _load_baseline(root)

    known = {n: ids for n, ids in duplicates.items() if n in baseline}
    new = {n: ids for n, ids in duplicates.items() if n not in baseline}

    if known:
        print(f"INFO: {len(known)} known, previously-disclosed duplicate number(s) (baseline: {_BASELINE_PATH}):")
        for number in sorted(known):
            print(f"  - MT{number:03d}: {', '.join(sorted(known[number]))}")

    if not new:
        print("PASS: no NEW duplicate mission-id numbers beyond the disclosed baseline.")
        return 0

    label = "FAIL" if args.strict else "ADVISORY"
    print(f"{label}: {len(new)} NEW duplicate mission-id number(s) not in the baseline:")
    for number in sorted(new):
        print(f"  - MT{number:03d}: {', '.join(sorted(new[number]))}")
    print("Fix: mint future ids ONLY via `mission_authority.py allocate` (never hand-pick a number); "
          "if this is a genuinely disclosed historical duplicate, add it to "
          f"{_BASELINE_PATH} with a citation, per the ST-194 disclose-not-rename policy.")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())

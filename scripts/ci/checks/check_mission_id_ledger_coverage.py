#!/usr/bin/env python3
"""check_mission_id_ledger_coverage.py — ST-157: mission-id allocation regression gate.

Flags any numeric MT0NN mission id that appears in `plans/missions/*.md` or
`docs/readme-refresh/plan-system-forensic-reconciliation.md`'s Track B table
but is absent from `scripts/pipeline/config/mission-ids.jsonl` -- i.e. a
mission whose id was hand-picked outside `mission_authority.py allocate` /
`seed-ledger`, bypassing the collision-safe minting path this fix introduced.

Non-numeric, free-text slug mission ids (e.g. backlink-governance-redesign)
are explicitly out of scope and never flagged -- see mission_id_ledger.py's
module docstring for why.

Landed ADVISORY (matching check_pipeline_registration.py's own landing
pattern for a first-time check in this workflow): a genuinely new,
unanticipated Track B table format change could produce a false positive
this check has not been proven against yet. Promote to blocking once this
has run clean against real CI traffic for a while.

Usage:
    python scripts/ci/checks/check_mission_id_ledger_coverage.py
    python scripts/ci/checks/check_mission_id_ledger_coverage.py --root PATH
    python scripts/ci/checks/check_mission_id_ledger_coverage.py --strict   # exit 1 on any finding

Exit codes:
    0 — clean, or findings present but --strict not given (advisory default)
    1 — findings present AND --strict given
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PIPELINE_DIR = _REPO_ROOT / "scripts" / "pipeline"
_GOVERNANCE_DIR = _PIPELINE_DIR / "commands" / "governance"
_LIB_DIR = _PIPELINE_DIR / "lib"
for _p in (str(_PIPELINE_DIR), str(_GOVERNANCE_DIR), str(_LIB_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mission_authority  # noqa: E402
from mission_id_ledger import MissionIdLedger  # noqa: E402


def find_uncovered(root: Path) -> list[str]:
    """Return every MT0NN-shaped mission id (plans/missions/*.md) or
    MT0NN placeholder (Track B table, bare numbers only -- see
    mission_authority._track_b_numbers's docstring) with no matching
    coverage in the ledger.

    plans/missions/*.md ids are matched by exact mission_id string (that's
    what seed-ledger records for this source). Track B numbers are matched
    by NUMBER, not by reconstructing the placeholder string: seed-ledger
    deliberately skips writing a placeholder when a REAL id for that number
    already exists from another source (see cmd_seed_ledger's Track B
    branch) -- so "covered" for Track B means "this number appears in the
    ledger under ANY id", not "this exact placeholder string is present".
    """
    ledger = MissionIdLedger(repo_root=root)
    history = ledger.history()
    ledger_ids = {e.get("mission_id") for e in history}
    ledger_numbers = {e.get("number") for e in history}

    uncovered: list[str] = []
    for mission_id in mission_authority._plans_missions_mission_ids(root):
        if mission_authority._MT_ID_RE.match(mission_id) and mission_id not in ledger_ids:
            uncovered.append(mission_id)
    for number in mission_authority._track_b_numbers(root):
        if number not in ledger_numbers:
            uncovered.append(f"MT{number:03d}-README-REFRESH-TRACK-B-PLACEHOLDER")

    return sorted(set(uncovered))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="Repo root override (for tests)")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any finding instead of advisory-only")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _REPO_ROOT
    uncovered = find_uncovered(root)

    if not uncovered:
        print("PASS: every MT0NN mission id in plans/missions/ and the Track B table is covered by the ledger.")
        return 0

    label = "FAIL" if args.strict else "ADVISORY"
    print(f"{label}: {len(uncovered)} MT0NN mission id(s) not found in {MissionIdLedger(repo_root=root).path}:")
    for mission_id in uncovered:
        print(f"  - {mission_id}")
    print("Fix: mint future ids via `mission_authority.py allocate`; "
          "backfill this one via `mission_authority.py seed-ledger`.")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())

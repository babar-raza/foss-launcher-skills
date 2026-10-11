#!/usr/bin/env python3
"""check_master_plan_index_completeness.py — flags a real MT0NN mission id
with no row in plans/master-plan.md's index table.

Companion to check_mission_id_ledger_coverage.py (ST-157), which flags a
mission id used OUTSIDE the ledger's collision-safe allocation path. This
check flags the opposite direction: a mission id that IS correctly in
scripts/pipeline/config/mission-ids.jsonl but was never followed through into
a plans/missions/{id}.md file + plans/master-plan.md row -- the exact gap
found live 2026-09-10 (commit bba6f36bd5 flagged it, unresolved; MT058-MT066
backfilled the same day this check was added).

Track B (readme-refresh's own private MT0NN sequence, `source:
track-b-table-scan` placeholder entries) is out of scope by design -- those
ids were never meant to have a plans/missions/ file or master-plan.md row;
see plans/master-plan.md's own header note and
docs/governance/planning-methodology.md's "Collision note".

Landed ADVISORY, matching check_mission_id_ledger_coverage.py's own
first-landing posture: a mission allocated but not yet formally opened (a
legitimate, disclosed state -- see MT063-2026-09-04-REFRESH-PROSE-CAPABILITY)
will report here until it opens or is explicitly abandoned. That is expected,
not a false positive to suppress.

Usage:
    python scripts/ci/checks/check_master_plan_index_completeness.py
    python scripts/ci/checks/check_master_plan_index_completeness.py --root PATH
    python scripts/ci/checks/check_master_plan_index_completeness.py --strict

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
_LIB_DIR = _PIPELINE_DIR / "lib"
for _p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from master_plan_index import _ROW_RE  # noqa: E402
from mission_id_ledger import MissionIdLedger  # noqa: E402

_TRACK_B_PLACEHOLDER_SOURCE = "track-b-table-scan"


def find_missing_rows(root: Path) -> list[str]:
    """Return every non-Track-B mission id in mission-ids.jsonl absent from
    plans/master-plan.md's index table, sorted by mission id."""
    ledger = MissionIdLedger(repo_root=root)
    real_ids = {
        entry["mission_id"]
        for entry in ledger.history()
        if entry.get("source") != _TRACK_B_PLACEHOLDER_SOURCE and entry.get("mission_id")
    }

    index_path = root / "plans" / "master-plan.md"
    indexed_ids: set[str] = set()
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8")
        indexed_ids = {m.group("id").strip() for m in _ROW_RE.finditer(text)}

    return sorted(real_ids - indexed_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="Repo root override (for tests)")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any finding instead of advisory-only")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _REPO_ROOT
    missing = find_missing_rows(root)

    if not missing:
        print("PASS: every non-Track-B mission id in mission-ids.jsonl has a plans/master-plan.md row.")
        return 0

    label = "FAIL" if args.strict else "ADVISORY"
    print(f"{label}: {len(missing)} mission id(s) have no plans/master-plan.md row:")
    for mission_id in missing:
        print(f"  - {mission_id}")
    print("Fix: write plans/missions/{id}.md and add its row (master_plan_index.upsert_mission_row(), "
          "or by hand matching the existing table format). If the mission is legitimately allocated but "
          "not yet opened, this finding is expected until it opens -- not a bug to work around.")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())

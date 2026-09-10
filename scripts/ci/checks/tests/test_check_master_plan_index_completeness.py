"""Tests for check_master_plan_index_completeness.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_master_plan_index_completeness import find_missing_rows, main  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "pipeline" / "lib"))
from mission_id_ledger import MissionIdLedger  # noqa: E402

_TABLE_HEADER = "| Mission ID | File | Status |\n|---|---|---|\n"


def _write_index(root: Path, rows: list[str]) -> None:
    plans_dir = root / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    body = _TABLE_HEADER + "".join(rows)
    (plans_dir / "master-plan.md").write_text(body, encoding="utf-8")


def test_empty_repo_has_nothing_to_flag(tmp_path):
    assert find_missing_rows(tmp_path) == []
    assert main(["--root", str(tmp_path)]) == 0


def test_indexed_mission_is_not_flagged(tmp_path):
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=58, mission_id="MT058-2026-08-31-EXAMPLE", track="main", source="git-history-backfill")
    _write_index(tmp_path, [
        "| MT058-2026-08-31-EXAMPLE | [plans/missions/MT058-2026-08-31-EXAMPLE.md](plans/missions/MT058-2026-08-31-EXAMPLE.md) | **CLOSED** |\n",
    ])

    assert find_missing_rows(tmp_path) == []


def test_ledger_id_missing_from_index_is_flagged_advisory_not_blocking(tmp_path, capsys):
    """The exact gap this check exists for: a real ledger id with no
    master-plan.md row -- advisory mode reports it but still exits 0."""
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=59, mission_id="MT059-2026-08-31-EXAMPLE-GAP", track="main", source="local-plan-state-scan")
    _write_index(tmp_path, [])

    missing = find_missing_rows(tmp_path)
    assert missing == ["MT059-2026-08-31-EXAMPLE-GAP"]

    exit_code = main(["--root", str(tmp_path)])
    assert exit_code == 0  # advisory: reported, not blocking
    out = capsys.readouterr().out
    assert "ADVISORY" in out
    assert "MT059-2026-08-31-EXAMPLE-GAP" in out


def test_strict_mode_fails_on_the_same_finding(tmp_path):
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=59, mission_id="MT059-2026-08-31-EXAMPLE-GAP", track="main", source="local-plan-state-scan")
    _write_index(tmp_path, [])

    exit_code = main(["--root", str(tmp_path), "--strict"])
    assert exit_code == 1


def test_track_b_placeholder_never_flagged(tmp_path):
    """Track B (readme-refresh's own private sequence) is never meant to
    have a plans/master-plan.md row -- see MT041-057's real-world case."""
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(
        number=41, mission_id="MT041-README-REFRESH-TRACK-B-PLACEHOLDER",
        track="readme-refresh", source="track-b-table-scan",
    )
    _write_index(tmp_path, [])

    assert find_missing_rows(tmp_path) == []


def test_missing_index_file_flags_every_real_id(tmp_path):
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=60, mission_id="MT060-2026-09-01-EXAMPLE", track="main", source="local-plan-state-scan")
    # No plans/master-plan.md written at all.

    assert find_missing_rows(tmp_path) == ["MT060-2026-09-01-EXAMPLE"]


def test_real_track_a_id_with_readme_refresh_track_tag_is_still_covered_when_indexed(tmp_path):
    """A real regression this check must not reintroduce: some Track-A
    missions carry track='readme-refresh' in the ledger despite belonging to
    the main index (e.g. MT061-2026-09-01-TRACKB-FOLLOWON-2) -- filtering
    must key off `source`, never `track`."""
    ledger = MissionIdLedger(repo_root=tmp_path)
    ledger.seed(number=61, mission_id="MT061-2026-09-01-EXAMPLE", track="readme-refresh", source="allocate")
    _write_index(tmp_path, [
        "| MT061-2026-09-01-EXAMPLE | [plans/missions/MT061-2026-09-01-EXAMPLE.md](plans/missions/MT061-2026-09-01-EXAMPLE.md) | **CLOSED** |\n",
    ])

    assert find_missing_rows(tmp_path) == []

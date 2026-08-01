"""Tests for lib/master_plan_index.py (production concurrency redesign,
2026-08-01, Step 8).

Includes a real concurrency test (threading, not mocked) proving the lock
actually prevents the lost-update race this module exists to close: two
sessions closing two DIFFERENT missions at the same moment must not silently
erase each other's row.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from lib.master_plan_index import (
    MasterPlanIndexLockTimeout,
    upsert_mission_row,
)

_INDEX_TEMPLATE = """# Master Plan — Index

| Mission ID | File | Status |
|---|---|---|
| MT001-EXISTING | [plans/missions/MT001-EXISTING.md](plans/missions/MT001-EXISTING.md) | **CLOSED** |
| MT002-EXISTING | [plans/missions/MT002-EXISTING.md](plans/missions/MT002-EXISTING.md) | **IN_PROGRESS** |
"""

_EMPTY_TABLE_TEMPLATE = """# Master Plan — Index

| Mission ID | File | Status |
|---|---|---|
"""


def _write_index(tmp_path: Path, text: str = _INDEX_TEMPLATE) -> Path:
    p = tmp_path / "master-plan.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_update_existing_row_in_place(tmp_path):
    idx = _write_index(tmp_path)
    inserted = upsert_mission_row(
        idx, "MT002-EXISTING", "plans/missions/MT002-EXISTING.md", "**CLOSED**",
    )
    assert inserted is False
    text = idx.read_text(encoding="utf-8")
    assert "| MT002-EXISTING | [plans/missions/MT002-EXISTING.md](plans/missions/MT002-EXISTING.md) | **CLOSED** |" in text
    # The other row is untouched.
    assert "| MT001-EXISTING | [plans/missions/MT001-EXISTING.md](plans/missions/MT001-EXISTING.md) | **CLOSED** |" in text


def test_update_preserves_row_order(tmp_path):
    idx = _write_index(tmp_path)
    upsert_mission_row(idx, "MT001-EXISTING", "plans/missions/MT001-EXISTING.md", "**REOPENED**")
    lines = [l for l in idx.read_text(encoding="utf-8").splitlines() if l.startswith("| MT")]
    assert lines[0].startswith("| MT001-EXISTING |")
    assert lines[1].startswith("| MT002-EXISTING |")


def test_insert_new_row_when_mission_absent(tmp_path):
    idx = _write_index(tmp_path)
    inserted = upsert_mission_row(
        idx, "MT003-NEW", "plans/missions/MT003-NEW.md", "**IN_PROGRESS**",
    )
    assert inserted is True
    text = idx.read_text(encoding="utf-8")
    assert "| MT003-NEW | [plans/missions/MT003-NEW.md](plans/missions/MT003-NEW.md) | **IN_PROGRESS** |" in text
    # Existing rows still present, new row appended after them.
    lines = [l for l in text.splitlines() if l.startswith("| MT")]
    assert [l.split(" | ")[0] for l in lines] == ["| MT001-EXISTING", "| MT002-EXISTING", "| MT003-NEW"]


def test_insert_into_empty_table(tmp_path):
    idx = _write_index(tmp_path, _EMPTY_TABLE_TEMPLATE)
    inserted = upsert_mission_row(
        idx, "MT001-FIRST", "plans/missions/MT001-FIRST.md", "**IN_PROGRESS**",
    )
    assert inserted is True
    text = idx.read_text(encoding="utf-8")
    assert "| MT001-FIRST | [plans/missions/MT001-FIRST.md](plans/missions/MT001-FIRST.md) | **IN_PROGRESS** |" in text


def test_missing_index_file_raises(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        upsert_mission_row(
            tmp_path / "nonexistent.md", "MT001", "plans/missions/MT001.md", "**CLOSED**",
        )


def test_no_table_in_file_raises(tmp_path):
    p = tmp_path / "master-plan.md"
    p.write_text("# Just a heading, no table\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no index table"):
        upsert_mission_row(p, "MT001", "plans/missions/MT001.md", "**CLOSED**")


def test_lock_timeout_raises_when_lock_held(tmp_path):
    """A call arriving while another process holds the lock must raise
    MasterPlanIndexLockTimeout, not hang or silently proceed unlocked."""
    idx = _write_index(tmp_path)

    from lib.advisory_lock import FileLock
    holder = FileLock(str(idx) + ".lock")
    holder.acquire()  # simulates another process holding the lock
    try:
        with pytest.raises(MasterPlanIndexLockTimeout):
            upsert_mission_row(
                idx, "MT001-EXISTING", "plans/missions/MT001-EXISTING.md",
                "**CLOSED**", timeout=0.2,
            )
    finally:
        holder.release()


def test_concurrent_upserts_of_different_missions_no_lost_update(tmp_path):
    """The core guarantee this module exists for: N threads each close a
    DIFFERENT mission at roughly the same moment. The lock must serialize
    the read-modify-write so every single mission's row lands correctly --
    none lost to another thread's concurrent write."""
    n_missions = 8
    idx = _write_index(tmp_path, _EMPTY_TABLE_TEMPLATE)

    errors: list[Exception] = []

    def _worker(i: int) -> None:
        try:
            upsert_mission_row(
                idx, f"MT{i:03d}-MISSION", f"plans/missions/MT{i:03d}-MISSION.md",
                "**CLOSED**",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_missions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"unexpected exceptions under concurrent upserts: {errors}"

    text = idx.read_text(encoding="utf-8")
    rows = [l for l in text.splitlines() if l.startswith("| MT")]
    assert len(rows) == n_missions, (
        f"expected {n_missions} rows, got {len(rows)} -- a concurrent write was lost"
    )
    seen_ids = {l.split(" | ")[0].removeprefix("| ") for l in rows}
    assert seen_ids == {f"MT{i:03d}-MISSION" for i in range(n_missions)}


def test_repeated_update_of_same_mission_last_write_wins_no_duplication(tmp_path):
    """Updating the SAME mission's row twice must never create a duplicate
    row -- the second call finds and updates the existing row in place."""
    idx = _write_index(tmp_path, _EMPTY_TABLE_TEMPLATE)
    upsert_mission_row(idx, "MT001-X", "plans/missions/MT001-X.md", "**IN_PROGRESS**")
    upsert_mission_row(idx, "MT001-X", "plans/missions/MT001-X.md", "**CLOSED**")

    text = idx.read_text(encoding="utf-8")
    rows = [l for l in text.splitlines() if l.startswith("| MT001-X")]
    assert len(rows) == 1
    assert "**CLOSED**" in rows[0]

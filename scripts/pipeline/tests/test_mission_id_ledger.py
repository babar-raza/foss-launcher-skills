"""Tests for lib/mission_id_ledger.py (ST-157 fix, MT060-2026-09-01-MISSION-ID-LEDGER).

Includes a real concurrency test (threading, not mocked) that is the literal
replay of the confirmed MT018 double-mint: two callers independently "compute
highest + 1" at the same moment. Against the pre-fix (unlocked, grep-and-pick)
process this collides; against MissionIdLedger.allocate() it must not.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from lib.mission_id_ledger import MissionIdLedger, MissionIdLedgerLockTimeout


def _ledger(tmp_path: Path) -> MissionIdLedger:
    return MissionIdLedger(repo_root=tmp_path)


def test_empty_ledger_history_and_highest_number(tmp_path):
    ledger = _ledger(tmp_path)
    assert ledger.history() == []
    assert ledger.highest_number() == 0


def test_allocate_first_id_is_mt001(tmp_path):
    ledger = _ledger(tmp_path)
    mission_id = ledger.allocate(track="main", slug="EXAMPLE", date="2026-09-01")
    assert mission_id == "MT001-2026-09-01-EXAMPLE"
    assert ledger.highest_number() == 1
    assert ledger.has_id(mission_id)


def test_allocate_increments_across_calls(tmp_path):
    ledger = _ledger(tmp_path)
    first = ledger.allocate(track="main", slug="A", date="2026-09-01")
    second = ledger.allocate(track="readme-refresh", slug="B", date="2026-09-01")
    assert first == "MT001-2026-09-01-A"
    assert second == "MT002-2026-09-01-B"


def test_allocate_continues_from_seeded_history(tmp_path):
    """The whole point of backfill: allocate() must never re-mint a number
    that was only ever recorded via seed(), not a prior allocate() call."""
    ledger = _ledger(tmp_path)
    ledger.seed(number=59, mission_id="MT059-2026-08-31-PDF-GO-S84-FANOUT", track="main", source="backfill")
    new_id = ledger.allocate(track="main", slug="NEXT", date="2026-09-01")
    assert new_id == "MT060-2026-09-01-NEXT"


def test_seed_is_idempotent(tmp_path):
    ledger = _ledger(tmp_path)
    first = ledger.seed(number=18, mission_id="MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE", track="main", source="backfill")
    second = ledger.seed(number=18, mission_id="MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE", track="main", source="backfill")
    assert first is not None
    assert second is None  # no-op re-run
    assert len(ledger.history()) == 1


def test_seed_records_both_historical_mt018_entries_without_collision(tmp_path):
    """The confirmed historical defect this whole fix targets: MT018 was
    issued to two DIFFERENT missions. seed() must be able to record both
    (they are distinct mission_id strings sharing one number) as disclosed
    history, without either write failing or overwriting the other."""
    ledger = _ledger(tmp_path)
    a = ledger.seed(number=18, mission_id="MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE", track="main", source="backfill")
    b = ledger.seed(number=18, mission_id="MT018-2026-08-01-GOVERNANCE-EVIDENCE-TRUST-FORENSICS", track="main", source="backfill")
    assert a is not None and b is not None
    assert len(ledger.history()) == 2
    assert ledger.highest_number() == 18


def test_history_tolerates_torn_last_line(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.allocate(track="main", slug="GOOD", date="2026-09-01")
    with open(ledger.path, "a", encoding="utf-8") as f:
        f.write('{"number": 2, "mission_id": "MT002-2026-09-01-TR')  # simulated crash mid-write, no trailing newline/close
    entries = ledger.history()
    assert len(entries) == 1
    assert entries[0]["mission_id"] == "MT001-2026-09-01-GOOD"


def test_lock_timeout_raises_when_lock_held(tmp_path):
    ledger = _ledger(tmp_path)
    from lib.advisory_lock import FileLock
    holder = FileLock(str(ledger.lock_path))
    holder.acquire()
    try:
        with pytest.raises(MissionIdLedgerLockTimeout):
            ledger._acquire_lock(timeout=0.2)
    finally:
        holder.release()


def test_concurrent_allocate_never_returns_duplicate_ids(tmp_path):
    """The literal MT018 regression proof: N threads race allocate() at the
    same moment. Every returned id must be distinct -- this is the exact
    scenario ("two sessions independently compute highest-seen + 1 at the
    same time") that produced the real, confirmed MT018 double-mint under
    the old grep-and-pick-by-eye process. n kept modest for the same reason
    documented in test_master_plan_index.py's equivalent test (tasklist
    liveness-probe overhead is pure cost, never a real steal, when every
    thread shares one pid)."""
    n = 6
    ledger = _ledger(tmp_path)
    results: list[str] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def _worker(i: int) -> None:
        try:
            mission_id = ledger.allocate(track="main", slug=f"WORKER{i}", date="2026-09-01")
            with lock:
                results.append(mission_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"unexpected exceptions under concurrent allocate(): {errors}"
    assert len(results) == n
    assert len(set(results)) == n, f"duplicate mission id minted under concurrency: {results}"
    numbers = sorted(int(mid.split("-")[0][2:]) for mid in results)
    assert numbers == list(range(1, n + 1)), f"expected a dense 1..{n} sequence, got {numbers}"

"""Tests for lib/taskcard_store.py (production concurrency redesign,
2026-08-01, Step 5).

Includes a real concurrency test (threading, not mocked) proving the
row-level CAS actually serializes competing writers under real contention,
not just sequential simulation -- mirroring test_baseline_ledger.py's own
concurrency proof for its sibling append-only ledger.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import lib.taskcard_store as taskcard_store_module
from lib.taskcard_store import (
    TaskcardCASError,
    TaskcardLockTimeout,
    TaskcardNotFoundError,
    TaskcardStore,
)

MISSION = "MT900-2026-08-01-TEST"


def _base_record(task_id: str, status: str = "TODO", **overrides) -> dict:
    record = {
        "task_id": task_id,
        "mission_id": MISSION,
        "status": status,
        "recorded_at": "2026-08-01T00:00:00Z",
        "recorded_by": "sess-a",
        "evidence_refs": [],
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# Basic append / read semantics
# ---------------------------------------------------------------------------

def test_append_then_get_roundtrips(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01"))
    assert store.get("TC-01")["status"] == "TODO"


def test_append_auto_fills_mission_id(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    record = _base_record("TC-01")
    del record["mission_id"]
    written = store.append(record)
    assert written["mission_id"] == MISSION
    assert store.get("TC-01")["mission_id"] == MISSION


def test_append_rejects_mismatched_mission_id(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        store.append(_base_record("TC-01", mission_id="OTHER-MISSION"))


def test_append_rejects_invalid_schema_missing_field(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    record = _base_record("TC-01")
    del record["recorded_by"]
    with pytest.raises(ValueError, match="invalid taskcard record"):
        store.append(record)


def test_append_rejects_invalid_status(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    with pytest.raises(ValueError, match="invalid taskcard record"):
        store.append(_base_record("TC-01", status="NOT_A_REAL_STATUS"))


def test_append_rejects_verified_status_with_no_evidence(tmp_path):
    """Schema 5f rule (validate_taskcard_record): any status past IMPLEMENTED
    must cite evidence_refs -- this module must actually enforce it on
    write, not just leave it to a downstream check."""
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    with pytest.raises(ValueError, match="invalid taskcard record"):
        store.append(_base_record("TC-01", status="FOCUSED_VERIFIED", evidence_refs=[]))


def test_read_history_is_append_only_and_ordered(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="TODO"))
    store.append(_base_record("TC-01", status="IN_PROGRESS"))
    history = store.read_history()
    assert [r["status"] for r in history] == ["TODO", "IN_PROGRESS"]


def test_read_latest_uses_last_occurrence_wins(tmp_path):
    """Matches check_taskcard_plan_parity.py's load_taskcards semantics:
    the LAST row for a task_id is authoritative, prior rows are history."""
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="TODO"))
    store.append(_base_record("TC-01", status="IN_PROGRESS"))
    store.append(_base_record("TC-02", status="TODO"))
    latest = store.read_latest()
    assert latest["TC-01"]["status"] == "IN_PROGRESS"
    assert latest["TC-02"]["status"] == "TODO"
    assert len(latest) == 2  # one entry per task_id, not per row


def test_get_returns_none_for_unknown_task(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    assert store.get("TC-NONEXISTENT") is None


def test_read_history_empty_when_file_never_created(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    assert store.read_history() == []
    assert store.read_latest() == {}


def test_read_history_tolerates_torn_last_line(tmp_path):
    """A crashed writer mid-append must not make read_history() raise --
    prior, complete lines stay readable; the torn line is silently skipped."""
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="TODO"))
    with open(store.path, "a", encoding="utf-8") as f:
        f.write('{"task_id": "TC-02", "status": "IN_PR')  # truncated, no closing brace/newline
    history = store.read_history()
    assert len(history) == 1
    assert history[0]["task_id"] == "TC-01"


# ---------------------------------------------------------------------------
# update_taskcard_status — row-level CAS
# ---------------------------------------------------------------------------

def test_update_status_happy_path_advances_and_preserves_other_fields(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record(
        "TC-01", status="TODO", title="Do the thing", phase_id="PHASE_1",
    ))
    updated = store.update_taskcard_status(
        "TC-01", expected_status="TODO", new_status="IN_PROGRESS",
        recorded_by="sess-a",
    )
    assert updated["status"] == "IN_PROGRESS"
    assert updated["title"] == "Do the thing"  # carried forward, not dropped
    assert updated["phase_id"] == "PHASE_1"
    assert store.get("TC-01")["status"] == "IN_PROGRESS"
    # Append-only: the original TODO row is still in history, not rewritten.
    statuses = [r["status"] for r in store.read_history() if r["task_id"] == "TC-01"]
    assert statuses == ["TODO", "IN_PROGRESS"]


def test_update_status_carries_forward_evidence_refs_when_not_given(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="TODO", evidence_refs=["prior-ref"]))
    updated = store.update_taskcard_status(
        "TC-01", expected_status="TODO", new_status="IN_PROGRESS",
        recorded_by="sess-a",
    )
    assert updated["evidence_refs"] == ["prior-ref"]


def test_update_status_replaces_evidence_refs_when_given(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="IMPLEMENTED", evidence_refs=["prior-ref"]))
    updated = store.update_taskcard_status(
        "TC-01", expected_status="IMPLEMENTED", new_status="FOCUSED_VERIFIED",
        recorded_by="sess-a", evidence_refs=["new-real-evidence"],
    )
    assert updated["evidence_refs"] == ["new-real-evidence"]


def test_update_status_unknown_task_raises_not_found(tmp_path):
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    with pytest.raises(TaskcardNotFoundError, match="TC-GHOST"):
        store.update_taskcard_status(
            "TC-GHOST", expected_status="TODO", new_status="IN_PROGRESS",
            recorded_by="sess-a",
        )


def test_update_status_rejects_result_failing_schema(tmp_path):
    """new_status must itself be a valid enum value -- a typo doesn't silently
    write garbage."""
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="TODO"))
    with pytest.raises(ValueError, match="invalid taskcard record"):
        store.update_taskcard_status(
            "TC-01", expected_status="TODO", new_status="NOT_A_REAL_STATUS",
            recorded_by="sess-a",
        )
    # Refused write must not have appended anything.
    assert store.get("TC-01")["status"] == "TODO"


def test_update_status_second_racing_session_gets_named_cas_refusal_not_silent_overwrite(
    tmp_path,
):
    """The core guarantee this module exists for (mirrors
    test_two_sessions_overlapping_scope_second_begin_fails_with_named_conflict's
    shape from skill_context.py): session A advances TC-01 from TODO to
    IN_PROGRESS. Session B, racing against a now-stale TODO snapshot, must
    get a NAMED TaskcardCASError -- not silently overwrite A's advance, and
    not corrupt the row."""
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="TODO"))

    # Session A wins the race.
    store.update_taskcard_status(
        "TC-01", expected_status="TODO", new_status="IN_PROGRESS",
        recorded_by="sess-a",
    )

    # Session B still believes TC-01 is TODO (its own stale read) and loses.
    with pytest.raises(TaskcardCASError) as exc_info:
        store.update_taskcard_status(
            "TC-01", expected_status="TODO", new_status="IN_PROGRESS",
            recorded_by="sess-b",
        )
    assert exc_info.value.task_id == "TC-01"
    assert exc_info.value.expected == "TODO"
    assert exc_info.value.actual == "IN_PROGRESS"
    assert exc_info.value.recorded_by == "sess-a"

    # A's advance survives untouched; B's refused attempt appended nothing.
    history = [r for r in store.read_history() if r["task_id"] == "TC-01"]
    assert len(history) == 2  # TODO, then A's IN_PROGRESS -- not 3
    assert store.get("TC-01")["recorded_by"] == "sess-a"


def test_update_status_lock_timeout(tmp_path):
    """A call arriving while another process holds the lock must raise
    TaskcardLockTimeout, not hang or silently proceed unlocked."""
    store = TaskcardStore(MISSION, repo_root=tmp_path)
    store.append(_base_record("TC-01", status="TODO"))
    holder = TaskcardStore(MISSION, repo_root=tmp_path)
    holder._acquire_lock()  # simulates another process holding the lock
    try:
        waiter = TaskcardStore(MISSION, repo_root=tmp_path)
        with pytest.raises(TaskcardLockTimeout):
            waiter._acquire_lock(timeout=0.2)  # short timeout — keep the test fast
    finally:
        holder._release_lock()


def test_concurrent_cas_updates_exactly_one_winner_no_corruption(tmp_path, monkeypatch):
    """Real concurrency test (threading): N threads all race to advance the
    SAME row from TODO to IN_PROGRESS via update_taskcard_status with an
    identical expected_status snapshot. The lock must serialize them so
    exactly ONE succeeds and every other raises TaskcardCASError -- never a
    lost update, a corrupted line, or more than one 'winner'.

    n_threads is deliberately modest (real proof of correct serialization
    under genuine OS-level threading needs a handful of racers, not a
    dozen) -- found while writing this test: every waiter's liveness probe
    shells out to `tasklist` (advisory_lock.py's own documented ~100-300ms/
    call cost), and since every thread here shares ONE pid, that probe can
    never actually find a dead holder to steal from -- it's pure overhead in
    this same-process shape, unlike real cross-session contention (distinct
    pids, naturally staggered by process start times). With enough
    simultaneous same-pid waiters (12, then 6, were both tried), many
    overlapping tasklist spawns on this dev machine (also running other
    genuinely concurrent sessions) occasionally compounded into stalls long
    enough to exceed even a raised timeout -- a real environment/tooling
    interaction specific to over-aggressive same-process stress, not a CAS
    correctness bug (every observed failure was a queued waiter's
    TaskcardLockTimeout, never a wrong winner count or a corrupted line).
    """
    n_threads = 3
    store_factory = lambda: TaskcardStore(MISSION, repo_root=tmp_path)
    store_factory().append(_base_record("TC-RACE", status="TODO"))

    results: list[str] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def _worker(i: int) -> None:
        try:
            TaskcardStore(MISSION, repo_root=tmp_path).update_taskcard_status(
                "TC-RACE", expected_status="TODO", new_status="IN_PROGRESS",
                recorded_by=f"sess-{i}",
            )
            with lock:
                results.append(f"sess-{i}")
        except TaskcardCASError:
            pass  # expected for every loser
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"unexpected exceptions under concurrent CAS: {errors}"
    assert len(results) == 1, f"expected exactly 1 winner, got {len(results)}: {results}"

    history = store_factory().read_history()
    race_rows = [r for r in history if r["task_id"] == "TC-RACE"]
    assert len(race_rows) == 2  # the initial TODO row + exactly one IN_PROGRESS row
    assert race_rows[-1]["status"] == "IN_PROGRESS"
    assert race_rows[-1]["recorded_by"] == results[0]

    # File itself is not corrupted -- every line parses.
    for line in store_factory().path.read_text(encoding="utf-8").splitlines():
        json.loads(line)  # raises if any line is malformed


def test_plan_state_dir_override_takes_precedence_over_repo_root(tmp_path):
    explicit_dir = tmp_path / "custom" / "location"
    store = TaskcardStore(MISSION, repo_root=tmp_path / "unused", plan_state_dir=explicit_dir)
    store.append(_base_record("TC-01"))
    assert (explicit_dir / "taskcards.jsonl").is_file()

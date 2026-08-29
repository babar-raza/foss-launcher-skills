"""Tests for scripts/pipeline/lib/taskcard_store.py (ported 2026-08-29,
TASK_BACKLOG.md SYNC-1). Includes a REAL multi-thread concurrency test --
this module's entire value proposition is race-safety, so a mocked or
sequential test alone would not actually prove it."""
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

from taskcard_store import (  # noqa: E402
    TaskcardCASError,
    TaskcardNotFoundError,
    TaskcardStore,
)


def _make_store(tmp_path, mission_id="TEST-MISSION"):
    return TaskcardStore(mission_id, plan_state_dir=tmp_path / mission_id)


def test_append_and_read_latest_round_trip(tmp_path):
    store = _make_store(tmp_path)
    store.append({
        "task_id": "T-1", "status": "TODO", "recorded_at": "2026-08-29T00:00:00Z",
        "recorded_by": "sess-a", "evidence_refs": [],
    })
    latest = store.read_latest()
    assert latest["T-1"]["status"] == "TODO"
    assert latest["T-1"]["mission_id"] == "TEST-MISSION"


def test_append_rejects_wrong_mission_id(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        store.append({
            "task_id": "T-1", "mission_id": "OTHER-MISSION", "status": "TODO",
            "recorded_at": "2026-08-29T00:00:00Z", "recorded_by": "sess-a", "evidence_refs": [],
        })


def test_append_rejects_invalid_schema(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(ValueError, match="invalid taskcard record"):
        store.append({"task_id": "T-1"})  # missing required fields


def test_append_requires_evidence_for_terminal_status(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(ValueError, match="requires a non-empty evidence_refs"):
        store.append({
            "task_id": "T-1", "status": "CLOSED", "recorded_at": "2026-08-29T00:00:00Z",
            "recorded_by": "sess-a", "evidence_refs": [],
        })


def test_append_allows_closed_with_evidence(tmp_path):
    store = _make_store(tmp_path)
    store.append({
        "task_id": "T-1", "status": "CLOSED", "recorded_at": "2026-08-29T00:00:00Z",
        "recorded_by": "sess-a", "evidence_refs": ["tests/test_x.py::test_y"],
    })
    assert store.get("T-1")["status"] == "CLOSED"


def test_read_history_is_append_order_and_last_wins(tmp_path):
    store = _make_store(tmp_path)
    store.append({"task_id": "T-1", "status": "TODO", "recorded_at": "t0", "recorded_by": "a", "evidence_refs": []})
    store.update_taskcard_status("T-1", expected_status="TODO", new_status="IN_PROGRESS", recorded_by="a")
    history = store.read_history()
    assert [r["status"] for r in history] == ["TODO", "IN_PROGRESS"]
    assert store.get("T-1")["status"] == "IN_PROGRESS"


def test_read_history_tolerates_torn_last_line(tmp_path):
    store = _make_store(tmp_path)
    store.append({"task_id": "T-1", "status": "TODO", "recorded_at": "t0", "recorded_by": "a", "evidence_refs": []})
    with open(store.path, "a", encoding="utf-8") as f:
        f.write('{"task_id": "T-2", "status": "TOD')  # torn, no trailing newline
    history = store.read_history()
    assert len(history) == 1  # torn line skipped, not raised


def test_update_taskcard_status_cas_success(tmp_path):
    store = _make_store(tmp_path)
    store.append({"task_id": "T-1", "status": "TODO", "recorded_at": "t0", "recorded_by": "a", "evidence_refs": []})
    result = store.update_taskcard_status("T-1", expected_status="TODO", new_status="READY", recorded_by="a")
    assert result["status"] == "READY"


def test_update_taskcard_status_cas_failure_on_stale_expectation(tmp_path):
    store = _make_store(tmp_path)
    store.append({"task_id": "T-1", "status": "TODO", "recorded_at": "t0", "recorded_by": "a", "evidence_refs": []})
    store.update_taskcard_status("T-1", expected_status="TODO", new_status="READY", recorded_by="a")
    with pytest.raises(TaskcardCASError):
        store.update_taskcard_status("T-1", expected_status="TODO", new_status="IN_PROGRESS", recorded_by="b")


def test_update_taskcard_status_not_found(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(TaskcardNotFoundError):
        store.update_taskcard_status("GHOST", expected_status="TODO", new_status="READY", recorded_by="a")


def test_pause_taskcard_creates_row_if_missing(tmp_path):
    store = _make_store(tmp_path)
    store.pause_taskcard("T-1", reason="waiting on external input", recorded_by="a")
    row = store.get("T-1")
    assert row["status"] == "PAUSED"
    assert row["pause_reason"] == "waiting on external input"


def test_pause_taskcard_requires_reason(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(ValueError, match="pause_reason"):
        store.pause_taskcard("T-1", reason="", recorded_by="a")


def test_pause_taskcard_not_found_without_create(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(TaskcardNotFoundError):
        store.pause_taskcard("GHOST", reason="x", recorded_by="a", create_if_missing=False)


# --- Real concurrency proof (actual threads, not mocked) --------------------

def test_concurrent_updates_to_same_task_exactly_one_winner(tmp_path):
    """The core safety claim: two REAL threads racing to advance the SAME
    task_id from the same expected_status must produce exactly one winner
    and one CASError, never two silent successes and never a lost update."""
    store = _make_store(tmp_path)
    store.append({"task_id": "T-1", "status": "TODO", "recorded_at": "t0", "recorded_by": "init", "evidence_refs": []})

    results = []
    lock = threading.Lock()

    def worker(name):
        try:
            store.update_taskcard_status("T-1", expected_status="TODO", new_status="IN_PROGRESS", recorded_by=name)
            with lock:
                results.append((name, "won"))
        except TaskcardCASError:
            with lock:
                results.append((name, "lost"))

    threads = [threading.Thread(target=worker, args=(f"sess-{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    wins = [r for r in results if r[1] == "won"]
    losses = [r for r in results if r[1] == "lost"]
    assert len(results) == 20  # every thread completed (no deadlock, no hang)
    assert len(wins) == 1  # exactly one winner -- not zero, not two
    assert len(losses) == 19
    assert store.get("T-1")["status"] == "IN_PROGRESS"
    # History has exactly 2 rows: the initial TODO + the one winning advance --
    # a lost race must append NOTHING, not a phantom row.
    assert len(store.read_history()) == 2


def test_concurrent_appends_of_different_tasks_all_survive(tmp_path):
    """Different task_ids racing to append must all land -- the lock
    serializes file access, it must not drop or corrupt sibling writes."""
    store = _make_store(tmp_path)
    errors = []

    def worker(i):
        try:
            store.append({
                "task_id": f"T-{i}", "status": "TODO", "recorded_at": "t0",
                "recorded_by": f"sess-{i}", "evidence_refs": [],
            })
        except Exception as exc:  # noqa: BLE001
            errors.append((i, exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    latest = store.read_latest()
    assert len(latest) == 30
    assert all(latest[f"T-{i}"]["status"] == "TODO" for i in range(30))

"""
Tests for scripts/pipeline/lib/baseline_ledger.py (RPR-C-01).

Includes a real concurrency test (threading, not mocked) — this class exists
specifically because plan §2.5 SW-1 found zero concurrency-control mechanisms
anywhere in this pipeline, so a fake/mocked "concurrency" test would prove
nothing about the one property that actually matters here: does the lock
serialize concurrent writers so no entry is lost or corrupted.
"""

import json
import threading
import time
from pathlib import Path

import pytest

from lib.baseline_ledger import BaselineLedger, LedgerLockTimeout


def test_append_is_schema_valid(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    entry = ledger.append(new_repo_sha="abc", sha_source="scout", run_id="RUN-001")
    assert entry["new_repo_sha"] == "abc"
    assert entry["family"] == "pdf"
    assert entry["platform"] == "net"
    assert entry["status"] == "attempted"


def test_append_writes_to_disk(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="abc", sha_source="scout", run_id="RUN-001")
    assert ledger.path.exists()
    lines = ledger.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["new_repo_sha"] == "abc"


def test_history_returns_all_entries_in_order(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001")
    ledger.append(new_repo_sha="sha2", sha_source="scout", run_id="RUN-002")
    ledger.append(new_repo_sha="sha3", sha_source="scout", run_id="RUN-003")
    history = ledger.history()
    assert len(history) == 3
    assert [e["new_repo_sha"] for e in history] == ["sha1", "sha2", "sha3"]


def test_last_accepted_returns_most_recent_accepted_only(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001",
                  status="accepted", accepted_at="2026-07-01T00:00:00Z")
    ledger.append(new_repo_sha="sha2", sha_source="scout", run_id="RUN-002",
                  status="attempted")  # failed run, not accepted
    last = ledger.last_accepted()
    assert last["new_repo_sha"] == "sha1"


def test_last_accepted_none_when_nothing_accepted_yet(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001", status="attempted")
    assert ledger.last_accepted() is None


def test_head_reflects_most_recent_append_regardless_of_status(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001",
                  status="accepted", accepted_at="2026-07-01T00:00:00Z")
    ledger.append(new_repo_sha="sha2", sha_source="scout", run_id="RUN-002", status="attempted")
    head = ledger.head()
    assert head["new_repo_sha"] == "sha2"
    assert head["status"] == "attempted"
    # last_accepted() must NOT be sha2 -- it's only attempted, not accepted.
    assert ledger.last_accepted()["new_repo_sha"] == "sha1"


def test_append_idempotent_when_reaccepting_same_sha(tmp_path):
    """A safe re-run against an unchanged upstream commit must not append a
    duplicate row -- this is the literal idempotency guarantee the plan's
    baseline-tracking contract (§3 point 1) depends on."""
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    e1 = ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001",
                        status="accepted", accepted_at="2026-07-01T00:00:00Z")
    e2 = ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-002",
                        status="accepted", accepted_at="2026-07-02T00:00:00Z")
    assert e1 == e2  # second call is a no-op, returns the existing head unchanged
    assert len(ledger.history()) == 1  # only one row was ever written


def test_append_new_sha_after_accepted_records_prior_sha(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001",
                  status="accepted", accepted_at="2026-07-01T00:00:00Z")
    entry2 = ledger.append(new_repo_sha="sha2", sha_source="scout", run_id="RUN-002",
                            status="accepted", accepted_at="2026-07-02T00:00:00Z")
    assert entry2["prior_repo_sha"] == "sha1"


def test_append_invalid_entry_raises_value_error(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    with pytest.raises(ValueError):
        ledger.append(new_repo_sha="sha1", sha_source="NOT_A_VALID_SOURCE", run_id="RUN-001")
    # And nothing was written on the failed validation.
    assert not ledger.path.exists()


def test_history_empty_for_never_appended_product(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    assert ledger.history() == []
    assert ledger.last_accepted() is None
    assert ledger.head() is None


def test_history_tolerates_torn_last_line(tmp_path):
    """A crashed writer mid-append (e.g. process killed after partial write)
    must not make history() raise -- prior, complete lines must still be
    readable, and the torn line silently skipped."""
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001")
    with open(ledger.path, "a", encoding="utf-8") as f:
        f.write('{"run_id": "RUN-002", "new_repo_sha": "sha2"')  # truncated JSON, no closing brace/newline
    history = ledger.history()
    assert len(history) == 1
    assert history[0]["new_repo_sha"] == "sha1"


def test_concurrent_append_no_corruption_no_lost_writes(tmp_path):
    """Real concurrency test (threading): N threads each append one entry to
    the SAME product's ledger concurrently. The lock must serialize them so
    every single entry survives, none are lost, and the file is never left
    in a corrupted (interleaved) state. This is the actual proof that the
    lock works -- not just that the API exists."""
    ledger_factory = lambda: BaselineLedger("pdf", "net", repo_root=tmp_path)
    n_threads = 12
    errors: list[Exception] = []

    def _worker(i: int) -> None:
        try:
            BaselineLedger("pdf", "net", repo_root=tmp_path).append(
                new_repo_sha=f"sha-{i}", sha_source="scout", run_id=f"RUN-{i:03d}",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent append() calls raised: {errors}"

    history = ledger_factory().history()
    assert len(history) == n_threads, (
        f"expected {n_threads} entries, got {len(history)} -- "
        f"lost writes or corrupted lines under concurrent access"
    )
    shas = {e["new_repo_sha"] for e in history}
    assert shas == {f"sha-{i}" for i in range(n_threads)}, "some entries were lost or duplicated"


def test_lock_timeout_raises_when_lock_held(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger._acquire_lock()  # hold the lock, simulating another process
    try:
        with pytest.raises(LedgerLockTimeout):
            ledger._acquire_lock(timeout=0.2)  # short timeout -- keep the test fast
    finally:
        ledger._release_lock()


def test_stale_lock_is_stolen_after_timeout(tmp_path, monkeypatch):
    """A lock file older than the stale threshold must be stolen, not honored
    forever -- otherwise a crashed process permanently deadlocks this product's
    ledger, which would be strictly worse than having no lock at all."""
    import lib.baseline_ledger as bl_module
    monkeypatch.setattr(bl_module, "_STALE_LOCK_SECONDS", 0.05)
    monkeypatch.setattr(bl_module, "_DEFAULT_LOCK_TIMEOUT", 0.2)

    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.lock_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.lock_path.write_text("99999:0", encoding="utf-8")  # simulate a stale lock
    time.sleep(0.15)  # let it become "stale" per the patched threshold

    entry = ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001")
    assert entry["new_repo_sha"] == "sha1"


def test_lock_released_after_successful_append(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001")
    assert not ledger.lock_path.exists()


def test_merged_dir_override_takes_precedence_over_repo_root(tmp_path):
    """RPR-C-02 integration point: callers that already compute their own
    merged/ path (e.g. promote.py, which uses a `knowledge_root` convention
    rather than repo_root) can point the ledger there directly."""
    custom_dir = tmp_path / "somewhere" / "else" / "merged"
    ledger = BaselineLedger("pdf", "net", merged_dir=custom_dir, repo_root=tmp_path / "unused")
    ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001")
    assert (custom_dir / "baseline_ledger.jsonl").exists()
    assert not (tmp_path / "unused").exists()  # repo_root was ignored, not silently also used


def test_lock_released_after_failed_append(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    with pytest.raises(ValueError):
        ledger.append(new_repo_sha="sha1", sha_source="INVALID", run_id="RUN-001")
    assert not ledger.lock_path.exists()


# --- RC-baseline-tree-identity (readme-refresh-hardening-and-regen-2026-08-30, TC-10) ----------


def test_append_records_repo_tree_sha_when_supplied(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    entry = ledger.append(
        new_repo_sha="sha1", sha_source="scout", run_id="RUN-001",
        status="accepted", accepted_at="2026-08-31T00:00:00Z", repo_tree_sha="tree1",
    )
    assert entry["repo_tree_sha"] == "tree1"
    assert ledger.head()["repo_tree_sha"] == "tree1"


def test_append_repo_tree_sha_defaults_to_none_when_not_supplied():
    # Additive field: existing callers that never pass it must not be forced to.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ledger = BaselineLedger("pdf", "net", repo_root=Path(td))
        entry = ledger.append(new_repo_sha="sha1", sha_source="scout", run_id="RUN-001")
        assert entry["repo_tree_sha"] is None


def test_mark_orphaned_appends_a_new_entry_without_changing_head(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    accepted = ledger.append(
        new_repo_sha="sha1", sha_source="scout", run_id="RUN-001",
        status="accepted", accepted_at="2026-08-31T00:00:00Z", repo_tree_sha="tree1",
    )
    orphan_entry = ledger.mark_orphaned(
        orphaned_sha="sha1", orphan_class="content_identical", run_id="RUN-002",
        detected_at="2026-09-01T00:00:00Z",
    )
    assert orphan_entry["orphaned_sha"] == "sha1"
    assert orphan_entry["orphan_class"] == "content_identical"
    assert orphan_entry["orphan_detected_at"] == "2026-09-01T00:00:00Z"
    assert orphan_entry["sha_source"] == "orphaned-recovered"
    # head() is unchanged -- mark_orphaned is a side-channel fact, not a new current baseline.
    assert ledger.head()["new_repo_sha"] == accepted["new_repo_sha"]
    assert ledger.head()["status"] == "accepted"
    # But it IS visible in full history -- an append-only fact, never lost.
    history = ledger.history()
    assert len(history) == 2
    assert history[-1]["orphan_class"] == "content_identical"


def test_mark_orphaned_rejects_invalid_orphan_class(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    with pytest.raises(ValueError, match="orphan_class"):
        ledger.mark_orphaned(orphaned_sha="sha1", orphan_class="bogus", run_id="RUN-001")


def test_mark_orphaned_content_changed_class(tmp_path):
    ledger = BaselineLedger("pdf", "net", repo_root=tmp_path)
    entry = ledger.mark_orphaned(orphaned_sha="sha1", orphan_class="content_changed", run_id="RUN-001")
    assert entry["orphan_class"] == "content_changed"

"""Tests for scripts/pipeline/lib/advisory_lock.py (ported 2026-08-29)."""
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

import advisory_lock  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402


def test_acquire_and_release_round_trip(tmp_path):
    lock_path = tmp_path / "state.lock"
    lock = FileLock(lock_path)
    lock.acquire()
    assert lock_path.exists()
    lock.release()
    assert not lock_path.exists()


def test_context_manager_round_trip(tmp_path):
    lock_path = tmp_path / "state.lock"
    with FileLock(lock_path):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_second_acquire_times_out_while_first_holds(tmp_path):
    lock_path = tmp_path / "state.lock"
    holder = FileLock(lock_path)
    holder.acquire()
    try:
        waiter = FileLock(lock_path, timeout=0.3, poll=0.05)
        with pytest.raises(LockTimeout):
            waiter.acquire()
    finally:
        holder.release()


def test_release_is_a_noop_if_lock_was_stolen(tmp_path, monkeypatch):
    """The exact bug this module's docstring calls out: if this instance's
    lock was stolen by a waiter, release() must never blindly unlink
    whatever now occupies the path -- that would destroy the NEW holder's
    live lock."""
    lock_path = tmp_path / "state.lock"
    original_holder = FileLock(lock_path)
    original_holder.acquire()

    # Simulate a steal: someone else took the path with a different payload.
    lock_path.write_text("99999:0.0", encoding="utf-8")

    original_holder.release()  # must be a no-op, not destroy the new payload
    assert lock_path.read_text(encoding="utf-8") == "99999:0.0"


def test_release_without_acquire_is_safe():
    lock = FileLock(Path("/nonexistent/does-not-matter.lock"))
    lock.release()  # must not raise


def test_stale_lock_is_stolen_after_timeout(tmp_path, monkeypatch):
    """A lock held by a verifiably-dead or indeterminate process past
    stale_seconds must be stolen, not block forever."""
    lock_path = tmp_path / "state.lock"
    # Write a stale lock payload with an ancient pid and force _pid_alive to
    # report "unknown" (None) so only the mtime-age path can steal it.
    lock_path.write_text("1:0.0", encoding="utf-8")
    import os
    old_time = time.time() - 1000
    os.utime(lock_path, (old_time, old_time))
    monkeypatch.setattr(advisory_lock, "_pid_alive", lambda pid: None)

    waiter = FileLock(lock_path, stale_seconds=1.0, timeout=0.5, poll=0.05)
    waiter.acquire()  # must succeed via the stale-steal path, not time out
    waiter.release()


def test_dead_pid_is_stolen_immediately(tmp_path, monkeypatch):
    lock_path = tmp_path / "state.lock"
    lock_path.write_text("12345:9999999999", encoding="utf-8")  # "fresh" mtime-wise, but dead pid
    monkeypatch.setattr(advisory_lock, "_pid_alive", lambda pid: False)

    waiter = FileLock(lock_path, timeout=2.0, poll=0.05)
    start = time.monotonic()
    waiter.acquire()
    elapsed = time.monotonic() - start
    waiter.release()
    assert elapsed < 1.5  # stolen via liveness probe, not the full stale-timeout wait

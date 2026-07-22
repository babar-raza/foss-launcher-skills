"""Tests for lib/advisory_lock.py (HARDEN-A1).

Covers: basic acquire/release, context manager, contention timeout, mtime-stale
steal, dead-pid immediate steal (the A1 improvement over the RPR-C-01 pattern),
and a real-thread concurrency test asserting no lost updates.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

_LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from advisory_lock import FileLock, LockTimeout, _pid_alive  # noqa: E402


@pytest.fixture()
def lock_path(tmp_path: Path) -> Path:
    return tmp_path / "state.json.lock"


def test_acquire_creates_and_release_removes(lock_path: Path):
    lock = FileLock(lock_path, timeout=2.0)
    lock.acquire()
    assert lock_path.exists()
    payload = lock_path.read_text(encoding="utf-8")
    assert payload.startswith(f"{os.getpid()}:")
    lock.release()
    assert not lock_path.exists()


def test_context_manager(lock_path: Path):
    with FileLock(lock_path, timeout=2.0):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_release_without_acquire_is_noop(lock_path: Path):
    lock = FileLock(lock_path)
    lock.release()  # must not raise
    assert not lock_path.exists()


def test_contention_times_out_against_live_holder(lock_path: Path):
    holder = FileLock(lock_path, timeout=2.0)
    holder.acquire()
    try:
        waiter = FileLock(lock_path, timeout=0.5)
        start = time.monotonic()
        with pytest.raises(LockTimeout):
            waiter.acquire()
        # Should have waited roughly the timeout, not stolen instantly:
        assert time.monotonic() - start >= 0.4
    finally:
        holder.release()


def test_stale_mtime_steal_from_live_pid(lock_path: Path):
    # Simulate a lock held by a live process (our own pid — liveness probe says
    # alive, so the dead-pid fast path must NOT fire) whose lock is ancient.
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(f"{os.getpid()}:{time.time() - 500}", encoding="utf-8")
    old = time.time() - 500
    os.utime(lock_path, (old, old))

    waiter = FileLock(lock_path, timeout=0.5, stale_seconds=120.0)
    waiter.acquire()  # steals after the timeout via the mtime-stale fallback
    assert waiter._held
    waiter.release()


def test_dead_pid_immediate_steal(lock_path: Path):
    # A verifiably-dead holder is stolen well before the stale window (120s)
    # and even before this waiter's own timeout would expire.
    proc = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True, text=True, timeout=30,
    )
    dead_pid = int(proc.stdout.strip())
    # Confirm the probe sees it as dead; if the OS recycled it already, skip.
    if _pid_alive(dead_pid) is not False:
        pytest.skip(f"pid {dead_pid} not verifiably dead on this host")

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(f"{dead_pid}:{time.time()}", encoding="utf-8")

    waiter = FileLock(lock_path, timeout=10.0, stale_seconds=120.0)
    start = time.monotonic()
    waiter.acquire()
    elapsed = time.monotonic() - start
    assert waiter._held
    assert elapsed < 5.0, f"dead-pid steal took {elapsed:.1f}s — fast path did not fire"
    waiter.release()


def test_pid_alive_self():
    assert _pid_alive(os.getpid()) is True


def test_concurrent_writers_no_lost_updates(tmp_path: Path):
    counter_path = tmp_path / "counter.txt"
    counter_path.write_text("0", encoding="utf-8")
    lock_file = tmp_path / "counter.lock"
    increments_per_thread = 25
    thread_count = 4
    errors: list[Exception] = []

    def worker():
        for _ in range(increments_per_thread):
            try:
                with FileLock(lock_file, timeout=30.0):
                    value = int(counter_path.read_text(encoding="utf-8"))
                    counter_path.write_text(str(value + 1), encoding="utf-8")
            except Exception as exc:  # pragma: no cover - failure diagnostics
                errors.append(exc)
                return

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert not errors, f"worker errors: {errors}"
    assert int(counter_path.read_text(encoding="utf-8")) == increments_per_thread * thread_count

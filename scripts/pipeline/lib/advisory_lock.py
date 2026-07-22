"""advisory_lock.py — shared advisory file lock (extracted RPR-C-01 pattern).

CONTRACT: scripts/pipeline/lib/advisory_lock.py
  purpose: One shared, tested lock primitive for every read-modify-write over
           shared mutable state files (session_ledger manifests, skill_context
           ACTIVE.json, project_phase_store state, baseline ledgers). Extracted
           from baseline_ledger.py (RPR-C-01), which proved the pattern; named
           advisory_lock (not filelock) to avoid shadowing the common pip
           "filelock" package should it ever land in the venv.
  improvement over the source pattern (HARDEN-A1, 2026-07-22): the lock file
           payload has always been "pid:timestamp"; this module actually uses
           the pid. A holder that is verifiably dead (tasklist/ps probe) is
           stolen immediately instead of only after the stale-timeout window.
           The mtime-age stale steal remains as the fallback for the
           cannot-determine-liveness case (e.g. pid recycled by an unrelated
           process — a genuine limit of pid-based liveness on any OS).
  concurrency: O_CREAT|O_EXCL creation is the atomic primitive. Stealing is
           guarded by a stat-signature re-check (mtime+size observed at
           examination time must still match at unlink time) to narrow the
           window where two waiters could both steal, or a waiter could unlink
           a lock that just changed hands. Narrowed, not eliminated — advisory
           locking on a plain filesystem cannot fully close that window; this
           is documented, not hidden.
  windows note: liveness probing shells out to `tasklist` (native Windows
           executable, also on PATH inside Git Bash / MSYS2). Probes are rate
           limited (once per second of waiting) because tasklist costs
           ~100-300 ms per call.

Usage::

    from advisory_lock import FileLock, LockTimeout

    with FileLock(state_path.with_suffix(state_path.suffix + ".lock")):
        state = load(state_path)
        mutate(state)
        save(state_path, state)
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

_STALE_LOCK_SECONDS = 120.0
_DEFAULT_TIMEOUT = 10.0
_LOCK_POLL_INTERVAL = 0.05
_LIVENESS_PROBE_INTERVAL = 1.0


class LockTimeout(Exception):
    """Raised when the lock could not be acquired within the timeout."""


def _pid_alive(pid: int) -> bool | None:
    """Best-effort liveness probe. True=alive, False=verifiably dead, None=unknown."""
    if pid <= 0:
        return None
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None
            # tasklist prints "INFO: No tasks are running..." when the pid is absent
            return f" {pid} " in f" {result.stdout} ".replace("\r", " ").replace("\n", " ")
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by someone else
    except Exception:
        return None


class FileLock:
    """Advisory exclusive lock backed by an O_CREAT|O_EXCL sidecar file."""

    def __init__(
        self,
        path: Path | str,
        *,
        stale_seconds: float = _STALE_LOCK_SECONDS,
        timeout: float = _DEFAULT_TIMEOUT,
        poll: float = _LOCK_POLL_INTERVAL,
    ):
        self.path = Path(path)
        self.stale_seconds = stale_seconds
        self.timeout = timeout
        self.poll = poll
        self._held = False
        self._observed_sig: tuple[float, int] | None = None

    # ── internals ────────────────────────────────────────────────────────

    def _examine_holder(self) -> tuple[int | None, float, bool]:
        """Read holder pid, lock age, and existence.

        The stat signature (for guarded steal) is captured independently of the
        pid parse (F7): an empty/torn lock file from a writer killed between
        open and write must still get a signature, or _steal would run blind.
        """
        pid: int | None = None
        age = 0.0
        try:
            st = self.path.stat()
        except OSError:
            self._observed_sig = None
            return pid, age, False
        self._observed_sig = (st.st_mtime, st.st_size)
        age = time.time() - st.st_mtime
        try:
            raw = self.path.read_text(encoding="utf-8", errors="replace")
            pid = int(raw.split(":", 1)[0])
        except (OSError, ValueError):
            pid = None  # unreadable/empty payload — liveness unknown, mtime path governs
        return pid, age, True

    def _steal(self) -> None:
        """Unlink the lock only if it still matches the signature we examined.

        With no observed signature (F7) we never steal blind — the lock either
        vanished (acquire will just retry) or could have changed hands.
        """
        if self._observed_sig is None:
            return
        try:
            st = self.path.stat()
            if (st.st_mtime, st.st_size) != self._observed_sig:
                return  # lock changed hands since we looked — do not steal
            self.path.unlink()
        except OSError:
            pass  # already gone, or another waiter stole it first

    # ── public API ───────────────────────────────────────────────────────

    def acquire(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        next_liveness_probe = 0.0
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, f"{os.getpid()}:{time.time()}".encode("utf-8"))
                finally:
                    os.close(fd)
                self._held = True
                return self
            except FileExistsError:
                now = time.monotonic()
                if now >= next_liveness_probe:
                    next_liveness_probe = now + _LIVENESS_PROBE_INTERVAL
                    pid, _age, exists = self._examine_holder()
                    if not exists:
                        continue  # lock vanished — retry immediately (F7)
                    if pid is not None and _pid_alive(pid) is False:
                        self._steal()
                        continue
                if now >= deadline:
                    _pid, age, exists = self._examine_holder()
                    if not exists:
                        continue  # freed just before the deadline — retry, not timeout (F7)
                    if age > self.stale_seconds:
                        self._steal()
                        continue
                    raise LockTimeout(
                        f"Could not acquire lock {self.path} within {self.timeout}s "
                        f"(held by a live or indeterminate process; age={age:.1f}s)"
                    )
                time.sleep(self.poll)

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            self.path.unlink()
        except OSError:
            pass  # already released/stolen — safe to ignore

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()

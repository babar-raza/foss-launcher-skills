"""knowledge_regen_lock.py — per-product lock over the full knowledge-regen chain.

CONTRACT: scripts/pipeline/lib/knowledge_regen_lock.py
  purpose: FRESH-001 (2026-08-14): the content-refresh state machine (refresh_run.py)
           already locks its own transitions via advisory_lock.FileLock at
           reports/locks/refresh/{family}-{platform}.lock. Knowledge regeneration
           itself (scout -> enrich -> promote -> index, and refresh_knowledge.py's own
           merged/<->merged.bak/ backup-restore around that chain) had NO lock at all --
           two concurrent invocations (manual /knowledge-update, S-90's auto-refresh,
           and now the scheduled bounded-auto-regen path) for the SAME product could
           race on the same merged/merged.bak directories. This module is a thin
           wrapper over the existing, already-tested advisory_lock.FileLock (do not
           reimplement locking primitives) that every chain-invoking entry point uses.
  lock path: knowledge/{family}/{platform}/merged/.regen.lock -- co-located with the
           bundle it guards, same pattern baseline_ledger.py already uses for its own
           lock file next to baseline_ledger.jsonl. Deliberately NOT git-tracked (see
           knowledge_tracking_policy.yaml -- a lock file has no business being tracked).
  payload: extends advisory_lock's existing "pid:timestamp" convention to
           "pid:timestamp:owner" -- backward compatible, since advisory_lock's own pid
           parse only reads the first ':'-split token. `owner` gives operator
           visibility into who holds the lock ("manual", "refresh-product",
           "scheduled-sweep", etc.) via inspect_lock().
  acquisition order (documented to prevent deadlock): this lock is always acquired
           BEFORE refresh_run.py's own content-refresh lock, never the reverse. They
           guard different resources (knowledge facts vs. generated content) and may
           legitimately be held together by a chain that does both, but only in this
           fixed order.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Self-register this file's own lib/ directory so bare sibling imports resolve
# regardless of what sys.path the caller set up (production scripts are invoked
# with only PYTHONPATH=scripts/pipeline set, which does not add lib/ itself).
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from advisory_lock import FileLock, LockTimeout  # noqa: F401,E402 (re-exported for callers)

_DEFAULT_TIMEOUT = 10.0


def regen_lock_path(family: str, platform: str, *, knowledge_root: "Path | str | None" = None) -> Path:
    root = Path(knowledge_root) if knowledge_root is not None else Path("knowledge")
    return root / family / platform / "merged" / ".regen.lock"


class _OwnedFileLock(FileLock):
    """FileLock whose payload carries an owner label, for operator visibility."""

    def __init__(self, path: Path, *, owner: str, timeout: float = _DEFAULT_TIMEOUT, **kwargs):
        super().__init__(path, timeout=timeout, **kwargs)
        self._owner = owner

    def acquire(self) -> "_OwnedFileLock":
        # Reuse FileLock.acquire()'s full retry/steal machinery, then append the
        # owner label to the payload it already wrote -- avoids duplicating that
        # logic here. A second, quick O_CREAT|O_EXCL-free rewrite of the same file
        # we just atomically created is safe: we are the confirmed holder at this
        # point (acquire() only returns after winning the race).
        super().acquire()
        try:
            payload_with_owner = f"{self._own_payload}:{self._owner}"
            self.path.write_text(payload_with_owner, encoding="utf-8")
            # release()'s compare-then-unlink safety check compares the CURRENT file
            # content against self._own_payload -- must be updated in lockstep with
            # the rewrite above, or release() would see a "changed" payload and
            # (correctly, by its own logic) refuse to unlink a lock we still hold.
            self._own_payload = payload_with_owner
        except OSError:
            pass  # best-effort — losing the owner label never invalidates the lock
        return self


def acquire_regen_lock(
    family: str,
    platform: str,
    *,
    owner: str,
    knowledge_root: "Path | str | None" = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> _OwnedFileLock:
    """Return an (unacquired) lock object for the full knowledge-regen chain of one
    product. Use as a context manager:

        with acquire_regen_lock(family, platform, owner="manual"):
            ... run scout -> enrich -> promote -> index ...

    Held for the WHOLE chain, not per-step, by every one of: manual /knowledge-update
    (refresh_knowledge.py), S-90's auto-refresh (publish_readiness_review_run.py), and
    the scheduled bounded-auto-regen path -- all three import this function rather
    than constructing their own lock, so correctness is enforced by refactoring, not
    convention.
    """
    path = regen_lock_path(family, platform, knowledge_root=knowledge_root)
    return _OwnedFileLock(path, owner=owner, timeout=timeout)


def inspect_lock(family: str, platform: str, *, knowledge_root: "Path | str | None" = None) -> "dict | None":
    """Read the current lock holder's pid/timestamp/owner without acquiring anything.

    Returns None if no lock file exists. Best-effort -- a torn/unreadable payload
    (e.g. a lock file caught mid-write) yields whatever fields could be parsed.
    """
    path = regen_lock_path(family, platform, knowledge_root=knowledge_root)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parts = raw.split(":", 2)
    result: dict = {"raw": raw}
    if len(parts) >= 1:
        try:
            result["pid"] = int(parts[0])
        except ValueError:
            result["pid"] = None
    if len(parts) >= 2:
        try:
            result["acquired_at"] = float(parts[1])
            result["age_seconds"] = time.time() - result["acquired_at"]
        except ValueError:
            result["acquired_at"] = None
    if len(parts) >= 3:
        result["owner"] = parts[2]
    return result

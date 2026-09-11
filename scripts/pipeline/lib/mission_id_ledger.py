"""mission_id_ledger.py — ST-157: append-only, cross-track mission-ID ledger.

CONTRACT: scripts/pipeline/lib/mission_id_ledger.py
  purpose: Replace "grep plans/master-plan.md, .supervisor/state/, reports/plan_state/,
           and docs/readme-refresh/plan-system-forensic-reconciliation.md's own table,
           then pick highest-seen-number + 1 by eye" (the process backlog/inbox.md's
           ST-157 documents as having already produced a confirmed duplicate --
           MT018 issued to two unrelated missions (both rows still present in
           plans/master-plan.md, cited by mission_id rather than a line number
           since that file's row count grows over time -- ST-194 has 6 more
           historical instances of this same class) -- and a second, entirely
           uncoordinated MT0NN track run by /readme-refresh,
           independently reaching MT056) with a single, shared, lock-protected
           counter. Modeled directly on baseline_ledger.py's proven append-only-
           ledger shape; reuses advisory_lock.FileLock rather than reimplementing it.
  scope: the numeric MT0NN track ONLY. Many mission ids in this repo are free-text
           slugs with no number at all (e.g. backlink-governance-redesign) -- this
           module does not, and is not intended to, prevent two sessions from
           independently choosing the same descriptive slug. It closes the specific,
           confirmed defect class: two sessions racing for the same MT0NN integer,
           or two tracks independently reusing one because neither is aware of the
           other's counter.
  concurrency: allocate() re-reads history() FRESH under the lock -- never a cached
           snapshot -- so two concurrent callers can never receive the same number.
           This is the direct fix for the MT018 double-mint.
  durability: unlike baseline_ledger.py (deliberately local-only under gitignored
           knowledge/, because it has a separate durable fallback), this ledger has
           no fallback -- it lives at scripts/pipeline/config/mission-ids.jsonl,
           tracked and committed, beside this repo's other shared script registry
           (registry.yaml). NOT under docs/registries/ -- that prefix is in
           path_guard.py's FORBIDDEN_PREFIXES (governance child-doc protection).
  seed() vs allocate(): seed() idempotently records a HISTORICAL id discovered by
           backfill (a no-op if the id is already present); allocate() mints a NEW
           id. Backfill must seed every historical id from every known track before
           allocate() is used for the first live mission, or the first allocate()
           call could re-mint an already-used number that simply wasn't in the
           ledger yet.

Usage::

    from mission_id_ledger import MissionIdLedger

    ledger = MissionIdLedger()
    ledger.seed(number=18, mission_id="MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE",
                track="main", source="git-history-backfill")
    new_id = ledger.allocate(track="main", slug="EXAMPLE-MISSION")
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root

from advisory_lock import FileLock, LockTimeout  # noqa: E402

_STALE_LOCK_SECONDS = 120.0
_DEFAULT_LOCK_TIMEOUT = 10.0
_LOCK_POLL_INTERVAL = 0.05


class MissionIdLedgerLockTimeout(Exception):
    """Raised when the ledger's exclusive lock could not be acquired within the timeout."""


class MissionIdLedger:
    """Append-only, lock-protected registry of every numeric MT0NN mission id
    ever allocated, across every numbering track."""

    def __init__(self, repo_root: Path | str | None = None):
        root = Path(repo_root) if repo_root is not None else _REPO_ROOT
        self.repo_root = root
        self.path = root / "scripts" / "pipeline" / "config" / "mission-ids.jsonl"
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    # ── Locking ──────────────────────────────────────────────────────────

    def _acquire_lock(self, timeout: float | None = None) -> FileLock:
        lock = FileLock(
            self.lock_path,
            stale_seconds=_STALE_LOCK_SECONDS,
            timeout=timeout if timeout is not None else _DEFAULT_LOCK_TIMEOUT,
            poll=_LOCK_POLL_INTERVAL,
        )
        try:
            lock.acquire()
        except LockTimeout as exc:
            raise MissionIdLedgerLockTimeout(str(exc)) from exc
        return lock

    # ── Reads (safe without the lock — append-only file, worst case is a
    #    torn read of the very last line mid-write, never corruption of prior
    #    lines) ──────────────────────────────────────────────────────────

    def history(self) -> list[dict[str, Any]]:
        """Return every entry ever appended, in append order. Tolerates a
        torn last line from a crashed writer -- never raises on read."""
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def highest_number(self) -> int:
        """Max `number` field across every entry; 0 if the ledger is empty."""
        numbers = [e["number"] for e in self.history() if isinstance(e.get("number"), int)]
        return max(numbers, default=0)

    def has_id(self, mission_id: str) -> bool:
        return any(e.get("mission_id") == mission_id for e in self.history())

    # ── Writes ───────────────────────────────────────────────────────────

    def _append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def seed(
        self,
        *,
        number: int,
        mission_id: str,
        track: str,
        source: str,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Idempotent backfill append. Returns None (no write) if mission_id
        is already present -- safe to re-run backfill any number of times."""
        lock = self._acquire_lock()
        try:
            if self.has_id(mission_id):
                return None
            entry: dict[str, Any] = {
                "number": number,
                "mission_id": mission_id,
                "track": track,
                "slug": None,
                "allocated_at": None,
                "session_id": session_id,
                "source": source,
            }
            self._append(entry)
            return entry
        finally:
            lock.release()

    def allocate(
        self,
        *,
        track: str,
        slug: str,
        date: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Atomically claim the next free MT0NN number and return the new id."""
        lock = self._acquire_lock()
        try:
            number = self.highest_number() + 1
            resolved_date = date or datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            mission_id = f"MT{number:03d}-{resolved_date}-{slug}"
            entry: dict[str, Any] = {
                "number": number,
                "mission_id": mission_id,
                "track": track,
                "slug": slug,
                "allocated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "session_id": session_id,
                "source": "allocate",
            }
            self._append(entry)
            return mission_id
        finally:
            lock.release()

"""
taskcard_store.py -- FileLock-guarded, row-level-CAS-protected reader/writer
for reports/plan_state/{mission_id}/taskcards.jsonl.

Ported near-verbatim from aspose.org (2026-08-29 sync, TASK_BACKLOG.md
SYNC-1). Source has zero content/product coupling -- pure task/mission
tracking (task_id, mission_id, status, timestamps, evidence). Directly
closes the gap this repo's own docs/governance/planning-methodology.md
names explicitly: "No concurrency-safe, compare-and-swap ledger... If this
repo starts being worked by multiple concurrent agent sessions... that gap
becomes real."

CONTRACT: scripts/pipeline/lib/taskcard_store.py
  purpose: Before this module, nothing in a repo like this had a real,
           lock-protected way to record task status -- every update would
           be an ad hoc file edit, with no protection against two sessions
           racing to advance the same task_id.
  inputs:  none (pure reader/writer over its own ledger file)
  outputs: reports/plan_state/{mission_id}/taskcards.jsonl (append-only)
  idempotent: append() is not idempotent (each call adds one row); read
           methods are pure and side-effect free.
  concurrency: two layers, each matched to what it protects.
             1. File-level: advisory_lock.FileLock serializes concurrent
                writers to the SAME mission's file.
             2. Row-level: update_taskcard_status() is a compare-and-swap,
                not a blind append -- it reloads the file UNDER the lock,
                checks the task's actual current (latest-row) status
                against the caller's expected_status, and refuses
                (TaskcardCASError) if another session already advanced
                that exact row.
  schema: validated via schema_validators.validate_taskcard_record on
           every write (append(), update_taskcard_status(),
           pause_taskcard()) -- a malformed or under-evidenced row is
           refused before it ever reaches disk.
  read semantics: append-only, LAST occurrence of a task_id wins. Callers
           must never rewrite an existing line to change a task's status;
           append a new row instead. read_history() tolerates a torn last
           line from a crashed writer (skips it, never raises) as an
           append-only file's worst-case corruption is confined to its
           final incomplete line.

Usage::

    from taskcard_store import TaskcardStore, TaskcardCASError

    store = TaskcardStore("SYNC-2026-08-29")
    store.append({
        "task_id": "SYNC-1", "mission_id": store.mission_id,
        "status": "TODO", "recorded_at": "2026-08-29T00:00:00Z",
        "recorded_by": "sess-a", "evidence_refs": [],
    })
    store.update_taskcard_status(
        "SYNC-1", expected_status="TODO", new_status="IN_PROGRESS",
        recorded_by="sess-a",
    )
    # A second session racing against the same row with a stale
    # expected_status gets a named refusal, not a silent overwrite:
    store.update_taskcard_status(
        "SYNC-1", expected_status="TODO", new_status="IN_PROGRESS",
        recorded_by="sess-b",
    )  # raises TaskcardCASError
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

from schema_validators import validate_taskcard_record  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402

_STALE_LOCK_SECONDS = 120.0
_DEFAULT_LOCK_TIMEOUT = 10.0
_LOCK_POLL_INTERVAL = 0.05


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


class TaskcardLockTimeout(Exception):
    """Raised when a mission's taskcards.jsonl lock could not be acquired
    within the timeout."""


class TaskcardNotFoundError(Exception):
    """Raised when update_taskcard_status targets a task_id with no existing row."""


class TaskcardCASError(Exception):
    """Raised when update_taskcard_status's expected_status does not match
    the task's actual current (latest-row) status -- another session already
    advanced or claimed it. Not a corruption; a named, actionable refusal."""

    def __init__(self, task_id: str, expected: str, actual: str, recorded_by: "str | None"):
        self.task_id = task_id
        self.expected = expected
        self.actual = actual
        self.recorded_by = recorded_by
        super().__init__(
            f"task_id={task_id!r}: expected status {expected!r} but current status is "
            f"{actual!r} (last recorded by {recorded_by!r}) -- another session may have "
            f"already advanced this task; re-read its current state before retrying"
        )


class TaskcardStore:
    """Append-only, lock-guarded, row-level-CAS-protected taskcards.jsonl for
    one mission."""

    def __init__(
        self,
        mission_id: str,
        *,
        repo_root: "Path | str | None" = None,
        plan_state_dir: "Path | str | None" = None,
    ):
        """
        Args:
            repo_root: repo root; the store lives at
                {repo_root}/reports/plan_state/{mission_id}/. Ignored if
                plan_state_dir is given.
            plan_state_dir: explicit override for the mission's plan_state
                directory -- takes precedence over repo_root.
        """
        self.mission_id = mission_id
        if plan_state_dir is not None:
            resolved_dir = Path(plan_state_dir)
            self.repo_root = None
        else:
            self.repo_root = Path(repo_root) if repo_root is not None else _REPO_ROOT
            resolved_dir = self.repo_root / "reports" / "plan_state" / mission_id
        self.path = resolved_dir / "taskcards.jsonl"
        self.lock_path = resolved_dir / "taskcards.jsonl.lock"
        self._active_lock: "FileLock | None" = None

    def _acquire_lock(self, timeout: "float | None" = None) -> None:
        lock = FileLock(
            self.lock_path,
            stale_seconds=_STALE_LOCK_SECONDS,
            timeout=timeout if timeout is not None else _DEFAULT_LOCK_TIMEOUT,
            poll=_LOCK_POLL_INTERVAL,
        )
        try:
            lock.acquire()
        except LockTimeout as exc:
            raise TaskcardLockTimeout(str(exc)) from exc
        self._active_lock = lock

    def _release_lock(self) -> None:
        lock = self._active_lock
        if lock is not None:
            self._active_lock = None
            lock.release()
            return
        try:
            self.lock_path.unlink()
        except OSError:
            pass

    def read_history(self) -> "list[dict[str, Any]]":
        """Return every row ever appended, in append order. Tolerates a torn
        last line from a crashed writer (skipped, never raises)."""
        if not self.path.exists():
            return []
        rows: "list[dict[str, Any]]" = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def read_latest(self) -> "dict[str, dict[str, Any]]":
        """task_id -> its latest row (append-only: last occurrence wins)."""
        latest: "dict[str, dict[str, Any]]" = {}
        for row in self.read_history():
            tid = row.get("task_id")
            if tid:
                latest[tid] = row
        return latest

    def get(self, task_id: str) -> "dict[str, Any] | None":
        """Return the latest row for one task_id, or None if it has never
        been recorded."""
        return self.read_latest().get(task_id)

    def append(self, record: "dict[str, Any]") -> "dict[str, Any]":
        """Append one schema-validated row. Never rewrites existing lines --
        this store is append-only; read_latest()'s last-occurrence-wins
        semantics are what makes a later status authoritative, not in-place
        mutation.

        mission_id is auto-filled from this store if absent from record; a
        record whose own mission_id disagrees with this store's is rejected.

        Raises ValueError if the record fails schema validation,
        TaskcardLockTimeout if the mission's lock cannot be acquired within
        the timeout.
        """
        record = dict(record)
        record.setdefault("mission_id", self.mission_id)
        if record["mission_id"] != self.mission_id:
            raise ValueError(
                f"record mission_id {record['mission_id']!r} does not match "
                f"this store's mission_id {self.mission_id!r}"
            )
        errors = validate_taskcard_record(record)
        if errors:
            raise ValueError(f"invalid taskcard record, refusing to write: {errors}")

        self._acquire_lock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return record
        finally:
            self._release_lock()

    def update_taskcard_status(
        self,
        task_id: str,
        *,
        expected_status: str,
        new_status: str,
        recorded_by: str,
        recorded_at: "str | None" = None,
        evidence_refs: "list[str] | None" = None,
        **extra_fields: Any,
    ) -> "dict[str, Any]":
        """Row-level compare-and-swap: appends a new row advancing task_id
        from expected_status to new_status, carrying forward every other
        field from the task's current row unless overridden via extra_fields.

        Refuses (raises, appends nothing) if the task's ACTUAL current
        status -- reloaded fresh under the lock, not from a caller's
        possibly-stale snapshot -- does not match expected_status.

        Raises TaskcardNotFoundError if task_id has no existing row at all
        (use append() to create the first row for a new task).
        """
        self._acquire_lock()
        try:
            current = self.read_latest()
            existing = current.get(task_id)
            if existing is None:
                raise TaskcardNotFoundError(
                    f"no existing row for task_id={task_id!r} in {self.path} "
                    f"-- use append() to create it first"
                )
            actual_status = existing.get("status")
            if actual_status != expected_status:
                raise TaskcardCASError(
                    task_id, expected_status, actual_status, existing.get("recorded_by"),
                )

            record = dict(existing)
            record["status"] = new_status
            record["recorded_at"] = recorded_at or _now_iso()
            record["recorded_by"] = recorded_by
            record["evidence_refs"] = (
                evidence_refs if evidence_refs is not None else existing.get("evidence_refs", [])
            )
            record.update(extra_fields)

            errors = validate_taskcard_record(record)
            if errors:
                raise ValueError(f"invalid taskcard record, refusing to write: {errors}")

            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return record
        finally:
            self._release_lock()

    def pause_taskcard(
        self,
        task_id: str,
        *,
        reason: str,
        recorded_by: str,
        title: "str | None" = None,
        recorded_at: "str | None" = None,
        create_if_missing: bool = True,
    ) -> "dict[str, Any]":
        """Cheap, near-zero-friction way to durably record "this step is
        being deliberately set aside" at the moment of a context switch --
        the eager-capture counterpart to the CAS-guarded
        update_taskcard_status().

        Unlike update_taskcard_status(), the caller does not need to know
        the task's current status first: any existing status may transition
        to PAUSED in one call.

        If task_id has no row yet and create_if_missing is True (the
        default), creates the first row directly at PAUSED -- this lets a
        caller register "I'm deferring this" for a step that was never
        given a taskcard at all, without first performing full mission setup.

        Raises TaskcardNotFoundError if create_if_missing is False and no
        row exists yet. Raises ValueError (ultimately from
        validate_taskcard_record) if reason is empty.
        """
        self._acquire_lock()
        try:
            current = self.read_latest()
            existing = current.get(task_id)
            ts = recorded_at or _now_iso()
            if existing is None:
                if not create_if_missing:
                    raise TaskcardNotFoundError(
                        f"no existing row for task_id={task_id!r} in {self.path} "
                        f"and create_if_missing=False"
                    )
                record2: "dict[str, Any]" = {
                    "task_id": task_id,
                    "mission_id": self.mission_id,
                    "status": "PAUSED",
                    "pause_reason": reason,
                    "recorded_at": ts,
                    "recorded_by": recorded_by,
                    "evidence_refs": [],
                }
                if title is not None:
                    record2["title"] = title
            else:
                record2 = dict(existing)
                record2["status"] = "PAUSED"
                record2["pause_reason"] = reason
                record2["recorded_at"] = ts
                record2["recorded_by"] = recorded_by
                if title is not None:
                    record2["title"] = title

            errors = validate_taskcard_record(record2)
            if errors:
                raise ValueError(f"invalid taskcard record, refusing to write: {errors}")

            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record2, ensure_ascii=False) + "\n")
            return record2
        finally:
            self._release_lock()

"""reconciliation_store.py — PKGINSTALL-RECONCILIATION-STORE.

FileLock-guarded, append-only reader/writer for
reports/package-reconciliation/inventory.jsonl -- the durable, per-page
state-tracking artifact governing plan section R.3.1 introduces to close a
real, root-caused structural weakness: no state currently persists between
detection (package_install_literal.py, install_recipe.py, the recurring
sweep) and remediation (the migrators, locale_patch.py) anywhere in this
pipeline. Every session re-derives scope from scratch, which is the primary
reason 16 completed ST-054 taskcards produced only ~68 of ~6,522 real fixes.
This store is the resumable work queue future sessions and automation read
instead of re-discovering scope.

Modeled directly on taskcard_store.py's own locking/append discipline
(advisory_lock.FileLock, append-only + last-occurrence-wins read semantics,
schema-validate-before-write) but BATCH-oriented: a single sweep run appends
~20k rows at once, so append_batch() acquires the lock exactly once per
call rather than once per row (taskcard_store.append() is deliberately
one-row-at-a-time -- a different usage shape, individual human/agent-paced
status transitions, not a bulk sweep).

Deliberately placed under reports/, never data/package_registry.json -- see
schema_validators.validate_reconciliation_record()'s own docstring for why.

Schema: scripts/pipeline/lib/schema_validators.validate_reconciliation_record()
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from advisory_lock import FileLock, LockTimeout  # noqa: E402
from schema_validators import validate_reconciliation_record  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]

_STALE_LOCK_SECONDS = 120.0
_DEFAULT_LOCK_TIMEOUT = 30.0  # a ~20k-row batch write can legitimately take longer than a single-row taskcard append
_LOCK_POLL_INTERVAL = 0.05


class ReconciliationStoreLockTimeout(Exception):
    pass


class ReconciliationStore:
    """Append-only, lock-guarded reconciliation inventory for the whole
    portfolio (not scoped per-mission, unlike TaskcardStore -- every sweep
    run and every migrator/locale-patch/block-updater consumer shares one
    inventory)."""

    def __init__(self, *, repo_root: "Path | str | None" = None):
        self.repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
        self._dir = self.repo_root / "reports" / "package-reconciliation"
        self.path = self._dir / "inventory.jsonl"
        self.lock_path = self._dir / "inventory.jsonl.lock"
        self._active_lock: "FileLock | None" = None

    # ── Locking ──────────────────────────────────────────────────────────

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
            raise ReconciliationStoreLockTimeout(str(exc)) from exc
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
            pass  # already released or never acquired -- safe to ignore

    # ── Reads (safe without the lock -- append-only file; worst case is a
    #    torn read of the very last line mid-write, never corruption of
    #    prior lines) ──────────────────────────────────────────────────────

    def read_history(self) -> list[dict[str, Any]]:
        """Return every row ever appended, in append order. Tolerates a torn
        last line from a crashed/interrupted writer (skipped, never raises)."""
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def read_latest(self) -> dict[str, dict[str, Any]]:
        """path -> its latest row (append-only: last occurrence wins). A path
        that appeared in an older sweep_run_id but not the most recent sweep
        (e.g. the file was deleted, or the sweep's own scope narrowed) still
        shows its last-known state -- callers that need "is this file still
        eligible today" should cross-check sweep_run_id against the most
        recent run they care about, not assume every row reflects today."""
        latest: dict[str, dict[str, Any]] = {}
        for row in self.read_history():
            path = row.get("path")
            if path:
                latest[path] = row
        return latest

    def read_latest_for_product(self, family: str, platform: str) -> dict[str, dict[str, Any]]:
        """Subset of read_latest() for one (family, platform) -- the shape
        most consumers (change-budget history, locale-patch readiness gate,
        content-healing-status reconciliation) actually need."""
        return {
            path: row for path, row in self.read_latest().items()
            if row.get("family") == family and row.get("platform") == platform
        }

    # ── Writes ───────────────────────────────────────────────────────────

    def append_batch(self, records: list[dict[str, Any]]) -> int:
        """Schema-validate every record, then append them all under ONE lock
        acquisition (unlike TaskcardStore.append(), which is one row at a
        time by design for a different usage shape -- see module docstring).

        Raises ValueError (validation failure -- nothing is written, not even
        the valid rows, so a partially-bad batch never partially lands) or
        ReconciliationStoreLockTimeout. Returns the number of rows written.
        """
        if not records:
            return 0

        all_errors: list[str] = []
        for i, record in enumerate(records):
            errors = validate_reconciliation_record(record)
            if errors:
                all_errors.append(f"record[{i}] ({record.get('path')!r}): {errors}")
        if all_errors:
            raise ValueError(
                f"refusing to write batch of {len(records)}: {len(all_errors)} invalid record(s): "
                + "; ".join(all_errors[:10])
                + (" ... (truncated)" if len(all_errors) > 10 else "")
            )

        self._acquire_lock()
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return len(records)
        finally:
            self._release_lock()

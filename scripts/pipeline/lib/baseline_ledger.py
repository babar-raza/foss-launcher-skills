"""
baseline_ledger.py — RPR-C-01: append-only baseline SHA history per product.

CONTRACT: scripts/pipeline/lib/baseline_ledger.py
  purpose: Replace the single mutable model.yaml.repo_sha scalar (destroyed on every
           promote.py full-dict rewrite — see RPR-C-02) with an append-only,
           schema-validated, concurrency-safe local ledger. This is the first
           concurrency-safe write primitive anywhere in this pipeline (plan §2.5 SW-1:
           a repo-wide grep found zero lock/lease mechanisms before this file existed —
           including in skill_context.py, the governance tool meant to prevent exactly
           this class of conflict).
  durability correction (RPR-J-04, session 5): this ledger lives under knowledge/,
           which is entirely gitignored (.gitignore:20, /knowledge). It is therefore a
           fast, concurrency-safe LOCAL CACHE — real and valuable within one checkout,
           where it correctly serializes concurrent writers and preserves full history
           that a bare scalar would destroy — but it does NOT survive a fresh clone and
           is not itself the durable source of truth. The one baseline source that is
           git-durable is evidence.model_sha, already committed on every generated
           content page's frontmatter; baseline_resolver.py's resolve_baseline_sha()
           falls back to sampling that field when this ledger and the legacy model.yaml
           scalar are both unavailable (fresh clone, or a product never migrated).
  inputs:  none (pure writer/reader over its own ledger file)
  outputs: knowledge/{family}/{platform}/merged/baseline_ledger.jsonl (append-only)
           knowledge/{family}/{platform}/merged/baseline_ledger_head.json (O(1) head cache)
  idempotent: yes — append() is a no-op (returns the existing head unchanged) when the
           requested new_repo_sha already matches an ACCEPTED head entry.
  concurrency: a real, working exclusive lock (create-with-O_EXCL sidecar file, poll with
           backoff, stale-lock steal after a timeout) serializes concurrent append() calls
           against the SAME product's ledger. This does not solve concurrency repo-wide
           (that is explicitly out of scope — see plan §14's honest limits) — it solves it
           for this one, specific, previously-unprotected write path.

Usage::

    from baseline_ledger import BaselineLedger

    ledger = BaselineLedger("pdf", "net")
    entry = ledger.append(
        new_repo_sha="abc123", sha_source="scout", run_id="RUN-001",
        status="accepted", accepted_at="2026-07-16T00:00:00Z",
    )
    ledger.last_accepted()   # -> most recent status="accepted" entry, or None
    ledger.history()         # -> full ordered list of every entry ever appended
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root

from schema_validators import validate_baseline_ledger_entry, ValidationError  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402

_STALE_LOCK_SECONDS = 120.0  # a lock older than this is assumed to be held by a crashed process
_DEFAULT_LOCK_TIMEOUT = 10.0
_LOCK_POLL_INTERVAL = 0.05


class LedgerLockTimeout(Exception):
    """Raised when a ledger's exclusive lock could not be acquired within the timeout."""


class BaselineLedger:
    """Append-only baseline SHA ledger for one product (family/platform)."""

    def __init__(
        self,
        family: str,
        platform: str,
        *,
        repo_root: Path | str | None = None,
        merged_dir: Path | str | None = None,
    ):
        """
        Args:
            repo_root: repo root; the ledger lives at
                {repo_root}/knowledge/{family}/{platform}/merged/. Ignored if merged_dir is given.
            merged_dir: explicit override for the merged/ directory, for callers (e.g. promote.py)
                that already compute this exact path under a knowledge_root convention that
                doesn't necessarily nest under a single repo_root — takes precedence over repo_root.
        """
        self.family = family
        self.platform = platform
        if merged_dir is not None:
            resolved_merged_dir = Path(merged_dir)
            self.repo_root = None
        else:
            self.repo_root = Path(repo_root) if repo_root is not None else _REPO_ROOT
            resolved_merged_dir = self.repo_root / "knowledge" / family / platform / "merged"
        self.path = resolved_merged_dir / "baseline_ledger.jsonl"
        self.head_path = resolved_merged_dir / "baseline_ledger_head.json"
        self.lock_path = resolved_merged_dir / "baseline_ledger.jsonl.lock"

    # ── Locking ──────────────────────────────────────────────────────────

    def _acquire_lock(self, timeout: float | None = None) -> None:
        # HARDEN-A1: delegates to the shared advisory_lock.FileLock (extracted from
        # this file's original RPR-C-01 loop, plus pid-liveness fast steal). Module
        # globals are read at call time so tests that monkeypatch them still work.
        lock = FileLock(
            self.lock_path,
            stale_seconds=_STALE_LOCK_SECONDS,
            timeout=timeout if timeout is not None else _DEFAULT_LOCK_TIMEOUT,
            poll=_LOCK_POLL_INTERVAL,
        )
        try:
            lock.acquire()
        except LockTimeout as exc:
            raise LedgerLockTimeout(str(exc)) from exc
        self._active_lock = lock

    def _release_lock(self) -> None:
        lock = getattr(self, "_active_lock", None)
        if lock is not None:
            self._active_lock = None
            lock.release()
            return
        try:
            self.lock_path.unlink()
        except OSError:
            pass  # already released or never acquired — safe to ignore

    # ── Reads (safe to call without the lock — append-only file, worst case is a
    #    torn read of the very last line mid-write, never corruption of prior lines) ──

    def history(self) -> list[dict[str, Any]]:
        """Return every entry ever appended, in append order."""
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
                continue  # tolerate a torn last line from a crashed writer; never raise on read
        return entries

    def last_accepted(self) -> dict[str, Any] | None:
        """Return the most recent status='accepted' entry, or None if none exists yet."""
        for entry in reversed(self.history()):
            if entry.get("status") == "accepted":
                return entry
        return None

    def head(self) -> dict[str, Any] | None:
        """O(1) read of the cached head (may be ahead of last_accepted() if the most
        recent append was 'attempted', not yet 'accepted')."""
        if not self.head_path.exists():
            return None
        try:
            return json.loads(self.head_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    # ── Write ────────────────────────────────────────────────────────────

    def append(
        self,
        *,
        new_repo_sha: str,
        sha_source: str,
        run_id: str,
        status: str = "attempted",
        prior_repo_sha: str | None = None,
        accepted_at: str | None = None,
        orphaned_sha: str | None = None,
        attempt_started_at: str | None = None,
    ) -> dict[str, Any]:
        """Append one schema-validated entry. Idempotent: a no-op if new_repo_sha
        already matches the current ACCEPTED head (returns that head unchanged,
        appends nothing new) — prevents duplicate rows when a refresh is safely
        re-run against an unchanged upstream commit.

        Raises ValueError if the constructed entry fails schema validation, and
        LedgerLockTimeout if the per-product lock cannot be acquired.
        """
        self._acquire_lock()
        try:
            current_head = self.head()
            if (
                current_head
                and current_head.get("status") == "accepted"
                and current_head.get("new_repo_sha") == new_repo_sha
                and status == "accepted"
            ):
                return current_head

            resolved_prior = prior_repo_sha
            if resolved_prior is None and current_head is not None:
                resolved_prior = current_head.get("new_repo_sha")

            entry: dict[str, Any] = {
                "run_id": run_id,
                "family": self.family,
                "platform": self.platform,
                "prior_repo_sha": resolved_prior,
                "new_repo_sha": new_repo_sha,
                "sha_source": sha_source,
                "orphaned_sha": orphaned_sha,
                "attempt_started_at": attempt_started_at or _now_iso(),
                "accepted_at": accepted_at,
                "superseded_by": None,
                "status": status,
            }

            errors = validate_baseline_ledger_entry(entry)
            if errors:
                raise ValueError(f"invalid baseline ledger entry, refusing to write: {errors}")

            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

            self.head_path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
            return entry
        finally:
            self._release_lock()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

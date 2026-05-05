"""harvest_ledger.py — Harvest ledger CRUD for report-to-backlog tracking.

Manages ``reports/harvest-state/ledger.json`` — the source of truth for which
report items have been harvested into the backlog.  Prevents duplicates,
enables re-harvest on report changes, and tracks failures.

Usage (CLI):
  # Show ledger status summary
  python scripts/pipeline/harvest_ledger.py status

  # Retry all failed entries (reset status to 'review')
  python scripts/pipeline/harvest_ledger.py retry-failed

  # Waive a report so it is never harvested
  python scripts/pipeline/harvest_ledger.py waive reports/eval/some-report.json --reason "not relevant"

  # DANGEROUS: clear the entire ledger
  python scripts/pipeline/harvest_ledger.py reset

Usage (Python import):
  from harvest_ledger import HarvestLedger

  ledger = HarvestLedger()
  run_id = ledger.start_run("manual")
  entry = ledger.record_item(
      item_hash="abcdef0123456789", report_path="reports/eval/foo.json",
      report_sha256="deadbeef...", section_key="not_completed",
      title="Missing API coverage", raw_text="...", confidence=0.85,
      item_type="gap", suggested_category="AA", suggested_priority="P2",
      status="harvested", source_line=42, harvest_run_id=run_id,
  )
  ledger.end_run(run_id, {"reports_scanned": 1, "items_extracted": 1,
                           "items_new": 1, "items_duplicate": 0,
                           "items_review": 0, "items_failed": 0})
  ledger.save()

Exit codes:
  0  Success
  1  Error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

# ---------------------------------------------------------------------------
# Module-level paths (reconfigurable via configure())
# ---------------------------------------------------------------------------

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_REPO_ROOT = _DEFAULT_REPO_ROOT
_LEDGER_DIR = _REPO_ROOT / "reports" / "harvest-state"
_LEDGER_PATH = _LEDGER_DIR / "ledger.json"


def configure(
    repo_root: Path | None = None,
    ledger_dir: Path | None = None,
) -> None:
    """Reconfigure module-level paths for testing or alternative layouts.

    - Called with no arguments: resets to built-in defaults.
    - repo_root only: derives ledger_dir as ``repo_root / "reports" / "harvest-state"``.
    - Both provided: uses them directly.
    """
    global _REPO_ROOT, _LEDGER_DIR, _LEDGER_PATH

    _REPO_ROOT = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT

    if ledger_dir is not None:
        _LEDGER_DIR = ledger_dir
    else:
        _LEDGER_DIR = _REPO_ROOT / "reports" / "harvest-state"

    _LEDGER_PATH = _LEDGER_DIR / "ledger.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_VALID_STATUSES = frozenset({
    "harvested", "merged", "review", "skipped", "waived", "superseded", "failed",
})


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """A single harvested item from a report."""

    item_hash: str           # 16-char hex, primary key
    report_path: str         # Repo-relative path
    report_sha256: str       # Full file hash
    section_key: str         # e.g. "not_completed"
    title: str
    raw_text: str
    confidence: float
    item_type: str
    suggested_category: str
    suggested_priority: str
    status: str              # harvested|merged|review|skipped|waived|superseded|failed
    backlog_target_id: str   # e.g. "ST-042" or ""
    harvested_at: str        # ISO datetime
    updated_at: str          # ISO datetime
    source_line: int
    harvest_run_id: str


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Metadata for a single harvest run."""

    run_id: str              # e.g. "harvest-20260421-143000"
    started_at: str
    completed_at: str        # "" if still running
    reports_scanned: int
    items_extracted: int
    items_new: int
    items_duplicate: int
    items_review: int
    items_failed: int
    trigger: str             # "auto:system-heal" | "auto:backlog-update" | "manual" | etc.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_file_sha256(path: Path) -> str:
    """Return full hex SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _entry_from_dict(d: dict) -> LedgerEntry:
    """Construct a LedgerEntry from a dict, ignoring unknown keys."""
    known = {f.name for f in fields(LedgerEntry)}
    return LedgerEntry(**{k: v for k, v in d.items() if k in known})


def _run_from_dict(d: dict) -> RunRecord:
    """Construct a RunRecord from a dict, ignoring unknown keys."""
    known = {f.name for f in fields(RunRecord)}
    return RunRecord(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# HarvestLedger class
# ---------------------------------------------------------------------------

class HarvestLedger:
    """CRUD interface for the harvest ledger."""

    def __init__(self, ledger_path: Path | None = None) -> None:
        self._path = ledger_path or _LEDGER_PATH
        self._entries: dict[str, LedgerEntry] = {}
        self._runs: dict[str, RunRecord] = {}
        self._waivers: dict[str, dict] = {}
        self._version: int = 1
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        self._version = data.get("version", 1)

        for k, v in data.get("entries", {}).items():
            try:
                self._entries[k] = _entry_from_dict(v)
            except (TypeError, KeyError):
                continue

        for k, v in data.get("runs", {}).items():
            try:
                self._runs[k] = _run_from_dict(v)
            except (TypeError, KeyError):
                continue

        self._waivers = dict(data.get("waivers", {}))

    def save(self) -> None:
        """Atomic write: tmp file + os.replace()."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self._version,
            "entries": {k: asdict(v) for k, v in self._entries.items()},
            "runs": {k: asdict(v) for k, v in self._runs.items()},
            "waivers": self._waivers,
        }
        with NamedTemporaryFile(
            "w", encoding="utf-8", delete=False,
            dir=self._path.parent, suffix=".tmp",
        ) as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(str(temp_path), str(self._path))

    # -- entry CRUD ---------------------------------------------------------

    def lookup(self, item_hash: str) -> LedgerEntry | None:
        """Look up an entry by item_hash. Returns None if not found."""
        return self._entries.get(item_hash)

    def record_item(
        self,
        item_hash: str,
        report_path: str,
        report_sha256: str,
        section_key: str,
        title: str,
        raw_text: str,
        confidence: float,
        item_type: str,
        suggested_category: str,
        suggested_priority: str,
        status: str,
        source_line: int,
        harvest_run_id: str,
        backlog_target_id: str = "",
    ) -> LedgerEntry:
        """Create or overwrite an entry. Returns the LedgerEntry."""
        now = _now_iso()
        entry = LedgerEntry(
            item_hash=item_hash,
            report_path=report_path,
            report_sha256=report_sha256,
            section_key=section_key,
            title=title,
            raw_text=raw_text,
            confidence=confidence,
            item_type=item_type,
            suggested_category=suggested_category,
            suggested_priority=suggested_priority,
            status=status,
            backlog_target_id=backlog_target_id,
            harvested_at=now,
            updated_at=now,
            source_line=source_line,
            harvest_run_id=harvest_run_id,
        )
        self._entries[item_hash] = entry
        return entry

    def update_status(self, item_hash: str, new_status: str, **kwargs: str) -> None:
        """Update the status (and optional fields) of an existing entry.

        Raises KeyError if item_hash not found.
        Raises ValueError if new_status is invalid.
        """
        if new_status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status!r} (valid: {sorted(_VALID_STATUSES)})")
        old = self._entries.get(item_hash)
        if old is None:
            raise KeyError(f"No entry with item_hash={item_hash!r}")

        updates = {"status": new_status, "updated_at": _now_iso()}
        updates.update(kwargs)

        d = asdict(old)
        d.update(updates)
        self._entries[item_hash] = _entry_from_dict(d)

    def get_items_by_status(self, status: str) -> list[LedgerEntry]:
        """Return all entries with the given status."""
        return [e for e in self._entries.values() if e.status == status]

    # -- run tracking -------------------------------------------------------

    def start_run(self, trigger: str) -> str:
        """Start a new harvest run. Returns the run_id."""
        now = datetime.now(timezone.utc)
        run_id = f"harvest-{now.strftime('%Y%m%d-%H%M%S')}"
        record = RunRecord(
            run_id=run_id,
            started_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at="",
            reports_scanned=0,
            items_extracted=0,
            items_new=0,
            items_duplicate=0,
            items_review=0,
            items_failed=0,
            trigger=trigger,
        )
        self._runs[run_id] = record
        self.save()
        return run_id

    def end_run(self, run_id: str, stats: dict) -> None:
        """Complete a run, recording stats and completion time."""
        old = self._runs.get(run_id)
        if old is None:
            raise KeyError(f"No run with run_id={run_id!r}")
        d = asdict(old)
        d["completed_at"] = _now_iso()
        for key in ("reports_scanned", "items_extracted", "items_new",
                     "items_duplicate", "items_review", "items_failed"):
            if key in stats:
                d[key] = stats[key]
        self._runs[run_id] = _run_from_dict(d)
        self.save()

    # -- report-level queries -----------------------------------------------

    def get_unharvested_reports(self, known_reports: list[str]) -> list[str]:
        """From *known_reports*, return those with no ledger entries and not waived."""
        harvested_reports = {e.report_path for e in self._entries.values()}
        return [
            r for r in known_reports
            if r not in harvested_reports and not self.is_waived(r)
        ]

    def report_changed(self, report_path: str, current_sha256: str) -> bool:
        """True if any stored entry for *report_path* has a different sha256."""
        for e in self._entries.values():
            if e.report_path == report_path and e.report_sha256 != current_sha256:
                return True
        return False

    # -- waivers ------------------------------------------------------------

    def waive_report(self, report_path: str, reason: str) -> None:
        """Mark a report as waived (will be skipped in future harvests)."""
        self._waivers[report_path] = {
            "waived_at": _now_iso(),
            "reason": reason,
        }
        self.save()

    def is_waived(self, report_path: str) -> bool:
        """Check if a report is waived."""
        return report_path in self._waivers

    # -- introspection (for CLI) --------------------------------------------

    @property
    def entries(self) -> dict[str, LedgerEntry]:
        return dict(self._entries)

    @property
    def runs(self) -> dict[str, RunRecord]:
        return dict(self._runs)

    @property
    def waivers(self) -> dict[str, dict]:
        return dict(self._waivers)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_status(_args: argparse.Namespace) -> int:
    """Print a summary of the harvest ledger."""
    ledger = HarvestLedger()
    entries = ledger.entries
    runs = ledger.runs
    waivers = ledger.waivers

    total = len(entries)
    by_status: dict[str, int] = {}
    tracked_reports: set[str] = set()
    for e in entries.values():
        by_status[e.status] = by_status.get(e.status, 0) + 1
        tracked_reports.add(e.report_path)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"HARVEST LEDGER STATUS — {today}")
    print(f"Entries: {total}")
    print(f"  harvested: {by_status.get('harvested', 0)}"
          f"  merged: {by_status.get('merged', 0)}"
          f"  review: {by_status.get('review', 0)}"
          f"  skipped: {by_status.get('skipped', 0)}")
    print(f"  waived: {by_status.get('waived', 0)}"
          f"     superseded: {by_status.get('superseded', 0)}"
          f"  failed: {by_status.get('failed', 0)}")
    print(f"Reports tracked: {len(tracked_reports)} ({len(waivers)} waived)")

    # Last 5 runs (most recent first)
    sorted_runs = sorted(runs.values(), key=lambda r: r.started_at, reverse=True)[:5]
    if sorted_runs:
        print("Last 5 runs:")
        for r in sorted_runs:
            date_part = r.started_at[:10] if r.started_at else "?"
            print(f"  {r.run_id} | {date_part} | {r.trigger}"
                  f" | new:{r.items_new} review:{r.items_review}"
                  f" skip:{r.items_duplicate} fail:{r.items_failed}")
    else:
        print("Last 5 runs: (none)")

    return 0


def cmd_retry_failed(_args: argparse.Namespace) -> int:
    """Reset all failed entries to 'review' status."""
    ledger = HarvestLedger()
    failed = ledger.get_items_by_status("failed")
    if not failed:
        print("No failed entries to retry.")
        return 0

    for entry in failed:
        ledger.update_status(entry.item_hash, "review")
    ledger.save()
    print(f"Reset {len(failed)} failed entries to 'review'.")
    return 0


def cmd_waive(args: argparse.Namespace) -> int:
    """Waive a report path."""
    if not args.reason:
        print("ERROR: --reason is required.", file=sys.stderr)
        return 1
    ledger = HarvestLedger()
    ledger.waive_report(args.report_path, args.reason)
    print(f"Waived: {args.report_path}")
    return 0


def cmd_reset(_args: argparse.Namespace) -> int:
    """Clear the entire ledger (DANGEROUS)."""
    if _LEDGER_PATH.exists():
        os.remove(str(_LEDGER_PATH))
        print(f"Ledger deleted: {_LEDGER_PATH}")
    else:
        print("Ledger file does not exist; nothing to reset.")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harvest_ledger",
        description="Harvest ledger CRUD — tracks report items processed into backlog.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show ledger status summary")

    # retry-failed
    sub.add_parser("retry-failed", help="Reset all failed entries to 'review'")

    # waive
    p_waive = sub.add_parser("waive", help="Waive a report so it is never harvested")
    p_waive.add_argument("report_path", help="Repo-relative report path to waive")
    p_waive.add_argument("--reason", required=True, help="Reason for waiving")

    # reset
    sub.add_parser("reset", help="DANGEROUS: clear the entire ledger")

    args = parser.parse_args(argv)
    dispatch = {
        "status": cmd_status,
        "retry-failed": cmd_retry_failed,
        "waive": cmd_waive,
        "reset": cmd_reset,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())

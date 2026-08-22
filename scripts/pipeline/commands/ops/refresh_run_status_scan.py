"""refresh_run_status_scan.py -- cross-product BLOCKED-run staleness scan.

Mission plan: mission-plan-the-end-to-end-vast-hejlsberg.md, Task 5 (S9.3, closes
G1). ``refresh_run.py``'s own ``status`` verb is single-run only (requires
``--run-id``) -- there is no existing cross-product view of every active run,
so a genuinely stuck ``BLOCKED`` run (e.g. ``cells/go``, blocked since
2026-07-28 with no automatic flag) can sit unnoticed indefinitely, and because
``create_run`` refuses to start a new run for a product with a non-terminal
active run, the stuck run permanently locks out new work for that product.

This is deliberately visibility, not auto-recovery: auto-transitioning a
BLOCKED run out from under an operator would defeat the exact safety property
the state exists for (see ``refresh_run.py``'s ``recover``/``abandon`` verbs,
which are the correct, explicit ways to clear one). This script only walks
``reports/refresh_runs/*/*/ACTIVE.json``, loads each referenced run's
``manifest.json``, and flags any ``BLOCKED`` run whose ``updated_at`` exceeds a
staleness threshold (default 7 days) as ``STALE_BLOCKED``.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from core.fs import atomic_write  # noqa: E402

DEFAULT_STALENESS_DAYS = 7

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT
_reports_root = _DEFAULT_REPO_ROOT / "reports"
_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def configure(
    *,
    repo_root: Path | str | None = None,
    reports_root: Path | str | None = None,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Override external boundaries for tests; call without arguments to reset."""
    global _repo_root, _reports_root, _now
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _reports_root = (
        Path(reports_root) if reports_root is not None else _repo_root / "reports"
    )
    _now = now or (lambda: datetime.now(timezone.utc))


def _parse_iso(value: str) -> datetime:
    # manifest/ACTIVE.json timestamps are written as "...Z" (see refresh_run.py
    # _utc()); fromisoformat needs the +00:00 form on Python < 3.11-safe path.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def discover_active_runs() -> list[dict[str, Any]]:
    """Return one entry per {family}/{platform}/ACTIVE.json found on disk."""
    runs_root = _reports_root / "refresh_runs"
    if not runs_root.is_dir():
        return []

    found: list[dict[str, Any]] = []
    for active_path in sorted(runs_root.glob("*/*/ACTIVE.json")):
        platform_dir = active_path.parent
        family = platform_dir.parent.name
        platform = platform_dir.name
        try:
            active = json.loads(active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            found.append({
                "family": family, "platform": platform,
                "active_path": str(active_path), "error": f"unreadable ACTIVE.json: {exc}",
            })
            continue

        run_id = active.get("run_id")
        manifest_path = platform_dir / run_id / "manifest.json" if run_id else None
        manifest: dict[str, Any] | None = None
        manifest_error = None
        if manifest_path is not None and manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                manifest_error = f"unreadable manifest.json: {exc}"
        elif manifest_path is not None:
            manifest_error = f"manifest.json not found at {manifest_path}"

        found.append({
            "family": family,
            "platform": platform,
            "run_id": run_id,
            "active_path": str(active_path),
            "active_updated_at": active.get("updated_at"),
            "manifest": manifest,
            "error": manifest_error,
        })
    return found


def scan(*, staleness_days: int = DEFAULT_STALENESS_DAYS) -> dict[str, Any]:
    """Scan every product's ACTIVE.json and classify BLOCKED-run staleness.

    Only ACTIVE.json entries are inspected -- a product with no active run
    (COMMITTED/ABANDONED terminal, or never started) has nothing to flag here
    by construction, since ``bind-commit``/``recover``/``abandon`` all clear
    ACTIVE.json on the way to a terminal state.
    """
    now = _now()
    threshold = timedelta(days=staleness_days)
    entries: list[dict[str, Any]] = []
    stale_count = 0

    for run in discover_active_runs():
        family, platform = run["family"], run["platform"]
        manifest = run.get("manifest")
        entry: dict[str, Any] = {
            "family": family,
            "platform": platform,
            "run_id": run.get("run_id"),
        }

        if run.get("error"):
            entry["classification"] = "UNREADABLE"
            entry["detail"] = run["error"]
            entries.append(entry)
            continue

        state = manifest.get("state") if manifest else None
        entry["state"] = state

        if state != "BLOCKED":
            # CREATED/INPUTS_PINNED/.../READY_TO_COMMIT: a run is legitimately
            # active and non-terminal without being stuck -- only BLOCKED
            # represents an operator-attention state this scan cares about.
            entry["classification"] = "ACTIVE_NOT_BLOCKED"
            entries.append(entry)
            continue

        updated_raw = manifest.get("updated_at")
        if not updated_raw:
            entry["classification"] = "BLOCKED_UNKNOWN_AGE"
            entry["detail"] = "manifest.json has no updated_at field"
            entries.append(entry)
            continue

        updated_at = _parse_iso(updated_raw)
        age = now - updated_at
        entry["updated_at"] = updated_raw
        entry["age_days"] = round(age.total_seconds() / 86400, 2)
        entry["failure_reason"] = manifest.get("failure_reason")

        if age >= threshold:
            entry["classification"] = "STALE_BLOCKED"
            stale_count += 1
        else:
            entry["classification"] = "BLOCKED_RECENT"
        entries.append(entry)

    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "staleness_threshold_days": staleness_days,
        "products_scanned": len(entries),
        "stale_blocked_count": stale_count,
        "entries": entries,
    }


def write_scan_report(result: dict[str, Any]) -> Path:
    scan_dir = _reports_root / "refresh_runs" / "_scan"
    scan_dir.mkdir(parents=True, exist_ok=True)
    date_str = _now().strftime("%Y-%m-%d")
    out_path = scan_dir / f"{date_str}.json"
    atomic_write(out_path, json.dumps(result, indent=2, sort_keys=True) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan every product's refresh-run ACTIVE.json for stuck BLOCKED runs."
    )
    parser.add_argument(
        "--staleness-days", type=int, default=DEFAULT_STALENESS_DAYS,
        help=f"Age threshold in days for BLOCKED -> STALE_BLOCKED (default: {DEFAULT_STALENESS_DAYS})",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="Print the scan result without writing reports/refresh_runs/_scan/{date}.json",
    )
    args = parser.parse_args(argv)

    result = scan(staleness_days=args.staleness_days)
    if not args.no_write:
        out_path = write_scan_report(result)
        print(f"Scan report written: {out_path}")

    print(json.dumps(result, indent=2, sort_keys=True))

    if result["stale_blocked_count"] > 0:
        stale = [e for e in result["entries"] if e["classification"] == "STALE_BLOCKED"]
        print(
            f"\nSTALE_BLOCKED: {result['stale_blocked_count']} run(s) exceed "
            f"{args.staleness_days}-day threshold:",
            file=sys.stderr,
        )
        for e in stale:
            print(
                f"  {e['family']}/{e['platform']} run={e['run_id']} "
                f"age={e['age_days']}d reason={e.get('failure_reason')!r}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""bounded_auto_regen.py — bounded, automatic knowledge regeneration for low-risk drift.

CONTRACT: scripts/pipeline/commands/ops/bounded_auto_regen.py
  purpose: FRESH-001 (2026-08-14). Closes the detection-to-action loop for real: once
           knowledge/ is git-tracked (T0), every automated regeneration write is a
           normal, diffable, revertable git commit -- the same property that makes
           auto-merging a dependency-bot PR reasonable once there's a real diff to
           review or revert. This module is the SELECTOR: given the latest fleet
           sweep + drift state, it picks which products are safe to regenerate fully
           unattended (LOW/MEDIUM impact only, capped per run, oldest-flagged-first,
           skipping any product whose regen lock is already contended) and which must
           route to a human-actionable issue instead (HIGH impact, or LOW/MEDIUM
           beyond the cap, or a locked/failed regen).
  HIGH impact NEVER auto-regenerates: that is precisely where a wrong published claim
           is most costly and where LLM enrichment spend is largest -- it always
           routes to the deduped issue check_upstream_drift.py files (T9).
  the actual regen/commit callables are injectable (regen_fn, lock_fn, commit_fn) so
           select_candidates()/run() are fully unit-testable without invoking the real
           S-12->S-14 chain or git_plumb_commit.py -- see test_bounded_auto_regen.py.
  scheduling: called by the closed-loop step of .github/workflows/upstream-monitor.yml
           after repo_patrol.py sweep has produced its impact classification for
           already-drifted products.

Usage:
    python scripts/pipeline/commands/ops/bounded_auto_regen.py select
    python scripts/pipeline/commands/ops/bounded_auto_regen.py select --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_LIB_DIR = _PIPELINE_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
SWEEP_REPORT_PATH = REPO_ROOT / "reports" / "discovery" / "sweep_report.json"
DRIFT_STATE_PATH = REPO_ROOT / "data" / "upstream_drift_state.json"

MAX_AUTO_REGEN_PER_RUN = 3
AUTO_REGEN_IMPACT_LEVELS = frozenset({"LOW", "MEDIUM"})


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, SWEEP_REPORT_PATH, DRIFT_STATE_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    SWEEP_REPORT_PATH = REPO_ROOT / "reports" / "discovery" / "sweep_report.json"
    DRIFT_STATE_PATH = REPO_ROOT / "data" / "upstream_drift_state.json"


def _load_sweep_changed() -> list[dict]:
    try:
        report = json.loads(SWEEP_REPORT_PATH.read_text(encoding="utf-8"))
        return report.get("changed", [])
    except (OSError, json.JSONDecodeError):
        return []


def _load_drift_state() -> dict:
    try:
        return json.loads(DRIFT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def select_candidates(
    changed: "list[dict] | None" = None,
    drift_state: "dict | None" = None,
    *,
    cap: int = MAX_AUTO_REGEN_PER_RUN,
) -> dict:
    """Pure selection function -- no I/O, no locking, no regen.

    Args:
        changed: sweep_report.json's "changed" list (each: family, platform, impact,
            stored_sha, current_sha). Defaults to reading the real sweep report.
        drift_state: upstream_drift_state.json's contents, used only for
            oldest-flagged-first ordering (consecutive_weeks_flagged, descending).
        cap: max products to select for auto-regen this run.

    Returns {"auto_regen": [...], "route_to_issue": [...]} -- both lists of the
    original changed-entry dicts, annotated with a "reason" key explaining the
    routing decision.
    """
    changed = _load_sweep_changed() if changed is None else changed
    drift_state = _load_drift_state() if drift_state is None else drift_state

    eligible = []
    high_or_unknown = []
    for entry in changed:
        impact = entry.get("impact")
        if impact in AUTO_REGEN_IMPACT_LEVELS:
            key = f"{entry['family']}/{entry['platform']}"
            weeks = drift_state.get(key, {}).get("consecutive_weeks_flagged", 0)
            eligible.append({**entry, "_weeks_flagged": weeks})
        else:
            high_or_unknown.append({**entry, "reason": f"impact={impact} never auto-regenerates"})

    # Oldest-flagged-first: highest consecutive_weeks_flagged first, so a
    # long-drifting product is not perpetually starved by newer findings.
    eligible.sort(key=lambda e: e["_weeks_flagged"], reverse=True)

    auto_regen = eligible[:cap]
    beyond_cap = eligible[cap:]
    for entry in beyond_cap:
        entry["reason"] = f"LOW/MEDIUM but beyond per-run cap ({cap})"

    for entry in auto_regen:
        entry.pop("_weeks_flagged", None)
    for entry in beyond_cap:
        entry.pop("_weeks_flagged", None)

    return {"auto_regen": auto_regen, "route_to_issue": high_or_unknown + beyond_cap}


RegenFn = Callable[[str, str], bool]
LockAcquireFn = Callable[[str, str], "object | None"]  # returns a context-manager-like or None if contended
CommitFn = Callable[[str, str, str], bool]  # (family, platform, message) -> success


def run(
    *,
    regen_fn: RegenFn,
    try_acquire_lock: LockAcquireFn,
    commit_fn: "CommitFn | None" = None,
    changed: "list[dict] | None" = None,
    drift_state: "dict | None" = None,
    cap: int = MAX_AUTO_REGEN_PER_RUN,
) -> dict:
    """Orchestrate the bounded auto-regen pass. Every side-effecting step is
    injected (regen_fn, try_acquire_lock, commit_fn) so this is fully testable
    without invoking the real S-12->S-14 chain, the real regen lock, or
    git_plumb_commit.py -- see test_bounded_auto_regen.py.

    try_acquire_lock(family, platform) must return a context manager on success,
    or None if the lock is already contended (never blocks/raises).
    """
    selection = select_candidates(changed, drift_state, cap=cap)
    regenerated: list[dict] = []
    skipped_locked: list[dict] = []
    failed: list[dict] = []

    for entry in selection["auto_regen"]:
        family, platform = entry["family"], entry["platform"]
        lock = try_acquire_lock(family, platform)
        if lock is None:
            skipped_locked.append({**entry, "reason": "regen lock contended, skipped (not blocked)"})
            continue
        try:
            ok = regen_fn(family, platform)
            if not ok:
                failed.append({**entry, "reason": "regen chain failed"})
                continue
            if commit_fn is not None:
                message = (f"chore(knowledge): auto-refresh {family}/{platform} "
                           f"({entry.get('stored_sha', '')[:10]} -> {entry.get('current_sha', '')[:10]}, "
                           f"impact={entry.get('impact')})")
                commit_fn(family, platform, message)
            regenerated.append(entry)
        finally:
            release = getattr(lock, "release", None)
            if callable(release):
                release()

    return {
        "regenerated": regenerated,
        "skipped_locked": skipped_locked,
        "failed": failed,
        "route_to_issue": selection["route_to_issue"],
    }


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Select products for bounded automatic knowledge regeneration")
    sub = parser.add_subparsers(dest="command", required=True)
    p_select = sub.add_parser("select", help="Report the selection decision (read-only, no regen)")
    p_select.add_argument("--json", action="store_true", dest="as_json")
    p_select.add_argument("--cap", type=int, default=MAX_AUTO_REGEN_PER_RUN)

    args = parser.parse_args(argv)

    if args.command == "select":
        result = select_candidates(cap=args.cap)
        if args.as_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Auto-regen ({len(result['auto_regen'])}):")
            for e in result["auto_regen"]:
                print(f"  {e['family']}/{e['platform']} ({e['impact']})")
            print(f"Route to issue ({len(result['route_to_issue'])}):")
            for e in result["route_to_issue"]:
                print(f"  {e['family']}/{e['platform']} ({e.get('impact')}) -- {e.get('reason')}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

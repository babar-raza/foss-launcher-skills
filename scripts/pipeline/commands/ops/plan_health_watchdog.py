"""plan_health_watchdog.py -- detect stalled taskcards and plan/store
parity contradictions.

New 2026-08-30 (TASK_BACKLOG.md SYNC-3-remaining), generalized from
aspose.org's plan-health-watchdog skill (S-113). Reuses this repo's own
taskcard_store.py (ported 2026-08-29, verbatim-identical schema to
source's) and the check_taskcard_plan_parity.py sibling (rewritten to
match source's real [STATUS: ...]-tag design after an earlier version's
cruder heuristic threw false positives against this repo's own plan doc
-- see that module's docstring). Read-only: never edits the plan,
taskcards, or content.

Usage:
    .venv/bin/python scripts/pipeline/commands/ops/plan_health_watchdog.py \
        --mission-id SYNC-2026-08-29 --plan-file plans/plan-hardening-addendum-from-latest-audit.md

Exit codes:
  0 -- no stalled tasks, no parity contradictions
  1 -- at least one stalled task or contradiction found
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from taskcard_store import TaskcardStore  # noqa: E402

_CHECKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ci" / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))
from check_taskcard_plan_parity import (  # noqa: E402
    extract_plan_tags,
    find_contradictions,
    infer_task_id_pattern,
    load_taskcards_latest,
)

_TERMINAL_STATUSES = {
    "CLOSED", "FOCUSED_VERIFIED", "INTEGRATION_VERIFIED", "END_TO_END_VERIFIED",
    "PILOT_PROVEN", "INDEPENDENTLY_REVIEWED", "SUPERSEDED", "OUT_OF_SCOPE",
}
_DEFAULT_THRESHOLD_DAYS = 5


def business_days_between(start: datetime, end: datetime) -> int:
    """Count weekdays strictly between start and end (exclusive of start,
    inclusive of end's date). Simple Mon-Fri calendar, no holiday table --
    documented as a deliberate simplification, not an oversight."""
    if end <= start:
        return 0
    days = 0
    one_day_seconds = 86400
    # Whole calendar days from start to end, e.g. start Mon -> end following
    # Mon is exactly 7 -- NOT 8 (a prior version added +1 here, an off-by-one
    # caught by this module's own test suite: it counted one day PAST end).
    total_days = int((end - start).total_seconds() // one_day_seconds)
    for offset in range(1, total_days + 1):
        day = start.timestamp() + offset * one_day_seconds
        weekday = datetime.fromtimestamp(day, tz=timezone.utc).weekday()
        if weekday < 5:  # Mon-Fri
            days += 1
    return days


def find_stalled(taskcards: dict, threshold_days: int = _DEFAULT_THRESHOLD_DAYS) -> "list[dict]":
    """Non-terminal tasks whose recorded_at is older than threshold_days
    (business days) ago."""
    now = datetime.now(tz=timezone.utc)
    stalled = []
    for task_id, row in sorted(taskcards.items()):
        if row.get("status") in _TERMINAL_STATUSES:
            continue
        raw = row.get("recorded_at", "")
        try:
            recorded_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue  # malformed timestamp -- not this tool's job to fix, skip
        age_days = business_days_between(recorded_at, now)
        if age_days >= threshold_days:
            stalled.append({
                "task_id": task_id,
                "status": row.get("status"),
                "age_business_days": age_days,
                "recorded_at": raw,
                "evidence_refs": row.get("evidence_refs", []),
            })
    return stalled


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--plan-file", default=None, help="If given, also runs the plan/store parity check")
    parser.add_argument("--threshold-days", type=int, default=_DEFAULT_THRESHOLD_DAYS)
    args = parser.parse_args(argv)

    store = TaskcardStore(args.mission_id)
    taskcards = store.read_latest()

    if not taskcards:
        print(f"No taskcards found for mission {args.mission_id!r} -- untracked (advisory, not blocking).", file=sys.stderr)
        return 0

    any_issue = False

    stalled = find_stalled(taskcards, args.threshold_days)
    if stalled:
        any_issue = True
        print(f"STALL: {len(stalled)} non-terminal task(s) older than {args.threshold_days} business days:")
        for s in stalled:
            print(f"  {s['task_id']}: status={s['status']} age={s['age_business_days']}bd recorded_at={s['recorded_at']}")
    else:
        print(f"No stalled tasks past {args.threshold_days} business days.")

    if args.plan_file:
        plan_path = Path(args.plan_file)
        if plan_path.is_file():
            plan_text = plan_path.read_text(encoding="utf-8")
            task_id_pattern = infer_task_id_pattern(taskcards.keys())
            plan_tags = extract_plan_tags(plan_text, task_id_pattern)
            problems = find_contradictions(plan_tags, taskcards)
            if problems:
                any_issue = True
                print(f"PARITY: {len(problems)} problem(s) found in {plan_path}:")
                for p in problems:
                    print(f"  [{p['kind']}] {p['task_id']}: {p['detail']}")
            else:
                print(f"PARITY: {len(plan_tags)} tagged task(s) checked in {plan_path}, no contradictions.")
        else:
            print(f"WARNING: --plan-file {plan_path} not found -- skipping parity check.", file=sys.stderr)

    return 1 if any_issue else 0


if __name__ == "__main__":
    sys.exit(main())

"""mission_taskcard_cli.py -- thin CLI over taskcard_store.py.

New 2026-08-29 (TASK_BACKLOG.md SYNC-1). taskcard_store.py's own module
docstring gives Python usage examples but no CLI -- every prior use in
this repo's own history (see git log) would otherwise be an inline
`python -c` snippet, exactly the "ad hoc one-off Python snippet" pattern
taskcard_store.py itself exists to replace for the FILE-WRITE side. This
gives it a durable, re-runnable entry point for the common operations.

Usage:
    .venv/bin/python scripts/pipeline/commands/ops/mission_taskcard_cli.py append \
        --mission-id M-1 --task-id T-1 --status TODO --recorded-by me
    .venv/bin/python scripts/pipeline/commands/ops/mission_taskcard_cli.py advance \
        --mission-id M-1 --task-id T-1 --from TODO --to IN_PROGRESS --recorded-by me
    .venv/bin/python scripts/pipeline/commands/ops/mission_taskcard_cli.py pause \
        --mission-id M-1 --task-id T-1 --reason "waiting on input" --recorded-by me
    .venv/bin/python scripts/pipeline/commands/ops/mission_taskcard_cli.py list \
        --mission-id M-1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from taskcard_store import TaskcardCASError, TaskcardNotFoundError, TaskcardStore  # noqa: E402


def cmd_append(args: argparse.Namespace) -> int:
    store = TaskcardStore(args.mission_id)
    record = {
        "task_id": args.task_id, "status": args.status,
        "recorded_at": args.recorded_at or _now(), "recorded_by": args.recorded_by,
        "evidence_refs": args.evidence_ref or [],
    }
    if args.title:
        record["title"] = args.title
    try:
        result = store.append(record)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    store = TaskcardStore(args.mission_id)
    try:
        result = store.update_taskcard_status(
            args.task_id, expected_status=args.from_status, new_status=args.to_status,
            recorded_by=args.recorded_by, evidence_refs=args.evidence_ref or None,
        )
    except TaskcardCASError as exc:
        print(f"CAS CONFLICT: {exc}", file=sys.stderr)
        return 2
    except TaskcardNotFoundError as exc:
        print(f"NOT FOUND: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    store = TaskcardStore(args.mission_id)
    try:
        result = store.pause_taskcard(
            args.task_id, reason=args.reason, recorded_by=args.recorded_by,
            title=args.title, create_if_missing=not args.no_create,
        )
    except (TaskcardNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = TaskcardStore(args.mission_id)
    latest = store.read_latest()
    if not latest:
        print(f"No taskcards recorded for mission {args.mission_id!r}.", file=sys.stderr)
        return 0
    for task_id, row in sorted(latest.items()):
        title = f" -- {row['title']}" if row.get("title") else ""
        print(f"{task_id}: {row['status']}{title}")
    return 0


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_append = sub.add_parser("append", help="Create the first row for a new task_id")
    p_append.add_argument("--mission-id", required=True)
    p_append.add_argument("--task-id", required=True)
    p_append.add_argument("--status", required=True)
    p_append.add_argument("--recorded-by", required=True)
    p_append.add_argument("--recorded-at", default=None)
    p_append.add_argument("--title", default=None)
    p_append.add_argument("--evidence-ref", action="append", default=[])

    p_advance = sub.add_parser("advance", help="CAS-guarded status transition")
    p_advance.add_argument("--mission-id", required=True)
    p_advance.add_argument("--task-id", required=True)
    p_advance.add_argument("--from", dest="from_status", required=True)
    p_advance.add_argument("--to", dest="to_status", required=True)
    p_advance.add_argument("--recorded-by", required=True)
    p_advance.add_argument("--evidence-ref", action="append", default=[])

    p_pause = sub.add_parser("pause", help="Record a task as deliberately set aside")
    p_pause.add_argument("--mission-id", required=True)
    p_pause.add_argument("--task-id", required=True)
    p_pause.add_argument("--reason", required=True)
    p_pause.add_argument("--recorded-by", required=True)
    p_pause.add_argument("--title", default=None)
    p_pause.add_argument("--no-create", action="store_true", help="Fail instead of creating a new row")

    p_list = sub.add_parser("list", help="List the latest status of every task in a mission")
    p_list.add_argument("--mission-id", required=True)

    args = parser.parse_args(argv)
    dispatch = {"append": cmd_append, "advance": cmd_advance, "pause": cmd_pause, "list": cmd_list}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

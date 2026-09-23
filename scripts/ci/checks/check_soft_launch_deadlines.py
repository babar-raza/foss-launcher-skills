"""check_soft_launch_deadlines.py -- MT069 HC-15: the "soft-launch deadline watch" proposal, built.

Reads data/soft_launch_deadlines.json and flags any entry whose soak_end date has passed while its
status is still "soaking" -- a soft-launched surface (a continue-on-error step, a CLI flag defaulting
to warn instead of block, etc.) that nobody has re-checked since its own stated deadline.

Why this exists: a real incident (TC-SG-07/R-04's stale-guard soak, tracked externally and in a
gitignored reminder) went silently overdue by 12 days before anyone re-verified its premise --
MT069 discovered this live on 2026-09-18. This is a mechanical, unconditional check for the same
recurring shape ("we deliberately made X non-blocking until DATE, and DATE has passed"), not tied
to any one incident.

Usage:
    python scripts/ci/checks/check_soft_launch_deadlines.py [--sidecar PATH] [--today YYYY-MM-DD] [--json]

Exit codes: 0 = nothing overdue (or nothing tracked); 1 = at least one overdue entry; 2 = the sidecar
is missing or malformed (a configuration problem, not a finding -- never silently treated as "clean").
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SIDECAR = _REPO_ROOT / "data" / "soft_launch_deadlines.json"

_VALID_STATUSES = frozenset({"soaking", "graduated", "reverted"})
_REQUIRED_FIELDS = ("id", "description", "soak_end", "owning_card", "status")


def load_entries(sidecar_path: Path) -> "list[dict]":
    """Raises FileNotFoundError / json.JSONDecodeError / ValueError -- callers decide how to report."""
    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("sidecar 'entries' must be a list")
    for i, e in enumerate(entries):
        missing = [f for f in _REQUIRED_FIELDS if f not in e]
        if missing:
            raise ValueError(f"entries[{i}] ({e.get('id', '?')}) missing required field(s): {missing}")
        if e["status"] not in _VALID_STATUSES:
            raise ValueError(f"entries[{i}] ({e['id']}) has invalid status {e['status']!r}")
        datetime.date.fromisoformat(e["soak_end"])  # raises ValueError if malformed
    return entries


def find_overdue(entries: "list[dict]", today: datetime.date) -> "list[dict]":
    """Soaking entries whose soak_end is strictly before today."""
    overdue = []
    for e in entries:
        if e["status"] != "soaking":
            continue
        if datetime.date.fromisoformat(e["soak_end"]) < today:
            overdue.append(e)
    return overdue


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sidecar", default=str(_DEFAULT_SIDECAR), help="Path to the soft-launch sidecar JSON")
    parser.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD), for testing")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text")
    args = parser.parse_args(argv)

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.datetime.now(datetime.timezone.utc).date()
    sidecar_path = Path(args.sidecar)

    try:
        entries = load_entries(sidecar_path)
    except FileNotFoundError:
        print(f"ERROR: sidecar not found: {sidecar_path}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: sidecar malformed ({sidecar_path}): {exc}", file=sys.stderr)
        return 2

    overdue = find_overdue(entries, today)

    if args.json:
        print(json.dumps({
            "checked_at": today.isoformat(),
            "total_entries": len(entries),
            "soaking": sum(1 for e in entries if e["status"] == "soaking"),
            "overdue": overdue,
        }, indent=2))
    else:
        if not entries:
            print("No soft-launch deadlines tracked.")
        elif not overdue:
            soaking = [e for e in entries if e["status"] == "soaking"]
            print(f"OK: {len(soaking)} soaking entr(y/ies), none overdue as of {today.isoformat()}.")
        else:
            print(f"OVERDUE ({len(overdue)}) as of {today.isoformat()}:")
            for e in overdue:
                days = (today - datetime.date.fromisoformat(e["soak_end"])).days
                print(f"  [{e['id']}] soak_end {e['soak_end']} ({days} day(s) overdue) -- owner {e['owning_card']}")
                print(f"    {e['description']}")

    return 1 if overdue else 0


if __name__ == "__main__":
    sys.exit(main())

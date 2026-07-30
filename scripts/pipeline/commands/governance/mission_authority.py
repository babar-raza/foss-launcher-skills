#!/usr/bin/env python3
"""mission_authority.py — durable multi-mission archive for MISSION_AUTHORITY.yaml.

Root-level MISSION_AUTHORITY.yaml is a single mutable "current mission"
projection with zero tooling behind it (confirmed: no script anywhere
referenced it before this one) — it gets overwritten per mission, and only
`git log -p` recovers prior missions. Meanwhile reports/plan_state/{mission_id}/
already holds a durable taskcards.jsonl per mission, for 6 missions at once.

This script closes that gap without replacing the root file's role: the root
file stays the human-authored "current mission" narrative (mission_summary,
in_scope_outcomes, etc. remain hand-written prose — a script must not
fabricate mission narrative). What this script adds:

  open --mission-id X   validate the root file's required fields, confirm its
                        mission_id matches X, and archive an immutable
                        snapshot to reports/plan_state/X/mission_authority.yaml
                        (status: open)
  list                  scan reports/plan_state/*/mission_authority.yaml and
                        print every known mission with its status
  close --mission-id X  mark mission X's archived snapshot status: closed

Required fields (concordance table, docs/governance/planning-methodology.md):
mission_id, mission_summary, governing_plan_path, in_scope_outcomes,
out_of_scope_items, mandatory_acceptance_criteria, mission_locked.

Usage:
    python scripts/pipeline/commands/governance/mission_authority.py open --mission-id X
    python scripts/pipeline/commands/governance/mission_authority.py list
    python scripts/pipeline/commands/governance/mission_authority.py close --mission-id X
"""
from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

REQUIRED_FIELDS = [
    "mission_id",
    "mission_summary",
    "governing_plan_path",
    "in_scope_outcomes",
    "out_of_scope_items",
    "mandatory_acceptance_criteria",
    "mission_locked",
]


def repo_root() -> Path:
    # scripts/pipeline/commands/governance/mission_authority.py -> repo root is 4 up
    return Path(__file__).resolve().parents[4]


def root_mission_authority_path(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "MISSION_AUTHORITY.yaml"


def plan_state_dir(mission_id: str, root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "reports" / "plan_state" / mission_id


def read_root_mission_authority(root: Optional[Path] = None) -> Dict[str, Any]:
    path = root_mission_authority_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"MISSION_AUTHORITY.yaml not found at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "mission_authority" not in data:
        raise ValueError("MISSION_AUTHORITY.yaml must have a top-level 'mission_authority' key")
    return data["mission_authority"]


def validate_mission_authority(ma: Dict[str, Any]) -> List[str]:
    """Return a list of validation errors (empty list = valid)."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in ma:
            errors.append(f"missing required field: {field}")
    for list_field in ("in_scope_outcomes", "out_of_scope_items", "mandatory_acceptance_criteria"):
        if list_field in ma and not isinstance(ma[list_field], list):
            errors.append(f"field must be a list: {list_field}")
    if "mission_locked" in ma and not isinstance(ma["mission_locked"], bool):
        errors.append("field must be a boolean: mission_locked")
    return errors


def archive_mission(
    mission_id: str,
    ma: Dict[str, Any],
    status: str,
    root: Optional[Path] = None,
) -> Path:
    """Write the durable per-mission snapshot. status is 'open' or 'closed'."""
    out_dir = plan_state_dir(mission_id, root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "mission_authority.yaml"

    snapshot = dict(ma)
    snapshot["_archive_status"] = status
    snapshot["_archived_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    out_path.write_text(
        yaml.safe_dump({"mission_authority": snapshot}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return out_path


def cmd_open(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    try:
        ma = read_root_mission_authority(root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    errors = validate_mission_authority(ma)
    if errors:
        print("ERROR: MISSION_AUTHORITY.yaml failed validation:")
        for e in errors:
            print(f"  - {e}")
        return 1

    if ma.get("mission_id") != args.mission_id:
        print(
            f"ERROR: root MISSION_AUTHORITY.yaml mission_id is "
            f"{ma.get('mission_id')!r}, not {args.mission_id!r}. "
            "The root file must already contain this mission's contract "
            "before it can be archived — this script does not author the "
            "mission narrative."
        )
        return 1

    out_path = archive_mission(args.mission_id, ma, status="open", root=root)
    print(f"Archived mission {args.mission_id!r} (status: open) -> {out_path}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    archive_path = plan_state_dir(args.mission_id, root) / "mission_authority.yaml"
    if not archive_path.is_file():
        print(f"ERROR: no archived mission found for {args.mission_id!r} at {archive_path}")
        return 1

    data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
    ma = data["mission_authority"]
    ma["_archive_status"] = "closed"
    ma["_closed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    archive_path.write_text(
        yaml.safe_dump({"mission_authority": ma}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Mission {args.mission_id!r} marked closed -> {archive_path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else repo_root()
    plan_state_root = root / "reports" / "plan_state"
    if not plan_state_root.is_dir():
        print("No missions archived yet.")
        return 0

    rows = []
    for mission_dir in sorted(plan_state_root.iterdir()):
        archive_path = mission_dir / "mission_authority.yaml"
        if not archive_path.is_file():
            continue
        try:
            data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
            ma = data["mission_authority"]
        except Exception as exc:  # noqa: BLE001
            rows.append((mission_dir.name, "UNREADABLE", str(exc)))
            continue
        status = ma.get("_archive_status", "unknown")
        rows.append((ma.get("mission_id", mission_dir.name), status, ma.get("mission_summary", "")[:80]))

    if not rows:
        print("No missions archived yet.")
        return 0

    for mission_id, status, summary in rows:
        print(f"[{status:>6}] {mission_id} - {summary}")
    return 0


def dedupe_missions_by_id(commit_mission_pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Collapse consecutive (sha, mission_id) pairs sharing the same mission_id,
    keeping only the LAST sha of each run — commit count is not mission count
    (a mission can be amended across several commits without its mission_id
    changing). `commit_mission_pairs` must be in chronological (oldest-first)
    order. Returns one (sha, mission_id) pair per distinct mission, in the
    order each mission first appeared.
    """
    if not commit_mission_pairs:
        return []

    result: List[Tuple[str, str]] = []
    current_id = None
    last_sha_for_current = None
    for sha, mission_id in commit_mission_pairs:
        if mission_id != current_id:
            if current_id is not None:
                result.append((last_sha_for_current, current_id))
            current_id = mission_id
        last_sha_for_current = sha
    result.append((last_sha_for_current, current_id))
    return result


def cmd_backfill(args: argparse.Namespace) -> int:
    """One-time backfill: reconstruct reports/plan_state/{mission_id}/mission_authority.yaml
    for every mission_id ever recorded in MISSION_AUTHORITY.yaml's git history.
    The mission matching the CURRENT working-tree root file is marked open;
    every other reconstructed mission is closed.
    """
    root = Path(args.root) if args.root else repo_root()

    log_result = subprocess.run(
        ["git", "log", "--format=%H", "--follow", "--", "MISSION_AUTHORITY.yaml"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    shas = [line.strip() for line in log_result.stdout.splitlines() if line.strip()]
    shas.reverse()  # git log is newest-first; we need chronological (oldest-first)

    pairs: List[Tuple[str, str]] = []
    for sha in shas:
        show_result = subprocess.run(
            ["git", "show", f"{sha}:MISSION_AUTHORITY.yaml"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if show_result.returncode != 0:
            continue
        try:
            data = yaml.safe_load(show_result.stdout)
            mission_id = data["mission_authority"]["mission_id"]
        except Exception:  # noqa: BLE001
            continue
        pairs.append((sha, mission_id))

    deduped = dedupe_missions_by_id(pairs)

    try:
        current_ma = read_root_mission_authority(root)
        current_mission_id = current_ma.get("mission_id")
    except (FileNotFoundError, ValueError):
        current_mission_id = None

    archived = []
    for sha, mission_id in deduped:
        show_result = subprocess.run(
            ["git", "show", f"{sha}:MISSION_AUTHORITY.yaml"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        data = yaml.safe_load(show_result.stdout)
        ma = data["mission_authority"]
        status = "open" if mission_id == current_mission_id else "closed"
        out_path = archive_mission(mission_id, ma, status=status, root=root)
        archived.append((mission_id, status, out_path))

    for mission_id, status, out_path in archived:
        print(f"Backfilled {mission_id!r} (status: {status}) -> {out_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="Repo root override (for tests)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_open = sub.add_parser("open", help="Validate + archive the current root MISSION_AUTHORITY.yaml")
    p_open.add_argument("--mission-id", required=True)
    p_open.set_defaults(func=cmd_open)

    p_close = sub.add_parser("close", help="Mark an archived mission closed")
    p_close.add_argument("--mission-id", required=True)
    p_close.set_defaults(func=cmd_close)

    p_list = sub.add_parser("list", help="List all archived missions")
    p_list.set_defaults(func=cmd_list)

    p_backfill = sub.add_parser(
        "backfill",
        help="One-time: reconstruct archives for every mission in MISSION_AUTHORITY.yaml's git history",
    )
    p_backfill.set_defaults(func=cmd_backfill)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

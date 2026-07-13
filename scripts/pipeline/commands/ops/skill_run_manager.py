"""Skill run record manager — creates and validates source-backed skill invocation records.

A skill run record is a JSON artifact that documents which skills were actually invoked
during an agent operation, including whether each was invoked as a full procedure (following
the SKILL.md) or as inline reasoning (equivalent work, but not through the registered skill).

Only full/partial invocations appear in "Skills invoked:" commit messages.
gap_approved entries document human-approved gap work (requires gap report reference).

This distinction converts undetectable bypass (FU-2 class defect) into documented deviation.

Usage:
  # Create a new pending run record before/during skill execution
  python scripts/pipeline/commands/ops/skill_run_manager.py create \\
    --skills S-48 S-23 --plan lovely-wandering-reef.md

  # Record each skill's invocation detail as you work
  python scripts/pipeline/commands/ops/skill_run_manager.py record-step \\
    --run-id <id> --skill S-01 --type full \\
    --note "Path validated via path_guard.py"

  # Get only the skills valid for "Skills invoked:" (excludes inline_reasoning)
  python scripts/pipeline/commands/ops/skill_run_manager.py get-declared-skills --run-id <id>

  # Validate that declared skills in a commit message match the record
  python scripts/pipeline/commands/ops/skill_run_manager.py validate \\
    --run-id <id> --declared "S-48, S-23, S-01"

  # Finalize a run record after the commit
  python scripts/pipeline/commands/ops/skill_run_manager.py finalize \\
    --run-id <id> --outcome success --commit-sha abc123

  # Find the most recent pending (not finalized) run record
  python scripts/pipeline/commands/ops/skill_run_manager.py find-pending

Exit codes:
  0  success / valid
  1  failure / validation failed
  2  record not found
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from path_utils import repo_rel

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def _default_runs_dir() -> Path:
    """Resolve the records directory.

    SKILL_RUN_RECORDS_DIR overrides the default. This exists so hook tests
    (e.g. test_commit_coauthor_hook.py, which runs commit-msg-skills.sh as a
    subprocess) can isolate themselves from the repo's LIVE pending records —
    without it, any real pending record makes those tests fail spuriously
    (TC-W3H-007).
    """
    env = os.environ.get("SKILL_RUN_RECORDS_DIR")
    if env:
        return Path(env)
    return _REPO_ROOT / "reports" / "skill-runs"


_RUNS_DIR = _default_runs_dir()


def configure(*, runs_dir: Path | str | None = None) -> None:
    """Override the runs directory for testing.

    Call with no arguments to reset to defaults.
    """
    global _RUNS_DIR
    if runs_dir is not None:
        _RUNS_DIR = Path(runs_dir)
    else:
        _RUNS_DIR = _default_runs_dir()


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_record(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _record_path(run_id: str) -> Path:
    return _RUNS_DIR / f"{run_id}.json"


def _parse_declared_skills(declared: str) -> list[str]:
    """Parse 'S-48, S-23, S-01' or '[S-48, S-23]' into ['S-48', 'S-23', 'S-01']."""
    cleaned = declared.strip().strip("[]")
    return [s.strip() for s in cleaned.split(",") if s.strip()]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> int:
    """Create a new pending skill run record."""
    # Accept both space-separated (--skills S-73 S-62) and comma-separated
    # (--skills S-73,S-62) forms. Without this, the comma form stored the
    # literal "S-73,S-62" as ONE skill id and every commit-msg validation
    # mismatched until the record JSON was hand-edited (TC-W3H-008).
    args.skills = [s.strip() for arg in args.skills for s in arg.split(",") if s.strip()]
    now = datetime.now(tz=timezone.utc)
    ts = now.strftime("%Y%m%d-%H%M%S")
    slug = "-".join(s.lower().replace("-", "") for s in args.skills[:2])
    run_id = f"{ts}-{slug}"
    if args.retroactive:
        run_id = f"retroactive-{run_id}"

    record = {
        "run_id": run_id,
        "skills_invoked": args.skills,
        "skill_details": [],
        "plans_referenced": [args.plan] if args.plan else [],
        "pre_conditions_verified": False,
        "outcome": "pending",
        "started_at": now.isoformat().replace("+00:00", "Z"),
        "completed_at": None,
        "commit_sha": None,
        "retroactive": args.retroactive,
        "run_type": getattr(args, "run_type", None) or "unknown",
    }

    out = _record_path(run_id)
    _save_record(out, record)
    print(f"Created skill run record: {run_id}")
    print(f"  File: {repo_rel(out)}")
    return 0


def cmd_record_step(args: argparse.Namespace) -> int:
    """Add a skill step detail to an existing run record."""
    record_file = _record_path(args.run_id)
    if not record_file.exists():
        print(f"ERROR: run record {args.run_id} not found", file=sys.stderr)
        return 2

    # gap_approved requires a gap report reference
    if args.type == "gap_approved" and not args.gap_report:
        print("ERROR: --gap-report is required for gap_approved invocations", file=sys.stderr)
        return 1

    record = _load_record(record_file)
    step = {
        "skill_id": args.skill,
        "invocation_type": args.type,
        "steps_completed": args.steps or "all",
        "files_written": args.files or [],
        "deviation": args.deviation,
    }
    if args.note:
        step["note"] = args.note
    if args.gap_report:
        step["gap_report"] = args.gap_report

    record["skill_details"].append(step)
    _save_record(record_file, record)
    print(f"Recorded step {args.skill} ({args.type}) in run {args.run_id}")
    return 0


def _compute_declared_skills(record: dict) -> list[str]:
    """Return the skills valid for 'Skills invoked:' (full/partial/gap_approved).

    Rules:
    - Skills in skills_invoked with no skill_details entry → assumed full (included).
    - Skills with a skill_details entry of type full/partial/gap_approved → included.
    """
    all_skills: list[str] = record.get("skills_invoked", [])
    return list(all_skills)


def cmd_get_declared_skills(args: argparse.Namespace) -> int:
    """Print the skills valid for 'Skills invoked:' (excludes inline_reasoning)."""
    record_file = _record_path(args.run_id)
    if not record_file.exists():
        print(f"ERROR: run record {args.run_id} not found", file=sys.stderr)
        return 2

    record = _load_record(record_file)
    declared = _compute_declared_skills(record)
    print(", ".join(declared))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate declared skills against the run record. Exit 1 if mismatch."""
    record_file = _record_path(args.run_id)
    if not record_file.exists():
        print(f"ERROR: run record {args.run_id} not found", file=sys.stderr)
        return 2

    record = _load_record(record_file)
    details = record.get("skill_details", [])
    declared_in_msg = set(_parse_declared_skills(args.declared))

    record_skills = set(_compute_declared_skills(record))

    # All skills with any record entry (full, partial, or inline_reasoning)
    all_recorded = {d["skill_id"] for d in details}

    # Skills declared in commit but with NO record entry at all — unverified
    false_positives = declared_in_msg - record_skills - all_recorded

    # Full/partial skills in record but not declared in commit — missing
    false_negatives = record_skills - declared_in_msg

    # inline_reasoning skills in declaration are now allowed (they have a record)
    # They're optional — not declaring them is also fine

    if not false_positives and not false_negatives:
        print(f"VALID: declared skills match run record {args.run_id}")
        return 0

    print(f"MISMATCH: declared skills do not match run record {args.run_id}", file=sys.stderr)
    if false_positives:
        print(f"  Declared but not in record (unverified claims): {sorted(false_positives)}",
              file=sys.stderr)
    if false_negatives:
        print(f"  In record but not declared (missing from message): {sorted(false_negatives)}",
              file=sys.stderr)
    return 1


def cmd_finalize(args: argparse.Namespace) -> int:
    """Mark a run record as complete and link it to a commit SHA."""
    record_file = _record_path(args.run_id)
    if not record_file.exists():
        print(f"ERROR: run record {args.run_id} not found", file=sys.stderr)
        return 2

    record = _load_record(record_file)
    record["outcome"] = args.outcome
    record["completed_at"] = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    if args.commit_sha:
        record["commit_sha"] = args.commit_sha

    _save_record(record_file, record)
    print(f"Finalized run {args.run_id}: outcome={args.outcome}, commit={args.commit_sha or '—'}")
    return 0


def cmd_find_pending(args: argparse.Namespace) -> int:
    """Print the most recent pending (outcome=pending) run record ID.

    Ignores records older than ``--max-age-hours`` (default 48) to prevent
    stale records from prior sessions blocking commits in new sessions.
    A record is considered stale when its ``started_at`` timestamp is more
    than ``max_age_hours`` in the past.  Stale records are printed to stderr
    as warnings but not returned as the active pending record.
    """
    _RUNS_DIR.mkdir(parents=True, exist_ok=True)
    max_age = getattr(args, "max_age_hours", 48)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=max_age)
    candidates = [
        f for f in sorted(_RUNS_DIR.glob("*.json"), reverse=True)
        if "retroactive" not in f.name
    ]
    for f in candidates:
        try:
            r = _load_record(f)
            if r.get("outcome") != "pending":
                continue
            started_raw = r.get("started_at", "")
            if started_raw:
                try:
                    started = datetime.fromisoformat(started_raw)
                    if started < cutoff:
                        print(
                            f"WARN: skipping stale pending record {r['run_id']!r} "
                            f"(started_at={started_raw}, older than {max_age}h)",
                            file=sys.stderr,
                        )
                        continue
                except ValueError:
                    pass  # Unparseable timestamp — include the record
            print(r["run_id"])
            return 0
        except (json.JSONDecodeError, OSError):
            continue
    # No pending record within the age window
    return 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill_run_manager",
        description="Lifecycle manager for skill run records.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new pending skill run record")
    p_create.add_argument("--skills", nargs="+", required=True, help="Skill IDs to be invoked")
    p_create.add_argument("--plan", default="", help="Plan reference")
    p_create.add_argument("--retroactive", action="store_true",
                          help="Mark as retroactive (documents a past execution)")
    p_create.add_argument(
        "--run-type",
        dest="run_type",
        default="unknown",
        choices=["full-s84", "reference-only", "knowledge-only", "targeted", "harness", "unknown"],
        help="Run type label for this skill run (default: unknown). "
             "Missing run_type in existing records is tolerated (backward compatible).",
    )

    # record-step
    p_step = sub.add_parser("record-step", help="Add skill step detail to a run record")
    p_step.add_argument("--run-id", required=True)
    p_step.add_argument("--skill", required=True, help="Skill ID (e.g. S-48)")
    p_step.add_argument("--type", required=True,
                        choices=["full", "partial", "gap_approved"],
                        help="How this skill was invoked (gap_approved requires --gap-report)")
    p_step.add_argument("--steps", default="", help="Which steps were completed (e.g. '1-9' or 'all')")
    p_step.add_argument("--files", nargs="*", default=[], help="Files written by this skill")
    p_step.add_argument("--note", default="", help="Explanation note")
    p_step.add_argument("--deviation", action="store_true", help="Flag this as a deviation")
    p_step.add_argument("--gap-report", default="", help="Path to gap escalation report (required for gap_approved type)")

    # get-declared-skills
    p_gds = sub.add_parser("get-declared-skills",
                            help="Print skills valid for 'Skills invoked:' (excludes inline_reasoning)")
    p_gds.add_argument("--run-id", required=True)

    # validate
    p_val = sub.add_parser("validate",
                            help="Validate declared skills against run record (exit 1 on mismatch)")
    p_val.add_argument("--run-id", required=True)
    p_val.add_argument("--declared", required=True,
                        help="The 'Skills invoked:' string from the commit message")

    # finalize
    p_fin = sub.add_parser("finalize", help="Mark run as complete")
    p_fin.add_argument("--run-id", required=True)
    p_fin.add_argument("--outcome", required=True, choices=["success", "failure", "partial"])
    p_fin.add_argument("--commit-sha", default="")

    # find-pending
    p_fp = sub.add_parser("find-pending", help="Print most recent pending run record ID")
    p_fp.add_argument(
        "--max-age-hours",
        dest="max_age_hours",
        type=float,
        default=48.0,
        help="Ignore pending records older than this many hours (default: 48). "
             "Prevents stale records from prior sessions blocking new-session commits.",
    )

    args = parser.parse_args(argv)
    dispatch = {
        "create": cmd_create,
        "record-step": cmd_record_step,
        "get-declared-skills": cmd_get_declared_skills,
        "validate": cmd_validate,
        "finalize": cmd_finalize,
        "find-pending": cmd_find_pending,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
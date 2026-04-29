"""skill_context.py — Active-skill state machine for governance enforcement.

Tracks which skill is currently active via a marker file at
``reports/skill-context/ACTIVE.json``.  PreToolUse hooks read this marker
to verify that governed file edits happen inside a skill context.

Usage:
  # Start a skill context (typically at the top of a skill's Steps)
  python scripts/pipeline/skill_context.py begin \\
    --skill S-20 --scope "content/docs.aspose.org/en/words/python/*"

  # Check whether a file is within the active scope
  python scripts/pipeline/skill_context.py check --file <path>

  # Print the current active skill (exit 2 if none)
  python scripts/pipeline/skill_context.py current

  # End the skill context
  python scripts/pipeline/skill_context.py end --skill S-20 --status completed

  # Create a gap-approved temporary context (30-min TTL)
  python scripts/pipeline/skill_context.py gap \\
    --task "description" --report reports/skill-gaps/2026-04-16-foo.md

Exit codes:
  0  success / file in scope
  1  failure / file out of scope / validation error
  2  no active context
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from path_utils import repo_rel

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTEXT_DIR = _REPO_ROOT / "reports" / "skill-context"
_ACTIVE_FILE = _CONTEXT_DIR / "ACTIVE.json"
_HISTORY_DIR = _CONTEXT_DIR / "history"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _CONTEXT_DIR, _ACTIVE_FILE, _HISTORY_DIR
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTEXT_DIR = _REPO_ROOT / "reports" / "skill-context"
    _ACTIVE_FILE = _CONTEXT_DIR / "ACTIVE.json"
    _HISTORY_DIR = _CONTEXT_DIR / "history"

# Stale-context guard: auto-expire after this duration
_MAX_CONTEXT_AGE = timedelta(hours=2)
_GAP_TTL = timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _load_active() -> dict | None:
    """Load ACTIVE.json if it exists and is not stale. Returns None if absent or expired."""
    if not _ACTIVE_FILE.exists():
        return None
    try:
        with open(_ACTIVE_FILE, encoding="utf-8") as f:
            record = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Check staleness
    started = record.get("started_at", "")
    try:
        start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        # Unparseable timestamp — treat as stale
        _archive_stale(record)
        return None

    # Check TTL for gap-approved contexts
    if record.get("context_type") == "gap_approved":
        ttl = _GAP_TTL
    else:
        ttl = _MAX_CONTEXT_AGE

    if _now() - start_dt > ttl:
        _archive_stale(record)
        return None

    return record


def _save_active(record: dict) -> None:
    _CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _archive(record: dict, status: str = "completed") -> None:
    """Move active context to history."""
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    record["ended_at"] = _now().isoformat().replace("+00:00", "Z")
    record["end_status"] = status
    ts = _now().strftime("%Y%m%d-%H%M%S")
    skill = record.get("skill_id", "unknown")
    out = _HISTORY_DIR / f"{ts}-{skill}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    if _ACTIVE_FILE.exists():
        _ACTIVE_FILE.unlink()


def _archive_stale(record: dict) -> None:
    """Archive a stale context (expired TTL)."""
    _archive(record, status="stale_expired")


def _normalize_path(p: str) -> str:
    """Normalize a path to forward-slash repo-relative form."""
    p = p.replace("\\", "/")
    # Strip absolute prefix if present
    try:
        rel = str(Path(p).resolve().relative_to(_REPO_ROOT.resolve()))
        return rel.replace("\\", "/")
    except (ValueError, OSError):
        return p


def _file_in_scope(file_path: str, scope_patterns: list[str]) -> bool:
    """Check if a file matches any scope pattern (glob-style)."""
    normalized = _normalize_path(file_path)
    for pattern in scope_patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_begin(args: argparse.Namespace) -> int:
    """Start a new skill context."""
    # DAR prerequisite gate — enforced by default (SR-04).
    # Use --skip-dar for bootstrap/recovery only.
    skip_dar = getattr(args, "skip_dar", False)
    if not skip_dar:
        dar_script = _REPO_ROOT / "scripts" / "pipeline" / "check_dar_prerequisites.py"
        if dar_script.exists():
            result = subprocess.run(
                [sys.executable, str(dar_script), "--skill", args.skill],
                capture_output=False,
            )
            if result.returncode == 1:
                print(
                    f"DAR gate blocked: skill {args.skill} prerequisites not satisfied. "
                    "Run required upstream skills first.",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                f"WARN: check_dar_prerequisites.py not found at {dar_script} -- skipping DAR check",
                file=sys.stderr,
            )

    existing = _load_active()
    if existing:
        # Clean up stale context from a crashed prior skill
        print(f"WARNING: Cleaning up prior active context for {existing.get('skill_id')}", file=sys.stderr)
        _archive(existing, status="superseded")

    scope = [s.strip() for s in args.scope.split(",") if s.strip()] if args.scope else ["*"]

    record = {
        "skill_id": args.skill,
        "context_type": "skill",
        "scope_patterns": scope,
        "started_at": _now().isoformat().replace("+00:00", "Z"),
    }
    _save_active(record)
    print(f"Skill context started: {args.skill} (scope: {scope})")
    return 0


def cmd_end(args: argparse.Namespace) -> int:
    """End the active skill context."""
    active = _load_active()
    if not active:
        print("WARNING: No active skill context to end.", file=sys.stderr)
        return 0

    if active.get("skill_id") != args.skill:
        print(f"WARNING: Active skill is {active.get('skill_id')}, not {args.skill}. Ending anyway.",
              file=sys.stderr)

    _archive(active, status=args.status)
    print(f"Skill context ended: {args.skill} ({args.status})")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Check if a file is within the active skill context scope. Exit 0=in scope, 1=out, 2=no context."""
    active = _load_active()
    if not active:
        print("No active skill context.", file=sys.stderr)
        return 2

    scope = active.get("scope_patterns", [])
    if _file_in_scope(args.file, scope):
        return 0
    else:
        print(f"File {args.file} is outside active skill {active.get('skill_id')} scope.", file=sys.stderr)
        return 1


def cmd_current(args: argparse.Namespace) -> int:
    """Print current active skill ID. Exit 2 if no active context."""
    active = _load_active()
    if not active:
        return 2

    skill = active.get("skill_id", "unknown")
    ctx_type = active.get("context_type", "skill")
    print(f"{skill} ({ctx_type})")
    return 0


def cmd_gap(args: argparse.Namespace) -> int:
    """Create a temporary gap-approved context with 30-min TTL."""
    if not args.report:
        print("ERROR: --report is required for gap-approved contexts.", file=sys.stderr)
        return 1

    # Verify the gap report exists
    report_path = Path(args.report)
    if not report_path.exists():
        # Try repo-relative
        report_path = _REPO_ROOT / args.report
    if not report_path.exists():
        print(f"ERROR: Gap report not found: {args.report}", file=sys.stderr)
        return 1

    existing = _load_active()
    if existing:
        _archive(existing, status="superseded_by_gap")

    scope = [s.strip() for s in args.scope.split(",") if s.strip()] if args.scope else ["*"]

    record = {
        "skill_id": "GAP-APPROVED",
        "context_type": "gap_approved",
        "task": args.task,
        "gap_report": str(report_path),
        "scope_patterns": scope,
        "started_at": _now().isoformat().replace("+00:00", "Z"),
        "ttl_minutes": 30,
    }
    _save_active(record)
    print(f"Gap-approved context started (30-min TTL): {args.task}")
    print(f"  Report: {args.report}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill_context",
        description="Active-skill state machine for governance enforcement.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # begin
    p_begin = sub.add_parser("begin", help="Start a skill context")
    p_begin.add_argument("--skill", required=True, help="Skill ID (e.g. S-20)")
    p_begin.add_argument("--scope", default="*",
                         help="Comma-separated glob patterns for allowed file paths")
    p_begin.add_argument("--skip-dar", action="store_true", dest="skip_dar",
                         help="Skip DAR prerequisite check (bootstrap/recovery only)")
    # Backwards compatibility: --check-dar is a no-op (DAR is now the default)
    p_begin.add_argument("--check-dar", action="store_true", dest="check_dar_legacy",
                         help=argparse.SUPPRESS)

    # end
    p_end = sub.add_parser("end", help="End the active skill context")
    p_end.add_argument("--skill", required=True, help="Skill ID to end")
    p_end.add_argument("--status", default="completed",
                       choices=["completed", "failed", "aborted"],
                       help="How the skill ended")

    # check
    p_check = sub.add_parser("check", help="Check if a file is in active scope")
    p_check.add_argument("--file", required=True, help="File path to check")

    # current
    sub.add_parser("current", help="Print current active skill ID")

    # gap
    p_gap = sub.add_parser("gap", help="Create gap-approved temporary context")
    p_gap.add_argument("--task", required=True, help="Description of the gap work")
    p_gap.add_argument("--report", required=True, help="Path to the gap escalation report")
    p_gap.add_argument("--scope", default="*",
                       help="Comma-separated glob patterns for allowed file paths")

    args = parser.parse_args(argv)
    dispatch = {
        "begin": cmd_begin,
        "end": cmd_end,
        "check": cmd_check,
        "current": cmd_current,
        "gap": cmd_gap,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())

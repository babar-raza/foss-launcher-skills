"""Active-skill context state machine for governance enforcement.

This standalone port tracks the active skill in
``reports/skill-context/ACTIVE.json``. Hooks and verification tools can use it
to prove that governed edits happen inside an explicit skill context.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTEXT_DIR = _REPO_ROOT / "reports" / "skill-context"
_ACTIVE_FILE = _CONTEXT_DIR / "ACTIVE.json"
_HISTORY_DIR = _CONTEXT_DIR / "history"

_MAX_CONTEXT_AGE = timedelta(hours=2)
_GAP_TTL = timedelta(minutes=30)


def configure(*, repo_root: Path | str | None = None) -> None:
    """Override module paths for tests."""

    global _REPO_ROOT, _CONTEXT_DIR, _ACTIVE_FILE, _HISTORY_DIR
    _REPO_ROOT = Path(repo_root).resolve() if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTEXT_DIR = _REPO_ROOT / "reports" / "skill-context"
    _ACTIVE_FILE = _CONTEXT_DIR / "ACTIVE.json"
    _HISTORY_DIR = _CONTEXT_DIR / "history"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _save_active(record: dict) -> None:
    _CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    _ACTIVE_FILE.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _archive(record: dict, status: str = "completed") -> None:
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record["ended_at"] = _now().isoformat().replace("+00:00", "Z")
    record["end_status"] = status
    skill = record.get("skill_id", "unknown")
    out = _HISTORY_DIR / f"{_now().strftime('%Y%m%d-%H%M%S')}-{skill}.json"
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if _ACTIVE_FILE.exists():
        _ACTIVE_FILE.unlink()


def _load_active() -> dict | None:
    if not _ACTIVE_FILE.exists():
        return None
    try:
        record = json.loads(_ACTIVE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    try:
        started = datetime.fromisoformat(str(record.get("started_at", "")).replace("Z", "+00:00"))
    except ValueError:
        _archive(record, "stale_expired")
        return None

    ttl = _GAP_TTL if record.get("context_type") == "gap_approved" else _MAX_CONTEXT_AGE
    if _now() - started > ttl:
        _archive(record, "stale_expired")
        return None
    return record


def _normalize_path(path: str) -> str:
    raw = path.replace("\\", "/")
    try:
        return str(Path(raw).resolve().relative_to(_REPO_ROOT.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return raw


def _file_in_scope(file_path: str, scope_patterns: list[str]) -> bool:
    normalized = _normalize_path(file_path)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in scope_patterns)


def cmd_begin(args: argparse.Namespace) -> int:
    active = _load_active()
    if active:
        _archive(active, "superseded")

    scope = [part.strip() for part in args.scope.split(",") if part.strip()] if args.scope else ["*"]
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
    active = _load_active()
    if not active:
        print("WARNING: No active skill context to end.")
        return 0
    _archive(active, args.status)
    print(f"Skill context ended: {args.skill} ({args.status})")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    active = _load_active()
    if not active:
        print("No active skill context.")
        return 2
    if _file_in_scope(args.file, active.get("scope_patterns", [])):
        return 0
    print(f"File {args.file} is outside active skill {active.get('skill_id')} scope.")
    return 1


def cmd_current(args: argparse.Namespace) -> int:
    active = _load_active()
    if not active:
        return 2
    print(f"{active.get('skill_id', 'unknown')} ({active.get('context_type', 'skill')})")
    return 0


def cmd_gap(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    if not report_path.exists():
        report_path = _REPO_ROOT / args.report
    if not report_path.exists():
        print(f"ERROR: Gap report not found: {args.report}")
        return 1

    active = _load_active()
    if active:
        _archive(active, "superseded_by_gap")

    scope = [part.strip() for part in args.scope.split(",") if part.strip()] if args.scope else ["*"]
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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill_context")
    sub = parser.add_subparsers(dest="command", required=True)

    begin = sub.add_parser("begin")
    begin.add_argument("--skill", required=True)
    begin.add_argument("--scope", default="*")
    begin.add_argument("--skip-dar", action="store_true", help="Accepted for compatibility; no-op in standalone helper.")
    begin.add_argument("--check-dar", action="store_true", help=argparse.SUPPRESS)

    end = sub.add_parser("end")
    end.add_argument("--skill", required=True)
    end.add_argument("--status", default="completed", choices=["completed", "failed", "aborted"])

    check = sub.add_parser("check")
    check.add_argument("--file", required=True)

    sub.add_parser("current")

    gap = sub.add_parser("gap")
    gap.add_argument("--task", required=True)
    gap.add_argument("--report", required=True)
    gap.add_argument("--scope", default="*")

    args = parser.parse_args(argv)
    return {
        "begin": cmd_begin,
        "end": cmd_end,
        "check": cmd_check,
        "current": cmd_current,
        "gap": cmd_gap,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())

# Adapted from aspose.org
"""session_logger.py — Log skill invocations to session records.

Pipeline scripts can call log_invocation() to record that a skill was executed.
Agents can also call this CLI to log attested invocations manually.

Records are written to reports/session-invocations/YYYY-MM-DD-{pid}.jsonl
and read by scripts/ci/checks/extract_session_skills.py to auto-populate commit messages.

Usage (Python import):
  from session_logger import log_invocation
  log_invocation("S-23", "content-check", args=["--files", "page.md"])

Usage (CLI):
  python scripts/pipeline/commands/ops/session_logger.py log --skill S-23 --name content-check
  python scripts/pipeline/commands/ops/session_logger.py log --skill S-23 --name content-check --exit-code 0 --verified

Exit codes:
  0  Always succeeds (logging failures are non-fatal)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent.parent)))
_SESSION_DIR = _REPO_ROOT / "reports" / "session-invocations"

_LOG_FILE: Path | None = None


def _get_log_file() -> Path:
    global _LOG_FILE
    if _LOG_FILE is None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pid = os.getpid()
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _LOG_FILE = _SESSION_DIR / f"{today}-{pid}.jsonl"
    return _LOG_FILE


def log_invocation(
    skill_id: str,
    skill_name: str = "",
    args: list[str] | None = None,
    exit_code: int = 0,
    verified: bool = True,
) -> None:
    """Append a skill invocation record to the session log.

    Args:
        skill_id:   The S-{n} skill ID (e.g., "S-23")
        skill_name: Human-readable skill name (e.g., "content-check")
        args:       CLI arguments passed to the skill
        exit_code:  Exit code of the invocation (0 = success)
        verified:   True = logged by pipeline code; False = manually attested
    """
    record = {
        "skill_id": skill_id.upper(),
        "skill_name": skill_name,
        "invoked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "args": args or [],
        "exit_code": exit_code,
        "verified": verified,
        "pid": os.getpid(),
    }
    try:
        log_file = _get_log_file()
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
    except OSError:
        pass  # Non-fatal — logging failures must not break pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="session_logger",
        description="Log skill invocations to session records.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_log = sub.add_parser("log", help="Log a skill invocation")
    p_log.add_argument("--skill", required=True, help="Skill ID (e.g., S-23)")
    p_log.add_argument("--name", default="", help="Skill name")
    p_log.add_argument("--exit-code", type=int, default=0, dest="exit_code")
    p_log.add_argument("--verified", action="store_true", default=False,
                       help="Mark as verified (logged by code, not attested manually)")
    p_log.add_argument("--args", nargs="*", default=[])

    p_show = sub.add_parser("show", help="Show today's logged invocations")

    args = parser.parse_args(argv)

    if args.command == "log":
        log_invocation(
            skill_id=args.skill,
            skill_name=args.name,
            args=args.args,
            exit_code=args.exit_code,
            verified=args.verified,
        )
        log_file = _get_log_file()
        print(f"Logged: {args.skill} ({args.name}) -> {log_file.relative_to(_REPO_ROOT)}")

    elif args.command == "show":
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        found = False
        for log_file in sorted(_SESSION_DIR.glob(f"{today}-*.jsonl")):
            found = True
            print(f"\n=== {log_file.name} ===")
            with log_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        verified_str = "verified" if rec.get("verified") else "attested"
                        print(f"  {rec['skill_id']} ({rec.get('skill_name', '')})"
                              f" [{verified_str}] exit={rec.get('exit_code', '?')}"
                              f" at {rec.get('invoked_at', '?')}")
        if not found:
            print(f"No session logs found for {today}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

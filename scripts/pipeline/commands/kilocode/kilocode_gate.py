# Adapted from aspose.org
"""Kilo Code gate: enforce skill-first execution and rule compliance.

This script provides pre-execution validation for Kilo Code to ensure
it follows repository-specific rules (AGENTS.md §6a).

Usage:
    python scripts/pipeline/commands/kilocode/kilocode_gate.py skill-first <request-type> <content-involved>
    python scripts/pipeline/commands/kilocode/kilocode_gate.py path <file-path>
    python scripts/pipeline/commands/kilocode/kilocode_gate.py skill <skill-name>

Exit codes:
    0  ALLOW - request is permitted
    1  DENY  - request is forbidden
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent


def check_skill_first(request_type: str, content_involved: bool) -> tuple[bool, str]:
    """Enforce skill-first execution for content work (AGENTS.md §6a).

    Args:
        request_type: Type of request (generate, edit, update, etc.)
        content_involved: Whether the request involves content files

    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    if content_involved and request_type in ("generate", "edit", "update"):
        return False, "Content work must use registered skills (AGENTS.md §6a)"
    return True, "OK"


def check_forbidden_path(file_path: str) -> tuple[bool, str]:
    """Check if file_path is in a forbidden path using path_guard.py.

    Args:
        file_path: Path to check

    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    result = subprocess.run(
        ["python", "scripts/pipeline/commands/governance/path_guard.py", file_path],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT)
    )
    if result.returncode == 0:
        return True, "ALLOWED"
    return False, result.stdout.strip()


def check_skill_exists(skill_name: str) -> tuple[bool, str]:
    """Check if skill_name is a registered skill in .kilocode/skills/.

    Args:
        skill_name: Name of the skill to check

    Returns:
        Tuple of (exists: bool, reason: str)
    """
    skills_dir = _REPO_ROOT / ".kilocode" / "skills"
    skill_file = skills_dir / skill_name / "SKILL.md"
    if skill_file.exists():
        return True, "OK"
    return False, f"Unknown skill: {skill_name}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kilocode_gate",
        description="Pre-execution gate for Kilo Code rule enforcement."
    )
    parser.add_argument("command", choices=["skill-first", "path", "skill"],
                        help="Type of check to perform")
    parser.add_argument("args", nargs="*", help="Arguments for the check")
    args = parser.parse_args(argv)

    if args.command == "skill-first":
        if len(args.args) < 2:
            print("Usage: kilocode_gate.py skill-first <request-type> <content-involved>",
                  file=sys.stderr)
            return 1
        allowed, reason = check_skill_first(args.args[0], args.args[1].lower() == "content")
    elif args.command == "path":
        if len(args.args) < 1:
            print("Usage: kilocode_gate.py path <file-path>", file=sys.stderr)
            return 1
        allowed, reason = check_forbidden_path(args.args[0])
    elif args.command == "skill":
        if len(args.args) < 1:
            print("Usage: kilocode_gate.py skill <skill-name>", file=sys.stderr)
            return 1
        allowed, reason = check_skill_exists(args.args[0])
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    print(f"{'ALLOW' if allowed else 'DENY'}: {reason}")
    return 0 if allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())

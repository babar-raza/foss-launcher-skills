# Adapted from aspose.org
"""Skill contract validation: verify skill invocations before execution.

This script validates skill invocations against registered skills and
their specifications before execution.

Usage:
    python scripts/pipeline/commands/kilocode/kilocode_skill_validator.py <skill-name> <arg1> [arg2 ...]

Exit codes:
    0  VALID - skill invocation is valid
    1  INVALID - skill invocation has issues
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent


def load_registered_skills() -> Dict[str, dict]:
    """Load registered skills from .kilocode/skills/.

    Returns:
        Dict mapping skill names to their specifications
    """
    skills_dir = _REPO_ROOT / ".kilocode" / "skills"
    skills = {}

    if not skills_dir.exists():
        return skills

    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skills[skill_dir.name] = {
                    "path": skill_file,
                    "exists": True
                }

    return skills


def extract_skill_args(skill_file: Path) -> str:
    """Extract args specification from skill file.

    Args:
        skill_file: Path to the skill's SKILL.md file

    Returns:
        Args specification string
    """
    with open(skill_file, encoding="utf-8") as f:
        content = f.read()

    # Look for args: line in the skill file
    match = re.search(r"^args:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def validate_args(args: List[str], expected_args: str) -> bool:
    """Validate arguments match expected format.

    Args:
        args: List of provided arguments
        expected_args: Expected args specification from skill file

    Returns:
        True if arguments are valid
    """
    # Count placeholders in expected args (e.g., {family} {platform} = 2)
    placeholder_count = len(re.findall(r"\{[^}]+\}", expected_args))

    # Check if we have at least the required number of arguments
    return len(args) >= placeholder_count


def check_preconditions(preconditions: List[str]) -> bool:
    """Check if preconditions are met.

    Args:
        preconditions: List of precondition descriptions

    Returns:
        True if all preconditions are met
    """
    # For now, return True - actual checks would be implemented
    # This would check things like upstream skills being ready
    return True


def is_upstream_ready(upstream: str) -> bool:
    """Check if upstream skill is ready.

    Args:
        upstream: Name of the upstream skill

    Returns:
        True if upstream skill is ready
    """
    # For now, return True - actual checks would be implemented
    # This would check if the upstream skill was invoked in this session
    return True


def validate_skill_invocation(skill_name: str, args: List[str]) -> Tuple[bool, str]:
    """Validate skill invocation against registered skills.

    Args:
        skill_name: Name of the skill to invoke
        args: List of arguments for the skill

    Returns:
        Tuple of (valid: bool, reason: str)
    """
    skills = load_registered_skills()

    if skill_name not in skills:
        return False, f"Unknown skill: {skill_name}"

    # Load skill spec
    skill_file = skills[skill_name]["path"]
    expected_args = extract_skill_args(skill_file)

    if not validate_args(args, expected_args):
        return False, f"Invalid arguments for {skill_name}. Expected: {expected_args}"

    # Check dependency chain (DAR table)
    # This would read AGENTS.md §6a DAR table
    # For now, return True
    return True, "OK"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kilocode_skill_validator",
        description="Skill contract validation for Kilo Code."
    )
    parser.add_argument("skill_name", help="Name of the skill to invoke")
    parser.add_argument("args", nargs="*", help="Arguments for the skill")
    args = parser.parse_args(argv)

    valid, reason = validate_skill_invocation(args.skill_name, args.args)

    print(f"{'VALID' if valid else 'INVALID'}: {reason}")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

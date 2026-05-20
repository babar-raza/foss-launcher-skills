# Adapted from aspose.org
"""Skill chain verification: validate skill dependency chains.

This module verifies that skill chains follow the correct dependency
order as defined in AGENTS.md §6a (DAR table).

Usage:
    python scripts/pipeline/commands/kilocode/kilocode_skill_chain.py <skill1> <skill2> ...

Exit codes:
    0  VALID - skill chain is valid
    1  INVALID - skill chain has issues
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent


def load_dar_table() -> Dict[str, str]:
    """Load DAR table from child doc (preferred) or AGENTS.md §6a (fallback).

    Returns:
        Dict mapping downstream skills to their required upstream skills
    """
    child_doc = _REPO_ROOT / "docs" / "governance" / "dar-table.md"
    agents_file = _REPO_ROOT / "AGENTS.md"
    dar_table: Dict[str, str] = {}

    if child_doc.exists():
        with open(child_doc, encoding="utf-8") as f:
            content = f.read()
    elif agents_file.exists():
        import logging
        logging.warning("FALLBACK: reading DAR from AGENTS.md — child doc missing")
        with open(agents_file, encoding="utf-8") as f:
            content = f.read()
    else:
        return dar_table

    # Find the DAR table section
    table_start = content.find("| Downstream skill")
    if table_start == -1:
        return dar_table

    # Find the end of the table (next table or section)
    table_end = content.find("---", table_start + 100)
    if table_end == -1:
        table_end = len(content)

    table_content = content[table_start:table_end]

    # Parse table rows
    for line in table_content.split("\n"):
        if "|" in line and "Downstream" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                downstream = parts[1].strip("`").strip()
                upstream = parts[2].strip("`").strip()
                if downstream and upstream:
                    dar_table[downstream] = upstream

    return dar_table


def get_upstream_skills(skill: str) -> List[str]:
    """Get upstream skills for a skill from the DAR table.

    Args:
        skill: Name of the skill

    Returns:
        List of upstream skill names
    """
    dar_table = load_dar_table()
    upstream = dar_table.get(skill, "")
    return [upstream] if upstream else []


def verify_skill_chain(chain: List[str]) -> Tuple[bool, List[str]]:
    """Verify that a skill chain is valid and complete.

    Args:
        chain: List of skill names in execution order

    Returns:
        Tuple of (valid: bool, issues: List[str])
    """
    issues: List[str] = []

    # Check all skills exist
    skills_dir = _REPO_ROOT / ".kilocode" / "skills"
    for skill in chain:
        skill_file = skills_dir / skill / "SKILL.md"
        if not skill_file.exists():
            issues.append(f"Unknown skill in chain: {skill}")

    # Check dependency chain (DAR table)
    for i, skill in enumerate(chain):
        upstream = get_upstream_skills(skill)
        for up in upstream:
            if up and up not in chain[:i]:
                issues.append(f"Missing upstream skill {up} before {skill}")

    return len(issues) == 0, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kilocode_skill_chain",
        description="Skill chain verification for Kilo Code."
    )
    parser.add_argument("skills", nargs="+", help="Skill names in execution order")
    args = parser.parse_args(argv)

    valid, issues = verify_skill_chain(args.skills)

    if valid:
        print("PASS: Skill chain is valid")
        return 0
    else:
        print("FAIL: Skill chain has issues:")
        for issue in issues:
            print(f"  - {issue}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

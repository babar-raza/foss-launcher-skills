# Adapted from aspose.org
#!/usr/bin/env python3
"""DAR prerequisite enforcer — checks if upstream skill prerequisites are satisfied.

Reads the DAR table from docs/governance/dar-table.md §6a and verifies that required upstream skills
have been invoked in the current session (via skill run records in reports/skill-runs/).

This script enforces the Downstream Activation Rules at runtime: a downstream skill
cannot begin its context unless all required upstream skills have a session run record.

Usage:
    python scripts/pipeline/commands/governance/check_dar_prerequisites.py --skill S-21
    python scripts/pipeline/commands/governance/check_dar_prerequisites.py --skill page-enhance

Exit codes:
    0  All prerequisites satisfied (or skill has no DAR prerequisites)
    1  One or more prerequisites not satisfied in current session
    2  DAR table cannot be read or skill not found — fail-open (caller should proceed)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_DAR_TABLE = _REPO_ROOT / "docs" / "governance" / "dar-table.md"
_RUNS_DIR = _REPO_ROOT / "reports" / "skill-runs"


def configure(
    *,
    dar_table: "Path | str | None" = None,
    runs_dir: "Path | str | None" = None,
) -> None:
    """Override module-level path constants for testing."""
    global _DAR_TABLE, _RUNS_DIR
    if dar_table is not None:
        _DAR_TABLE = Path(dar_table)
    if runs_dir is not None:
        _RUNS_DIR = Path(runs_dir)


# ---------------------------------------------------------------------------
# DAR table parsing (mirrors check_dar_coverage.py logic, kept local to avoid
# cross-package imports between scripts/ci and scripts/pipeline)
# ---------------------------------------------------------------------------

def _parse_dar_table(text: str) -> list[tuple[str, str, str]]:
    """Extract (downstream, upstream, trigger) triples from the DAR table."""
    rows = []
    in_table = False
    for line in text.splitlines():
        if "| Downstream skill |" in line:
            in_table = True
            continue
        if in_table and "---" in line:
            continue
        if in_table and line.startswith("|"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 3:
                rows.append((cols[0], cols[1], cols[2]))
        elif in_table and not line.startswith("|"):
            in_table = False
    return rows


def _extract_identifiers(cell: str) -> list[str]:
    """Extract all S-IDs and slug names from a DAR table cell."""
    s_ids = re.findall(r"S-\d+", cell)
    slugs = re.findall(r"/([\w-]+)", cell)
    return list(set(s_ids + slugs))


def _skill_matches(downstream_cell: str, skill_arg: str) -> bool:
    """Return True if skill_arg (S-ID or slug) matches the downstream cell."""
    ids = _extract_identifiers(downstream_cell)
    return skill_arg in ids


def _get_prerequisites(dar_rows: list[tuple[str, str, str]], skill_arg: str) -> list[list[str]]:
    """Return prerequisite groups for skill_arg.

    Each group is a list of alternative identifiers — any ONE satisfies the group.
    The caller must satisfy ALL groups.
    """
    groups = []
    for downstream, upstream, _trigger in dar_rows:
        if _skill_matches(downstream, skill_arg):
            alternatives = _extract_identifiers(upstream)
            if alternatives:
                groups.append(alternatives)
    return groups


# ---------------------------------------------------------------------------
# Session run record scanning
# ---------------------------------------------------------------------------

def _get_session_skills(runs_dir: Path) -> set[str]:
    """Collect all skill identifiers mentioned in any run record in runs_dir."""
    found: set[str] = set()
    if not runs_dir.exists():
        return found
    for f in sorted(runs_dir.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                record = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        for s in record.get("skills_invoked", []):
            if s:
                found.add(s)
        for detail in record.get("skill_details", []):
            sid = detail.get("skill_id", "")
            if sid:
                found.add(sid)
    return found


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def check(skill_arg: str) -> int:
    """Check DAR prerequisites for skill_arg. Returns exit code."""
    # Load AGENTS.md
    try:
        agents_text = _DAR_TABLE.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"WARN: Cannot read dar-table.md: {exc} -- fail-open", file=sys.stderr)
        return 0

    dar_rows = _parse_dar_table(agents_text)
    if not dar_rows:
        print("WARN: DAR table not found in dar-table.md -- fail-open", file=sys.stderr)
        return 0

    prereq_groups = _get_prerequisites(dar_rows, skill_arg)

    if not prereq_groups:
        # Skill not in DAR table, or has no prerequisites -- allowed
        print(f"DAR: {skill_arg} has no DAR prerequisites -- OK")
        return 0

    session_skills = _get_session_skills(_RUNS_DIR)

    missing: list[list[str]] = []
    for alternatives in prereq_groups:
        satisfied = any(alt in session_skills for alt in alternatives)
        if not satisfied:
            missing.append(alternatives)

    if not missing:
        print(f"DAR: {skill_arg} prerequisites satisfied -- OK")
        return 0

    # Report missing prerequisites
    print(f"DAR PREREQUISITE FAILURE: skill {skill_arg} requires upstream skills not yet run this session.")
    for group in missing:
        if len(group) == 1:
            print(f"  MISSING: {group[0]}")
        else:
            print(f"  MISSING (any one satisfies): {' | '.join(sorted(group))}")
    print(f"\nSession run records checked: {_RUNS_DIR}")
    print(f"Skills found in session: {sorted(session_skills) or '(none)'}")
    print(f"\nTo resolve: run the required upstream skill(s) before invoking {skill_arg}.")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_dar_prerequisites",
        description="Check DAR prerequisites for a skill before execution.",
    )
    parser.add_argument(
        "--skill",
        required=True,
        help="Skill ID (e.g. S-21) or slug (e.g. page-enhance) to check prerequisites for",
    )
    args = parser.parse_args(argv)
    return check(args.skill)


if __name__ == "__main__":
    raise SystemExit(main())

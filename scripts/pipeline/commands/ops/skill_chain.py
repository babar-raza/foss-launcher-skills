# Adapted from aspose.org
"""skill_chain.py — resolve ordered skill execution chain from the DAR table.

Given a target skill, resolves the full prerequisite chain (including transitive
dependencies) from the AGENTS.md DAR table and outputs an ordered execution plan.
This implements the "machine-readable orchestration" part of TC-SR-04.

The script does NOT execute skills — it plans the execution order, enabling
operators to see exactly what must run before their target skill.

Usage:
    python scripts/pipeline/commands/ops/skill_chain.py --skill S-21
    python scripts/pipeline/commands/ops/skill_chain.py --skill page-enhance --check-session

Options:
    --skill SKILL        Skill S-ID (e.g. S-21) or slug (e.g. page-enhance)
    --check-session      Also check which prerequisites are already satisfied
                         in the current session run records; exit 1 if any missing
    --json               Output as JSON instead of human-readable text

Exit codes:
    0  Chain resolved; all prerequisites satisfied (with --check-session)
    0  Chain resolved and displayed (without --check-session)
    1  One or more prerequisites unsatisfied (only with --check-session)
    2  AGENTS.md unreadable or DAR table absent — fail-open
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import os

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent.parent)))

# Import shared DAR logic from check_dar_prerequisites
_GOVERNANCE_DIR = Path(__file__).resolve().parents[1] / "governance"  # commands/ops/ -> commands/governance/
if str(_GOVERNANCE_DIR) not in sys.path:
    sys.path.insert(0, str(_GOVERNANCE_DIR))

from check_dar_prerequisites import (  # noqa: E402
    _parse_dar_table,
    _extract_identifiers,
    _skill_matches,
    _get_prerequisites,
    _get_session_skills,
)

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
# Chain resolution
# ---------------------------------------------------------------------------

def _resolve_chain(
    skill_arg: str,
    dar_rows: list[tuple[str, str, str]],
    visited: "set[str] | None" = None,
) -> list[list[list[str]]]:
    """Resolve the full prerequisite chain for skill_arg, depth-first.

    Returns a list of prerequisite groups in reverse topological order
    (things to run FIRST appear first). Each group is a list of alternatives.

    Cycles are broken by tracking visited skills.
    """
    if visited is None:
        visited = set()

    if skill_arg in visited:
        return []  # cycle guard
    visited = visited | {skill_arg}

    groups = _get_prerequisites(dar_rows, skill_arg)
    chain: list[list[list[str]]] = []

    for group in groups:
        # For each alternative in the group, resolve ITS prerequisites first
        # We use the first alternative to resolve transitively (alternatives
        # are equivalent choices — resolving one is sufficient for planning)
        primary = group[0]
        sub_chain = _resolve_chain(primary, dar_rows, visited)
        chain.extend(sub_chain)
        chain.append(group)

    return chain


def _deduplicate_chain(chain: list[list[list[str]]]) -> list[list[list[str]]]:
    """Remove duplicate prerequisite groups while preserving order."""
    seen: set[str] = set()
    result: list[list[list[str]]] = []
    for group in chain:
        key = "|".join(sorted(str(g) for g in group))
        if key not in seen:
            seen.add(key)
            result.append(group)
    return result


def resolve(skill_arg: str) -> tuple[int, list[list[list[str]]]]:
    """Resolve the full execution chain for skill_arg.

    Returns (exit_code, chain) where chain is ordered list of prerequisite groups.
    exit_code 2 means fail-open (AGENTS.md unreadable).
    """
    try:
        agents_text = _DAR_TABLE.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"WARN: Cannot read dar-table.md: {exc} -- fail-open", file=sys.stderr)
        return 2, []

    dar_rows = _parse_dar_table(agents_text)
    if not dar_rows:
        print("WARN: DAR table not found in dar-table.md -- fail-open", file=sys.stderr)
        return 2, []

    raw_chain = _resolve_chain(skill_arg, dar_rows)
    chain = _deduplicate_chain(raw_chain)
    return 0, chain


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _format_group(group: list[str], step: int, satisfied: "set[str] | None" = None) -> str:
    if len(group) == 1:
        skill = group[0]
        status = ""
        if satisfied is not None:
            status = "  [satisfied]" if skill in satisfied else "  [MISSING]"
        return f"  Step {step}: {skill}{status}"
    else:
        opts = " | ".join(sorted(group))
        any_sat = satisfied is not None and any(s in satisfied for s in group)
        status = ""
        if satisfied is not None:
            status = "  [satisfied]" if any_sat else "  [MISSING — need any one]"
        return f"  Step {step}: ({opts}){status}"


def print_chain(
    skill_arg: str,
    chain: list[list[list[str]]],
    satisfied: "set[str] | None" = None,
    as_json: bool = False,
) -> None:
    if as_json:
        output = {
            "target": skill_arg,
            "prerequisites": [
                {
                    "step": i + 1,
                    "alternatives": group,
                    "satisfied": (
                        any(s in satisfied for s in group) if satisfied is not None else None
                    ),
                }
                for i, group in enumerate(chain)
            ],
        }
        print(json.dumps(output, indent=2))
        return

    if not chain:
        print(f"Skill {skill_arg}: no DAR prerequisites — can run immediately.")
        return

    print(f"Execution chain for {skill_arg} ({len(chain)} prerequisite step(s)):")
    for i, group in enumerate(chain):
        print(_format_group(group, i + 1, satisfied))
    print(f"  Target: {skill_arg}  <-- run this last")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill_chain",
        description="Resolve ordered prerequisite chain for a skill from the DAR table.",
    )
    parser.add_argument(
        "--skill",
        required=True,
        help="Skill S-ID (e.g. S-21) or slug (e.g. page-enhance)",
    )
    parser.add_argument(
        "--check-session",
        action="store_true",
        dest="check_session",
        help="Check which prerequisites are satisfied in the current session; exit 1 if any missing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output as JSON",
    )
    args = parser.parse_args(argv)

    exit_code, chain = resolve(args.skill)
    if exit_code == 2:
        return 2  # fail-open — let caller proceed

    satisfied: "set[str] | None" = None
    missing_count = 0

    if args.check_session:
        satisfied = _get_session_skills(_RUNS_DIR)
        for group in chain:
            if not any(s in satisfied for s in group):
                missing_count += 1

    print_chain(args.skill, chain, satisfied=satisfied, as_json=args.as_json)

    if args.check_session and missing_count > 0:
        print(
            f"\nDAR CHAIN: {missing_count} prerequisite step(s) not yet satisfied in session.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""Anti-drift check: warn when a pipeline script changes without its skill CONTRACT being updated.

Parses CONTRACT comments in skills/ to build a script→skill map, then checks whether
any changed pipeline scripts have a corresponding skill that was NOT also modified in this PR.

Exit codes:
  0 — no unacknowledged drift
  1 — one or more scripts changed without skill CONTRACT update (advisory warning)

Usage (CI):
    python scripts/ci/checks/check_script_skill_sync.py          # auto-detects changed files via git
    python scripts/ci/checks/check_script_skill_sync.py --base main  # diff against specific base branch
    python scripts/ci/checks/check_script_skill_sync.py --files scripts/pipeline/commands/knowledge/index.py  # explicit list

Notes:
- Only BLOCKING when the changed script is the PRIMARY backing script in a CONTRACT comment.
- Changes to scripts not referenced in any CONTRACT are silently ignored (no skill to sync).
- This check is ADVISORY: it reminds authors to update skill docs, but does not block on
  cosmetic script changes that don't alter the documented interface.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))
_SKILLS_DIR = _REPO_ROOT / "skills"
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

# Matches: <!-- CONTRACT: scripts/pipeline/commands/ops/foo.py ... -->
_CONTRACT_RE = re.compile(
    r"<!--\s*CONTRACT:\s*(scripts/[\w/._-]+\.py)",
    re.IGNORECASE,
)


def build_contract_map() -> dict[str, list[str]]:
    """Return {script_path: [skill_slugs]} from CONTRACT comments in skills/."""
    mapping: dict[str, list[str]] = {}
    for skill_file in sorted(_SKILLS_DIR.glob("*.md")):
        if skill_file.stem.lower() == "readme":
            continue
        text = skill_file.read_text(encoding="utf-8", errors="replace")
        for m in _CONTRACT_RE.finditer(text):
            script = m.group(1).strip()
            mapping.setdefault(script, []).append(skill_file.stem)
    return mapping


def get_changed_files(base: str) -> list[str]:
    """Return list of files changed vs base branch using git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        # Fall back to diff against last commit
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_script_skill_sync",
        description="Warn when pipeline scripts change without skill CONTRACT updates.",
    )
    parser.add_argument(
        "--base",
        default="main",
        help="Base branch/ref for git diff (default: main)",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="Explicit list of changed files (overrides git diff)",
    )
    args = parser.parse_args(argv)

    contract_map = build_contract_map()

    changed = args.files if args.files else get_changed_files(args.base)
    changed_set = set(changed)

    # Find changed pipeline scripts that are referenced in CONTRACT comments
    warnings = []
    for changed_file in sorted(changed):
        # Normalize to forward slashes
        cf = changed_file.replace("\\", "/")
        if cf not in contract_map:
            continue  # not a backed script — no skill to sync

        backed_skills = contract_map[cf]
        for slug in backed_skills:
            skill_path = f"skills/{slug}.md"
            if skill_path not in changed_set:
                warnings.append((cf, slug, skill_path))

    if not warnings:
        script_refs = sum(
            1 for f in changed if f.replace("\\", "/") in contract_map
        )
        if script_refs:
            print(
                f"OK: {script_refs} script(s) with CONTRACT references changed — "
                f"all corresponding skills also updated."
            )
        else:
            print("OK: No pipeline scripts with CONTRACT references changed.")
        return 0

    print(f"WARN: {len(warnings)} script→skill sync gap(s) found:")
    for script, slug, skill_path in warnings:
        print(f"  {script}")
        print(f"    backs skill: {slug}")
        print(f"    skill file not updated: {skill_path}")
        print(f"    ACTION: Update CONTRACT comment in {skill_path} if the script")
        print(f"            interface, steps, or postconditions changed.")
    print()
    print("This is an advisory warning. If your script change does not affect")
    print("the documented interface/steps, you may ignore this warning.")
    print("If it does, update the skill CONTRACT comment before merging.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

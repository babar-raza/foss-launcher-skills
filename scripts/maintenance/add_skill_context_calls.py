"""add_skill_context_calls.py — Batch-add skill_context.py begin/end to all skill files.

One-off maintenance script. Reads each skill .md file in skills/, inserts
skill_context.py begin at the start of ## Steps and skill_context.py end at the
end of ## Steps (before the next ## heading or EOF).

Usage:
  python scripts/maintenance/add_skill_context_calls.py [--dry-run]

Arguments:
  --dry-run   Show what would be changed without writing files
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"

# Pattern to extract skill ID from the first # heading
_SKILL_ID_RE = re.compile(r"#\s+S-(\d+)")

# Sentinel text to detect if already instrumented
_SENTINEL = "skill_context.py begin"


def _extract_skill_id(content: str) -> str | None:
    """Extract S-XX from the first heading."""
    m = _SKILL_ID_RE.search(content)
    if m:
        return f"S-{m.group(1)}"
    return None


def _instrument_skill(content: str, skill_id: str) -> str | None:
    """Add begin/end calls around ## Steps. Returns modified content or None if no change."""
    if _SENTINEL in content:
        return None  # Already instrumented

    # Find ## Steps
    steps_match = re.search(r"^## Steps\s*$", content, re.MULTILINE)
    if not steps_match:
        return None  # No Steps section

    steps_pos = steps_match.end()

    # Find the next ## heading after Steps (or EOF)
    next_heading = re.search(r"^## ", content[steps_pos:], re.MULTILINE)
    if next_heading:
        end_pos = steps_pos + next_heading.start()
    else:
        end_pos = len(content)

    # Build the begin block (inserted right after "## Steps\n")
    begin_block = f"""
> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill {skill_id} --scope "*"
> ```

"""

    # Build the end block (inserted before the next heading)
    end_block = f"""
> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill {skill_id} --status completed
> ```

"""

    # Insert begin after ## Steps line
    new_content = content[:steps_pos] + begin_block + content[steps_pos:end_pos].rstrip() + "\n" + end_block + content[end_pos:]
    return new_content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add skill_context.py begin/end to skill files.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args(argv)

    skill_files = sorted(_SKILLS_DIR.glob("*.md"))
    # Exclude README.md
    skill_files = [f for f in skill_files if f.name != "README.md"]

    modified = 0
    skipped = 0
    already = 0

    for skill_file in skill_files:
        content = skill_file.read_text(encoding="utf-8")
        skill_id = _extract_skill_id(content)

        if not skill_id:
            skipped += 1
            if args.dry_run:
                print(f"  SKIP (no S-XX ID): {skill_file.name}")
            continue

        new_content = _instrument_skill(content, skill_id)

        if new_content is None:
            if _SENTINEL in content:
                already += 1
            else:
                skipped += 1
                if args.dry_run:
                    print(f"  SKIP (no Steps section): {skill_file.name}")
            continue

        modified += 1
        if args.dry_run:
            print(f"  MODIFY: {skill_file.name} ({skill_id})")
        else:
            skill_file.write_text(new_content, encoding="utf-8")
            print(f"  Updated: {skill_file.name} ({skill_id})")

    print(f"\nSummary: {modified} modified, {already} already instrumented, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

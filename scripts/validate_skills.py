"""validate_skills.py — CI gate for skill registry integrity.

Checks:
  1. No duplicate skill IDs in registry.yaml
  2. Every skills/{name}.md has a matching registry entry
  3. Every registry entry has a corresponding skills/{name}.md
  4. Every non-internal skill has a .claude/commands/{name}.md that is
     byte-identical to skills/{name}.md (frontmatter stripped)
  5. Non-null script: paths exist on disk (relative to repo root)
  6. Every registry entry has an internal: field (true or false)
  7. No internal skill appears in .claude/commands/

Exit codes:
  0  PASS — all checks passed
  1  FAIL — one or more violations found

Usage:
    python scripts/validate_skills.py [--repo-root <path>]
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def load_registry(registry_path: Path) -> list[dict]:
    with open(registry_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("skills", [])


def check_id_uniqueness(skills: list[dict]) -> list[str]:
    """Return error strings for any duplicate skill IDs."""
    seen: dict[str, str] = {}
    errors = []
    for entry in skills:
        sid = entry.get("id")
        name = entry.get("name", "(unnamed)")
        if sid is None:
            errors.append(f"  MISSING_ID  entry '{name}' has no id field")
            continue
        if sid in seen:
            errors.append(
                f"  DUPLICATE   {sid} claimed by both '{seen[sid]}' and '{name}'"
            )
        else:
            seen[sid] = name
    return errors


def check_registry_vs_files(skills: list[dict], skills_dir: Path) -> list[str]:
    """Return errors for registry entries missing their skill file."""
    errors = []
    for entry in skills:
        name = entry.get("name")
        if not name:
            errors.append(f"  NO_NAME     registry entry id={entry.get('id')} has no name")
            continue
        skill_file = skills_dir / f"{name}.md"
        if not skill_file.exists():
            errors.append(f"  MISSING_FILE  skills/{name}.md not found (registered as {entry.get('id')})")
    return errors


def check_files_vs_registry(skills: list[dict], skills_dir: Path) -> list[str]:
    """Return errors for skill files that have no registry entry."""
    registered_names = {e["name"] for e in skills if e.get("name")}
    errors = []
    for md_file in sorted(skills_dir.glob("*.md")):
        if md_file.name == "registry.yaml":
            continue
        stem = md_file.stem
        if stem not in registered_names:
            errors.append(f"  UNREGISTERED  skills/{md_file.name} has no entry in registry.yaml")
    return errors


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block from markdown text.

    skills/*.md has frontmatter; .claude/commands/*.md is the same content
    with frontmatter stripped.  Comparison must strip before comparing.
    """
    stripped = _FRONTMATTER_RE.sub("", text, count=1)
    # Remove one leading blank line that frontmatter removal may leave
    return stripped.lstrip("\n")


def check_commands_sync(
    skills_dir: Path,
    commands_dir: Path,
    skills: list[dict] | None = None,
) -> list[str]:
    """Return errors for .claude/commands/ files that diverge from skills/ body.

    The commands/ file should equal the skills/ file with frontmatter removed.
    Internal skills (internal: true) must NOT appear in commands/.
    """
    internal_names: set[str] = set()
    if skills:
        internal_names = {e["name"] for e in skills if e.get("internal") and e.get("name")}

    errors = []
    if not commands_dir.exists():
        errors.append(f"  MISSING_DIR  {commands_dir} does not exist")
        return errors

    for skill_file in sorted(skills_dir.glob("*.md")):
        stem = skill_file.stem
        if stem in internal_names:
            # Internal skills must not be in commands — checked separately
            continue
        cmd_file = commands_dir / skill_file.name
        if not cmd_file.exists():
            errors.append(f"  MISSING_CMD  .claude/commands/{skill_file.name} not found")
            continue
        skill_body = _strip_frontmatter(skill_file.read_text(encoding="utf-8"))
        cmd_body = cmd_file.read_text(encoding="utf-8")
        if skill_body != cmd_body:
            errors.append(
                f"  DIFFERS      .claude/commands/{skill_file.name} body "
                f"differs from skills/{skill_file.name}"
            )

    for cmd_file in sorted(commands_dir.glob("*.md")):
        if not (skills_dir / cmd_file.name).exists():
            errors.append(
                f"  EXTRA_CMD    .claude/commands/{cmd_file.name} has no canonical in skills/"
            )
    return errors


def check_script_refs(skills: list[dict], repo_root: Path) -> list[str]:
    """Return errors for non-null script: references that don't exist on disk."""
    errors = []
    for entry in skills:
        script = entry.get("script")
        if not script:
            continue
        script_path = repo_root / script
        if not script_path.exists():
            errors.append(
                f"  MISSING_SCRIPT  {entry.get('id')} ({entry.get('name')}): "
                f"script '{script}' not found"
            )
    return errors


def check_internal_field(skills: list[dict]) -> list[str]:
    """Return errors for entries missing the required internal: boolean field."""
    errors = []
    for entry in skills:
        if "internal" not in entry:
            errors.append(
                f"  MISSING_INTERNAL  {entry.get('id')} ({entry.get('name')}): "
                f"registry entry is missing required 'internal:' field"
            )
        elif not isinstance(entry["internal"], bool):
            errors.append(
                f"  BAD_INTERNAL  {entry.get('id')} ({entry.get('name')}): "
                f"'internal:' must be true or false, got: {entry['internal']!r}"
            )
    return errors


def check_internal_not_in_commands(skills: list[dict], commands_dir: Path) -> list[str]:
    """Return errors for internal skills that appear in .claude/commands/."""
    errors = []
    if not commands_dir.exists():
        return errors
    for entry in skills:
        if not entry.get("internal"):
            continue
        name = entry.get("name")
        if not name:
            continue
        cmd_file = commands_dir / f"{name}.md"
        if cmd_file.exists():
            errors.append(
                f"  INTERNAL_IN_CMD  {entry.get('id')} ({name}): "
                f"internal skill must not appear in .claude/commands/"
            )
    return errors


def run(repo_root: Path) -> int:
    registry_path = repo_root / "skills" / "registry.yaml"
    skills_dir = repo_root / "skills"
    commands_dir = repo_root / ".claude" / "commands"

    if not registry_path.exists():
        print(f"FAIL: skills/registry.yaml not found at {registry_path}")
        return 1

    skills = load_registry(registry_path)

    all_errors: list[tuple[str, list[str]]] = []

    dupes = check_id_uniqueness(skills)
    if dupes:
        all_errors.append(("ID uniqueness", dupes))

    missing_files = check_registry_vs_files(skills, skills_dir)
    if missing_files:
        all_errors.append(("Registry → files", missing_files))

    unregistered = check_files_vs_registry(skills, skills_dir)
    if unregistered:
        all_errors.append(("Files → registry", unregistered))

    internal_field_errors = check_internal_field(skills)
    if internal_field_errors:
        all_errors.append(("Internal field", internal_field_errors))

    internal_cmd_errors = check_internal_not_in_commands(skills, commands_dir)
    if internal_cmd_errors:
        all_errors.append(("Internal in commands", internal_cmd_errors))

    sync_errors = check_commands_sync(skills_dir, commands_dir, skills)
    if sync_errors:
        all_errors.append(("Commands sync", sync_errors))

    script_errors = check_script_refs(skills, repo_root)
    if script_errors:
        all_errors.append(("Script refs", script_errors))

    if not all_errors:
        n_internal = sum(1 for s in skills if s.get("internal"))
        print(
            f"PASS: skill registry valid "
            f"({len(skills)} skills, {n_internal} internal, no violations)"
        )
        return 0

    total = sum(len(errs) for _, errs in all_errors)
    print(f"FAIL: {total} violation(s) found\n")
    for category, errors in all_errors:
        print(f"[{category}]")
        for err in errors:
            print(err)
        print()
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate skill registry integrity.")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root path (default: parent of this script's directory)",
    )
    args = parser.parse_args(argv)

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent

    return run(repo_root)


if __name__ == "__main__":
    sys.exit(main())

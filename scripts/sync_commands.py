"""sync_commands.py — Sync skills/ → .claude/commands/ (and optionally other targets).

The canonical source for all skills is skills/*.md.
Derived targets strip the YAML frontmatter and contain only the skill body.

Derived targets:
  .claude/commands/*.md   — Claude Code slash commands

Usage:
    python scripts/sync_commands.py --check   # diff only; exit 1 if out of sync
    python scripts/sync_commands.py --sync    # overwrite targets from canonical

Exit codes (--check):
  0  in sync
  1  drift detected (run --sync to fix)

Exit codes (--sync):
  0  sync complete (or already in sync)
  1  error during sync
"""
import argparse
import re
import sys
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter and the blank line that typically follows it."""
    stripped = _FRONTMATTER_RE.sub("", text, count=1)
    return stripped.lstrip("\n")


def _derive_body(skill_file: Path) -> str:
    """Read a skills/*.md file and return its body (frontmatter stripped)."""
    return strip_frontmatter(skill_file.read_text(encoding="utf-8"))


def check_sync(skills_dir: Path, commands_dir: Path) -> list[str]:
    """Return a list of human-readable diff descriptions. Empty = in sync."""
    diffs = []

    for skill_file in sorted(skills_dir.glob("*.md")):
        if skill_file.name == "registry.yaml":
            continue
        cmd_file = commands_dir / skill_file.name
        expected_body = _derive_body(skill_file)

        if not cmd_file.exists():
            diffs.append(f"MISSING  .claude/commands/{skill_file.name}")
            continue

        actual_body = cmd_file.read_text(encoding="utf-8")
        if expected_body != actual_body:
            diffs.append(f"DIFFERS  .claude/commands/{skill_file.name}")

    for cmd_file in sorted(commands_dir.glob("*.md")):
        if not (skills_dir / cmd_file.name).exists():
            diffs.append(f"EXTRA    .claude/commands/{cmd_file.name} (no canonical in skills/)")

    return diffs


def do_sync(skills_dir: Path, commands_dir: Path) -> tuple[int, int]:
    """Sync skills/ → .claude/commands/. Returns (synced_count, already_ok_count)."""
    commands_dir.mkdir(parents=True, exist_ok=True)
    synced = 0
    already_ok = 0

    for skill_file in sorted(skills_dir.glob("*.md")):
        if skill_file.name == "registry.yaml":
            continue
        cmd_file = commands_dir / skill_file.name
        body = _derive_body(skill_file)

        current = cmd_file.read_text(encoding="utf-8") if cmd_file.exists() else None
        if current == body:
            already_ok += 1
        else:
            cmd_file.write_text(body, encoding="utf-8")
            synced += 1

    return synced, already_ok


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sync skills/ → .claude/commands/ (frontmatter stripped)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Diff only; exit 1 if drift")
    mode.add_argument("--sync", action="store_true", help="Write derived targets")
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

    skills_dir = repo_root / "skills"
    commands_dir = repo_root / ".claude" / "commands"

    if args.check:
        diffs = check_sync(skills_dir, commands_dir)
        if not diffs:
            print("PASS: .claude/commands/ is in sync with skills/")
            return 0
        print(f"FAIL: {len(diffs)} file(s) out of sync:\n")
        for d in diffs:
            print(f"  {d}")
        print(
            "\nRun: python scripts/sync_commands.py --sync  to fix"
        )
        return 1

    if args.sync:
        try:
            synced, already_ok = do_sync(skills_dir, commands_dir)
            if synced:
                print(f"SYNC: {synced} file(s) updated, {already_ok} already in sync")
            else:
                print(f"SYNC: already in sync ({already_ok} files)")
            return 0
        except Exception as exc:
            print(f"ERROR: sync failed: {exc}")
            return 1


if __name__ == "__main__":
    sys.exit(main())

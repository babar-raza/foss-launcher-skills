"""sync_agents.py — Sync skills/ → .agents/skills/ and .kilocode/skills/ mirrors.

The canonical source for all skills is skills/*.md (with YAML frontmatter).
Derived targets for .agents/ and .kilocode/ use per-skill subdirectories with
a SKILL.md file containing the same content AS the canonical (frontmatter included).

Unlike .claude/commands/ (which strips frontmatter), the .agents/ and .kilocode/
mirrors preserve frontmatter so agents can read skill metadata (id, name, args).

Structure:
  .agents/skills/{skill-name}/SKILL.md
  .kilocode/skills/{skill-name}/SKILL.md

Internal skills (internal: true in registry.yaml) ARE included in these mirrors
because Codex/KiloCode agents may need to invoke them directly.

Usage:
    python scripts/sync_agents.py --check   # diff only; exit 1 if out of sync
    python scripts/sync_agents.py --sync    # overwrite targets from canonical

Exit codes (--check):
  0  in sync
  1  drift detected (run --sync to fix)

Exit codes (--sync):
  0  sync complete (or already in sync)
  1  error during sync
"""
import argparse
import sys
from pathlib import Path

import yaml


def load_skill_names(registry_path: Path) -> list[str]:
    """Load ordered list of skill names from registry.yaml."""
    with open(registry_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [entry["name"] for entry in data.get("skills", []) if entry.get("name")]


def _agent_skill_file(mirror_dir: Path, skill_name: str) -> Path:
    """Return the SKILL.md path for a given skill in a mirror directory."""
    return mirror_dir / skill_name / "SKILL.md"


def check_sync(skills_dir: Path, mirror_dirs: list[Path]) -> list[str]:
    """Return human-readable diff descriptions for all mirrors. Empty = in sync."""
    diffs = []

    for skill_file in sorted(skills_dir.glob("*.md")):
        canonical_text = skill_file.read_text(encoding="utf-8")
        stem = skill_file.stem

        for mirror_dir in mirror_dirs:
            target = _agent_skill_file(mirror_dir, stem)
            mirror_name = mirror_dir.parent.name  # e.g. ".agents" or ".kilocode"

            if not target.parent.exists():
                diffs.append(f"MISSING_DIR  {mirror_name}/skills/{stem}/")
                continue
            if not target.exists():
                diffs.append(f"MISSING      {mirror_name}/skills/{stem}/SKILL.md")
                continue
            if target.read_text(encoding="utf-8") != canonical_text:
                diffs.append(f"DIFFERS      {mirror_name}/skills/{stem}/SKILL.md")

    # Check for stale subdirectories in mirrors (no canonical skill file)
    for mirror_dir in mirror_dirs:
        if not mirror_dir.exists():
            continue
        mirror_name = mirror_dir.parent.name
        skills_subdir = mirror_dir
        if not skills_subdir.exists():
            continue
        for subdir in sorted(skills_subdir.iterdir()):
            if not subdir.is_dir():
                continue
            canonical = skills_dir / f"{subdir.name}.md"
            if not canonical.exists():
                diffs.append(
                    f"STALE        {mirror_name}/skills/{subdir.name}/ "
                    f"(no canonical in skills/)"
                )

    return diffs


def do_sync(skills_dir: Path, mirror_dirs: list[Path]) -> tuple[int, int]:
    """Sync skills/ → all mirror dirs. Returns (synced_count, already_ok_count)."""
    synced = 0
    already_ok = 0

    for skill_file in sorted(skills_dir.glob("*.md")):
        canonical_text = skill_file.read_text(encoding="utf-8")
        stem = skill_file.stem

        for mirror_dir in mirror_dirs:
            target = _agent_skill_file(mirror_dir, stem)
            target.parent.mkdir(parents=True, exist_ok=True)

            current = target.read_text(encoding="utf-8") if target.exists() else None
            if current == canonical_text:
                already_ok += 1
            else:
                target.write_text(canonical_text, encoding="utf-8")
                synced += 1

    return synced, already_ok


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Sync skills/ → .agents/skills/ and .kilocode/skills/ mirrors. "
            "Each skill gets a subdirectory containing SKILL.md (frontmatter preserved)."
        )
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
    mirror_dirs = [
        repo_root / ".agents" / "skills",
        repo_root / ".kilocode" / "skills",
    ]

    if args.check:
        diffs = check_sync(skills_dir, mirror_dirs)
        if not diffs:
            print("PASS: .agents/skills/ and .kilocode/skills/ are in sync with skills/")
            return 0
        print(f"FAIL: {len(diffs)} discrepancy(ies) found:\n")
        for d in diffs:
            print(f"  {d}")
        print("\nRun: python scripts/sync_agents.py --sync  to fix")
        return 1

    if args.sync:
        try:
            synced, already_ok = do_sync(skills_dir, mirror_dirs)
            if synced:
                print(f"SYNC: {synced} file(s) updated, {already_ok} already in sync")
            else:
                print(f"SYNC: already in sync ({already_ok} files across all mirrors)")
            return 0
        except Exception as exc:
            print(f"ERROR: sync failed: {exc}")
            return 1


if __name__ == "__main__":
    sys.exit(main())

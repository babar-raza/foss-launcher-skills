"""detect_orphans.py — Detect orphan adapters and orphan skills.

Orphan command: a .claude/commands/ file with no entry in skills/registry.yaml
Orphan skill: a .agents/skills/ or .kilocode/skills/ directory with no canonical in skills/

Usage:
    python tools/capability_sync/detect_orphans.py --check   # exit 1 if orphans found
    python tools/capability_sync/detect_orphans.py --sync    # write report and exit 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"
_CLAUDE_COMMANDS = _REPO_ROOT / ".claude" / "commands"
_AGENTS_SKILLS = _REPO_ROOT / ".agents" / "skills"
_KILO_SKILLS = _REPO_ROOT / ".kilocode" / "skills"


def load_registered_names() -> set[str]:
    if not _HAS_YAML:
        return set()
    registry = _SKILLS_DIR / "registry.yaml"
    if not registry.exists():
        return set()
    with open(registry, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {e.get("name", "") for e in data.get("skills", []) if e.get("name")}


def detect_orphans() -> dict[str, Any]:
    registered = load_registered_names()
    canonical_names = {f.stem for f in _SKILLS_DIR.glob("*.md")}

    orphan_commands: list[dict] = []
    orphan_agent_skills: list[dict] = []
    orphan_kilo_skills: list[dict] = []
    unregistered_canonicals: list[str] = []

    # Orphan commands: .claude/commands/*.md without canonical
    if _CLAUDE_COMMANDS.exists():
        for cmd_file in sorted(_CLAUDE_COMMANDS.glob("*.md")):
            stem = cmd_file.stem
            if stem not in registered:
                orphan_commands.append({
                    "name": stem,
                    "path": str(cmd_file.relative_to(_REPO_ROOT)),
                    "reason": "not in skills/registry.yaml",
                })

    # Orphan agent skills: .agents/skills/{name}/ without canonical
    if _AGENTS_SKILLS.exists():
        for skill_dir in sorted(_AGENTS_SKILLS.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name not in registered:
                orphan_agent_skills.append({
                    "name": skill_dir.name,
                    "path": str(skill_dir.relative_to(_REPO_ROOT)),
                    "reason": "not in skills/registry.yaml",
                })

    # Orphan kilocode skills
    if _KILO_SKILLS.exists():
        for skill_dir in sorted(_KILO_SKILLS.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name not in registered:
                orphan_kilo_skills.append({
                    "name": skill_dir.name,
                    "path": str(skill_dir.relative_to(_REPO_ROOT)),
                    "reason": "not in skills/registry.yaml",
                })

    # Unregistered canonicals: skills/*.md without registry entry
    for name in sorted(canonical_names):
        if name not in registered:
            unregistered_canonicals.append(name)

    total_orphans = len(orphan_commands) + len(orphan_agent_skills) + len(orphan_kilo_skills)

    return {
        "orphan_commands": orphan_commands,
        "orphan_agent_skills": orphan_agent_skills,
        "orphan_kilo_skills": orphan_kilo_skills,
        "unregistered_canonicals": unregistered_canonicals,
        "total_orphans": total_orphans,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect orphan adapters (no canonical capability).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Exit 1 if orphans found")
    mode.add_argument("--sync", action="store_true", help="Report only; exit 0")
    args = parser.parse_args(argv)

    try:
        result = detect_orphans()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total = result["total_orphans"]

    if total > 0:
        print(f"ORPHANS: {total} orphan adapter(s) detected:")
        for entry in result["orphan_commands"]:
            print(f"  [ORPHAN_COMMAND] {entry['path']} — {entry['reason']}")
        for entry in result["orphan_agent_skills"]:
            print(f"  [ORPHAN_AGENT_SKILL] {entry['path']} — {entry['reason']}")
        for entry in result["orphan_kilo_skills"]:
            print(f"  [ORPHAN_KILO_SKILL] {entry['path']} — {entry['reason']}")
        if result["unregistered_canonicals"]:
            print(f"\n  Unregistered canonical skills (in skills/ but not in registry):")
            for name in result["unregistered_canonicals"]:
                print(f"    skills/{name}.md")
        if args.check:
            return 1
    else:
        registered = len({f.stem for f in _SKILLS_DIR.glob("*.md")})
        print(f"PASS: no orphan adapters found ({registered} registered capabilities)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

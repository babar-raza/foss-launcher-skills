"""migrate_legacy.py — Migrate command-only or skill-only capabilities to canonical registry.

Identifies capabilities that exist only in adapter surfaces (no canonical skills/*.md) and
creates canonical contracts for them. Identifies skills that exist canonically but lack
proper registry entries.

This is an advisory migration tool — it prints recommended actions but does not overwrite
existing files without confirmation.

Usage:
    python tools/capability_sync/migrate_legacy.py --check     # report orphans and gaps
    python tools/capability_sync/migrate_legacy.py --scaffold  # generate missing canonical stubs
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


def load_registry() -> dict[str, Any]:
    if not _HAS_YAML:
        return {}
    registry = _SKILLS_DIR / "registry.yaml"
    if not registry.exists():
        return {}
    with open(registry, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    skills = data.get("skills", [])
    return {s.get("name", ""): s for s in skills}


def analyze() -> dict[str, Any]:
    registered = load_registry()
    canonical_files = {f.stem: f for f in _SKILLS_DIR.glob("*.md")}

    # Commands that have no canonical skill file
    command_only = []
    if _CLAUDE_COMMANDS.exists():
        for cmd_file in sorted(_CLAUDE_COMMANDS.glob("*.md")):
            if cmd_file.stem not in canonical_files:
                command_only.append({
                    "name": cmd_file.stem,
                    "path": str(cmd_file.relative_to(_REPO_ROOT)),
                    "recommendation": f"Create skills/{cmd_file.stem}.md as canonical contract",
                })

    # Agent skills that have no canonical
    agent_only = []
    if _AGENTS_SKILLS.exists():
        for skill_dir in sorted(_AGENTS_SKILLS.iterdir()):
            if skill_dir.is_dir() and skill_dir.name not in canonical_files:
                agent_only.append({
                    "name": skill_dir.name,
                    "path": str(skill_dir.relative_to(_REPO_ROOT)),
                    "recommendation": f"Create skills/{skill_dir.name}.md as canonical contract",
                })

    # Canonical files not in registry
    unregistered = []
    for name, path in sorted(canonical_files.items()):
        if name not in registered:
            unregistered.append({
                "name": name,
                "path": str(path.relative_to(_REPO_ROOT)),
                "recommendation": f"Add {name} entry to skills/registry.yaml",
            })

    return {
        "command_only": command_only,
        "agent_only": agent_only,
        "unregistered_canonicals": unregistered,
        "migration_required": bool(command_only or agent_only or unregistered),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy command-only or skill-only capabilities.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Report migration gaps; exit 1 if any found")
    mode.add_argument("--scaffold", action="store_true", help="Generate canonical stub for command-only capabilities")
    args = parser.parse_args(argv)

    try:
        result = analyze()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not result["migration_required"]:
        print("PASS: no legacy migration required — all capabilities have canonical contracts")
        return 0

    if result["command_only"]:
        print(f"\nCOMMAND-ONLY (no canonical skill contract):")
        for item in result["command_only"]:
            print(f"  {item['path']}")
            print(f"  → {item['recommendation']}")

    if result["agent_only"]:
        print(f"\nAGENT-ONLY (no canonical skill contract):")
        for item in result["agent_only"]:
            print(f"  {item['path']}")
            print(f"  → {item['recommendation']}")

    if result["unregistered_canonicals"]:
        print(f"\nUNREGISTERED CANONICALS (in skills/ but not in registry):")
        for item in result["unregistered_canonicals"]:
            print(f"  {item['path']}")
            print(f"  → {item['recommendation']}")

    if args.check:
        return 1

    # Scaffold mode: generate minimal canonical stubs for command-only capabilities
    if args.scaffold:
        for item in result["command_only"]:
            name = item["name"]
            out = _SKILLS_DIR / f"{name}.md"
            if out.exists():
                print(f"SKIP: {out.relative_to(_REPO_ROOT)} already exists")
                continue
            stub = f"""---
name: {name}
id: UNASSIGNED
description: >
  (Migrated from .claude/commands/{name}.md — assign ID and complete description)
internal: false
script: null
---

# {name.replace('-', ' ').title()}

> **Migration stub** — This skill was migrated from `.claude/commands/{name}.md`.
> Complete the canonical contract before use.

## Purpose

(TODO: describe the capability purpose)

## Steps

(TODO: document the execution steps)
"""
            out.write_text(stub, encoding="utf-8")
            print(f"SCAFFOLD: {out.relative_to(_REPO_ROOT)} created (assign ID in registry)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

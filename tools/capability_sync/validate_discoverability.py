"""validate_discoverability.py — Prove each agent can discover capabilities from its entry point.

For Claude Code:
  - CLAUDE.md must exist
  - .claude/commands/ must contain non-internal skill adapters
  - A representative capability must resolve to a command file

For Codex / generic agents:
  - CODEX.md or AGENTS.md must exist
  - .agents/skills/ must contain skill directories with SKILL.md
  - A representative capability must resolve to an agent skill

Usage:
    python tools/capability_sync/validate_discoverability.py --check
    python tools/capability_sync/validate_discoverability.py --sync
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
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_CODEX_MD = _REPO_ROOT / "CODEX.md"
_AGENTS_MD = _REPO_ROOT / "AGENTS.md"

# Representative public skills that must be discoverable by all agents
_REPRESENTATIVE_SKILLS = ["ground-check", "session-start", "knowledge-diff", "eval-page"]


def load_skills() -> list[dict[str, Any]]:
    if not _HAS_YAML:
        raise RuntimeError("pyyaml required: pip install pyyaml")
    registry = _SKILLS_DIR / "registry.yaml"
    with open(registry, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("skills", [])


def check_claude_discoverability(registered: set[str]) -> list[str]:
    failures = []

    # Entry point must exist
    if not _CLAUDE_MD.exists():
        failures.append("CLAUDE.md not found — Claude Code has no entry point")

    # Commands directory must exist and be non-empty
    if not _CLAUDE_COMMANDS.exists():
        failures.append(".claude/commands/ directory not found")
        return failures

    cmd_names = {f.stem for f in _CLAUDE_COMMANDS.glob("*.md")}
    if not cmd_names:
        failures.append(".claude/commands/ is empty — no commands available to Claude Code")

    # Representative skills must be discoverable
    for name in _REPRESENTATIVE_SKILLS:
        if name in registered and name not in cmd_names:
            failures.append(f"Representative skill '{name}' not discoverable by Claude Code")

    return failures


def check_codex_discoverability(registered: set[str]) -> list[str]:
    failures = []

    # Either CODEX.md or AGENTS.md must exist
    if not _CODEX_MD.exists() and not _AGENTS_MD.exists():
        failures.append("Neither CODEX.md nor AGENTS.md found — Codex has no entry point")

    # .agents/skills/ must exist and be non-empty
    if not _AGENTS_SKILLS.exists():
        failures.append(".agents/skills/ directory not found")
        return failures

    skill_dirs = {d.name for d in _AGENTS_SKILLS.iterdir() if d.is_dir()}
    if not skill_dirs:
        failures.append(".agents/skills/ is empty — no skills available to Codex")

    # Each skill dir must have a SKILL.md
    for skill_dir in sorted(_AGENTS_SKILLS.iterdir()):
        if skill_dir.is_dir() and not (skill_dir / "SKILL.md").exists():
            failures.append(f".agents/skills/{skill_dir.name}/SKILL.md not found")

    # Representative skills must be discoverable
    for name in _REPRESENTATIVE_SKILLS:
        if name in registered and name not in skill_dirs:
            failures.append(f"Representative skill '{name}' not discoverable by Codex")

    return failures


def check_kilo_discoverability(registered: set[str]) -> list[str]:
    failures = []

    if not _KILO_SKILLS.exists():
        failures.append(".kilocode/skills/ directory not found")
        return failures

    skill_dirs = {d.name for d in _KILO_SKILLS.iterdir() if d.is_dir()}
    for skill_dir in sorted(_KILO_SKILLS.iterdir()):
        if skill_dir.is_dir() and not (skill_dir / "SKILL.md").exists():
            failures.append(f".kilocode/skills/{skill_dir.name}/SKILL.md not found")

    for name in _REPRESENTATIVE_SKILLS:
        if name in registered and name not in skill_dirs:
            failures.append(f"Representative skill '{name}' not discoverable by KiloCode")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate agent discoverability of capabilities.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Exit 1 if any discoverability failures")
    mode.add_argument("--sync", action="store_true", help="Report only; exit 0")
    args = parser.parse_args(argv)

    try:
        skills = load_skills()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    registered = {s.get("name", "") for s in skills if not s.get("internal")}

    claude_failures = check_claude_discoverability(registered)
    codex_failures = check_codex_discoverability(registered)
    kilo_failures = check_kilo_discoverability(registered)

    all_failures = claude_failures + codex_failures + kilo_failures
    has_failures = bool(all_failures)

    if claude_failures:
        print("CLAUDE CODE discoverability failures:")
        for f in claude_failures:
            print(f"  {f}")
    else:
        cmd_count = len(list(_CLAUDE_COMMANDS.glob("*.md"))) if _CLAUDE_COMMANDS.exists() else 0
        print(f"PASS: Claude Code can discover {cmd_count} capabilities")

    if codex_failures:
        print("CODEX discoverability failures:")
        for f in codex_failures:
            print(f"  {f}")
    else:
        skill_count = sum(1 for d in _AGENTS_SKILLS.iterdir() if d.is_dir()) if _AGENTS_SKILLS.exists() else 0
        print(f"PASS: Codex can discover {skill_count} capabilities")

    if kilo_failures:
        print("KILOCODE discoverability failures:")
        for f in kilo_failures:
            print(f"  {f}")
    else:
        kilo_count = sum(1 for d in _KILO_SKILLS.iterdir() if d.is_dir()) if _KILO_SKILLS.exists() else 0
        print(f"PASS: KiloCode can discover {kilo_count} capabilities")

    if has_failures and args.check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""distribute.py — Generate agent-specific skill directories from canonical skills/.

Reads skills/*.md (YAML frontmatter + markdown body) and produces:
  .claude/commands/{name}.md   — body only (frontmatter stripped)
  .agents/skills/{name}/SKILL.md  — full file (frontmatter preserved)
  .kilocode/skills/{name}/SKILL.md — full file (frontmatter preserved)

Usage:
  python tools/distribute.py                  # output to current directory
  python tools/distribute.py /path/to/target  # output to target repo
"""

import os
import re
import sys
import shutil
import importlib.util
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)

AGENT_TARGETS = {
    "claude":   lambda name: Path(".claude", "commands", f"{name}.md"),
    "codex":    lambda name: Path(".agents", "skills", name, "SKILL.md"),
    "kilocode": lambda name: Path(".kilocode", "skills", name, "SKILL.md"),
}


def parse_skill(text: str):
    """Split a skill file into (frontmatter_block, body).

    Returns (frontmatter_block, body) where frontmatter_block includes the
    --- delimiters.  If there is no frontmatter, frontmatter_block is empty.
    """
    m = FRONTMATTER_RE.match(text)
    if m:
        return m.group(0), text[m.end():]
    return "", text


def load_internal_skill_names(skills_dir: Path) -> set[str]:
    """Return skill names marked internal in skills/registry.yaml."""
    registry_path = skills_dir / "registry.yaml"
    if not registry_path.exists():
        return set()

    text = registry_path.read_text(encoding="utf-8")
    internal_names: set[str] = set()
    for match in re.finditer(r"(?ms)^\s*-\s+id:.*?(?=^\s*-\s+id:|\Z)", text):
        block = match.group(0)
        name_match = re.search(r"(?m)^\s+name:\s*([^\s#]+)", block)
        internal_match = re.search(r"(?m)^\s+internal:\s*true\s*(?:#.*)?$", block)
        if name_match and internal_match:
            internal_names.add(name_match.group(1).strip("\"'"))
    return internal_names


def distribute(skills_dir: Path, target_dir: Path):
    """Read skills from skills_dir and write agent directories under target_dir."""
    skills = sorted(skills_dir.glob("*.md"))
    if not skills:
        print(f"No .md files found in {skills_dir}", file=sys.stderr)
        sys.exit(1)

    counts = {agent: 0 for agent in AGENT_TARGETS}
    internal_skill_names = load_internal_skill_names(skills_dir)

    for skill_path in skills:
        name = skill_path.stem
        text = skill_path.read_text(encoding="utf-8")
        frontmatter, body = parse_skill(text)

        for agent, path_fn in AGENT_TARGETS.items():
            out_path = target_dir / path_fn(name)

            if agent == "claude" and name in internal_skill_names:
                if out_path.exists():
                    out_path.unlink()
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)

            if agent == "claude":
                # Claude Code commands: strip frontmatter
                out_path.write_text(body.lstrip("\n"), encoding="utf-8")
            else:
                # Codex / Kilo Code: keep full file
                out_path.write_text(text, encoding="utf-8")

            counts[agent] += 1

    print(f"Distributed {len(skills)} skills:")
    for agent, count in counts.items():
        print(f"  {agent}: {count} files")


def check_readme(repo_root: Path, skills_dir: Path):
    """Warn if README.md skill count doesn't match actual skill count."""
    readme_sync_path = repo_root / "scripts" / "readme_sync.py"
    if not readme_sync_path.exists():
        return

    # Import readme_sync dynamically
    spec = importlib.util.spec_from_file_location("readme_sync", readme_sync_path)
    readme_sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(readme_sync)

    manifest = readme_sync.build_manifest()
    findings = readme_sync.check_readme(manifest)
    if findings:
        print(f"\n⚠  README.md is stale ({len(findings)} issue(s)):")
        for f in findings:
            print(f"   - [{f['section']}] {f['issue']}")
        print("   Run: python scripts/readme_sync.py --check  for details\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Distribute skills to agent directories")
    parser.add_argument("target", nargs="?", help="Target directory (default: repo root)")
    parser.add_argument("--check-readme", action="store_true",
                        help="Warn if README.md is out of sync with project state")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    skills_dir = repo_root / "skills"

    target_dir = Path(args.target).resolve() if args.target else repo_root

    if not skills_dir.is_dir():
        print(f"Skills directory not found: {skills_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Skills source: {skills_dir}")
    print(f"Target:        {target_dir}")
    distribute(skills_dir, target_dir)

    if args.check_readme:
        check_readme(repo_root, skills_dir)


if __name__ == "__main__":
    main()

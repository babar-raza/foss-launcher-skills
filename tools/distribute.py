#!/usr/bin/env python3
"""distribute.py — Generate agent-specific skill directories from canonical skills/.

Reads skills/*.md (YAML frontmatter + markdown body) and produces:
  .claude/commands/{name}.md   — body only (frontmatter stripped); internal skills excluded
  .agents/skills/{name}/SKILL.md  — full file (frontmatter preserved); all skills
  .kilocode/skills/{name}/SKILL.md — full file (frontmatter preserved); all skills

Also generates skills/registry.json — machine-readable skill catalog.

Usage:
  python tools/distribute.py                   # distribute to current directory
  python tools/distribute.py /path/to/target   # distribute to target repo
  python tools/distribute.py --dry-run         # preview without writing
  python tools/distribute.py --verify          # check parity between canonical and distributed
  python tools/distribute.py --registry        # regenerate skills/registry.json only
"""

import json
import os
import re
import sys
import shutil
import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SKILLS_DIR = REPO_ROOT / "skills"

# Load INTERNAL_SKILLS from scripts/skill_constants.py
_constants_path = REPO_ROOT / "scripts" / "skill_constants.py"
if _constants_path.exists():
    _spec = importlib.util.spec_from_file_location("skill_constants", _constants_path)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    INTERNAL_SKILLS: frozenset[str] = _mod.INTERNAL_SKILLS
else:
    INTERNAL_SKILLS = frozenset()

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)
YAML_FIELD_RE = re.compile(r"^(\w[\w-]*):\s*(.+)$", re.MULTILINE)

# ---------------------------------------------------------------------------
# Agent target configurations
# ---------------------------------------------------------------------------

AGENT_TARGETS = {
    "claude":   lambda name: Path(".claude", "commands", f"{name}.md"),
    "codex":    lambda name: Path(".agents", "skills", name, "SKILL.md"),
    "kilocode": lambda name: Path(".kilocode", "skills", name, "SKILL.md"),
}

# Agents that receive ALL skills (including internal sub-routines)
FULL_SKILL_AGENTS = {"codex", "kilocode"}

# ---------------------------------------------------------------------------
# Core parsing
# ---------------------------------------------------------------------------


def parse_skill(text: str):
    """Split a skill file into (frontmatter_block, body).

    Returns (frontmatter_block, body) where frontmatter_block includes the
    --- delimiters.  If there is no frontmatter, frontmatter_block is empty.
    """
    m = FRONTMATTER_RE.match(text)
    if m:
        return m.group(0), text[m.end():]
    return "", text


def extract_frontmatter_fields(frontmatter_block: str) -> dict:
    """Extract simple key: value pairs from a frontmatter block."""
    fields = {}
    # Strip the --- delimiters
    inner = frontmatter_block.lstrip("-\n").rstrip("-\n").strip()
    for line in inner.splitlines():
        m = YAML_FIELD_RE.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
            fields[key] = val
    return fields


def _parse_depends_on(val: str) -> list[str]:
    """Parse a YAML inline list value into a Python list.

    Handles: ``[]``, ``[path-guard]``, ``[path-guard, ground-check]``.
    """
    val = val.strip()
    if not val or val == "[]":
        return []
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1]
        return [item.strip().strip('"').strip("'") for item in inner.split(",") if item.strip()]
    # Scalar (single value, no brackets)
    return [val] if val else []


def _detect_dependency_cycles(catalog: list[dict]) -> list[str]:
    """Detect cycles in the skill dependency graph.

    Returns a list of cycle descriptions. Empty list = no cycles detected.
    Note: detection is best-effort on a partial graph (only skills with explicit
    ``depends_on`` fields contribute edges). Reports cycles as strings for logging.
    """
    name_to_deps: dict[str, list[str]] = {
        entry["name"]: entry.get("depends_on", []) for entry in catalog
    }
    found: list[str] = []
    reported: set[str] = set()

    def _visit(name: str, path: list[str]) -> None:
        if name in path:
            cycle_start = path.index(name)
            cycle_key = " -> ".join(path[cycle_start:] + [name])
            if cycle_key not in reported:
                reported.add(cycle_key)
                found.append(f"CYCLE: {cycle_key}")
            return
        for dep in name_to_deps.get(name, []):
            _visit(dep, path + [name])

    for skill_name in name_to_deps:
        _visit(skill_name, [])

    return found

# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------


def distribute(
    skills_dir: Path,
    target_dir: Path,
    dry_run: bool = False,
    internal_skills: frozenset | None = None,
) -> dict[str, int]:
    """Read skills from skills_dir and write agent directories under target_dir.

    Returns counts dict: {agent_name: files_written}.

    Args:
        skills_dir: Directory containing canonical *.md skill files.
        target_dir: Root of the repo to write agent directories into.
        dry_run: If True, print what would be written without actually writing.
        internal_skills: Set of skill slugs to exclude from user-facing agents
            (e.g. Claude Code). Defaults to the module-level INTERNAL_SKILLS.
    """
    if internal_skills is None:
        internal_skills = INTERNAL_SKILLS

    skills = sorted(skills_dir.glob("*.md"))
    if not skills:
        print(f"No .md files found in {skills_dir}", file=sys.stderr)
        sys.exit(1)

    counts: dict[str, int] = {agent: 0 for agent in AGENT_TARGETS}

    for skill_path in skills:
        name = skill_path.stem
        text = skill_path.read_text(encoding="utf-8")
        frontmatter, body = parse_skill(text)

        for agent, path_fn in AGENT_TARGETS.items():
            # Internal skills are excluded from user-facing agents (Claude)
            if agent not in FULL_SKILL_AGENTS and name in internal_skills:
                continue

            out_path = target_dir / path_fn(name)

            if dry_run:
                print(f"  [dry-run] would write: {out_path.relative_to(target_dir)}")
                counts[agent] += 1
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)

            if agent == "claude":
                # Claude Code commands: strip frontmatter (body only)
                out_path.write_text(body.lstrip("\n"), encoding="utf-8")
            else:
                # Codex / Kilo Code: keep full file (frontmatter + body)
                out_path.write_text(text, encoding="utf-8")

            counts[agent] += 1

    return counts


# ---------------------------------------------------------------------------
# Registry generation
# ---------------------------------------------------------------------------


def generate_registry(
    skills_dir: Path,
    internal_skills: frozenset | None = None,
) -> list[dict]:
    """Build a machine-readable skill catalog from canonical skill files.

    Returns a list of skill descriptor dicts sorted by id then name.
    Also writes skills/registry.json to disk.
    """
    if internal_skills is None:
        internal_skills = INTERNAL_SKILLS

    catalog = []
    for skill_path in sorted(skills_dir.glob("*.md")):
        name = skill_path.stem
        text = skill_path.read_text(encoding="utf-8")
        frontmatter, _body = parse_skill(text)
        fields = extract_frontmatter_fields(frontmatter)

        entry = {
            "name": fields.get("name", name),
            "id": fields.get("id", ""),
            "description": fields.get("description", ""),
            "args": fields.get("args", ""),
            "depends_on": _parse_depends_on(fields.get("depends_on", "[]")),
            "internal": name in internal_skills,
        }
        catalog.append(entry)

    # Sort: internal skills last, then by id (numeric part), then name
    def sort_key(e):
        id_str = e.get("id", "") or ""
        try:
            num = int(id_str.lstrip("S-").lstrip("s-"))
        except ValueError:
            num = 9999
        return (e["internal"], num, e["name"])

    catalog.sort(key=sort_key)

    registry_path = skills_dir / "registry.json"
    registry_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return catalog


# ---------------------------------------------------------------------------
# Parity verification
# ---------------------------------------------------------------------------


def verify_parity(
    skills_dir: Path,
    target_dir: Path,
    internal_skills: frozenset | None = None,
) -> list[str]:
    """Compare canonical skills against distributed agent directories.

    Returns a list of drift descriptions.  Empty list = parity confirmed.
    """
    if internal_skills is None:
        internal_skills = INTERNAL_SKILLS

    issues = []
    skills = {p.stem: p for p in skills_dir.glob("*.md")}

    for name, skill_path in sorted(skills.items()):
        text = skill_path.read_text(encoding="utf-8")
        frontmatter, body = parse_skill(text)
        is_internal = name in internal_skills

        for agent, path_fn in AGENT_TARGETS.items():
            out_path = target_dir / path_fn(name)

            if agent not in FULL_SKILL_AGENTS and is_internal:
                # Internal skills must NOT be present in user-facing agent dirs
                if out_path.exists():
                    issues.append(
                        f"UNEXPECTED: {out_path.relative_to(target_dir)} "
                        f"(internal skill '{name}' should not be in {agent})"
                    )
                continue

            if not out_path.exists():
                issues.append(
                    f"MISSING: {out_path.relative_to(target_dir)} "
                    f"(skill '{name}' not distributed to {agent})"
                )
                continue

            distributed = out_path.read_text(encoding="utf-8")
            if agent == "claude":
                expected = body.lstrip("\n")
            else:
                expected = text

            if distributed != expected:
                issues.append(
                    f"DRIFT: {out_path.relative_to(target_dir)} "
                    f"(content differs from canonical for skill '{name}')"
                )

    return issues


# ---------------------------------------------------------------------------
# README freshness check
# ---------------------------------------------------------------------------


def check_readme(repo_root: Path, skills_dir: Path):
    """Warn if README.md skill count doesn't match actual skill count."""
    readme_sync_path = repo_root / "scripts" / "readme_sync.py"
    if not readme_sync_path.exists():
        return

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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Distribute skills to agent directories")
    parser.add_argument("target", nargs="?", help="Target directory (default: repo root)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be written without actually writing",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Check parity between canonical skills and distributed agent directories",
    )
    parser.add_argument(
        "--registry",
        action="store_true",
        help="Regenerate skills/registry.json only (no distribution)",
    )
    parser.add_argument(
        "--check-readme",
        action="store_true",
        help="Warn if README.md is out of sync with project state",
    )
    args = parser.parse_args()

    target_dir = Path(args.target).resolve() if args.target else REPO_ROOT

    if not SKILLS_DIR.is_dir():
        print(f"Skills directory not found: {SKILLS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Skills source: {SKILLS_DIR}")
    print(f"Target:        {target_dir}")
    if INTERNAL_SKILLS:
        print(f"Internal skills (excluded from Claude): {sorted(INTERNAL_SKILLS)}")

    # --registry: regenerate registry.json only
    if args.registry:
        catalog = generate_registry(SKILLS_DIR)
        print(f"Registry regenerated: {SKILLS_DIR / 'registry.json'} ({len(catalog)} skills)")
        return

    # --verify: parity check
    if args.verify:
        issues = verify_parity(SKILLS_DIR, target_dir)
        if issues:
            print(f"\nParity check FAILED ({len(issues)} issue(s)):")
            for issue in issues:
                print(f"   {issue}")
            sys.exit(1)
        else:
            skill_count = len(list(SKILLS_DIR.glob("*.md")))
            print(f"\nParity confirmed -- {skill_count} skills distributed correctly")

        # Dependency cycle check (partial graph — WARN only, no exit)
        catalog = generate_registry(SKILLS_DIR)
        cycles = _detect_dependency_cycles(catalog)
        if cycles:
            print(f"\nDependency graph WARN ({len(cycles)} cycle(s) detected):")
            for c in cycles:
                print(f"   {c}")
        else:
            annotated = sum(1 for e in catalog if e.get("depends_on"))
            print(f"Dependency graph: no cycles ({annotated}/{len(catalog)} skills annotated)")
        return

    # Normal distribution
    if args.dry_run:
        print("\n[dry-run] Files that would be written:")

    counts = distribute(SKILLS_DIR, target_dir, dry_run=args.dry_run)

    if args.dry_run:
        total = sum(counts.values())
        print(f"\n[dry-run] Would write {total} files across {len(counts)} targets:")
    else:
        skill_count = len(list(SKILLS_DIR.glob("*.md")))
        internal_count = len(INTERNAL_SKILLS)
        print(
            f"\nDistributed {skill_count} skills "
            f"({internal_count} internal, excluded from Claude):"
        )

    for agent, count in counts.items():
        print(f"  {agent}: {count} files")

    if not args.dry_run:
        # Also regenerate registry
        catalog = generate_registry(SKILLS_DIR)
        print(f"\nRegistry: {SKILLS_DIR / 'registry.json'} ({len(catalog)} entries)")

    if args.check_readme:
        check_readme(REPO_ROOT, SKILLS_DIR)


if __name__ == "__main__":
    main()

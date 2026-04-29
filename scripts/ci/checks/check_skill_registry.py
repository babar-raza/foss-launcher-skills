"""Check that AGENTS.md skill registry matches canonical skills/ directory.

Detects:
- Skills in skills/ but missing from AGENTS.md §12 (unregistered)
- Skills in AGENTS.md §12 but missing from skills/ (orphan registry entries)
- Duplicate S-XX IDs in the registry
- S-XX IDs in skill file headers that don't match the registry
- (--cross-tree) Duplicate S-XX IDs across all 4 provider trees

Usage:
    python scripts/ci/checks/check_skill_registry.py
    python scripts/ci/checks/check_skill_registry.py --cross-tree
    python scripts/ci/checks/check_skill_registry.py --json

Exit codes:
    0  All checks pass
    1  Drift detected
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
AGENTS_MD = _REPO_ROOT / "AGENTS.md"
SKILLS_CHILD_DOC = _REPO_ROOT / "docs" / "registries" / "skills.md"
SKILLS_DIR = _REPO_ROOT / "skills"

PROVIDER_TREES = {
    "canonical": SKILLS_DIR,
    "agents": _REPO_ROOT / ".agents" / "skills",
    "claude": _REPO_ROOT / ".claude" / "commands",
    "kilocode": _REPO_ROOT / ".kilocode" / "skills",
}

# Regex for AGENTS.md §12 table rows: | slug | S-XX | description |
_REGISTRY_ROW_RE = re.compile(
    r"^\|\s*([\w-]+)\s*\|\s*(S-\d+)\s*\|", re.MULTILINE
)

# Regex for S-XX in skill file headers: # S-XX: Name or # S-XX — Name
_SKILL_ID_RE = re.compile(r"#\s*(S-\d+)")


def _load_skills_source() -> str:
    """Dual-read: prefer child doc, fall back to AGENTS.md."""
    if SKILLS_CHILD_DOC.exists():
        return SKILLS_CHILD_DOC.read_text(encoding="utf-8")
    logging.warning("FALLBACK: reading Skills reference from AGENTS.md — child doc missing")
    return AGENTS_MD.read_text(encoding="utf-8")


def _parse_registry(agents_md: Path) -> dict[str, str]:
    """Parse skill registry table. Returns {slug: id}."""
    text = _load_skills_source()
    # Find the "Skills reference" section
    start = text.find("### Skills reference")
    if start == -1:
        return {}
    # Limit to the section (until next ### or end)
    section = text[start:]
    next_section = section.find("\n### ", 1)
    if next_section != -1:
        section = section[:next_section]
    entries: dict[str, str] = {}
    for m in _REGISTRY_ROW_RE.finditer(section):
        slug, sid = m.group(1).strip(), m.group(2).strip()
        entries[slug] = sid
    return entries


_NON_SKILL_SLUGS = {"readme"}  # documentation files that live alongside skills


def _parse_skill_files(skills_dir: Path) -> dict[str, str | None]:
    """Read canonical skill files. Returns {slug: id_from_header_or_None}."""
    skills: dict[str, str | None] = {}
    for f in sorted(skills_dir.glob("*.md")):
        slug = f.stem
        if slug.lower() in _NON_SKILL_SLUGS:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = _SKILL_ID_RE.search(text[:200])  # Only check first 200 chars
        skills[slug] = m.group(1) if m else None
    return skills


def _scan_tree_ids(tree_name: str, tree_path: Path) -> list[tuple[str, str, str]]:
    """Scan a provider tree for S-XX IDs. Returns [(id, slug, tree_name)]."""
    results = []
    _NON = {"readme"}
    if tree_name == "canonical":
        for f in sorted(tree_path.glob("*.md")):
            slug = f.stem
            if slug.lower() in _NON:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            m = _SKILL_ID_RE.search(text[:1500])
            if m:
                results.append((m.group(1), slug, tree_name))
    elif tree_name == "claude":
        for f in sorted(tree_path.glob("*.md")):
            slug = f.stem
            if slug.lower() in _NON:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            m = _SKILL_ID_RE.search(text[:1500])
            if m:
                results.append((m.group(1), slug, tree_name))
    else:
        for d in sorted(tree_path.iterdir()):
            skill_file = d / "SKILL.md"
            if d.is_dir() and skill_file.exists():
                text = skill_file.read_text(encoding="utf-8", errors="ignore")
                m = _SKILL_ID_RE.search(text[:1500])
                if m:
                    results.append((m.group(1), d.name, tree_name))
    return results


def check_cross_tree() -> list[dict]:
    """Check for ID collisions across all 4 provider trees."""
    all_ids: dict[str, list[tuple[str, str]]] = {}  # id -> [(slug, tree)]
    for tree_name, tree_path in PROVIDER_TREES.items():
        if not tree_path.exists():
            continue
        for sid, slug, tree in _scan_tree_ids(tree_name, tree_path):
            all_ids.setdefault(sid, []).append((slug, tree))

    issues = []
    for sid, entries in sorted(all_ids.items()):
        # Deduplicate: same slug across trees is expected (it's the same skill mirrored)
        unique_slugs = set(slug for slug, _ in entries)
        if len(unique_slugs) > 1:
            detail_parts = [f"{slug} ({tree})" for slug, tree in entries]
            issues.append({
                "check": "cross_tree_id_collision",
                "id": sid,
                "entries": [{"slug": s, "tree": t} for s, t in entries],
                "detail": f"{sid} used by different skills: {', '.join(detail_parts)}",
            })
    return issues


def check(as_json: bool = False, cross_tree: bool = False) -> int:
    """Run all checks. Returns exit code."""
    registry = _parse_registry(AGENTS_MD)
    skill_files = _parse_skill_files(SKILLS_DIR)

    if not registry:
        print("ERROR: Could not parse any entries from AGENTS.md Skills reference section", file=sys.stderr)
        return 1
    if not skill_files:
        print("ERROR: No skill files found in skills/", file=sys.stderr)
        return 1

    issues: list[dict] = []

    # Check 1: skills/ files missing from registry
    for slug in sorted(skill_files):
        if slug not in registry:
            issues.append({
                "check": "unregistered_skill",
                "slug": slug,
                "detail": f"skills/{slug}.md exists but has no entry in AGENTS.md §12",
            })

    # Check 2: registry entries missing from skills/
    for slug in sorted(registry):
        if slug not in skill_files:
            issues.append({
                "check": "orphan_registry",
                "slug": slug,
                "id": registry[slug],
                "detail": f"AGENTS.md §12 has {slug} ({registry[slug]}) but skills/{slug}.md does not exist",
            })

    # Check 3: duplicate S-XX IDs in registry
    id_to_slugs: dict[str, list[str]] = {}
    for slug, sid in registry.items():
        id_to_slugs.setdefault(sid, []).append(slug)
    for sid, slugs in sorted(id_to_slugs.items()):
        if len(slugs) > 1:
            issues.append({
                "check": "duplicate_id",
                "id": sid,
                "slugs": slugs,
                "detail": f"{sid} is assigned to multiple skills: {', '.join(slugs)}",
            })

    # Check 4: skill file header ID doesn't match registry ID
    for slug in sorted(skill_files):
        file_id = skill_files[slug]
        reg_id = registry.get(slug)
        if file_id and reg_id and file_id != reg_id:
            issues.append({
                "check": "id_mismatch",
                "slug": slug,
                "file_id": file_id,
                "registry_id": reg_id,
                "detail": f"skills/{slug}.md header has {file_id} but AGENTS.md §12 has {reg_id}",
            })

    # Check 5: cross-tree ID uniqueness (only when --cross-tree is passed)
    if cross_tree:
        cross_issues = check_cross_tree()
        issues.extend(cross_issues)

    # Output
    if as_json:
        result = {
            "canonical_skills": len(skill_files),
            "registry_entries": len(registry),
            "issue_count": len(issues),
            "issues": issues,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"Canonical skills: {len(skill_files)}")
        print(f"Registry entries: {len(registry)}")
        if issues:
            print(f"\nDRIFT DETECTED: {len(issues)} issue(s)\n")
            for issue in issues:
                print(f"  [{issue['check']}] {issue['detail']}")
            print(f"\nFAIL: Skill registry is out of sync with skills/ directory")
        else:
            print(f"\nPASS: Registry matches canonical skills directory")

    return 1 if issues else 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check AGENTS.md skill registry completeness")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--cross-tree", action="store_true",
                        help="Also check for S-XX ID collisions across all 4 provider trees")
    args = parser.parse_args()
    return check(as_json=args.json, cross_tree=args.cross_tree)


if __name__ == "__main__":
    raise SystemExit(main())

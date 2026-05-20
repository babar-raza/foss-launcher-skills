# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
"""Validate basic DAR coverage between AGENTS.md and skills."""
from __future__ import annotations

import argparse
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parents[3])))


def parse_dar_downstreams(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"/([\w-]+)", text):
        names.add(match.group(1))
    return names


def skill_mentions_bootstrap(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    return "/knowledge-bootstrap" in text or "knowledge.bootstrap" in text


def check(repo_root: Path = REPO_ROOT) -> list[str]:
    agents = repo_root / "AGENTS.md"
    skills_dir = repo_root / "skills"
    registry = repo_root / "skills" / "registry.yaml"
    issues: list[str] = []
    if not agents.exists():
        return [f"SETUP missing AGENTS.md: {agents}"]
    if not skills_dir.exists():
        return [f"SETUP missing skills directory: {skills_dir}"]
    agents_text = agents.read_text(encoding="utf-8", errors="ignore")
    downstreams = parse_dar_downstreams(agents_text)
    for skill in sorted(skills_dir.glob("*.md")):
        if skill.stem.lower() == "readme":
            continue
        if skill_mentions_bootstrap(skill) and skill.stem != "knowledge-bootstrap" and skill.stem not in downstreams:
            issues.append(f"MISSING_DAR_ENTRY {skill.stem}: mentions knowledge-bootstrap but no DAR slash reference found")
    if registry.exists():
        registry_text = registry.read_text(encoding="utf-8", errors="ignore")
        for skill in sorted(skills_dir.glob("*.md")):
            if skill.stem.lower() != "readme" and f"name: {skill.stem}" not in registry_text:
                issues.append(f"SKILL_NOT_IN_REGISTRY {skill.stem}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    issues = check(args.repo_root)
    if issues:
        print("\n".join(issues))
        return 1
    print("DAR coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

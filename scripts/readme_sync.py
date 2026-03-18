#!/usr/bin/env python3
"""readme_sync.py — Detect README.md staleness by comparing it to project state.

Scans the project for current skill count, script list, directory structure,
and other README-relevant facts, then checks whether README.md reflects them.

Usage:
  python scripts/readme_sync.py                # print manifest of current facts
  python scripts/readme_sync.py --check        # exit 1 if README is stale
  python scripts/readme_sync.py --check --json # output staleness report as JSON
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
SKILLS_DIR = REPO_ROOT / "skills"
SCRIPTS_DIR = REPO_ROOT / "scripts"
CONFIGS_DIR = REPO_ROOT / "configs"


def build_manifest() -> dict:
    """Build a manifest of README-relevant facts from the project."""
    manifest = {}

    # Skill count and names
    skills = sorted(p.stem for p in SKILLS_DIR.glob("*.md")) if SKILLS_DIR.is_dir() else []
    manifest["skill_count"] = len(skills)
    manifest["skill_names"] = skills

    # Script count and names (exclude __pycache__, requirements.txt, __init__.py)
    if SCRIPTS_DIR.is_dir():
        scripts = sorted(
            p.stem for p in SCRIPTS_DIR.glob("*.py")
            if p.stem != "__init__" and not p.stem.startswith("__")
        )
    else:
        scripts = []
    manifest["script_count"] = len(scripts)
    manifest["script_names"] = scripts

    # Top-level directories
    dirs = sorted(
        p.name for p in REPO_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".")
        and p.name not in {"__pycache__", "node_modules", ".git"}
    )
    manifest["top_dirs"] = dirs

    # Config files
    if CONFIGS_DIR.is_dir():
        configs = sorted(p.name for p in CONFIGS_DIR.iterdir() if p.is_file())
    else:
        configs = []
    manifest["config_files"] = configs

    # Families count (from families.yaml if present)
    families_path = CONFIGS_DIR / "families.yaml" if CONFIGS_DIR.is_dir() else None
    if families_path and families_path.exists():
        try:
            text = families_path.read_text(encoding="utf-8")
            # Count top-level keys that look like family names (lines starting without space followed by colon)
            family_lines = re.findall(r"^([a-z][a-z0-9_-]*):", text, re.MULTILINE)
            # Filter out meta keys like 'platforms', 'defaults'
            meta_keys = {"platforms", "defaults", "import_templates", "install_commands"}
            families = [f for f in family_lines if f not in meta_keys]
            manifest["family_count"] = len(families)
        except Exception:
            manifest["family_count"] = None
    else:
        manifest["family_count"] = None

    return manifest


def check_readme(manifest: dict) -> list[dict]:
    """Compare manifest against README.md content. Return list of stale findings."""
    if not README_PATH.exists():
        return [{"section": "file", "issue": "README.md does not exist"}]

    readme = README_PATH.read_text(encoding="utf-8")
    findings = []

    # Check skill count
    skill_count_match = re.search(r"(\d+)\s+(?:agent\s+)?skills?\b", readme, re.IGNORECASE)
    if skill_count_match:
        readme_count = int(skill_count_match.group(1))
        if readme_count != manifest["skill_count"]:
            findings.append({
                "section": "skill_count",
                "readme_value": readme_count,
                "actual_value": manifest["skill_count"],
                "issue": f"README says {readme_count} skills, project has {manifest['skill_count']}",
            })

    # Check script count
    script_count_match = re.search(r"(\d+)\s+modules?\b", readme, re.IGNORECASE)
    if script_count_match:
        readme_scount = int(script_count_match.group(1))
        if readme_scount != manifest["script_count"]:
            findings.append({
                "section": "script_count",
                "readme_value": readme_scount,
                "actual_value": manifest["script_count"],
                "issue": f"README says {readme_scount} modules, project has {manifest['script_count']}",
            })

    # Check that each skill name appears in the skill catalog
    missing_skills = []
    for name in manifest["skill_names"]:
        if name not in readme:
            missing_skills.append(name)
    if missing_skills:
        findings.append({
            "section": "skill_catalog",
            "missing": missing_skills,
            "issue": f"Skills missing from README: {', '.join(missing_skills)}",
        })

    # Check that each script appears in the project structure
    missing_scripts = []
    for name in manifest["script_names"]:
        # Look for the .py filename in README
        if f"{name}.py" not in readme:
            missing_scripts.append(f"{name}.py")
    if missing_scripts:
        findings.append({
            "section": "project_structure",
            "missing": missing_scripts,
            "issue": f"Scripts missing from README: {', '.join(missing_scripts)}",
        })

    # Check top-level directories mentioned in project structure
    # Look for the tree block between "Project Structure" and the next ## heading
    tree_match = re.search(
        r"## Project Structure.*?```(.*?)```",
        readme,
        re.DOTALL,
    )
    if tree_match:
        tree_text = tree_match.group(1)
        missing_dirs = []
        for d in manifest["top_dirs"]:
            if d + "/" not in tree_text and d not in tree_text:
                missing_dirs.append(d)
        if missing_dirs:
            findings.append({
                "section": "project_structure_dirs",
                "missing": missing_dirs,
                "issue": f"Directories missing from project tree: {', '.join(missing_dirs)}",
            })

    return findings


def main():
    parser = argparse.ArgumentParser(description="Check README.md freshness")
    parser.add_argument("--check", action="store_true", help="Exit 1 if README is stale")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    manifest = build_manifest()

    if not args.check:
        # Just print the manifest
        print(json.dumps(manifest, indent=2))
        return

    findings = check_readme(manifest)

    if args.json:
        print(json.dumps({"stale": bool(findings), "findings": findings}, indent=2))
    else:
        if findings:
            print(f"README.md is STALE — {len(findings)} issue(s) found:")
            for f in findings:
                print(f"  - [{f['section']}] {f['issue']}")
        else:
            print("README.md is UP TO DATE")

    if findings:
        sys.exit(1)


if __name__ == "__main__":
    main()

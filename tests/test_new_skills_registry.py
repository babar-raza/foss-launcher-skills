"""Tests verifying S-111 to S-115 governance capability skills are correctly registered.

Checks that:
  - All 5 new skills appear in skills/registry.yaml with correct IDs
  - Each skill has a canonical .md file in skills/
  - Each public skill has a Claude command in .claude/commands/
  - Each skill has an agent skill in .agents/skills/
  - validate_skills.py passes (no violations)
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

NEW_SKILLS = [
    ("S-111", "capability-status"),
    ("S-112", "sync-capabilities"),
    ("S-113", "validate-capability-parity"),
    ("S-114", "detect-capability-drift"),
    ("S-115", "scaffold-capability"),
]


def test_new_skills_in_registry():
    """S-111 to S-115 must all appear in skills/registry.yaml."""
    try:
        import yaml
    except ImportError:
        pytest.skip("pyyaml not installed")

    registry_path = _REPO_ROOT / "skills" / "registry.yaml"
    with open(registry_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    skills = data.get("skills", [])
    ids_in_registry = {s.get("id"): s.get("name") for s in skills}
    names_in_registry = {s.get("name"): s.get("id") for s in skills}

    for expected_id, expected_name in NEW_SKILLS:
        assert expected_id in ids_in_registry, f"{expected_id} missing from skills/registry.yaml"
        assert ids_in_registry[expected_id] == expected_name, (
            f"{expected_id} has wrong name: expected {expected_name}, got {ids_in_registry[expected_id]}"
        )
        assert expected_name in names_in_registry, f"{expected_name} missing from registry"


def test_canonical_skill_files_exist():
    """Each new skill must have a canonical skills/{name}.md file."""
    for _, name in NEW_SKILLS:
        skill_path = _REPO_ROOT / "skills" / f"{name}.md"
        assert skill_path.exists(), f"skills/{name}.md not found"


def test_claude_command_adapters_exist():
    """Each new public skill must have a .claude/commands/{name}.md adapter."""
    for _, name in NEW_SKILLS:
        cmd_path = _REPO_ROOT / ".claude" / "commands" / f"{name}.md"
        assert cmd_path.exists(), f".claude/commands/{name}.md not found"


def test_agent_skill_adapters_exist():
    """Each new skill must have a .agents/skills/{name}/SKILL.md adapter."""
    for _, name in NEW_SKILLS:
        skill_path = _REPO_ROOT / ".agents" / "skills" / name / "SKILL.md"
        assert skill_path.exists(), f".agents/skills/{name}/SKILL.md not found"


def test_kilocode_skill_adapters_exist():
    """Each new skill must have a .kilocode/skills/{name}/SKILL.md adapter."""
    for _, name in NEW_SKILLS:
        skill_path = _REPO_ROOT / ".kilocode" / "skills" / name / "SKILL.md"
        assert skill_path.exists(), f".kilocode/skills/{name}/SKILL.md not found"


def test_skill_frontmatter_has_correct_id():
    """Each canonical skill file must have matching id: in YAML frontmatter."""
    import re
    for expected_id, name in NEW_SKILLS:
        skill_path = _REPO_ROOT / "skills" / f"{name}.md"
        if not skill_path.exists():
            pytest.skip(f"skills/{name}.md not found")
        content = skill_path.read_text(encoding="utf-8")
        match = re.search(r"^id:\s*(\S+)", content, re.MULTILINE)
        if match:
            assert match.group(1) == expected_id, (
                f"skills/{name}.md frontmatter id mismatch: expected {expected_id}, got {match.group(1)}"
            )


def test_validate_skills_passes():
    """validate_skills.py must pass with no violations after adding new skills."""
    result = subprocess.run(
        [sys.executable, "scripts/validate_skills.py"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"validate_skills.py failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "PASS" in result.stdout


def test_claude_commands_match_canonical_bodies():
    """Claude command bodies must match canonical skill bodies (frontmatter stripped)."""
    import re
    frontmatter_re = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)

    for _, name in NEW_SKILLS:
        canonical = _REPO_ROOT / "skills" / f"{name}.md"
        command = _REPO_ROOT / ".claude" / "commands" / f"{name}.md"
        if not canonical.exists() or not command.exists():
            continue

        canonical_text = canonical.read_text(encoding="utf-8")
        canonical_body = frontmatter_re.sub("", canonical_text, count=1).lstrip("\n")
        command_body = command.read_text(encoding="utf-8")

        assert canonical_body == command_body, (
            f".claude/commands/{name}.md does not match skills/{name}.md body"
        )

"""Tests for tools/distribute.py — skill distribution to agent-specific formats."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.distribute import distribute, generate_registry, parse_skill, verify_parity  # noqa: E402
from scripts.skill_constants import INTERNAL_SKILLS  # noqa: E402

SKILLS_DIR = REPO_ROOT / "skills"


# ---------------------------------------------------------------------------
# parse_skill
# ---------------------------------------------------------------------------

SKILL_WITH_FRONTMATTER = """\
---
name: test-skill
id: S-99
description: A test skill
args: "{family} {platform}"
---

# Test Skill

This is the body of the skill.
"""

SKILL_WITHOUT_FRONTMATTER = """\
# Test Skill

This is a skill without frontmatter.
"""


def test_parse_skill_extracts_frontmatter():
    fm, body = parse_skill(SKILL_WITH_FRONTMATTER)
    assert "name: test-skill" in fm
    assert fm.startswith("---")
    assert fm.rstrip().endswith("---")


def test_parse_skill_extracts_body():
    fm, body = parse_skill(SKILL_WITH_FRONTMATTER)
    assert "# Test Skill" in body
    assert "This is the body" in body


def test_parse_skill_no_frontmatter():
    fm, body = parse_skill(SKILL_WITHOUT_FRONTMATTER)
    assert fm == ""
    assert "# Test Skill" in body


def test_parse_skill_body_does_not_contain_frontmatter():
    fm, body = parse_skill(SKILL_WITH_FRONTMATTER)
    assert "name: test-skill" not in body


# ---------------------------------------------------------------------------
# distribute
# ---------------------------------------------------------------------------

def test_distribute_creates_claude_dir(tmp_path):
    distribute(SKILLS_DIR, tmp_path)
    assert (tmp_path / ".claude" / "commands").is_dir()


def test_distribute_creates_agents_dir(tmp_path):
    distribute(SKILLS_DIR, tmp_path)
    assert (tmp_path / ".agents" / "skills").is_dir()


def test_distribute_creates_kilocode_dir(tmp_path):
    distribute(SKILLS_DIR, tmp_path)
    assert (tmp_path / ".kilocode" / "skills").is_dir()


def test_distribute_skill_count_matches(tmp_path):
    """Claude should have total_skills minus internal_skills files."""
    distribute(SKILLS_DIR, tmp_path)
    skill_files = list(SKILLS_DIR.glob("*.md"))
    claude_files = list((tmp_path / ".claude" / "commands").glob("*.md"))
    expected = len(skill_files) - len(INTERNAL_SKILLS)
    assert len(claude_files) == expected


def test_distribute_claude_strips_frontmatter(tmp_path):
    distribute(SKILLS_DIR, tmp_path)
    for f in (tmp_path / ".claude" / "commands").glob("*.md"):
        content = f.read_text(encoding="utf-8")
        assert not content.startswith("---"), f"{f.name} should not start with frontmatter"


def test_distribute_agents_keeps_frontmatter(tmp_path):
    distribute(SKILLS_DIR, tmp_path)
    for skill_dir in (tmp_path / ".agents" / "skills").iterdir():
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{skill_dir.name}/SKILL.md must start with frontmatter"


def test_distribute_kilocode_keeps_frontmatter(tmp_path):
    distribute(SKILLS_DIR, tmp_path)
    for skill_dir in (tmp_path / ".kilocode" / "skills").iterdir():
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{skill_dir.name}/SKILL.md must start with frontmatter"


def test_distribute_idempotent(tmp_path):
    distribute(SKILLS_DIR, tmp_path)
    files_first = {
        p.relative_to(tmp_path): p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.md")
    }
    distribute(SKILLS_DIR, tmp_path)
    files_second = {
        p.relative_to(tmp_path): p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.md")
    }
    assert files_first == files_second


def test_distribute_all_three_targets_equal_count(tmp_path):
    """codex and kilocode get all skills; Claude gets all minus internal."""
    distribute(SKILLS_DIR, tmp_path)
    skill_files = list(SKILLS_DIR.glob("*.md"))
    total = len(skill_files)
    claude_count = len(list((tmp_path / ".claude" / "commands").glob("*.md")))
    codex_count = len(list((tmp_path / ".agents" / "skills").iterdir()))
    kilo_count = len(list((tmp_path / ".kilocode" / "skills").iterdir()))
    assert codex_count == total, f"codex should have all {total} skills"
    assert kilo_count == total, f"kilocode should have all {total} skills"
    assert claude_count == total - len(INTERNAL_SKILLS), (
        f"claude should have {total - len(INTERNAL_SKILLS)} skills "
        f"(total={total}, internal={len(INTERNAL_SKILLS)})"
    )


# ---------------------------------------------------------------------------
# INTERNAL_SKILLS exclusion
# ---------------------------------------------------------------------------

def test_internal_skills_excluded_from_claude(tmp_path):
    """Internal skills must not appear in .claude/commands."""
    distribute(SKILLS_DIR, tmp_path)
    claude_names = {f.stem for f in (tmp_path / ".claude" / "commands").glob("*.md")}
    for internal in INTERNAL_SKILLS:
        assert internal not in claude_names, (
            f"Internal skill '{internal}' should not be in .claude/commands"
        )


def test_internal_skills_present_in_codex(tmp_path):
    """Internal skills must appear in .agents/skills (codex gets all)."""
    distribute(SKILLS_DIR, tmp_path)
    codex_names = {d.name for d in (tmp_path / ".agents" / "skills").iterdir() if d.is_dir()}
    for internal in INTERNAL_SKILLS:
        assert internal in codex_names, (
            f"Internal skill '{internal}' should be in .agents/skills"
        )


def test_internal_skills_present_in_kilocode(tmp_path):
    """Internal skills must appear in .kilocode/skills."""
    distribute(SKILLS_DIR, tmp_path)
    kilo_names = {d.name for d in (tmp_path / ".kilocode" / "skills").iterdir() if d.is_dir()}
    for internal in INTERNAL_SKILLS:
        assert internal in kilo_names, (
            f"Internal skill '{internal}' should be in .kilocode/skills"
        )


# ---------------------------------------------------------------------------
# registry.json generation
# ---------------------------------------------------------------------------

def test_generate_registry_creates_file(tmp_path):
    """generate_registry() writes skills/registry.json."""
    catalog = generate_registry(SKILLS_DIR)
    registry_path = SKILLS_DIR / "registry.json"
    assert registry_path.exists(), "skills/registry.json should be created"
    assert len(catalog) > 0


def test_generate_registry_has_required_fields(tmp_path):
    """Every entry in registry.json has id, name, description, internal."""
    catalog = generate_registry(SKILLS_DIR)
    for entry in catalog:
        assert "id" in entry, f"registry entry missing 'id': {entry}"
        assert "name" in entry, f"registry entry missing 'name': {entry}"
        assert "description" in entry, f"registry entry missing 'description': {entry}"
        assert "internal" in entry, f"registry entry missing 'internal': {entry}"


def test_generate_registry_internal_flag_correct():
    """Internal skills must have internal=true in registry.json."""
    catalog = generate_registry(SKILLS_DIR)
    registry_by_name = {e["name"]: e for e in catalog}
    for internal in INTERNAL_SKILLS:
        if internal in registry_by_name:
            assert registry_by_name[internal]["internal"] is True, (
                f"'{internal}' should have internal=true in registry"
            )


# ---------------------------------------------------------------------------
# verify_parity
# ---------------------------------------------------------------------------

def test_verify_parity_passes_after_distribute(tmp_path):
    """verify_parity should return no issues after a fresh distribute."""
    distribute(SKILLS_DIR, tmp_path)
    issues = verify_parity(SKILLS_DIR, tmp_path)
    assert issues == [], f"Expected no parity issues, got: {issues}"


def test_verify_parity_detects_missing_skill(tmp_path):
    """verify_parity should flag a skill that was distributed but whose source was removed."""
    distribute(SKILLS_DIR, tmp_path)
    # Simulate a missing distributed file
    victim = next((tmp_path / ".agents" / "skills").iterdir())
    skill_file = victim / "SKILL.md"
    skill_file.unlink()
    issues = verify_parity(SKILLS_DIR, tmp_path)
    assert any("MISSING" in i for i in issues)


# ---------------------------------------------------------------------------
# depends_on in registry (RC-3)
# ---------------------------------------------------------------------------

def test_generate_registry_entries_have_depends_on_key():
    """Every registry entry must have a 'depends_on' key (empty list if not set)."""
    catalog = generate_registry(SKILLS_DIR)
    for entry in catalog:
        assert "depends_on" in entry, (
            f"registry entry '{entry.get('name')}' missing 'depends_on' key"
        )
        assert isinstance(entry["depends_on"], list), (
            f"registry entry '{entry.get('name')}' depends_on must be a list"
        )


def test_registry_depends_on_correct_for_critical_chain():
    """The write-path gate chain must have correct depends_on declarations."""
    catalog = generate_registry(SKILLS_DIR)
    by_name = {e["name"]: e for e in catalog}

    # path-guard has no dependencies
    assert by_name["path-guard"]["depends_on"] == [], (
        "path-guard should declare depends_on: []"
    )
    # ground-check depends on path-guard
    assert "path-guard" in by_name["ground-check"]["depends_on"], (
        "ground-check should declare depends_on: [path-guard]"
    )
    # evidence-cite depends on path-guard and ground-check
    assert "path-guard" in by_name["evidence-cite"]["depends_on"]
    assert "ground-check" in by_name["evidence-cite"]["depends_on"]
    # change-guard depends on path-guard and ground-check
    assert "path-guard" in by_name["change-guard"]["depends_on"]
    assert "ground-check" in by_name["change-guard"]["depends_on"]


def test_dependency_graph_has_no_cycles():
    """The annotated dependency graph must be acyclic."""
    from tools.distribute import _detect_dependency_cycles
    catalog = generate_registry(SKILLS_DIR)
    cycles = _detect_dependency_cycles(catalog)
    assert not cycles, f"Dependency cycles detected: {cycles}"

"""Tests for tools/distribute.py — skill distribution to agent-specific formats."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.distribute import distribute, parse_skill  # noqa: E402

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
    distribute(SKILLS_DIR, tmp_path)
    skill_files = list(SKILLS_DIR.glob("*.md"))
    claude_files = list((tmp_path / ".claude" / "commands").glob("*.md"))
    assert len(claude_files) == len(skill_files)


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
    distribute(SKILLS_DIR, tmp_path)
    claude_count = len(list((tmp_path / ".claude" / "commands").glob("*.md")))
    codex_count = len(list((tmp_path / ".agents" / "skills").iterdir()))
    kilo_count = len(list((tmp_path / ".kilocode" / "skills").iterdir()))
    assert claude_count == codex_count == kilo_count

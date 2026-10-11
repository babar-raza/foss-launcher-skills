"""Tests for sync_skills.py — skill registry parity checks."""

import pytest
import sync_skills
from sync_skills import (
    discover_canonical,
    discover_provider,
    check_parity,
    list_skill_ids,
    _extract_id,
)


class TestDiscovery:
    """Test that canonical and provider skill directories are discoverable."""

    def test_canonical_not_empty(self):
        skills = discover_canonical()
        assert len(skills) >= 40, f"Expected 40+ canonical skills, got {len(skills)}"

    def test_agents_not_empty(self):
        skills = discover_provider("agents")
        assert len(skills) >= 30, f"Expected 30+ agent skills, got {len(skills)}"

    def test_claude_not_empty(self):
        skills = discover_provider("claude")
        assert len(skills) >= 30, f"Expected 30+ claude commands, got {len(skills)}"

    def test_kilocode_not_empty(self):
        skills = discover_provider("kilocode")
        assert len(skills) >= 30, f"Expected 30+ kilocode skills, got {len(skills)}"


class TestParity:
    """Test that canonical skills match providers (accounting for known exceptions)."""

    def test_parity_check_passes(self, tmp_path, monkeypatch):
        """check_parity() returns no issues when providers match canonical."""
        # Create an isolated, fully-synced set of skill dirs so the test is
        # hermetic and does not depend on real working-tree skill file state.
        canonical = tmp_path / "skills"
        canonical.mkdir()
        content = "# S-99: Test Skill\n\n## Purpose\nA minimal test skill.\n"
        (canonical / "test-skill.md").write_text(content, encoding="utf-8")

        agents = tmp_path / "agents"
        claude = tmp_path / "claude"
        kilocode = tmp_path / "kilocode"
        agents.mkdir(); claude.mkdir(); kilocode.mkdir()

        (agents / "test-skill").mkdir()
        (agents / "test-skill" / "SKILL.md").write_text(content, encoding="utf-8")
        (claude / "test-skill.md").write_text(content, encoding="utf-8")
        (kilocode / "test-skill").mkdir()
        (kilocode / "test-skill" / "SKILL.md").write_text(content, encoding="utf-8")

        monkeypatch.setattr(sync_skills, "CANONICAL_DIR", canonical)
        monkeypatch.setattr(sync_skills, "PROVIDERS", {
            "agents": agents,
            "claude": claude,
            "kilocode": kilocode,
        })

        issues = check_parity()
        assert len(issues) == 0, (
            f"Parity check found {len(issues)} issue(s):\n"
            + "\n".join(f"  [{i['type']}] {i['provider']}: {i['slug']}" for i in issues)
        )


class TestSkillIDs:
    """Test that all canonical skills have unique S-XX IDs."""

    def test_all_skills_have_ids(self):
        skills = list_skill_ids()
        no_id = [s for s in skills if s[0] == "NONE"]
        assert len(no_id) == 0, (
            f"{len(no_id)} skills without IDs: "
            + ", ".join(s[1] for s in no_id)
        )

    def test_no_duplicate_ids(self):
        skills = list_skill_ids()
        ids = [s[0] for s in skills if s[0] != "NONE"]
        seen = set()
        dupes = []
        for sid in ids:
            if sid in seen:
                dupes.append(sid)
            seen.add(sid)
        assert len(dupes) == 0, f"Duplicate IDs: {dupes}"


class TestExtractID:
    """Test ID extraction from skill file headers."""

    def test_standard_header(self):
        assert _extract_id("# S-01: Path Guard") == "S-01"

    def test_high_number(self):
        assert _extract_id("# S-64: Getting Started") == "S-64"

    def test_no_id(self):
        assert _extract_id("# Some Skill Without ID") is None

    def test_description_first(self):
        assert _extract_id("Some description text.") is None

    def test_id_past_1500_chars_still_found(self):
        """ST-147/TC-SG-20c (2026-08-31): a verbose CONTRACT comment block can
        legitimately push the # S-XX: heading past a fixed prefix window --
        foss-java-publish.md's heading sat at char offset 1833, past the old
        1500-char scan, which made a real ID read as "NONE". Unlike
        sync_providers.py's sibling extractor (which deliberately treats a
        far heading as absent, see test_id_beyond_1500_chars_not_found), this
        checker must find any heading in the file."""
        padding = "x" * 1600 + "\n# S-110: Late Heading\n"
        assert _extract_id(padding) == "S-110"

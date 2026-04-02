"""Tests for scripts/sync_commands.py — skills/ ↔ .claude/commands/ sync."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sync_commands import check_sync, do_sync, strip_frontmatter


# ---------------------------------------------------------------------------
# strip_frontmatter
# ---------------------------------------------------------------------------

class TestStripFrontmatter:
    def test_strips_frontmatter_block(self):
        text = "---\nname: foo\nid: S-01\n---\n\n# Body\n\nContent here.\n"
        result = strip_frontmatter(text)
        assert result == "# Body\n\nContent here.\n"

    def test_no_frontmatter_unchanged(self):
        text = "# No frontmatter\n\nJust content.\n"
        result = strip_frontmatter(text)
        assert result == text

    def test_multiline_frontmatter(self):
        text = "---\nname: my-skill\nid: S-01\nargs: \"{x}\"\n---\n\n# Body\n"
        result = strip_frontmatter(text)
        assert result == "# Body\n"


# ---------------------------------------------------------------------------
# check_sync
# ---------------------------------------------------------------------------

class TestCheckSync:
    def _make_dirs(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()
        return skills_dir, commands_dir

    def test_in_sync_returns_empty(self, tmp_path):
        skills_dir, commands_dir = self._make_dirs(tmp_path)
        body = "# My Skill\n\nDoes things.\n"
        (skills_dir / "my-skill.md").write_text(
            f"---\nname: my-skill\n---\n\n{body}", encoding="utf-8"
        )
        (commands_dir / "my-skill.md").write_text(body, encoding="utf-8")
        assert check_sync(skills_dir, commands_dir) == []

    def test_missing_command_detected(self, tmp_path):
        skills_dir, commands_dir = self._make_dirs(tmp_path)
        (skills_dir / "my-skill.md").write_text("---\nname: x\n---\n\nbody\n", encoding="utf-8")
        diffs = check_sync(skills_dir, commands_dir)
        assert len(diffs) == 1
        assert "MISSING" in diffs[0]

    def test_content_drift_detected(self, tmp_path):
        skills_dir, commands_dir = self._make_dirs(tmp_path)
        (skills_dir / "my-skill.md").write_text(
            "---\nname: x\n---\n\nnew body\n", encoding="utf-8"
        )
        (commands_dir / "my-skill.md").write_text("old body\n", encoding="utf-8")
        diffs = check_sync(skills_dir, commands_dir)
        assert len(diffs) == 1
        assert "DIFFERS" in diffs[0]

    def test_extra_command_file_detected(self, tmp_path):
        skills_dir, commands_dir = self._make_dirs(tmp_path)
        (commands_dir / "ghost.md").write_text("ghost content\n", encoding="utf-8")
        diffs = check_sync(skills_dir, commands_dir)
        assert len(diffs) == 1
        assert "EXTRA" in diffs[0]

    def test_registry_yaml_not_treated_as_skill(self, tmp_path):
        skills_dir, commands_dir = self._make_dirs(tmp_path)
        (skills_dir / "registry.yaml").write_text("schema_version: 1\nskills: []\n")
        diffs = check_sync(skills_dir, commands_dir)
        assert diffs == []


# ---------------------------------------------------------------------------
# do_sync
# ---------------------------------------------------------------------------

class TestDoSync:
    def test_sync_creates_missing_command(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        body = "# New Skill\n\nDoes things.\n"
        (skills_dir / "new-skill.md").write_text(
            f"---\nname: new-skill\nid: S-99\n---\n\n{body}", encoding="utf-8"
        )

        synced, already_ok = do_sync(skills_dir, commands_dir)
        assert synced == 1
        assert already_ok == 0
        result = (commands_dir / "new-skill.md").read_text(encoding="utf-8")
        assert result == body

    def test_sync_updates_drifted_command(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        new_body = "# Updated content\n"
        (skills_dir / "my-skill.md").write_text(
            f"---\nname: my-skill\n---\n\n{new_body}", encoding="utf-8"
        )
        (commands_dir / "my-skill.md").write_text("# Old content\n", encoding="utf-8")

        synced, already_ok = do_sync(skills_dir, commands_dir)
        assert synced == 1
        assert (commands_dir / "my-skill.md").read_text(encoding="utf-8") == new_body

    def test_sync_skips_already_ok(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        body = "# Same content\n"
        (skills_dir / "my-skill.md").write_text(
            f"---\nname: my-skill\n---\n\n{body}", encoding="utf-8"
        )
        (commands_dir / "my-skill.md").write_text(body, encoding="utf-8")

        synced, already_ok = do_sync(skills_dir, commands_dir)
        assert synced == 0
        assert already_ok == 1

    def test_sync_result_is_idempotent(self, tmp_path):
        """Running sync twice produces the same result."""
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        body = "# My Skill\n\nContent.\n"
        (skills_dir / "my-skill.md").write_text(
            f"---\nname: my-skill\n---\n\n{body}", encoding="utf-8"
        )

        do_sync(skills_dir, commands_dir)
        synced2, already_ok2 = do_sync(skills_dir, commands_dir)
        assert synced2 == 0
        assert already_ok2 == 1

    def test_sync_then_check_passes(self, tmp_path):
        """After do_sync(), check_sync() should return no diffs."""
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        for name in ["skill-a", "skill-b"]:
            (skills_dir / f"{name}.md").write_text(
                f"---\nname: {name}\n---\n\n# {name} body\n", encoding="utf-8"
            )

        do_sync(skills_dir, commands_dir)
        assert check_sync(skills_dir, commands_dir) == []

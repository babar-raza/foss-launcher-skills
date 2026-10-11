"""Tests for check_skill_registry.py — cross-tree ID collision checks."""
from __future__ import annotations

import sys
from pathlib import Path

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks" 
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import check_skill_registry  # noqa: E402


# ---------------------------------------------------------------------------
# _scan_tree_ids
# ---------------------------------------------------------------------------


class TestScanTreeIds:
    """Test ID extraction from different provider tree structures."""

    def test_canonical_flat_md(self, tmp_path: Path):
        """Canonical tree: flat *.md files."""
        (tmp_path / "foo.md").write_text("# S-10: Foo Skill\n\nBody.", encoding="utf-8")
        (tmp_path / "bar.md").write_text("# S-20: Bar Skill\n\nBody.", encoding="utf-8")
        results = check_skill_registry._scan_tree_ids("canonical", tmp_path)
        ids = {r[0] for r in results}
        slugs = {r[1] for r in results}
        assert ids == {"S-10", "S-20"}
        assert slugs == {"foo", "bar"}

    def test_claude_flat_md(self, tmp_path: Path):
        """Claude tree: flat *.md files (same structure as canonical)."""
        (tmp_path / "skill-a.md").write_text("---\nid: S-05\n---\n\n# S-05: A\n", encoding="utf-8")
        results = check_skill_registry._scan_tree_ids("claude", tmp_path)
        assert len(results) == 1
        assert results[0] == ("S-05", "skill-a", "claude")

    def test_agents_subfolder_structure(self, tmp_path: Path):
        """Agents/kilocode tree: {slug}/SKILL.md structure."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# S-42: My Skill\n", encoding="utf-8")
        results = check_skill_registry._scan_tree_ids("agents", tmp_path)
        assert len(results) == 1
        assert results[0] == ("S-42", "my-skill", "agents")

    def test_empty_directory(self, tmp_path: Path):
        results = check_skill_registry._scan_tree_ids("canonical", tmp_path)
        assert results == []

    def test_skips_files_without_id(self, tmp_path: Path):
        (tmp_path / "no-id.md").write_text("# A Skill Without ID\n\nBody.", encoding="utf-8")
        results = check_skill_registry._scan_tree_ids("canonical", tmp_path)
        assert results == []

    def test_skips_readme(self, tmp_path: Path):
        """README.md should be ignored (not a skill)."""
        (tmp_path / "README.md").write_text("# S-99: Fake\n", encoding="utf-8")
        (tmp_path / "real.md").write_text("# S-01: Real\n", encoding="utf-8")
        results = check_skill_registry._scan_tree_ids("canonical", tmp_path)
        assert len(results) == 1
        assert results[0][1] == "real"


# ---------------------------------------------------------------------------
# check_cross_tree (real repo integration)
# ---------------------------------------------------------------------------


class TestCheckCrossTree:
    def test_no_collisions_in_real_repo(self):
        """The actual repo should have no cross-tree ID collisions."""
        issues = check_skill_registry.check_cross_tree()
        assert issues == [], (
            f"Cross-tree ID collisions found:\n"
            + "\n".join(i["detail"] for i in issues)
        )


# ---------------------------------------------------------------------------
# check_cross_tree (synthetic collision)
# ---------------------------------------------------------------------------


class TestCheckCrossTreeSynthetic:
    def test_detects_collision(self, tmp_path: Path, monkeypatch):
        """Two different slugs sharing the same S-XX ID should be detected."""
        # Set up two synthetic trees with colliding IDs
        tree_a = tmp_path / "tree_a"
        tree_a.mkdir()
        (tree_a / "skill-alpha.md").write_text("# S-99: Alpha\n", encoding="utf-8")

        tree_b = tmp_path / "tree_b"
        tree_b.mkdir()
        skill_dir = tree_b / "skill-beta"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# S-99: Beta\n", encoding="utf-8")

        # Monkeypatch PROVIDER_TREES to use synthetic directories
        monkeypatch.setattr(
            check_skill_registry,
            "PROVIDER_TREES",
            {"canonical": tree_a, "agents": tree_b},
        )

        issues = check_skill_registry.check_cross_tree()
        assert len(issues) == 1
        assert issues[0]["id"] == "S-99"
        assert issues[0]["check"] == "cross_tree_id_collision"
        slugs_found = {e["slug"] for e in issues[0]["entries"]}
        assert slugs_found == {"skill-alpha", "skill-beta"}

    def test_same_slug_across_trees_is_not_collision(self, tmp_path: Path, monkeypatch):
        """Same slug in multiple trees (normal mirroring) is NOT a collision."""
        tree_a = tmp_path / "tree_a"
        tree_a.mkdir()
        (tree_a / "my-skill.md").write_text("# S-10: My Skill\n", encoding="utf-8")

        tree_b = tmp_path / "tree_b"
        tree_b.mkdir()
        (tree_b / "my-skill.md").write_text("# S-10: My Skill\n", encoding="utf-8")

        monkeypatch.setattr(
            check_skill_registry,
            "PROVIDER_TREES",
            {"canonical": tree_a, "claude": tree_b},
        )

        issues = check_skill_registry.check_cross_tree()
        assert issues == []

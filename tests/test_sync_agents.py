"""Tests for scripts/sync_agents.py — .agents/skills/ and .kilocode/skills/ mirror sync."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sync_agents import check_sync, do_sync, load_skill_names


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_skill(skills_dir: Path, name: str, body: str | None = None) -> None:
    content = body or f"---\nname: {name}\nid: S-99\n---\n\n# {name} body\n"
    (skills_dir / f"{name}.md").write_text(content, encoding="utf-8")


def _make_mirror(base: Path, mirror_name: str) -> Path:
    """Create .agents/skills/ or .kilocode/skills/ directory structure."""
    mirror = base / mirror_name / "skills"
    mirror.mkdir(parents=True, exist_ok=True)
    return mirror


# ---------------------------------------------------------------------------
# load_skill_names
# ---------------------------------------------------------------------------

class TestLoadSkillNames:
    def test_returns_names_in_order(self, tmp_path):
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "schema_version: 1\n"
            "skills:\n"
            "  - {id: S-01, name: alpha}\n"
            "  - {id: S-02, name: beta}\n",
            encoding="utf-8",
        )
        names = load_skill_names(registry)
        assert names == ["alpha", "beta"]

    def test_skips_entries_without_name(self, tmp_path):
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            "schema_version: 1\n"
            "skills:\n"
            "  - {id: S-01, name: alpha}\n"
            "  - {id: S-02}\n",
            encoding="utf-8",
        )
        names = load_skill_names(registry)
        assert names == ["alpha"]

    def test_empty_registry(self, tmp_path):
        registry = tmp_path / "registry.yaml"
        registry.write_text("schema_version: 1\nskills: []\n", encoding="utf-8")
        names = load_skill_names(registry)
        assert names == []


# ---------------------------------------------------------------------------
# check_sync
# ---------------------------------------------------------------------------

class TestCheckSync:
    def _setup(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        agents_mirror = _make_mirror(tmp_path, ".agents")
        kilocode_mirror = _make_mirror(tmp_path, ".kilocode")
        return skills_dir, [agents_mirror, kilocode_mirror]

    def test_in_sync_returns_empty(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        content = "---\nname: my-skill\n---\n\n# Body\n"
        _write_skill(skills_dir, "my-skill", body=content)
        for mirror in mirrors:
            skill_dir = mirror / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        diffs = check_sync(skills_dir, mirrors)
        assert diffs == []

    def test_missing_skill_dir_detected(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        _write_skill(skills_dir, "my-skill")

        diffs = check_sync(skills_dir, mirrors)
        # Should report MISSING_DIR for both mirrors
        assert len(diffs) == 2
        assert all("MISSING" in d for d in diffs)

    def test_missing_skill_md_detected(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        content = "---\nname: my-skill\n---\n\n# Body\n"
        _write_skill(skills_dir, "my-skill", body=content)
        # Create subdirectory but NOT the SKILL.md file
        for mirror in mirrors:
            (mirror / "my-skill").mkdir()

        diffs = check_sync(skills_dir, mirrors)
        assert len(diffs) == 2
        assert all("MISSING" in d for d in diffs)

    def test_content_drift_detected(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        canonical = "---\nname: my-skill\n---\n\n# Updated body\n"
        stale = "---\nname: my-skill\n---\n\n# Old body\n"
        _write_skill(skills_dir, "my-skill", body=canonical)
        for mirror in mirrors:
            skill_dir = mirror / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(stale, encoding="utf-8")

        diffs = check_sync(skills_dir, mirrors)
        assert len(diffs) == 2
        assert all("DIFFERS" in d for d in diffs)

    def test_stale_subdir_detected(self, tmp_path):
        """Mirror subdir with no canonical skill file is flagged as STALE."""
        skills_dir, mirrors = self._setup(tmp_path)
        # No skill files in skills_dir, but mirrors have a stale subdir
        for mirror in mirrors:
            stale_dir = mirror / "old-skill"
            stale_dir.mkdir()
            (stale_dir / "SKILL.md").write_text("stale\n", encoding="utf-8")

        diffs = check_sync(skills_dir, mirrors)
        assert len(diffs) == 2
        assert all("STALE" in d for d in diffs)

    def test_multiple_skills_partial_drift(self, tmp_path):
        """Only drifted skills are reported; in-sync ones are silent."""
        skills_dir, mirrors = self._setup(tmp_path)

        ok_content = "---\nname: ok-skill\n---\n\n# OK\n"
        bad_content = "---\nname: bad-skill\n---\n\n# New\n"
        old_content = "---\nname: bad-skill\n---\n\n# Old\n"

        _write_skill(skills_dir, "ok-skill", body=ok_content)
        _write_skill(skills_dir, "bad-skill", body=bad_content)

        for mirror in mirrors:
            ok_dir = mirror / "ok-skill"
            ok_dir.mkdir()
            (ok_dir / "SKILL.md").write_text(ok_content, encoding="utf-8")

            bad_dir = mirror / "bad-skill"
            bad_dir.mkdir()
            (bad_dir / "SKILL.md").write_text(old_content, encoding="utf-8")

        diffs = check_sync(skills_dir, mirrors)
        assert len(diffs) == 2  # one DIFFERS per mirror for bad-skill only
        assert all("bad-skill" in d for d in diffs)

    def test_frontmatter_preserved_in_mirror(self, tmp_path):
        """Unlike .claude/commands/, agents mirrors keep frontmatter intact."""
        skills_dir, mirrors = self._setup(tmp_path)
        content = "---\nname: my-skill\nid: S-42\n---\n\n# Body\n"
        _write_skill(skills_dir, "my-skill", body=content)
        for mirror in mirrors:
            skill_dir = mirror / "my-skill"
            skill_dir.mkdir()
            # Mirror has full content including frontmatter
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        diffs = check_sync(skills_dir, mirrors)
        assert diffs == []


# ---------------------------------------------------------------------------
# do_sync
# ---------------------------------------------------------------------------

class TestDoSync:
    def _setup(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        agents_mirror = _make_mirror(tmp_path, ".agents")
        kilocode_mirror = _make_mirror(tmp_path, ".kilocode")
        return skills_dir, [agents_mirror, kilocode_mirror]

    def test_creates_missing_subdirs(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        content = "---\nname: new-skill\n---\n\n# New\n"
        _write_skill(skills_dir, "new-skill", body=content)

        synced, already_ok = do_sync(skills_dir, mirrors)
        assert synced == 2  # one per mirror
        assert already_ok == 0

        for mirror in mirrors:
            skill_md = mirror / "new-skill" / "SKILL.md"
            assert skill_md.exists()
            assert skill_md.read_text(encoding="utf-8") == content

    def test_preserves_frontmatter_in_skill_md(self, tmp_path):
        """SKILL.md in mirrors should contain full content, not stripped."""
        skills_dir, mirrors = self._setup(tmp_path)
        content = "---\nname: my-skill\nid: S-10\ndescription: test\n---\n\n# Body\n"
        _write_skill(skills_dir, "my-skill", body=content)

        do_sync(skills_dir, mirrors)

        for mirror in mirrors:
            result = (mirror / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
            assert result == content
            assert "---" in result  # frontmatter present

    def test_updates_drifted_skill_md(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        new_content = "---\nname: my-skill\n---\n\n# Updated\n"
        old_content = "---\nname: my-skill\n---\n\n# Old\n"

        _write_skill(skills_dir, "my-skill", body=new_content)
        for mirror in mirrors:
            skill_dir = mirror / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(old_content, encoding="utf-8")

        synced, already_ok = do_sync(skills_dir, mirrors)
        assert synced == 2
        for mirror in mirrors:
            result = (mirror / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
            assert result == new_content

    def test_already_in_sync_not_counted_as_synced(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        content = "---\nname: my-skill\n---\n\n# Same\n"
        _write_skill(skills_dir, "my-skill", body=content)
        for mirror in mirrors:
            skill_dir = mirror / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        synced, already_ok = do_sync(skills_dir, mirrors)
        assert synced == 0
        assert already_ok == 2

    def test_idempotent_double_sync(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        content = "---\nname: skill-x\n---\n\n# X\n"
        _write_skill(skills_dir, "skill-x", body=content)

        do_sync(skills_dir, mirrors)
        synced2, already_ok2 = do_sync(skills_dir, mirrors)
        assert synced2 == 0
        assert already_ok2 == 2

    def test_sync_then_check_passes(self, tmp_path):
        """After do_sync(), check_sync() must return no diffs."""
        skills_dir, mirrors = self._setup(tmp_path)
        for name in ["skill-a", "skill-b", "skill-c"]:
            _write_skill(skills_dir, name)

        do_sync(skills_dir, mirrors)
        diffs = check_sync(skills_dir, mirrors)
        assert diffs == []

    def test_internal_skills_included_in_agent_mirrors(self, tmp_path):
        """Unlike .claude/commands, agent mirrors include internal skills."""
        skills_dir, mirrors = self._setup(tmp_path)
        # Create an "internal" skill (the sync_agents script doesn't filter by internal flag)
        content = "---\nname: path-guard\nid: S-01\ninternal: true\n---\n\n# Path Guard\n"
        _write_skill(skills_dir, "path-guard", body=content)

        synced, _ = do_sync(skills_dir, mirrors)
        assert synced == 2

        for mirror in mirrors:
            skill_md = mirror / "path-guard" / "SKILL.md"
            assert skill_md.exists()
            assert "path-guard" in skill_md.read_text(encoding="utf-8")

    def test_counts_across_multiple_skills_and_mirrors(self, tmp_path):
        skills_dir, mirrors = self._setup(tmp_path)
        for name in ["skill-a", "skill-b"]:
            _write_skill(skills_dir, name)

        synced, already_ok = do_sync(skills_dir, mirrors)
        # 2 skills × 2 mirrors = 4 total synced
        assert synced == 4
        assert already_ok == 0


# ---------------------------------------------------------------------------
# Integration against real repo
# ---------------------------------------------------------------------------

class TestRealRepoIntegration:
    def test_real_mirrors_pass_check(self):
        """Real .agents/ and .kilocode/ mirrors must be in sync with skills/."""
        skills_dir = REPO_ROOT / "skills"
        mirror_dirs = [
            REPO_ROOT / ".agents" / "skills",
            REPO_ROOT / ".kilocode" / "skills",
        ]
        if not skills_dir.exists():
            pytest.skip("skills/ directory not present")
        if not all(m.exists() for m in mirror_dirs):
            pytest.skip("One or more mirror directories not present")

        diffs = check_sync(skills_dir, mirror_dirs)
        assert diffs == [], (
            f"{len(diffs)} discrepancy(ies) found:\n" + "\n".join(diffs)
        )

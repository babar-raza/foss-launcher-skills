"""Tests for scripts/ci/checks/check_skill_mirror_parity.py (pre-commit Step 25).

Proves the pre-commit skill-mirror-parity gate actually blocks when a touched
skill has drifted between canonical and a provider mirror, and does NOT block
on pre-existing drift in a skill the commit does not touch.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

_PIPELINE_DIR = str(Path(__file__).resolve().parents[3] / "scripts" / "pipeline")
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)

import check_skill_mirror_parity as gate  # noqa: E402
import sync_skills  # noqa: E402


class TestExtractTouchedSlugs:
    def test_canonical_path(self):
        slugs = gate.extract_touched_slugs(["skills/foss-java-publish.md"])
        assert slugs == {"foss-java-publish"}

    def test_claude_mirror_path(self):
        slugs = gate.extract_touched_slugs([".claude/commands/commit.md"])
        assert slugs == {"commit"}

    def test_agents_mirror_path(self):
        slugs = gate.extract_touched_slugs([".agents/skills/session-start/SKILL.md"])
        assert slugs == {"session-start"}

    def test_kilocode_mirror_path(self):
        slugs = gate.extract_touched_slugs([".kilocode/skills/page-plan/SKILL.md"])
        assert slugs == {"page-plan"}

    def test_windows_backslash_path(self):
        slugs = gate.extract_touched_slugs(["skills\\foss-java-publish.md"])
        assert slugs == {"foss-java-publish"}

    def test_non_skill_paths_ignored(self):
        slugs = gate.extract_touched_slugs([
            "content/docs.aspose.org/en/slides/java/_index.md",
            "data/foss_packages.json",
        ])
        assert slugs == set()

    def test_multiple_files_multiple_providers_same_slug(self):
        slugs = gate.extract_touched_slugs([
            "skills/commit.md",
            ".claude/commands/commit.md",
            ".agents/skills/commit/SKILL.md",
        ])
        assert slugs == {"commit"}


class TestMainGate:
    """Hermetic — points sync_skills at synthetic tmp_path dirs so this never
    depends on real working-tree skill drift state."""

    def _make_synced_skill(self, tmp_path, slug: str, content: str):
        canonical = tmp_path / "skills"
        agents = tmp_path / "agents"
        claude = tmp_path / "claude"
        kilocode = tmp_path / "kilocode"
        for d in (canonical, agents, claude, kilocode):
            d.mkdir(exist_ok=True)
        canonical_content = f"# S-01: {slug}\n\n## Purpose\n{content}\n"
        (canonical / f"{slug}.md").write_text(canonical_content, encoding="utf-8")
        (claude / f"{slug}.md").write_text(canonical_content, encoding="utf-8")
        (agents / slug).mkdir(exist_ok=True)
        (agents / slug / "SKILL.md").write_text(canonical_content, encoding="utf-8")
        (kilocode / slug).mkdir(exist_ok=True)
        (kilocode / slug / "SKILL.md").write_text(canonical_content, encoding="utf-8")
        return canonical, agents, claude, kilocode

    def test_allows_commit_when_touched_skill_in_parity(self, tmp_path, monkeypatch):
        self._make_synced_skill(tmp_path, "in-sync-skill", "Fully synced.")
        monkeypatch.setattr(sync_skills, "CANONICAL_DIR", tmp_path / "skills")
        monkeypatch.setattr(sync_skills, "PROVIDERS", {
            "agents": tmp_path / "agents",
            "claude": tmp_path / "claude",
            "kilocode": tmp_path / "kilocode",
        })

        exit_code = gate.main(["--staged-files", "skills/in-sync-skill.md"])
        assert exit_code == 0

    def test_blocks_commit_when_touched_skill_has_drift(self, tmp_path, monkeypatch):
        canonical, agents, claude, kilocode = self._make_synced_skill(
            tmp_path, "drifted-skill", "Original content."
        )
        # Introduce drift: claude mirror diverges from canonical, matching the
        # real-world case where an agent edits one skill file and never syncs.
        (claude / "drifted-skill.md").write_text(
            "# S-02: drifted-skill\n\n## Purpose\nDIVERGED CONTENT.\n", encoding="utf-8"
        )
        monkeypatch.setattr(sync_skills, "CANONICAL_DIR", canonical)
        monkeypatch.setattr(sync_skills, "PROVIDERS", {
            "agents": agents, "claude": claude, "kilocode": kilocode,
        })

        exit_code = gate.main(["--staged-files", "skills/drifted-skill.md"])
        assert exit_code == 1

    def test_does_not_block_on_untouched_skill_drift(self, tmp_path, monkeypatch):
        """The core scoping guarantee: pre-existing drift in a DIFFERENT skill
        than the one being committed must never block this commit."""
        canonical, agents, claude, kilocode = self._make_synced_skill(
            tmp_path, "in-sync-skill", "Fine."
        )
        # A second, already-drifted skill that this commit does NOT touch.
        (canonical / "unrelated-drifted.md").write_text(
            "# S-03: unrelated-drifted\n\n## Purpose\nCanonical version.\n", encoding="utf-8"
        )
        (claude / "unrelated-drifted.md").write_text(
            "# S-03: unrelated-drifted\n\n## Purpose\nStale mirror version.\n", encoding="utf-8"
        )
        (agents / "unrelated-drifted").mkdir()
        (agents / "unrelated-drifted" / "SKILL.md").write_text(
            "# S-03: unrelated-drifted\n\n## Purpose\nCanonical version.\n", encoding="utf-8"
        )
        (kilocode / "unrelated-drifted").mkdir()
        (kilocode / "unrelated-drifted" / "SKILL.md").write_text(
            "# S-03: unrelated-drifted\n\n## Purpose\nCanonical version.\n", encoding="utf-8"
        )
        monkeypatch.setattr(sync_skills, "CANONICAL_DIR", canonical)
        monkeypatch.setattr(sync_skills, "PROVIDERS", {
            "agents": agents, "claude": claude, "kilocode": kilocode,
        })

        # Commit only touches in-sync-skill — unrelated-drifted's drift must not block it.
        exit_code = gate.main(["--staged-files", "skills/in-sync-skill.md"])
        assert exit_code == 0

    def test_no_staged_skill_files_is_a_noop(self):
        exit_code = gate.main(["--staged-files"])
        assert exit_code == 0

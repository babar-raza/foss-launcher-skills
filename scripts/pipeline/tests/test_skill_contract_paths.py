"""Contract-path regression tests for skill/docs alignment.

These tests are intentionally file-content based so they do not require pytest
plugins or live knowledge data. They catch stale command paths, removed flows,
and missing wrapper inventory in the docs layer.
"""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def read_text(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8", errors="ignore")


class TestCanonicalSkillContracts(unittest.TestCase):
    def test_knowledge_bootstrap_uses_current_chain(self):
        text = read_text("skills/knowledge-bootstrap.md")
        self.assertIn("knowledge-enrich", text)
        self.assertIn("truth-merge", text)
        self.assertIn("truth-index", text)
        self.assertNotIn("truth-sync", text)

    def test_knowledge_update_uses_promote_and_enrich(self):
        text = read_text("skills/knowledge-update.md")
        self.assertIn("scripts/pipeline/enrich.py", text)
        self.assertIn("scripts/pipeline/promote.py", text)
        self.assertIn("scripts/pipeline/index.py", text)
        self.assertNotIn("scripts/pipeline/merge.py", text)

    def test_truth_index_uses_pipeline_index_script(self):
        text = read_text("skills/truth-index.md")
        self.assertIn("scripts/pipeline/index.py", text)
        self.assertNotIn("scripts/index.py", text)

    def test_evidence_cite_uses_frontmatter(self):
        text = read_text("skills/evidence-cite.md")
        self.assertIn("evidence:", text)
        self.assertIn("attach_evidence.py", text)
        self.assertIn("Do not use inline HTML comments", text)

    def test_getting_started_uses_current_pipeline(self):
        text = read_text("skills/getting-started.md")
        self.assertIn("python enrich.py", text)
        self.assertIn("python promote.py", text)
        self.assertIn("python index.py", text)
        self.assertNotIn("python merge.py", text)
        self.assertNotIn("truth-sync", text)

    def test_knowledge_enrich_exists(self):
        text = read_text("skills/knowledge-enrich.md")
        self.assertIn("enriched_claims.json", text)
        self.assertIn("scripts/pipeline/enrich.py", text)


class TestWrapperInventory(unittest.TestCase):
    def test_codex_kilo_wrapper_inventory(self):
        required = [
            ".agents/skills/knowledge-update/SKILL.md",
            ".kilocode/skills/knowledge-update/SKILL.md",
            ".agents/skills/rubric-align/SKILL.md",
            ".kilocode/skills/rubric-align/SKILL.md",
            ".agents/skills/faq-generate/SKILL.md",
            ".kilocode/skills/faq-generate/SKILL.md",
            ".agents/skills/category-fix/SKILL.md",
            ".kilocode/skills/category-fix/SKILL.md",
        ]
        for rel_path in required:
            with self.subTest(rel_path=rel_path):
                self.assertTrue((REPO_ROOT / rel_path).exists(), rel_path)

    def test_stack_wrappers_track_current_bootstrap_and_evidence_policy(self):
        for rel_path in [
            ".agents/skills/knowledge-bootstrap/SKILL.md",
            ".kilocode/skills/knowledge-bootstrap/SKILL.md",
            # knowledge-bootstrap internalized from .claude/commands/ (S-54)
            ".agents/skills/getting-started/SKILL.md",
            ".kilocode/skills/getting-started/SKILL.md",
            ".claude/commands/getting-started.md",
            ".agents/skills/evidence-cite/SKILL.md",
            ".kilocode/skills/evidence-cite/SKILL.md",
            # evidence-cite internalized from .claude/commands/ (S-24)
            ".agents/skills/truth-index/SKILL.md",
            ".kilocode/skills/truth-index/SKILL.md",
            ".claude/commands/truth-index.md",
        ]:
            with self.subTest(rel_path=rel_path):
                text = read_text(rel_path)
                self.assertNotIn("/truth-sync", text)
                self.assertNotIn("python merge.py", text)
                self.assertNotIn("python scripts/index.py", text)
                self.assertNotIn("<!-- evidence:", text)


class TestSkillFirstAwareness(unittest.TestCase):
    """Drift-detection tests: entry-point files must reference §6a/§6b and capability states.

    These tests catch drift when AGENTS.md §6a/§6b are updated but entry-point files
    are not updated to match. Fail here = update CLAUDE.md, CODEX.md, or governance.md.
    """

    ENTRY_POINTS = [
        "CLAUDE.md",
        "CODEX.md",
        ".kilocode/rules-code/governance.md",
    ]

    def test_entry_points_mention_skill_first(self):
        """Each entry-point must reference §6a or 'skill-first' or §6b."""
        for rel_path in self.ENTRY_POINTS:
            with self.subTest(rel_path=rel_path):
                text = read_text(rel_path)
                has_ref = (
                    "§6a" in text
                    or "skill-first" in text.lower()
                    or "§6b" in text
                )
                self.assertTrue(
                    has_ref,
                    f"{rel_path} does not mention §6a, §6b, or 'skill-first'. "
                    "Update it to reference AGENTS.md §6a/§6b when those sections change.",
                )

    def test_entry_points_mention_capability_classification(self):
        """Each entry-point must reference the capability classification states."""
        for rel_path in self.ENTRY_POINTS:
            with self.subTest(rel_path=rel_path):
                text = read_text(rel_path)
                has_states = (
                    "FULL" in text
                    or "PARTIAL" in text
                    or "NONE" in text
                    or "BROKEN" in text
                    or "capability" in text.lower()
                )
                self.assertTrue(
                    has_states,
                    f"{rel_path} does not mention capability classification states "
                    "(FULL/PARTIAL/NONE/BROKEN). Update when AGENTS.md §6b changes.",
                )


if __name__ == "__main__":
    unittest.main()

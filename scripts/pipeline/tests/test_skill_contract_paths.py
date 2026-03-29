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
            ".claude/commands/knowledge-bootstrap.md",
            ".agents/skills/getting-started/SKILL.md",
            ".kilocode/skills/getting-started/SKILL.md",
            ".claude/commands/getting-started.md",
            ".agents/skills/evidence-cite/SKILL.md",
            ".kilocode/skills/evidence-cite/SKILL.md",
            ".claude/commands/evidence-cite.md",
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


if __name__ == "__main__":
    unittest.main()

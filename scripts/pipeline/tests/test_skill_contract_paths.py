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
                self.assertNotIn("python scripts/index.py", text)
                self.assertNotIn("<!-- evidence:", text)


class TestSkillFirstAwareness(unittest.TestCase):
    """Drift-detection tests: entry-point files must reference §6a/§6b and capability states.

    These tests catch drift when AGENTS.md §6a/§6b are updated but entry-point files
    are not updated to match. Fail here = update CODEX.md or governance.md.

    CLAUDE.md was refactored to a "Session Gate" (no operational rules; all governance
    lives in AGENTS.md). It is intentionally excluded from this drift-detection list.
    """

    ENTRY_POINTS = [
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


class TestS12Completeness(unittest.TestCase):
    """Every skills/*.md file must be listed in AGENTS.md §12 Skills reference table.

    Catches the class of defect where a skill is added to skills/ but is never
    registered in §12 and therefore never subject to DAR governance checks.
    Fail here = add the skill to the §12 Skills reference table in AGENTS.md.
    """

    def _parse_s12_names(self, agents_text: str) -> set[str]:
        names: set[str] = set()
        in_skills = False
        for line in agents_text.splitlines():
            if "Skills reference" in line:
                in_skills = True
                continue
            if in_skills and "---" not in line and "Skill" not in line and line.startswith("| "):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if cols:
                    names.add(cols[0].strip())
            if in_skills and line.startswith("##") and "Skills reference" not in line:
                in_skills = False
        return names

    # Documentation files that coexist with skills in skills/ but are not skills themselves
    _NON_SKILL_SLUGS: set[str] = {"readme"}

    def test_all_skill_files_registered_in_s12(self):
        agents_text = read_text("AGENTS.md")
        s12_names = self._parse_s12_names(agents_text)
        skills_dir = REPO_ROOT / "skills"
        for skill_path in sorted(skills_dir.glob("*.md")):
            skill_name = skill_path.stem
            if skill_name.lower() in self._NON_SKILL_SLUGS:
                continue
            with self.subTest(skill=skill_name):
                self.assertIn(
                    skill_name,
                    s12_names,
                    f"skills/{skill_name}.md exists but is not listed in AGENTS.md §12 "
                    "Skills reference table. Add it to maintain DAR governance coverage.",
                )


class TestSkillContractPathExistence(unittest.TestCase):
    """Phase F: every scripts/pipeline/ path referenced in skills/CI/docs must exist."""

    _PATH_RE = __import__("re").compile(r"scripts/(?:pipeline|tests/pipeline)/[\w./]+\.py")

    def _missing_refs(self, text: str, source_label: str) -> list[str]:
        missing = []
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in self._PATH_RE.finditer(line):
                p = REPO_ROOT / m.group()
                if not p.exists():
                    missing.append(f"{source_label}:{lineno} → {m.group()}")
        return missing

    def test_contract_tags_in_skills_exist(self):
        skills_dir = REPO_ROOT / "skills"
        all_missing: list[str] = []
        for skill_file in sorted(skills_dir.glob("*.md")):
            text = skill_file.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), 1):
                if "CONTRACT:" in line:
                    for m in self._PATH_RE.finditer(line):
                        p = REPO_ROOT / m.group()
                        if not p.exists():
                            all_missing.append(
                                f"skills/{skill_file.name}:{lineno} → {m.group()}"
                            )
        self.assertEqual(all_missing, [], "\n".join(all_missing))

    def test_ci_workflow_paths_exist(self):
        ci_yml = REPO_ROOT / ".github" / "workflows" / "content-audit.yml"
        if not ci_yml.exists():
            self.skipTest("content-audit.yml not found")
        text = ci_yml.read_text(encoding="utf-8", errors="ignore")
        missing = self._missing_refs(text, ".github/workflows/content-audit.yml")
        self.assertEqual(missing, [], "\n".join(missing))

    def test_pipeline_docs_paths_exist(self):
        all_missing: list[str] = []
        for doc in ["scripts/pipeline/README.md", "scripts/pipeline/PIPELINE.md"]:
            p = REPO_ROOT / doc
            if p.exists():
                text = p.read_text(encoding="utf-8", errors="ignore")
                all_missing.extend(self._missing_refs(text, doc))
        self.assertEqual(all_missing, [], "\n".join(all_missing))

    def test_commit_skill_paths_exist(self):
        commit_md = REPO_ROOT / "skills" / "commit.md"
        if not commit_md.exists():
            self.skipTest("skills/commit.md not found")
        text = commit_md.read_text(encoding="utf-8", errors="ignore")
        missing = self._missing_refs(text, "skills/commit.md")
        self.assertEqual(missing, [], "\n".join(missing))


if __name__ == "__main__":
    unittest.main()

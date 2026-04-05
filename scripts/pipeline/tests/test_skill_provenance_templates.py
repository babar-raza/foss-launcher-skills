"""Regression tests: creation-path skill templates must include provenance blocks.

These tests enforce the PC-05 contract: every skill that creates a new content page
must write `content_origin` in the page's frontmatter template, concurrent with creation.

Fail here = a skill template is missing its provenance block.
Fix: add the required provenance: block to the skill's frontmatter template (see PC-05).

Creation-path skills (must carry content_origin: skill-generated):
  S-56 new-docs-page, S-57 new-blog-post, S-58 new-kb-howto, S-59 new-kb-faq,
  S-60 new-reference-page, S-19 page-draft, S-61 new-products-page

Index-scaffold skills (must carry content_origin: unknown + auto_updatable: false):
  S-70 new-docs-index, S-69 new-kb-index, S-71 new-reference-index

Out of scope (not tested here):
  S-62 batch-reference (delegates to S-60; no own template)
  S-48 family-sync (updates existing pages only; does not create pages)
  S-66 register-human-content (already correct; human-authored pattern)
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Canonical skill files in skills/
# ---------------------------------------------------------------------------

# Creation-path skills: must include content_origin: skill-generated
CREATION_PATH_SKILLS = [
    "skills/new-docs-page.md",
    "skills/new-blog-post.md",
    "skills/new-kb-howto.md",
    "skills/new-kb-faq.md",
    "skills/new-reference-page.md",
    "skills/page-draft.md",
    "skills/new-products-page.md",
]

# Index-scaffold skills: must include content_origin: unknown (structural-deferred)
INDEX_SCAFFOLD_SKILLS = [
    "skills/new-docs-index.md",
    "skills/new-kb-index.md",
    "skills/new-reference-index.md",
]

# All in-scope skills (creation-path + index-scaffold)
ALL_IN_SCOPE_SKILLS = CREATION_PATH_SKILLS + INDEX_SCAFFOLD_SKILLS

# Mirror directory layout: each skill name maps to its .claude/commands/<name>.md
# and .agents/skills/<name>/SKILL.md and .kilocode/skills/<name>/SKILL.md
def _skill_mirrors(skill_rel: str) -> list[str]:
    """Return mirror paths for a skill relative path (e.g. 'skills/new-docs-page.md')."""
    name = Path(skill_rel).stem
    return [
        f".claude/commands/{name}.md",
        f".agents/skills/{name}/SKILL.md",
        f".kilocode/skills/{name}/SKILL.md",
    ]


class TestCreationPathSkillsHaveProvenance(unittest.TestCase):
    """Creation-path skills must include content_origin: skill-generated in templates."""

    def test_content_origin_skill_generated_in_template(self):
        """Every creation-path skill must have content_origin: skill-generated."""
        for skill_path in CREATION_PATH_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                self.assertNotEqual(
                    text, "",
                    f"{skill_path} does not exist or is empty",
                )
                self.assertIn(
                    "content_origin: skill-generated",
                    text,
                    f"{skill_path} is missing 'content_origin: skill-generated' in its "
                    "frontmatter template. Add the provenance: block per PC-05.",
                )

    def test_last_mechanism_skill_in_template(self):
        """Every creation-path skill must have last_mechanism: skill."""
        for skill_path in CREATION_PATH_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                self.assertIn(
                    "last_mechanism: skill",
                    text,
                    f"{skill_path} is missing 'last_mechanism: skill' in its frontmatter "
                    "template. Add it to the provenance: block per PC-05.",
                )

    def test_auto_updatable_true_in_creation_path_templates(self):
        """Creation-path skills must have auto_updatable: true (skill-generated pages are updatable)."""
        for skill_path in CREATION_PATH_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                self.assertIn(
                    "auto_updatable: true",
                    text,
                    f"{skill_path} is missing 'auto_updatable: true' in its frontmatter "
                    "template. Add it to the provenance: block per PC-05.",
                )

    def test_creation_path_provenance_block_structure(self):
        """Creation-path skill templates must have a provenance: block with all three fields."""
        for skill_path in CREATION_PATH_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                self.assertIn(
                    "provenance:",
                    text,
                    f"{skill_path} is missing a 'provenance:' block in its frontmatter "
                    "template. Add per PC-05 specification.",
                )

    def test_deprecated_reviewed_field_absent_from_creation_templates(self):
        """Creation-path skill templates must NOT include the deprecated 'reviewed:' field.

        The reviewed: field was removed in TC-5. Including it in new page templates
        would re-introduce the deprecated field into all new skill-generated pages.
        """
        for skill_path in CREATION_PATH_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                # Only check within the provenance block if present to avoid
                # false positives in prose text of the skill description
                import re
                prov_match = re.search(
                    r'provenance:\s*\n((?:\s+\S.*\n)*)', text
                )
                if prov_match:
                    prov_block = prov_match.group(0)
                    self.assertNotIn(
                        "reviewed:",
                        prov_block,
                        f"{skill_path} has 'reviewed:' in its provenance: block. "
                        "The reviewed: field is deprecated — remove it.",
                    )

    def test_content_created_at_absent_from_creation_templates(self):
        """Creation-path skill templates must NOT include content_created_at in the template.

        content_created_at cannot be set accurately at Write time (the agent does not know
        the exact creation timestamp). It is populated by provenance_backfill.py post-creation.
        Including it in the template would result in an empty or incorrect value.
        """
        for skill_path in CREATION_PATH_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                import re
                prov_match = re.search(
                    r'provenance:\s*\n((?:\s+\S.*\n)*)', text
                )
                if prov_match:
                    prov_block = prov_match.group(0)
                    self.assertNotIn(
                        "content_created_at:",
                        prov_block,
                        f"{skill_path} has 'content_created_at:' in its provenance: block. "
                        "Omit it from templates — it is populated post-creation by "
                        "provenance_backfill.py.",
                    )


class TestIndexScaffoldSkillsHaveStructuralProvenance(unittest.TestCase):
    """Index-scaffold skills create structural _index.md pages and must use structural-deferred provenance."""

    def test_content_origin_unknown_in_index_scaffold_templates(self):
        """Index-scaffold skills must have content_origin: unknown (structural-deferred, not skill-generated)."""
        for skill_path in INDEX_SCAFFOLD_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                self.assertNotEqual(
                    text, "",
                    f"{skill_path} does not exist or is empty",
                )
                self.assertIn(
                    "content_origin: unknown",
                    text,
                    f"{skill_path} is missing 'content_origin: unknown' in its frontmatter "
                    "template. Index-scaffold skills create structural pages (not authored "
                    "content). Use content_origin: unknown + auto_updatable: false per PC-05.",
                )

    def test_auto_updatable_false_in_index_scaffold_templates(self):
        """Index-scaffold skills must have auto_updatable: false (structural pages must not be overwritten)."""
        for skill_path in INDEX_SCAFFOLD_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                self.assertIn(
                    "auto_updatable: false",
                    text,
                    f"{skill_path} is missing 'auto_updatable: false' in its frontmatter "
                    "template. Structural index pages must be write-locked per PC-05.",
                )

    def test_provenance_recovery_note_in_index_scaffold_templates(self):
        """Index-scaffold skills must have provenance_recovery_note: structural-page."""
        for skill_path in INDEX_SCAFFOLD_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                self.assertIn(
                    "provenance_recovery_note: structural-page",
                    text,
                    f"{skill_path} is missing 'provenance_recovery_note: structural-page'. "
                    "Add it to the provenance: block per PC-05 to distinguish structural "
                    "pages from unresolved unknowns.",
                )

    def test_index_scaffold_not_skill_generated(self):
        """Index-scaffold skills must NOT claim content_origin: skill-generated.

        These are structural Hugo navigation pages, not authored content.
        """
        for skill_path in INDEX_SCAFFOLD_SKILLS:
            with self.subTest(skill=skill_path):
                text = _read(skill_path)
                import re
                prov_match = re.search(
                    r'provenance:\s*\n((?:\s+\S.*\n)*)', text
                )
                if prov_match:
                    prov_block = prov_match.group(0)
                    self.assertNotIn(
                        "content_origin: skill-generated",
                        prov_block,
                        f"{skill_path} has 'content_origin: skill-generated' in its provenance "
                        "block. Index-scaffold skills create structural pages — use "
                        "'content_origin: unknown' instead.",
                    )


class TestSkillMirrorsSyncProvenance(unittest.TestCase):
    """Mirror copies of skills must carry the same provenance block as the canonical skill file.

    Each canonical skills/<name>.md has mirrors in:
      - .claude/commands/<name>.md
      - .agents/skills/<name>/SKILL.md
      - .kilocode/skills/<name>/SKILL.md

    If a mirror exists, it must have the same provenance fields as the canonical.
    Mirrors that do not exist are skipped (not all skills have all mirrors).
    """

    def _check_mirror(self, canonical_path: str, mirror_path: str, expected_text: str) -> None:
        mirror_text = _read(mirror_path)
        if mirror_text == "":
            return  # mirror does not exist; skip
        self.assertIn(
            expected_text,
            mirror_text,
            f"Mirror {mirror_path} is out of sync with {canonical_path}. "
            f"Expected '{expected_text}' but not found. "
            "Run sync_skills.py or update the mirror manually.",
        )

    def test_creation_path_mirrors_have_content_origin_skill_generated(self):
        """All existing creation-path skill mirrors must have content_origin: skill-generated."""
        for skill_path in CREATION_PATH_SKILLS:
            for mirror in _skill_mirrors(skill_path):
                with self.subTest(skill=skill_path, mirror=mirror):
                    self._check_mirror(skill_path, mirror, "content_origin: skill-generated")

    def test_creation_path_mirrors_have_last_mechanism_skill(self):
        """All existing creation-path skill mirrors must have last_mechanism: skill."""
        for skill_path in CREATION_PATH_SKILLS:
            for mirror in _skill_mirrors(skill_path):
                with self.subTest(skill=skill_path, mirror=mirror):
                    self._check_mirror(skill_path, mirror, "last_mechanism: skill")

    def test_index_scaffold_mirrors_have_content_origin_unknown(self):
        """All existing index-scaffold skill mirrors must have content_origin: unknown."""
        for skill_path in INDEX_SCAFFOLD_SKILLS:
            for mirror in _skill_mirrors(skill_path):
                with self.subTest(skill=skill_path, mirror=mirror):
                    self._check_mirror(skill_path, mirror, "content_origin: unknown")


class TestOutOfScopeSkillsNotChanged(unittest.TestCase):
    """Verify that out-of-scope skills were NOT modified by PC-05.

    batch-reference (S-62) covers its scope via new-reference-page delegation.
    family-sync (S-48) does not create pages.
    register-human-content (S-66) is already correct (human-authored pattern).
    """

    def test_batch_reference_delegates_not_creates(self):
        """batch-reference must reference new-reference-page (delegation, not own template)."""
        text = _read("skills/batch-reference.md")
        self.assertIn(
            "new-reference-page",
            text,
            "skills/batch-reference.md must delegate to new-reference-page skill.",
        )

    def test_register_human_content_has_human_authored(self):
        """register-human-content is the reference pattern — must keep human-authored."""
        text = _read("skills/register-human-content.md")
        self.assertIn(
            "content_origin: human-authored",
            text,
            "skills/register-human-content.md must keep 'content_origin: human-authored'. "
            "This is the reference pattern for human-authored provenance.",
        )
        self.assertIn(
            "auto_updatable: false",
            text,
            "skills/register-human-content.md must keep 'auto_updatable: false'.",
        )


if __name__ == "__main__":
    unittest.main()

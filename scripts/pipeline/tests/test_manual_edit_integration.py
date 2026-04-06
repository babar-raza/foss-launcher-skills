"""Integration tests for S-73 manual-edit skill — fixture-based pre-condition verification.

These tests verify that:
1. The five section fixture files are structurally valid per section rules
2. Section detection produces the correct result for each fixture path
3. Scope validation correctly gates each fixture scenario
4. Forbidden-field detection works for each fixture type
5. The AGENTS.md patch file exists (ready for human application)

Tests tagged @pytest.mark.integration require the full pipeline stack.
Tests without that tag are pure Python (no pipeline scripts needed).

NOTE: These tests do NOT invoke the actual S-73 skill execution (which is agent-driven).
They verify the precondition logic and contract invariants that the skill relies on.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import manual_edit_helpers as meh

from _repo_root import repo_root

_REPO_ROOT = repo_root()
_FIXTURES_DIR = _REPO_ROOT / "scripts" / "tests" / "fixtures" / "manual_edit"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    return yaml.safe_load(text[3:end]) or {}


# ===========================================================================
# Fixture files exist
# ===========================================================================

class TestFixtureFilesExist:
    @pytest.mark.parametrize("name", [
        "blog_fixture.md",
        "docs_fixture.md",
        "kb_fixture.md",
        "products_fixture.md",
        "reference_fixture.md",
    ])
    def test_fixture_file_exists(self, name):
        assert (_FIXTURES_DIR / name).exists(), f"Missing fixture: {name}"


# ===========================================================================
# Section detection for each fixture path
# ===========================================================================

_FIXTURE_SECTION_MAP = {
    "content/blog.aspose.org/3d/python/blog_fixture/index.md": "blog",
    "content/docs.aspose.org/en/3d/python/developer-guide/docs_fixture.md": "docs",
    "content/kb.aspose.org/en/3d/python/kb_fixture.md": "kb",
    "content/products.aspose.org/en/3d/_index.md": "products",
    "content/reference.aspose.org/en/3d/python/reference_fixture.md": "reference",
}


class TestFixtureSectionDetection:
    @pytest.mark.parametrize("path,expected_section", _FIXTURE_SECTION_MAP.items())
    def test_section_detected_correctly(self, path, expected_section):
        assert meh.detect_section(path) == expected_section

    def test_fixture_paths_cover_all_five_sections(self):
        detected = {meh.detect_section(p) for p in _FIXTURE_SECTION_MAP}
        assert detected == {"blog", "docs", "kb", "products", "reference"}


# ===========================================================================
# Fixture frontmatter structure per section rules
# ===========================================================================

class TestBlogFixtureFrontmatter:
    def setup_method(self):
        self.fm = _read_frontmatter(_FIXTURES_DIR / "blog_fixture.md")
        self.rules = meh.load_section_rules("blog")

    def test_title_present(self):
        assert self.fm.get("title")

    def test_description_present(self):
        assert self.fm.get("description")

    def test_author_is_aspose(self):
        assert self.fm.get("author") == "Aspose"

    def test_draft_field_present(self):
        assert "draft" in self.fm

    def test_evidence_block_present(self):
        assert "evidence" in self.fm

    def test_claims_non_empty(self):
        assert len(self.fm["evidence"].get("claims", [])) > 0

    def test_apis_non_empty(self):
        assert len(self.fm["evidence"].get("apis", [])) > 0

    def test_grade_present(self):
        assert self.fm.get("grade") in ("A", "B", "C", "D", "F")

    def test_provenance_block_present(self):
        assert "provenance" in self.fm

    def test_provenance_last_mechanism_not_manual_edit(self):
        # Fixtures start with grade-writer, not manual-edit-skill (that's post-execution)
        assert self.fm["provenance"]["last_mechanism"] != "manual-edit-skill"


class TestDocsFixtureFrontmatter:
    def setup_method(self):
        self.fm = _read_frontmatter(_FIXTURES_DIR / "docs_fixture.md")

    def test_title_present(self):
        assert self.fm.get("title")

    def test_description_present(self):
        assert self.fm.get("description")

    def test_type_is_docs(self):
        assert self.fm.get("type") == "docs"

    def test_evidence_present(self):
        assert "evidence" in self.fm


class TestKbFixtureFrontmatter:
    def setup_method(self):
        self.fm = _read_frontmatter(_FIXTURES_DIR / "kb_fixture.md")

    def test_type_is_topic(self):
        assert self.fm.get("type") == "topic"

    def test_keywords_present_and_sufficient(self):
        keywords = self.fm.get("keywords", [])
        assert len(keywords) >= 5, f"KB how-to needs >= 5 keywords, got {len(keywords)}"

    def test_evidence_present(self):
        assert "evidence" in self.fm


class TestProductsFixtureFrontmatter:
    def setup_method(self):
        self.fm = _read_frontmatter(_FIXTURES_DIR / "products_fixture.md")
        self.rules = meh.load_section_rules("products")

    def test_no_evidence_block(self):
        # Products pages do not use evidence blocks
        assert "evidence" not in self.fm

    def test_no_grade_fields(self):
        # Products pages are not graded
        assert "grade" not in self.fm

    def test_title_present(self):
        assert self.fm.get("title")

    def test_rules_say_grading_inactive(self):
        assert self.rules.grading_active is False

    def test_rules_say_code_discouraged(self):
        assert self.rules.code_examples_policy == "discouraged"


class TestReferenceFixtureFrontmatter:
    def setup_method(self):
        self.fm = _read_frontmatter(_FIXTURES_DIR / "reference_fixture.md")

    def test_description_present(self):
        assert self.fm.get("description")

    def test_categories_present(self):
        assert "categories" in self.fm

    def test_layout_is_single(self):
        assert self.fm.get("layout") in ("single", "reference-single")

    def test_evidence_present(self):
        assert "evidence" in self.fm


# ===========================================================================
# Scope gate tests (precondition enforcement)
# ===========================================================================

class TestScopeGatesForFixtures:
    """Verify scope validation logic for realistic fixture scenarios."""

    def test_frontmatter_only_valid_for_all_sections(self):
        for section in ("blog", "docs", "kb", "products", "reference"):
            result = meh.validate_scope("frontmatter-only", None, None)
            assert result.valid, f"frontmatter-only should be valid for {section}"

    def test_code_snippet_requires_section_arg(self):
        result = meh.validate_scope("code-snippet", target_section=None, evidence_justification=None)
        assert not result.valid

    def test_code_snippet_valid_with_section_arg(self):
        result = meh.validate_scope("code-snippet", target_section="Load OBJ Files", evidence_justification=None)
        assert result.valid

    def test_full_remediation_requires_evidence_arg(self):
        result = meh.validate_scope("full-remediation", target_section=None, evidence_justification=None)
        assert not result.valid

    def test_full_remediation_valid_with_evidence(self):
        result = meh.validate_scope(
            "full-remediation",
            target_section=None,
            evidence_justification="CLM-3d-46f64e",
        )
        assert result.valid

    def test_section_replacement_requires_section_arg(self):
        result = meh.validate_scope("section-replacement", target_section=None, evidence_justification=None)
        assert not result.valid

    def test_body_wording_needs_no_extras(self):
        result = meh.validate_scope("body-wording", None, None)
        assert result.valid


# ===========================================================================
# Forbidden-field intent detection
# ===========================================================================

class TestForbiddenFieldIntents:
    """These intents should be refused because they target system-managed fields."""

    @pytest.mark.parametrize("bad_intent", [
        "Set evidence.claims to [CLM-3d-abc]",
        "Update grade to A",
        "Change graded_at timestamp",
        "Modify provenance.last_mechanism",
        "Clear graded_model_sha",
        "Reset graded_logic_version to 1",
    ])
    def test_intent_touching_system_field_detected(self, bad_intent):
        result = meh.intent_touches_system_field(bad_intent)
        assert result is not None, f"System-field intent not detected: '{bad_intent}'"

    @pytest.mark.parametrize("safe_intent", [
        "Set description to 'New description'",
        "Fix the typo in the Introduction section",
        "Replace the code block in Load OBJ Files section",
        "Update title to 'Render 3D Scenes'",
        "Remove the incorrect sentence about version 2.0",
    ])
    def test_safe_intent_not_flagged(self, safe_intent):
        result = meh.intent_touches_system_field(safe_intent)
        assert result is None, f"Safe intent wrongly flagged: '{safe_intent}'"


# ===========================================================================
# AGENTS.md patch file readiness
# ===========================================================================

class TestAgentsPatchFile:
    def test_patch_file_exists(self):
        patch_path = _REPO_ROOT / "patches" / "agents-md-s73-manual-edit.md"
        assert patch_path.exists(), "AGENTS.md patch file is missing"

    def test_patch_file_contains_all_changes(self):
        patch_path = _REPO_ROOT / "patches" / "agents-md-s73-manual-edit.md"
        text = patch_path.read_text(encoding="utf-8")
        assert "S-73" in text
        assert "manual-edit" in text
        assert "§11" in text
        assert "§6a" in text
        assert "§12" in text


# ===========================================================================
# Negative scenarios — refusal conditions documented in skill spec
# ===========================================================================

class TestRefusalConditions:
    """Verify that each documented refusal condition maps to a detectable precondition."""

    def test_unknown_section_returns_none(self):
        # Skill Step 3: REFUSE if path does not map to a known section
        assert meh.detect_section("some/unknown/path/file.md") is None

    def test_unknown_scope_fails_validation(self):
        # Skill Step 1: REFUSE on unknown scope
        result = meh.validate_scope("anything-goes", None, None)
        assert not result.valid

    def test_system_field_in_frontmatter_scope_detected(self):
        # Skill Step 9 (frontmatter-only): REFUSE if intent names system field
        result = meh.intent_touches_system_field("Set evidence.apis to []")
        assert result is not None

    def test_products_section_triggers_code_warning(self):
        # Skill Step 4: WARN before applying code to products pages
        assert meh.requires_code_warning("products") is True
        assert meh.requires_code_warning("docs") is False


# ===========================================================================
# End-to-end scenario documentation (manual operator test cases)
# ===========================================================================

class TestEndToEndScenarioDocumentation:
    """These are documented operator scenarios. They do not execute the skill;
    they verify that the preconditions for each scenario can be evaluated by
    the helper functions.

    Scenario 1: Typo fix on blog post
    Scenario 2: Version in frontmatter
    Scenario 3: Code block replacement in KB
    Scenario 4: Section rewrite in reference page
    Scenario 5: Bad API token refusal
    Scenario 6: Products code warning
    """

    def test_scenario_1_blog_body_wording(self):
        # Blog typo fix: scope=body-wording, no extras required
        path = "content/blog.aspose.org/3d/python/post/index.md"
        section = meh.detect_section(path)
        assert section == "blog"
        result = meh.validate_scope("body-wording", None, None)
        assert result.valid

    def test_scenario_2_docs_frontmatter_only(self):
        path = "content/docs.aspose.org/en/3d/python/developer-guide/rendering.md"
        section = meh.detect_section(path)
        assert section == "docs"
        result = meh.validate_scope("frontmatter-only", None, None)
        assert result.valid
        # Confirm system fields are protected
        assert meh.intent_touches_system_field("Set description to new value") is None
        assert meh.intent_touches_system_field("Set grade to A") is not None

    def test_scenario_3_kb_code_snippet(self):
        path = "content/kb.aspose.org/en/3d/python/how-to-load-3d-models-in-python.md"
        section = meh.detect_section(path)
        assert section == "kb"
        rules = meh.load_section_rules(section)
        assert rules.code_examples_policy == "in_steps"
        result = meh.validate_scope("code-snippet", target_section="Load OBJ Files", evidence_justification=None)
        assert result.valid

    def test_scenario_4_reference_section_replacement(self):
        path = "content/reference.aspose.org/en/3d/python/Scene.md"
        section = meh.detect_section(path)
        assert section == "reference"
        # Missing --section should be refused
        result_no_section = meh.validate_scope("section-replacement", None, None)
        assert not result_no_section.valid
        # With --section provided, should be valid
        result_with_section = meh.validate_scope("section-replacement", "Parameters", None)
        assert result_with_section.valid

    def test_scenario_5_bad_api_token_is_governance_responsibility(self):
        # The bad-token check happens via api_surface.json lookup (runtime, not helper).
        # Here we verify the scope itself is valid (the token check happens at Step 8 of skill).
        result = meh.validate_scope("body-wording", None, None)
        assert result.valid  # scope is fine; token check is a separate runtime guard

    def test_scenario_6_products_code_warning(self):
        path = "content/products.aspose.org/en/3d/_index.md"
        section = meh.detect_section(path)
        assert section == "products"
        assert meh.requires_code_warning(section) is True

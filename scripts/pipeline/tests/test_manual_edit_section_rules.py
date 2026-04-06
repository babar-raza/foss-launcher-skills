"""Unit tests for S-73 manual-edit skill — section detection and rule loading.

Tests the deterministic logic extracted to scripts/pipeline/manual_edit_helpers.py.
All tests are pure Python: no network, no LLM, no real content files required.

Coverage:
- detect_section: all 5 known sections, unknown paths, empty paths, windows-style paths
- extract_family_platform: blog, docs/kb/reference, products
- validate_scope: all 5 scopes, missing --section, missing --evidence, unknown scope
- intent_touches_system_field: detects system-managed field names in intent strings
- load_section_rules: all 5 sections, unknown section
- Per-section rule assertions: evidence_required, grading_active, code_examples_policy, etc.
"""
from __future__ import annotations

import pytest

import manual_edit_helpers as meh
from _repo_root import repo_root

_REPO_ROOT = repo_root()


# ===========================================================================
# detect_section
# ===========================================================================

class TestDetectSection:
    @pytest.mark.parametrize("path,expected", [
        ("content/blog.aspose.org/3d/python/post/index.md", "blog"),
        ("content/docs.aspose.org/en/cells/python/developer-guide/features.md", "docs"),
        ("content/kb.aspose.org/en/slides/java/how-to-add-comments-java.md", "kb"),
        ("content/products.aspose.org/en/3d/python/_index.md", "products"),
        ("content/reference.aspose.org/en/3d/java/Scene.md", "reference"),
    ])
    def test_known_sections(self, path, expected):
        assert meh.detect_section(path) == expected

    @pytest.mark.parametrize("path", [
        "content/unknown.aspose.org/en/foo/bar.md",
        "scripts/pipeline/audit.py",
        "AGENTS.md",
        "themes/default/layouts/index.html",
        "",
    ])
    def test_unknown_paths_return_none(self, path):
        assert meh.detect_section(path) is None

    def test_windows_backslash_normalised(self):
        # Windows-style paths should be normalised to forward slashes
        path = r"content\blog.aspose.org\3d\python\post\index.md"
        assert meh.detect_section(path) == "blog"

    def test_leading_slash_stripped(self):
        path = "/content/kb.aspose.org/en/slides/python/faq.md"
        assert meh.detect_section(path) == "kb"

    def test_docs_not_confused_with_blog(self):
        assert meh.detect_section("content/docs.aspose.org/en/3d/python/_index.md") == "docs"
        assert meh.detect_section("content/blog.aspose.org/3d/python/post/index.md") == "blog"


# ===========================================================================
# extract_family_platform
# ===========================================================================

class TestExtractFamilyPlatform:
    def test_docs_path(self):
        f, p = meh.extract_family_platform(
            "content/docs.aspose.org/en/3d/python/developer-guide/rendering.md"
        )
        assert f == "3d"
        assert p == "python"

    def test_kb_path(self):
        f, p = meh.extract_family_platform(
            "content/kb.aspose.org/en/cells/python/how-to-create-charts-python.md"
        )
        assert f == "cells"
        assert p == "python"

    def test_reference_path(self):
        f, p = meh.extract_family_platform(
            "content/reference.aspose.org/en/3d/java/Scene.md"
        )
        assert f == "3d"
        assert p == "java"

    def test_blog_path(self):
        f, p = meh.extract_family_platform(
            "content/blog.aspose.org/slides/net/introducing-slides-foss-dotnet/index.md"
        )
        assert f == "slides"
        assert p == "net"

    def test_products_path_has_no_platform(self):
        f, p = meh.extract_family_platform(
            "content/products.aspose.org/en/3d/python/_index.md"
        )
        assert f == "3d"
        assert p is None  # products has no platform level

    def test_unknown_path_returns_none_none(self):
        f, p = meh.extract_family_platform("AGENTS.md")
        assert f is None
        assert p is None


# ===========================================================================
# validate_scope
# ===========================================================================

class TestValidateScope:
    @pytest.mark.parametrize("scope", [
        "frontmatter-only",
        "body-wording",
        "code-snippet",
        "section-replacement",
        "full-remediation",
    ])
    def test_all_valid_scopes_accepted_with_required_args(self, scope):
        section = "Test Section" if scope in ("code-snippet", "section-replacement") else None
        evidence = "CLM-3d-abc123" if scope == "full-remediation" else None
        result = meh.validate_scope(scope, target_section=section, evidence_justification=evidence)
        assert result.valid, f"Expected valid for scope '{scope}': {result.reason}"

    def test_unknown_scope_refused(self):
        result = meh.validate_scope("magic-edit", None, None)
        assert not result.valid
        assert "Unknown scope" in result.reason
        assert "magic-edit" in result.reason

    def test_code_snippet_without_section_refused(self):
        result = meh.validate_scope("code-snippet", target_section=None, evidence_justification=None)
        assert not result.valid
        assert "--section" in result.reason

    def test_section_replacement_without_section_refused(self):
        result = meh.validate_scope("section-replacement", target_section=None, evidence_justification=None)
        assert not result.valid
        assert "--section" in result.reason

    def test_full_remediation_without_evidence_refused(self):
        result = meh.validate_scope("full-remediation", target_section=None, evidence_justification=None)
        assert not result.valid
        assert "--evidence" in result.reason

    def test_frontmatter_only_requires_no_extras(self):
        result = meh.validate_scope("frontmatter-only", None, None)
        assert result.valid

    def test_body_wording_requires_no_extras(self):
        result = meh.validate_scope("body-wording", None, None)
        assert result.valid

    def test_empty_scope_refused(self):
        result = meh.validate_scope("", None, None)
        assert not result.valid


# ===========================================================================
# intent_touches_system_field
# ===========================================================================

class TestIntentTouchesSystemField:
    @pytest.mark.parametrize("field_name", [
        "evidence",
        "grade",
        "graded_at",
        "graded_model_sha",
        "graded_evaluators",
        "graded_logic_version",
        "provenance",
    ])
    def test_detects_system_field_in_intent(self, field_name):
        intent = f"Set {field_name} to some_value"
        result = meh.intent_touches_system_field(intent)
        assert result == field_name

    def test_safe_intent_returns_none(self):
        intent = "Set description to 'Render 3D scenes in Python'"
        assert meh.intent_touches_system_field(intent) is None

    def test_case_insensitive_detection(self):
        assert meh.intent_touches_system_field("Update GRADE to A") == "grade"
        assert meh.intent_touches_system_field("Set Evidence.claims to []") == "evidence"


# ===========================================================================
# load_section_rules
# ===========================================================================

class TestLoadSectionRules:
    def test_returns_none_for_unknown_section(self):
        assert meh.load_section_rules("unknown") is None

    @pytest.mark.parametrize("section", ["blog", "docs", "kb", "products", "reference"])
    def test_returns_rules_for_all_known_sections(self, section):
        rules = meh.load_section_rules(section)
        assert rules is not None
        assert rules.section == section


# ===========================================================================
# Per-section rule assertions (critical governance contracts)
# ===========================================================================

class TestBlogRules:
    def setup_method(self):
        self.rules = meh.load_section_rules("blog")

    def test_evidence_required(self):
        assert self.rules.evidence_required is True

    def test_author_field_required(self):
        assert self.rules.author_field_required is True

    def test_draft_field_required(self):
        assert self.rules.draft_field_required is True

    def test_grading_active(self):
        assert self.rules.grading_active is True

    def test_code_examples_recommended(self):
        assert self.rules.code_examples_policy == "recommended"

    def test_no_index_shortcode(self):
        assert self.rules.index_shortcode is None

    def test_system_fields_forbidden(self):
        assert "evidence" in self.rules.forbidden_frontmatter_fields
        assert "grade" in self.rules.forbidden_frontmatter_fields
        assert "provenance" in self.rules.forbidden_frontmatter_fields


class TestDocsRules:
    def setup_method(self):
        self.rules = meh.load_section_rules("docs")

    def test_type_field_is_docs(self):
        assert self.rules.type_field_value == "docs"

    def test_grading_active(self):
        assert self.rules.grading_active is True

    def test_index_shortcode(self):
        assert self.rules.index_shortcode == "{{< sections >}}"

    def test_no_author_requirement(self):
        assert self.rules.author_field_required is False


class TestKbRules:
    def setup_method(self):
        self.rules = meh.load_section_rules("kb")

    def test_type_field_is_topic(self):
        assert self.rules.type_field_value == "topic"

    def test_code_policy_is_in_steps(self):
        assert self.rules.code_examples_policy == "in_steps"

    def test_index_shortcode(self):
        assert self.rules.index_shortcode == "{{< children >}}"

    def test_grading_active(self):
        assert self.rules.grading_active is True


class TestProductsRules:
    def setup_method(self):
        self.rules = meh.load_section_rules("products")

    def test_no_evidence_required(self):
        assert self.rules.evidence_required is False

    def test_grading_not_active(self):
        assert self.rules.grading_active is False

    def test_code_discouraged(self):
        assert self.rules.code_examples_policy == "discouraged"

    def test_requires_code_warning(self):
        assert meh.requires_code_warning("products") is True

    def test_no_index_shortcode(self):
        assert self.rules.index_shortcode is None


class TestReferenceRules:
    def setup_method(self):
        self.rules = meh.load_section_rules("reference")

    def test_evidence_required(self):
        assert self.rules.evidence_required is True

    def test_grading_active(self):
        assert self.rules.grading_active is True

    def test_index_shortcode(self):
        assert self.rules.index_shortcode == "{{< children >}}"

    def test_no_author_requirement(self):
        assert self.rules.author_field_required is False


# ===========================================================================
# requires_code_warning
# ===========================================================================

class TestRequiresCodeWarning:
    def test_products_requires_warning(self):
        assert meh.requires_code_warning("products") is True

    @pytest.mark.parametrize("section", ["blog", "docs", "kb", "reference"])
    def test_other_sections_do_not_require_warning(self, section):
        assert meh.requires_code_warning(section) is False

    def test_unknown_section_returns_false(self):
        assert meh.requires_code_warning("unknown") is False


# ===========================================================================
# Skill contract tests — verify the skill file exists and is well-formed
# ===========================================================================

class TestSkillContractFile:
    """Verify that skills/manual-edit.md exists and contains all required contract elements."""

    def setup_method(self):
        self.skill_path = _REPO_ROOT / "skills" / "manual-edit.md"
        self.command_path = _REPO_ROOT / ".claude" / "commands" / "manual-edit.md"
        assert self.skill_path.exists(), f"Skill file missing: {self.skill_path}"
        self.skill_text = self.skill_path.read_text(encoding="utf-8")

    def test_skill_file_exists(self):
        assert self.skill_path.exists()

    def test_command_mirror_exists(self):
        assert self.command_path.exists()

    def test_skill_id_is_s73(self):
        assert "S-73" in self.skill_text

    def test_all_five_scopes_documented(self):
        for scope in ("frontmatter-only", "body-wording", "code-snippet",
                      "section-replacement", "full-remediation"):
            assert scope in self.skill_text, f"Scope '{scope}' not documented in skill file"

    def test_all_five_sections_documented(self):
        for section in ("blog", "docs", "kb", "products", "reference"):
            assert section in self.skill_text, f"Section '{section}' not documented in skill file"

    def test_path_guard_referenced(self):
        assert "path_guard" in self.skill_text or "path-guard" in self.skill_text

    def test_audit_py_referenced(self):
        assert "audit.py" in self.skill_text

    def test_revert_on_failure_documented(self):
        assert "revert" in self.skill_text.lower()

    def test_evidence_update_documented(self):
        assert "attach_evidence" in self.skill_text

    def test_provenance_update_documented(self):
        assert "manual-edit-skill" in self.skill_text

    def test_audit_trail_documented(self):
        assert "reports/manual-edits" in self.skill_text

    def test_post_conditions_section_present(self):
        assert "## Post-conditions" in self.skill_text

    def test_refusal_conditions_section_present(self):
        assert "Refusal" in self.skill_text or "refusal" in self.skill_text

    def test_minimal_edit_principle_documented(self):
        assert "minimal" in self.skill_text.lower()

    def test_pre_edit_steps_documented(self):
        assert "Pre-conditions" in self.skill_text or "pre-edit" in self.skill_text.lower()

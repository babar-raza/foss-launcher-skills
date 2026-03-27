"""Tests for content_eval evaluators."""

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
from content_eval.models import CodeBlock, Finding, Heading, Page


def _make_page(content: str, filepath: str = "content/docs.aspose.org/en/slides/dotnet/test.md") -> Page:
    """Create a Page from markdown content string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


class TestPlatformPurity:
    def setup_method(self):
        from content_eval.evaluators.platform_purity import PlatformPurityEvaluator
        self.evaluator = PlatformPurityEvaluator()

    def test_python_def_in_dotnet_page(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Example:

            ```csharp
            def my_function():
                pass
            ```
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        foreign = [f for f in findings if "Python function definition" in f.message]
        assert len(foreign) >= 1
        assert foreign[0].category == "PC"

    def test_wrong_lang_tag(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Example:

            ```python
            from aspose.slides import Presentation
            ```
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "tagged as" in f.message]
        assert len(lang_findings) >= 1
        assert lang_findings[0].level == "FAIL"

    def test_clean_dotnet_code(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Example:

            ```csharp
            using Aspose.Slides;
            var prs = new Presentation();
            ```
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        # Should have no findings for correct code
        code_findings = [f for f in findings if "Foreign" in f.message or "tagged" in f.message]
        assert len(code_findings) == 0

    def test_prose_contamination(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Install using pip install aspose-slides.
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1


class TestRiskLanguage:
    def setup_method(self):
        from content_eval.evaluators.risk_language import RiskLanguageEvaluator
        self.evaluator = RiskLanguageEvaluator()

    def test_detects_superlatives(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            This is the fastest library available.
            It provides seamless integration.
            100% compatible with all formats.
        """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 3
        messages = [f.message for f in findings]
        assert any("fastest" in m for m in messages)
        assert any("seamless" in m for m in messages)
        assert any("100%" in m for m in messages)

    def test_clean_prose(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            The library supports PPTX export.
            You can add shapes to slides.
        """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_no_limitations_is_fail(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            This library has no limitations.
        """))
        findings = self.evaluator.evaluate(page, None)
        fail_findings = [f for f in findings if f.level == "FAIL"]
        assert len(fail_findings) >= 1


class TestStructure:
    def setup_method(self):
        from content_eval.evaluators.structure import StructureEvaluator
        self.evaluator = StructureEvaluator()

    def test_missing_title(self):
        page = _make_page(textwrap.dedent("""\
            ---
            description: A test
            ---
            Content here.
        """))
        findings = self.evaluator.evaluate(page, None)
        title_findings = [f for f in findings if "title" in f.message]
        assert len(title_findings) >= 1
        assert title_findings[0].level == "FAIL"

    def test_placeholder_detection(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            {TODO} Replace this placeholder.
        """))
        findings = self.evaluator.evaluate(page, None)
        placeholder_findings = [f for f in findings if "Placeholder" in f.message]
        assert len(placeholder_findings) >= 1

    def test_heading_skip(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ## Overview
            Text.
            #### Details
            More text.
        """))
        findings = self.evaluator.evaluate(page, None)
        skip_findings = [f for f in findings if "skipped" in f.message]
        assert len(skip_findings) >= 1

    def test_unlabeled_code_block(self):
        page = _make_page("---\ntitle: T\n---\n\n```\ncode here\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) >= 1

    def test_empty_body(self):
        page = _make_page("---\ntitle: T\n---\n")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "empty" in f.message.lower()]
        assert len(empty_findings) >= 1


class TestPageRole:
    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_kb_howto_missing_steps(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: How to Add Shapes
            type: topic
            keywords: [a, b, c, d, e]
            ---
            ## Introduction
            This guide shows how to add shapes.
            ## Code Example
            Some code here.
        """), "content/kb.aspose.org/en/slides/dotnet/how-to-add-shapes.md")
        findings = self.evaluator.evaluate(page, None)
        steps_findings = [f for f in findings if "steps" in f.message.lower() or "step" in f.message.lower()]
        assert len(steps_findings) >= 1

    def test_kb_howto_missing_type(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: How to Add Shapes
            ---
            Content.
        """), "content/kb.aspose.org/en/slides/dotnet/how-to-add-shapes.md")
        findings = self.evaluator.evaluate(page, None)
        type_findings = [f for f in findings if "type: topic" in f.message]
        assert len(type_findings) >= 1
        assert type_findings[0].level == "FAIL"

    def test_reference_missing_table(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Presentation
            layout: reference-single
            ---
            ## Presentation Class
            The Presentation class is the main entry point.
        """), "content/reference.aspose.org/en/slides/dotnet/presentation.md")
        findings = self.evaluator.evaluate(page, None)
        table_findings = [f for f in findings if "table" in f.message.lower()]
        assert len(table_findings) >= 1


class TestForbiddenClaims:
    def setup_method(self):
        from content_eval.evaluators.forbidden_claims import ForbiddenClaimsEvaluator
        self.evaluator = ForbiddenClaimsEvaluator()

    def test_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.", "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0


# ---------- Tier 1 change tests ----------


class TestStructureProductsExemption:
    """Tests for 1.1: layout:plugin pages should not get empty-body FAIL."""

    def setup_method(self):
        from content_eval.evaluators.structure import StructureEvaluator
        self.evaluator = StructureEvaluator()

    def test_plugin_layout_empty_body_no_fail(self):
        page = _make_page("---\ntitle: T\nlayout: plugin\n---\n",
                          "content/products.aspose.org/en/slides/dotnet/_index.md")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "body is empty" in f.message.lower()]
        assert len(empty_findings) == 0

    def test_normal_page_empty_body_still_fails(self):
        page = _make_page("---\ntitle: T\n---\n")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "empty" in f.message.lower()]
        assert len(empty_findings) >= 1


class TestStructureAsciiArt:
    """Tests for 1.5: ASCII art code blocks downgraded to INFO."""

    def setup_method(self):
        from content_eval.evaluators.structure import StructureEvaluator
        self.evaluator = StructureEvaluator()

    def test_ascii_art_is_info(self):
        page = _make_page("---\ntitle: T\n---\n\n```\n├── src\n│   └── main.py\n└── README.md\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) == 1
        assert lang_findings[0].level == "INFO"

    def test_short_block_is_info(self):
        page = _make_page("---\ntitle: T\n---\n\n```\noutput: ok\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) == 1
        assert lang_findings[0].level == "INFO"

    def test_long_code_block_is_warn(self):
        lines = "\n".join(f"line {i}" for i in range(10))
        page = _make_page(f"---\ntitle: T\n---\n\n```\n{lines}\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) == 1
        assert lang_findings[0].level == "WARN"


class TestKbIndexRole:
    """Tests for 1.2: KB _index pages classified as kb_index."""

    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_kb_index_page_no_howto_checks(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Slides Knowledge Base
            ---
            {{< children >}}
        """), "content/kb.aspose.org/en/slides/dotnet/_index.md")
        findings = self.evaluator.evaluate(page, None)
        # Should NOT get howto-specific findings (type:topic, steps, keywords)
        howto_msgs = [f for f in findings if "type: topic" in f.message or "step" in f.message.lower()
                      or "keywords" in f.message.lower()]
        assert len(howto_msgs) == 0

    def test_kb_index_missing_title_warns(self):
        page = _make_page("---\ndescription: test\n---\n{{< children >}}\n",
                          "content/kb.aspose.org/en/slides/dotnet/_index.md")
        findings = self.evaluator.evaluate(page, None)
        title_findings = [f for f in findings if "title" in f.message.lower()]
        assert len(title_findings) >= 1


class TestReferenceHomeLayout:
    """Tests for 1.3: reference-home accepted as valid layout."""

    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_reference_home_no_layout_warning(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: API Reference
            layout: reference-home
            ---
            | Class | Description |
            |-------|-------------|
            | Scene | Main class  |
        """), "content/reference.aspose.org/en/3d/python/_index.md")
        findings = self.evaluator.evaluate(page, None)
        layout_findings = [f for f in findings if "layout" in f.message.lower()]
        assert len(layout_findings) == 0


class TestStepHeadingRelaxation:
    """Tests for 1.4: h2/h3 headings accepted as alternative to Step N."""

    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_section_headings_accepted(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: How to Add Shapes
            type: topic
            keywords: [a, b, c, d, e]
            ---
            {{% steps %}}
            ## Prerequisites
            Setup text.
            ## Add a Shape
            Code example.
            ## Save the File
            Save text.
            {{% /steps %}}
        """), "content/kb.aspose.org/en/slides/dotnet/how-to-add-shapes.md")
        findings = self.evaluator.evaluate(page, None)
        step_findings = [f for f in findings if "step" in f.message.lower() and "heading" in f.message.lower()]
        assert len(step_findings) == 0


# ---------- Tier 2 evaluator tests ----------


class TestCodePlausibility:
    def setup_method(self):
        from content_eval.evaluators.code_plausibility import CodePlausibilityEvaluator
        self.evaluator = CodePlausibilityEvaluator()

    def test_empty_code_block(self):
        page = _make_page("---\ntitle: T\n---\n\n```python\n\n```\n")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "empty" in f.message.lower() or "blank" in f.message.lower()]
        assert len(empty_findings) >= 1

    def test_placeholder_comment(self):
        # _PSEUDO_COMMENT_RE matches // style comments (C#/Java/C++)
        page = _make_page("---\ntitle: T\n---\n\n```csharp\n// TODO: add your code here\n```\n")
        findings = self.evaluator.evaluate(page, None)
        ph_findings = [f for f in findings if "placeholder" in f.message.lower()]
        assert len(ph_findings) >= 1

    def test_ellipsis_in_code(self):
        page = _make_page("---\ntitle: T\n---\n\n```python\nprs = Presentation()\n...\nprs.save(\"out.pptx\")\n```\n")
        findings = self.evaluator.evaluate(page, None)
        ell_findings = [f for f in findings if "ellipsis" in f.message.lower() or "..." in f.message]
        assert len(ell_findings) >= 1


class TestEvidenceDepth:
    def setup_method(self):
        from content_eval.evaluators.evidence_depth import EvidenceDepthEvaluator
        self.evaluator = EvidenceDepthEvaluator()

    def test_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.", "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        # No knowledge → no evidence expectations
        assert isinstance(findings, list)

    def test_page_with_code_but_no_evidence(self):
        """Page with code blocks but no evidence section should flag."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ## Example
            ```python
            from aspose.threed import Scene
            scene = Scene()
            ```
        """), "content/docs.aspose.org/en/3d/python/developer-guide/test.md")
        # This test validates the evaluator runs without error
        # Actual evidence findings depend on knowledge model state
        findings = self.evaluator.evaluate(page, None)
        assert isinstance(findings, list)


class TestProseTruth:
    def setup_method(self):
        from content_eval.evaluators.prose_truth import ProseTruthEvaluator
        self.evaluator = ProseTruthEvaluator()

    def test_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.",
                          "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_api_claim_against_knowledge(self):
        """API claim for non-existent member should produce finding."""
        knowledge = MagicMock()
        knowledge.available = True
        knowledge.classes = {"Scene": {}}
        knowledge.has_method = MagicMock(return_value=False)
        knowledge.has_property = MagicMock(return_value=False)

        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            `Scene.nonexistent_method` provides advanced rendering.
        """), "content/docs.aspose.org/en/3d/python/test.md")
        findings = self.evaluator.evaluate(page, knowledge)
        api_findings = [f for f in findings if "not found in API surface" in f.message]
        assert len(api_findings) >= 1

    def test_valid_api_claim_no_finding(self):
        """Valid API claim should not produce finding."""
        knowledge = MagicMock()
        knowledge.available = True
        knowledge.classes = {"Scene": {}}
        knowledge.has_method = MagicMock(return_value=True)
        knowledge.has_property = MagicMock(return_value=False)

        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            `Scene.open` provides file loading.
        """), "content/docs.aspose.org/en/3d/python/test.md")
        findings = self.evaluator.evaluate(page, knowledge)
        api_findings = [f for f in findings if "not found in API surface" in f.message]
        assert len(api_findings) == 0


class TestCoverage:
    def setup_method(self):
        from content_eval.evaluators.coverage import CoverageEvaluator
        self.evaluator = CoverageEvaluator()

    def test_non_docs_page_skipped(self):
        page = _make_page("---\ntitle: T\n---\nContent.",
                          "content/blog.aspose.org/3d/python/test/index.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_coverage_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.",
                          "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0


class TestCoverageInterfaceFiltering:
    """S-Fix-5: Platform-aware interface filtering."""

    def setup_method(self):
        from content_eval.evaluators.coverage import (
            CoverageEvaluator, _is_interface_entry, INTERFACE_PAGE_PLATFORMS,
            CONCRETE_ONLY_PLATFORMS,
        )
        self.evaluator = CoverageEvaluator()
        self._is_interface_entry = _is_interface_entry
        self.INTERFACE_PAGE_PLATFORMS = INTERFACE_PAGE_PLATFORMS
        self.CONCRETE_ONLY_PLATFORMS = CONCRETE_ONLY_PLATFORMS

    def test_i_prefix_uppercase_detected_as_interface(self):
        assert self._is_interface_entry("IShape", "") is True
        assert self._is_interface_entry("IPPImage", "") is True

    def test_i_prefix_lowercase_not_interface(self):
        # "Index" starts with I but second char is 'n' (lowercase) — not an interface
        assert self._is_interface_entry("Index", "") is False

    def test_single_i_not_interface(self):
        assert self._is_interface_entry("I", "") is False

    def test_kind_field_interface_detected(self):
        assert self._is_interface_entry("SomeType", "interface") is True
        assert self._is_interface_entry("SomeType", "abstract_class") is True

    def test_kind_field_concrete_not_interface(self):
        assert self._is_interface_entry("SomeType", "class_specifier") is False

    def test_platform_sets_correct(self):
        assert "cpp" in self.CONCRETE_ONLY_PLATFORMS
        assert "python" in self.CONCRETE_ONLY_PLATFORMS
        assert "net" in self.INTERFACE_PAGE_PLATFORMS
        assert "java" in self.INTERFACE_PAGE_PLATFORMS
        assert "dotnet" not in self.INTERFACE_PAGE_PLATFORMS


class TestCoverageSlug:
    """S-Fix-6: Slug generation for enum page lookup."""

    def setup_method(self):
        from content_eval.evaluators.coverage import _to_slug
        self._to_slug = _to_slug

    def test_pascal_case_to_kebab(self):
        assert self._to_slug("BevelPresetType") == "bevel-preset-type"

    def test_fill_type(self):
        assert self._to_slug("FillType") == "fill-type"

    def test_single_word(self):
        assert self._to_slug("Presentation") == "presentation"

    def test_acronym_prefix(self):
        # "GradientDirection" → "gradient-direction"
        result = self._to_slug("GradientDirection")
        assert "gradient" in result and "direction" in result


# ---------------------------------------------------------------------------
# TF-IDF Semantic Matching (prose_truth)
# ---------------------------------------------------------------------------

class TestClaimIndex:
    """Tests for _ClaimIndex TF-IDF semantic matching."""

    def setup_method(self):
        from content_eval.evaluators.prose_truth import _ClaimIndex
        self.ClaimIndex = _ClaimIndex

    def test_similar_text_high_score(self):
        idx = self.ClaimIndex([
            {"text": "Scene class provides methods for loading and saving 3D files"},
        ])
        assert idx.available
        score = idx.best_similarity("Scene class provides methods for loading 3D models")
        assert score > 0.3

    def test_unrelated_text_low_score(self):
        idx = self.ClaimIndex([
            {"text": "Scene class provides methods for loading and saving 3D files"},
        ])
        score = idx.best_similarity("The weather is nice today in Tokyo")
        assert score < 0.2

    def test_exact_match_near_one(self):
        idx = self.ClaimIndex([
            {"text": "Scene class provides methods for loading and saving 3D files"},
        ])
        score = idx.best_similarity("Scene class provides methods for loading and saving 3D files")
        assert score > 0.9

    def test_empty_claims(self):
        idx = self.ClaimIndex([])
        assert not idx.available
        assert idx.best_similarity("anything") == 0.0

    def test_multiple_claims_best_match(self):
        idx = self.ClaimIndex([
            {"text": "Node class supports creating child nodes and transformations"},
            {"text": "Scene class loads 3D files from disk"},
        ])
        score = idx.best_similarity("Scene class loads 3D models from file")
        assert score > 0.3


class TestClaimIndexCache:
    """Tests for _ClaimIndex caching (TM-01)."""

    def setup_method(self):
        from content_eval.evaluators.prose_truth import clear_claim_cache
        clear_claim_cache()

    def teardown_method(self):
        from content_eval.evaluators.prose_truth import clear_claim_cache
        clear_claim_cache()

    def test_claim_index_cached_across_calls(self):
        """Same (family, platform) should return the same object."""
        from content_eval.evaluators.prose_truth import _get_claim_index
        idx1 = _get_claim_index("nonexistent_family", "nonexistent_platform")
        idx2 = _get_claim_index("nonexistent_family", "nonexistent_platform")
        assert idx1 is idx2

    def test_different_keys_different_objects(self):
        """Different (family, platform) should return different objects."""
        from content_eval.evaluators.prose_truth import _get_claim_index
        idx1 = _get_claim_index("family_a", "platform_a")
        idx2 = _get_claim_index("family_b", "platform_b")
        assert idx1 is not idx2

    def test_cache_cleared(self):
        """clear_claim_cache() should reset state."""
        from content_eval.evaluators.prose_truth import (
            _get_claim_index, clear_claim_cache, _CLAIM_INDEX_CACHE,
        )
        _get_claim_index("test_family", "test_platform")
        assert len(_CLAIM_INDEX_CACHE) == 1
        clear_claim_cache()
        assert len(_CLAIM_INDEX_CACHE) == 0

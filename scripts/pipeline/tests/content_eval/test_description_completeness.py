"""Tests for the description_completeness evaluator."""

import tempfile
import textwrap
from pathlib import Path

import pytest

from content_eval.models import Page


def _make_page(content: str, filepath: str = "content/reference.aspose.org/en/3d/python/Scene.md") -> Page:
    """Create a Page from markdown content string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


class TestDescriptionCompleteness:
    def setup_method(self):
        from content_eval.evaluators.description_completeness import DescriptionCompletenessEvaluator
        self.evaluator = DescriptionCompletenessEvaluator()

    def test_full_table_no_finding(self):
        """Reference page with all description cells populated → no findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Scene
            ---
            ## Properties

            | Name | Description |
            |------|-------------|
            | root_node | The root node of the scene graph |
            | library | The asset library for shared resources |
            | animation_clips | List of animation clips in the scene |
            | current_camera | The active camera used for rendering |
        """))
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 0

    def test_mostly_empty_descriptions_fail(self):
        """Reference page with >70% empty description cells → FAIL."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Scene
            ---
            ## Properties

            | Name | Description |
            |------|-------------|
            | root_node | |
            | library | |
            | animation_clips | |
            | current_camera | The active camera |
        """))
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 1
        assert dc_findings[0].level == "FAIL"
        assert "empty description" in dc_findings[0].message.lower()

    def test_partially_empty_descriptions_warn(self):
        """Reference page with ~50% empty description cells → WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Scene
            ---
            ## Properties

            | Name | Description |
            |------|-------------|
            | root_node | The root node of the scene |
            | library | The asset library for resources |
            | animation_clips | |
            | current_camera | |
        """))
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 1
        assert dc_findings[0].level == "WARN"

    def test_non_reference_page_skipped(self):
        """Blog page with empty table descriptions → no DC findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Feature List
            ---
            ## Features

            | Name | Description |
            |------|-------------|
            | feature_a | |
            | feature_b | |
            | feature_c | |
            | feature_d | |
        """), "content/blog.aspose.org/3d/python/features/index.md")
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 0

    def test_small_table_skipped(self):
        """Table with only 2 data rows → no DC findings (too small)."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Scene
            ---
            ## Properties

            | Name | Description |
            |------|-------------|
            | root_node | |
            | library | |
        """))
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 0

    def test_no_description_column_skipped(self):
        """Table without Description/Summary column → no DC findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Scene
            ---
            ## Properties

            | Name | Type | Default |
            |------|------|---------|
            | root_node | Node | None |
            | library | AssetLibrary | None |
            | clips | list | [] |
        """))
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 0

    def test_summary_column_detected(self):
        """Table with 'Summary' header treated same as 'Description'."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Scene
            ---
            ## Methods

            | Method | Summary |
            |--------|---------|
            | open | |
            | save | |
            | merge | |
            | clear | |
        """))
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 1
        assert dc_findings[0].level == "FAIL"

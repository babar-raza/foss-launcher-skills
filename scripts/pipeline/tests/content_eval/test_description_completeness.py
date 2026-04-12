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

    def test_mostly_empty_descriptions_small_table_fail(self):
        """Small table (4 rows, 3 empty = 75%) gets FAIL with tightened thresholds.

        With _FAIL_EMPTY_MIN=3 and _FAIL_EMPTY_PCT=50, a table with 3 empty cells
        at 75% now triggers FAIL — the absolute-count guard was lowered so that
        small-but-sparse classes are caught as well as large ones.
        """
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
        assert dc_findings[0].level == "FAIL", (
            "Table with 3 empty cells at 75% should FAIL — "
            "_FAIL_EMPTY_MIN=3 and _FAIL_EMPTY_PCT=50 both met"
        )
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

    def test_summary_column_detected_small_table_fail(self):
        """Table with 'Summary' header and all 4 rows empty → FAIL.

        With _FAIL_EMPTY_MIN=3 and _FAIL_EMPTY_PCT=50, a table with 4 empty
        cells at 100% now triggers FAIL — the absolute-count guard was lowered
        so that small-but-fully-undocumented classes are no longer let through.
        """
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
        assert dc_findings[0].level == "FAIL", (
            "4-row table with all cells empty should FAIL — "
            "_FAIL_EMPTY_MIN=3 and _FAIL_EMPTY_PCT=50 both met (4 >= 3 and 100% > 50%)"
        )

    def test_large_table_mostly_empty_still_fails(self):
        """Large table (7 rows, 6 empty = 86%) → FAIL even with absolute-count guard.

        When empty >= _FAIL_EMPTY_MIN (5) AND empty_pct > 70%, FAIL fires normally.
        This confirms large undocumented API surfaces are still caught.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Workbook
            ---
            ## Methods

            | Method | Description |
            |--------|-------------|
            | Save | Writes the workbook to disk |
            | Open | |
            | Close | |
            | Dispose | |
            | Calculate | |
            | Protect | |
            | Unprotect | |
        """))
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 1
        assert dc_findings[0].level == "FAIL", (
            "Large table (7 rows, 6 empty = 86%) should FAIL "
            "— 6 >= _FAIL_EMPTY_MIN(3) and 86% > 50%"
        )

    def test_retired_page_skipped_by_dc_evaluator(self):
        """Reference page with retired_at set → zero DC findings even with empty table.

        Regression guard for SR-05 Behavior 3: verifies that
        DescriptionCompletenessEvaluator returns early when
        page.frontmatter['retired_at'] is populated, treating the page as a
        read-only snapshot that must not generate FAIL findings.
        """
        page = _make_page(
            textwrap.dedent("""\
                ---
                title: LegacyClass
                retired_at: "2025-01-01"
                ---
                ## Properties

                | Name | Description |
                |------|-------------|
                | alpha | |
                | beta | |
                | gamma | |
                | delta | |
                | epsilon | |
                | zeta | |
            """),
            filepath="content/reference.aspose.org/en/slides/net/LegacyClass.md",
        )
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 0, (
            "Retired reference page must not produce DC findings — "
            "evaluator should return early when retired_at is set"
        )

    def test_enum_page_skipped_by_dc_evaluator(self):
        """Enum page with categories: [Enum] → zero DC findings even with 100% empty table.

        Regression guard for SR-07a: enum member names (XYZ, NOT_DEFINED, etc.)
        ARE the documentation. Requiring description cells for enum values produces
        false positives. Evaluator must return early when 'Enum' is in categories.
        """
        page = _make_page(
            textwrap.dedent("""\
                ---
                title: RotationOrder
                categories:
                - Enum
                ---
                ## Values

                | Value | Description |
                |-------|-------------|
                | `XYZ` | |
                | `XZY` | |
                | `YZX` | |
                | `YXZ` | |
                | `ZXY` | |
                | `ZYX` | |
            """),
            filepath="content/reference.aspose.org/en/3d/net/RotationOrder.md",
        )
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 0, (
            "Enum reference page must not produce DC findings — "
            "enum value names are self-documenting; evaluator must skip when "
            "'Enum' is in categories"
        )

    def test_dc_exempt_page_skipped(self):
        """Page with dc_exempt: true → zero DC findings regardless of empty cells.

        Regression guard for SR-07a: dc_exempt frontmatter flag allows opting
        out of description completeness checks for pages where empty cells are
        structurally correct (e.g. internal utility classes).
        """
        page = _make_page(
            textwrap.dedent("""\
                ---
                title: CellCollection
                dc_exempt: true
                ---
                ## Methods

                | Name | Description |
                |------|-------------|
                | get | |
                | set | |
                | add | |
                | remove | |
                | clear | |
            """),
            filepath="content/reference.aspose.org/en/slides/cpp/CellCollection.md",
        )
        findings = self.evaluator.evaluate(page, None)
        dc_findings = [f for f in findings if f.category == "DC"]
        assert len(dc_findings) == 0, (
            "Page with dc_exempt: true must not produce DC findings"
        )

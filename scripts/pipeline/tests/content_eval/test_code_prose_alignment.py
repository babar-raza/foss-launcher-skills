"""Tests for code_prose_alignment evaluator (TC-EVAL-003)."""

import tempfile
import textwrap
from pathlib import Path

import pytest

from content_eval.models import Page


def _make_page(content: str, filepath: str = "content/docs.aspose.org/en/cells/python/overview.md") -> Page:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


class TestCodeProseAlignment:
    def setup_method(self):
        from content_eval.evaluators.code_prose_alignment import CodeProseAlignmentEvaluator
        self.evaluator = CodeProseAlignmentEvaluator()

    def test_evaluator_name(self):
        assert self.evaluator.name == "code_prose_alignment"

    def test_aligned_prose_code_no_findings(self):
        """Prose that closely mirrors code identifiers should produce no findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Workbook Export
            ---
            Create a new Workbook instance and load the spreadsheet cells data from
            the workbook worksheets. Then call workbook save to write the workbook
            cells output to a file on disk using the workbook save method.

            ```python
            workbook = Workbook()
            workbook.worksheets[0].cells.put_value("A1", "Hello")
            workbook.save("output.xlsx")
            ```
        """))
        findings = self.evaluator.evaluate(page, None)
        cpa = [f for f in findings if f.category == "CPA"]
        assert len(cpa) == 0

    def test_misaligned_prose_code_produces_warn(self):
        """Prose about PDF but code about spreadsheets → WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: PDF Generation
            ---
            This section demonstrates how to generate PDF documents
            with embedded images and custom watermarks for printing.

            ```python
            import json
            data = {"key": "value", "numbers": [1, 2, 3]}
            with open("output.json", "w") as fp:
                json.dump(data, fp, indent=2)
            ```
        """))
        findings = self.evaluator.evaluate(page, None)
        cpa = [f for f in findings if f.category == "CPA"]
        # Expect at least one warning about misalignment
        assert len(cpa) >= 1
        assert all(f.level == "WARN" for f in cpa)

    def test_no_code_blocks_skipped(self):
        """Page without code blocks → no findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Overview
            ---
            This library provides powerful spreadsheet processing capabilities.
        """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_reference_page_skipped(self):
        """Reference pages are skipped (they use tables, not prose-code pairs)."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Workbook
            ---
            The Workbook class represents a spreadsheet workbook.

            ```python
            wb = Workbook()
            ```
        """), filepath="content/reference.aspose.org/en/cells/python/Workbook.md")
        findings = self.evaluator.evaluate(page, None)
        cpa = [f for f in findings if f.category == "CPA"]
        assert len(cpa) == 0

    def test_short_prose_skipped(self):
        """Very short prose before code block → skipped."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Example:

            ```python
            workbook = Workbook()
            workbook.save("output.xlsx")
            ```
        """))
        findings = self.evaluator.evaluate(page, None)
        cpa = [f for f in findings if f.category == "CPA"]
        assert len(cpa) == 0

    def test_evaluator_field_set(self):
        """Findings must have evaluator='code_prose_alignment'."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            This demonstrates PDF rendering with custom page layout settings
            and watermark overlay configuration for enterprise documents.

            ```python
            import json
            data = {"key": "value", "numbers": [1, 2, 3]}
            with open("output.json", "w") as fp:
                json.dump(data, fp, indent=2)
            ```
        """))
        findings = self.evaluator.evaluate(page, None)
        for f in findings:
            assert f.evaluator == "code_prose_alignment"

    def test_all_findings_are_warn(self):
        """EXPERIMENTAL evaluator must never emit FAIL — only WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            This demonstrates PDF rendering with custom page layout settings
            and watermark overlay configuration for enterprise documents.

            ```python
            import json
            data = {"key": "value", "numbers": [1, 2, 3]}
            with open("output.json", "w") as fp:
                json.dump(data, fp, indent=2)
            ```
        """))
        findings = self.evaluator.evaluate(page, None)
        for f in findings:
            assert f.level == "WARN", f"EXPERIMENTAL evaluator must only emit WARN, got {f.level}"


class TestRegistration:
    def test_in_default_evaluators(self):
        from content_eval.config import DEFAULT_EVALUATORS
        assert "code_prose_alignment" in DEFAULT_EVALUATORS

    def test_not_in_experimental_evaluators(self):
        from content_eval.config import EXPERIMENTAL_EVALUATORS
        assert "code_prose_alignment" not in EXPERIMENTAL_EVALUATORS

    def test_self_registers_via_name(self):
        from content_eval.evaluators import _ensure_loaded, _REGISTRY
        _ensure_loaded()
        assert "code_prose_alignment" in _REGISTRY

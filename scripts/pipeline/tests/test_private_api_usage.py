"""Tests for the private_api_usage evaluator — including import-path detection."""

from __future__ import annotations

from content_eval.evaluators.private_api_usage import PrivateApiUsageEvaluator
from content_eval.models import CodeBlock, Page


def _make_page(code: str, lang: str = "python", platform: str = "python") -> Page:
    page = Page.__new__(Page)
    page.filepath = "test.md"
    page.family = "tex"
    page.platform = platform
    page.code_blocks = [CodeBlock(lang=lang, content=code, start_line=10, end_line=20)]
    page.body = ""
    page.headings = []
    page.raw_frontmatter = {}
    return page


class TestPrivateImportDetection:
    def setup_method(self):
        self.ev = PrivateApiUsageEvaluator()

    def test_private_module_import_detected(self):
        code = "from aspose_tex._input.reader import StringInputSource"
        page = _make_page(code)
        findings = self.ev.evaluate(page, None)
        warns = [f for f in findings if f.level == "WARN"]
        assert len(warns) == 1
        assert "aspose_tex._input.reader" in warns[0].message

    def test_public_import_not_flagged(self):
        code = "from aspose_tex import StringInputSource"
        page = _make_page(code)
        findings = self.ev.evaluate(page, None)
        assert len(findings) == 0

    def test_private_brotli_import_detected(self):
        code = "from aspose_font._brotli import BrotliEncoder"
        page = _make_page(code)
        findings = self.ev.evaluate(page, None)
        warns = [f for f in findings if f.level == "WARN"]
        assert len(warns) == 1

    def test_import_detection_is_warn_not_fail(self):
        code = "from aspose_tex._input import reader"
        page = _make_page(code)
        findings = self.ev.evaluate(page, None)
        assert all(f.level == "WARN" for f in findings if "private module" in f.message)

    def test_dedup_same_module_import(self):
        code = (
            "from aspose_tex._input.reader import StringInputSource\n"
            "from aspose_tex._input.reader import FileInputSource\n"
        )
        page = _make_page(code)
        findings = self.ev.evaluate(page, None)
        warns = [f for f in findings if f.level == "WARN"]
        assert len(warns) == 1  # same module path, only reported once

    def test_non_python_page_skipped(self):
        code = "from aspose_tex._input import reader"
        page = _make_page(code, platform="java")
        findings = self.ev.evaluate(page, None)
        assert len(findings) == 0

    def test_dot_access_still_detected_as_fail(self):
        code = "result = obj._private_method()"
        page = _make_page(code)
        findings = self.ev.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert len(fails) == 1

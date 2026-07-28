"""HARDEN-cpp-destructor (MT012): api_completeness must recognize C++
destructor names (`~ClassName`) as documented.

Found live while launching pdf/cpp: `api_surface.json` names a class's
destructor literally `~ClassName` (e.g. Device's is `'~Device'`). The
generator (batch_reference.py) already writes a real table row for it
(a `~Device()` cell with a "Calls ~Device on this Device instance." description),
but the
evaluator's three member-extraction regexes all used a bare `(\w+)` capture
group -- `\w` excludes `~`, so the regex never matched starting at the
backtick (the tilde is the very next character), and the destructor was
reported as permanently undocumented (FAIL) regardless of real page content.
This affected every C++ class with a destructor (8 reference pages failed on
pdf/cpp's launch alone).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from content_eval.evaluators.api_completeness import ApiCompletenessEvaluator
from content_eval.models import Page


def _make_ref_page(tmp_path: Path, body: str, class_name: str) -> Page:
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "cpp"
    ref_dir.mkdir(parents=True, exist_ok=True)
    md_file = ref_dir / f"{class_name}.md"
    frontmatter = f"---\ntitle: {class_name}\nlinkTitle: {class_name}\n---\n\n"
    md_file.write_text(frontmatter + body, encoding="utf-8")
    return Page.load(md_file)


def _api_surface_with(class_name: str, methods: list[str]) -> list[dict]:
    return [{"name": class_name, "methods": [{"name": m} for m in methods], "properties": []}]


class TestCppDestructorRecognized:
    def test_destructor_in_table_row_is_documented(self, tmp_path):
        class_name = "Device"
        body = (
            "## Methods\n\n"
            "| Signature | Description |\n"
            "|-----------|-------------|\n"
            "| `~Device()` | Calls ~Device on this Device instance. |\n"
        )
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)
        api_data = _api_surface_with(class_name, methods=["~Device"])

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            f"'~Device()' table row should document the '~Device' destructor, got: {findings}"
        )

    def test_destructor_missing_still_fails(self, tmp_path):
        """Regression guard: a genuinely undocumented destructor must still FAIL."""
        class_name = "Shape"
        body = "This page never mentions the destructor.\n"
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)
        api_data = _api_surface_with(class_name, methods=["~Shape", "GraphInfo", "CheckBounds"])

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1
        assert findings[0].level == "FAIL"

    def test_destructor_in_section_header_is_documented(self, tmp_path):
        class_name = "PdfAction"
        body = "## Overview\n\n### ~PdfAction()\n\nReleases resources.\n"
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)
        api_data = _api_surface_with(class_name, methods=["~PdfAction"])

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == []

    def test_ordinary_method_names_unaffected(self, tmp_path):
        """Regression guard: the optional '~?' must not change matching for
        ordinary (non-destructor) member names."""
        class_name = "ValueClass"
        body = (
            "## Methods\n\n"
            "| Method | Description |\n"
            "|--------|-------------|\n"
            "| `getValue()` | Returns the current value. |\n"
        )
        page = _make_ref_page(tmp_path, body=body, class_name=class_name)
        api_data = _api_surface_with(class_name, methods=["getValue"])

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=api_data):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == []

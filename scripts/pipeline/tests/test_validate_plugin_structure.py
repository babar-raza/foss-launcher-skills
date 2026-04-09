"""Tests for validate_plugin_structure.py — display-control severity promotion."""

import pytest
from pathlib import Path
from unittest.mock import patch

from validate_plugin_structure import check_file, Finding


def _write_plugin_page(tmp_path: Path, *, english: bool = True,
                       include_optional: bool = True,
                       include_more_formats: bool = True) -> Path:
    """Create a synthetic plugin page for testing."""
    locale = "en" if english else "fr"
    page_dir = tmp_path / "content" / "products.aspose.org" / locale / "test" / "python"
    page_dir.mkdir(parents=True, exist_ok=True)
    filepath = page_dir / "_index.md"

    sections = []
    sections.append("layout: plugin")
    sections.append('family_name: "Test FOSS"')
    sections.append('plugin_description: "Test desc"')
    sections.append('plugin_platform: "Python"')
    sections.append('head_title: "Test"')
    sections.append('head_description: "Test desc"')
    sections.append('title: "Test"')
    sections.append('description: "Test"')
    sections.append('github_url: "https://github.com/test"')
    sections.append("submenu:\n  enable: true")
    sections.append("overview:\n  enable: true\n  title: Test\n  content: Test content")
    sections.append("content:\n  enable: true\n  block:\n  - title_left: Test")
    sections.append("single:\n  enable: true\n  block:\n  - title: Test")
    sections.append("provenance:\n  content_origin: skill-generated")
    sections.append("evidence:\n  model_sha: abc123")

    if include_optional:
        sections.append("supportandlearning:\n  enable: true")
        sections.append("back_to_top:\n  enable: true")
    if include_more_formats:
        sections.append("more_formats:\n  enable: true")

    content = "---\n" + "\n".join(sections) + "\n---\n"
    filepath.write_text(content, encoding="utf-8")
    return filepath


class TestDisplaySectionSeverity:
    """Verify display-control sections are ERROR for English, WARN for locale."""

    def test_english_missing_optional_is_error(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=True,
                                      include_optional=False,
                                      include_more_formats=False)
        findings = check_file(filepath)
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(errors) == 3, f"Expected 3 ERRORs for missing display sections, got {len(errors)}"
        check_ids = {f.check_id for f in errors}
        assert "MISSING_DISPLAY" in check_ids

    def test_locale_missing_optional_is_warn(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=False,
                                      include_optional=False,
                                      include_more_formats=False)
        findings = check_file(filepath)
        errors = [f for f in findings if f.severity == "ERROR"]
        warns = [f for f in findings if f.severity == "WARN"]
        assert len(errors) == 0, "Locale pages should not get ERROR for missing display sections"
        display_warns = [f for f in warns if f.check_id == "MISSING_DISPLAY"]
        assert len(display_warns) == 3

    def test_english_complete_page_passes(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=True,
                                      include_optional=True,
                                      include_more_formats=True)
        findings = check_file(filepath)
        fatals = [f for f in findings if f.severity == "FATAL"]
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(fatals) == 0
        assert len(errors) == 0

    def test_more_formats_included_in_check(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=True,
                                      include_optional=True,
                                      include_more_formats=False)
        findings = check_file(filepath)
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(errors) == 1
        assert "more_formats" in errors[0].message

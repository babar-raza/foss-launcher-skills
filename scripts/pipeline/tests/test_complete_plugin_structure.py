"""Tests for complete_plugin_structure.py — deterministic skeleton filler."""

import pytest
from pathlib import Path

from complete_plugin_structure import complete_file


def _write_plugin_page(tmp_path: Path, *, include_optional: bool = False) -> Path:
    """Create a synthetic plugin page."""
    filepath = tmp_path / "_index.md"
    sections = [
        "layout: plugin",
        'family_name: "Test FOSS"',
        'plugin_description: "Test desc"',
        "overview:\n  enable: true\n  title: Test\n  content: Test content",
        "content:\n  enable: true\n  block:\n  - title_left: Test",
        "single:\n  enable: true\n  block:\n  - title: Test",
    ]
    if include_optional:
        sections.append("supportandlearning:\n  enable: true")
        sections.append("more_formats:\n  enable: true")
        sections.append("back_to_top:\n  enable: true")

    sections.append("provenance:\n  content_origin: skill-generated")
    sections.append("evidence:\n  model_sha: abc123")

    content = "---\n" + "\n".join(sections) + "\n---\n"
    filepath.write_text(content, encoding="utf-8")
    return filepath


class TestCompleteFile:
    """Test the structural completion logic."""

    def test_adds_missing_sections(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, include_optional=False)
        result = complete_file(filepath)
        assert result is True, "Should have modified file"

        text = filepath.read_text(encoding="utf-8")
        assert "supportandlearning:" in text
        assert "more_formats:" in text
        assert "back_to_top:" in text

    def test_idempotent(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, include_optional=False)
        complete_file(filepath)
        text_after_first = filepath.read_text(encoding="utf-8")

        result = complete_file(filepath)
        assert result is False, "Second run should detect no changes needed"
        text_after_second = filepath.read_text(encoding="utf-8")
        assert text_after_first == text_after_second

    def test_preserves_existing_content(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, include_optional=False)
        original = filepath.read_text(encoding="utf-8")

        complete_file(filepath)
        text = filepath.read_text(encoding="utf-8")

        # All original content sections should be preserved
        assert "Test content" in text
        assert "title_left: Test" in text
        assert 'family_name: "Test FOSS"' in text

    def test_already_complete_page_unchanged(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, include_optional=True)
        result = complete_file(filepath)
        assert result is False, "Complete page should not be modified"

    def test_non_plugin_page_skipped(self, tmp_path):
        filepath = tmp_path / "_index.md"
        filepath.write_text("---\nlayout: family\ntitle: Test\n---\nBody\n", encoding="utf-8")
        result = complete_file(filepath)
        assert result is False, "Non-plugin pages should be skipped"

    def test_inserts_before_provenance(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, include_optional=False)
        complete_file(filepath)
        text = filepath.read_text(encoding="utf-8")

        # Boilerplate sections should appear before provenance
        sup_pos = text.index("supportandlearning:")
        prov_pos = text.index("provenance:")
        assert sup_pos < prov_pos, "Boilerplate should be inserted before provenance"

    def test_dry_run_no_writes(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, include_optional=False)
        original = filepath.read_text(encoding="utf-8")

        result = complete_file(filepath, dry_run=True)
        assert result is True, "Dry run should report changes needed"

        after = filepath.read_text(encoding="utf-8")
        assert original == after, "Dry run should not modify file"

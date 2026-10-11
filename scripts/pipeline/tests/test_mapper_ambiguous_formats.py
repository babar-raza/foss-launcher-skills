"""Tests for CV2-003c: ambiguous format detection in mapper.py.

Verifies that format names colliding with common English words (e.g. "text")
are only detected when strong contextual evidence exists (file extension,
enum reference, save/load method call), not from bare prose mentions.
"""

import json
import types
from pathlib import Path

import pytest

from evidence.mapper import (
    _detect_formats_in_text,
    _has_format_context,
    _load_known_formats,
)


@pytest.fixture
def knowledge():
    return types.SimpleNamespace(family="words", platform="python")


def _write_formats(tmp_path, knowledge, formats):
    fmt_path = tmp_path / knowledge.family / knowledge.platform / "merged" / "formats.json"
    fmt_path.parent.mkdir(parents=True, exist_ok=True)
    fmt_path.write_text(json.dumps(formats), encoding="utf-8")


@pytest.fixture(autouse=True)
def _patch_knowledge_root(tmp_path, monkeypatch):
    import evidence.mapper as mod
    monkeypatch.setattr(mod, "KNOWLEDGE_ROOT", tmp_path)


_TEXT_FORMAT = [{"extension": "text", "support": "export"}]
_PDF_FORMAT = [{"extension": "pdf", "support": "both"}]
_BOTH_FORMATS = _TEXT_FORMAT + _PDF_FORMAT


# ---------------------------------------------------------------------------
# _has_format_context unit tests
# ---------------------------------------------------------------------------

class TestHasFormatContext:
    def test_dot_extension(self):
        assert _has_format_context("text", "save the file as output.text for review")

    def test_saveformat_enum(self):
        assert _has_format_context("text", "use saveformat.text to export")

    def test_loadformat_enum(self):
        assert _has_format_context("text", "use loadformat.text to import")

    def test_save_to_method(self):
        assert _has_format_context("text", "call save_to_text() to export")

    def test_export_to_method(self):
        assert _has_format_context("text", "call export_to_text() for output")

    def test_to_text_method(self):
        assert _has_format_context("text", "use to_text() for conversion")

    def test_save_code_pattern(self):
        assert _has_format_context("text", 'doc.save("output.text")')

    def test_bare_prose_rejected(self):
        assert not _has_format_context("text", "extract text from the document")

    def test_property_name_rejected(self):
        assert not _has_format_context("text", "the text annotation is visible")

    def test_method_name_rejected(self):
        assert not _has_format_context("text", "call gettext to retrieve content")


# ---------------------------------------------------------------------------
# _detect_formats_in_text integration tests
# ---------------------------------------------------------------------------

class TestDetectFormatsInText:
    def test_text_in_prose_not_detected(self, tmp_path, knowledge):
        _write_formats(tmp_path, knowledge, _TEXT_FORMAT)
        result = _detect_formats_in_text(
            "Extract text from the PDF document for processing.",
            knowledge,
        )
        assert not any(e["ext"] == "text" for e in result)

    def test_text_with_saveformat_enum_detected(self, tmp_path, knowledge):
        _write_formats(tmp_path, knowledge, _TEXT_FORMAT)
        result = _detect_formats_in_text(
            "Use SaveFormat.Text to export the document as plain text.",
            knowledge,
        )
        assert any(e["ext"] == "text" for e in result)

    def test_text_with_dot_extension_detected(self, tmp_path, knowledge):
        _write_formats(tmp_path, knowledge, _TEXT_FORMAT)
        result = _detect_formats_in_text(
            'Save the output to "result.text" for later review.',
            knowledge,
        )
        assert any(e["ext"] == "text" for e in result)

    def test_text_with_save_method_detected(self, tmp_path, knowledge):
        _write_formats(tmp_path, knowledge, _TEXT_FORMAT)
        result = _detect_formats_in_text(
            "Call doc.save_to_text() to export as plain text.",
            knowledge,
        )
        assert any(e["ext"] == "text" for e in result)

    def test_non_ambiguous_ext_unchanged(self, tmp_path, knowledge):
        """Non-ambiguous formats like 'pdf' should still use bare-word matching."""
        _write_formats(tmp_path, knowledge, _PDF_FORMAT)
        result = _detect_formats_in_text(
            "This page explains PDF document processing.",
            knowledge,
        )
        assert any(e["ext"] == "pdf" for e in result)

    def test_mixed_formats_selective(self, tmp_path, knowledge):
        """With both text and pdf in formats.json, pdf detected but text not (prose only)."""
        _write_formats(tmp_path, knowledge, _BOTH_FORMATS)
        result = _detect_formats_in_text(
            "Convert text content to PDF format.",
            knowledge,
        )
        exts = {e["ext"] for e in result}
        assert "pdf" in exts
        assert "text" not in exts

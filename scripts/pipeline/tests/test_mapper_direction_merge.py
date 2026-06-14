"""Tests for mapper.py format-direction merge logic (FIX Sprint 1 2026-06-14).

Verifies that _load_known_formats() correctly merges import+export->both
for the same file extension, rather than using first-seen-wins dedup.
"""

import json
import types

import pytest

from evidence.mapper import _load_known_formats


@pytest.fixture
def knowledge():
    """Minimal knowledge namespace object."""
    return types.SimpleNamespace(family="pdf", platform="net")


def _write_formats(tmp_path, knowledge, formats):
    """Helper: write formats.json and patch KNOWLEDGE_ROOT."""
    fmt_path = tmp_path / knowledge.family / knowledge.platform / "merged" / "formats.json"
    fmt_path.parent.mkdir(parents=True, exist_ok=True)
    fmt_path.write_text(json.dumps(formats), encoding="utf-8")


@pytest.fixture(autouse=True)
def _patch_knowledge_root(tmp_path, monkeypatch):
    """Point KNOWLEDGE_ROOT at tmp_path for all tests."""
    import evidence.mapper as mod
    monkeypatch.setattr(mod, "KNOWLEDGE_ROOT", tmp_path)


class TestDirectionMerge:
    """_load_known_formats should merge directions for same extension."""

    def test_import_export_merges_to_both(self, tmp_path, knowledge):
        """Two entries for 'pdf' (import + export) -> single entry with 'both'."""
        _write_formats(tmp_path, knowledge, [
            {"extension": "pdf", "support": "import"},
            {"extension": "pdf", "support": "export"},
        ])
        result = _load_known_formats(knowledge)
        pdf_entries = [e for e in result if e["ext"] == "pdf"]
        assert len(pdf_entries) == 1
        assert pdf_entries[0]["support"] == "both"

    def test_export_import_order_independent(self, tmp_path, knowledge):
        """Merge works regardless of which direction appears first."""
        _write_formats(tmp_path, knowledge, [
            {"extension": "pdf", "support": "export"},
            {"extension": "pdf", "support": "import"},
        ])
        result = _load_known_formats(knowledge)
        pdf_entries = [e for e in result if e["ext"] == "pdf"]
        assert len(pdf_entries) == 1
        assert pdf_entries[0]["support"] == "both"

    def test_same_direction_deduplicates(self, tmp_path, knowledge):
        """Two 'import' entries for same ext -> single 'import' entry."""
        _write_formats(tmp_path, knowledge, [
            {"extension": "docx", "support": "import"},
            {"extension": "docx", "support": "import"},
        ])
        result = _load_known_formats(knowledge)
        docx_entries = [e for e in result if e["ext"] == "docx"]
        assert len(docx_entries) == 1
        assert docx_entries[0]["support"] == "import"

    def test_both_absorbs_import(self, tmp_path, knowledge):
        """If one entry is 'both' and another is 'import', result is 'both'."""
        _write_formats(tmp_path, knowledge, [
            {"extension": "html", "support": "both"},
            {"extension": "html", "support": "import"},
        ])
        result = _load_known_formats(knowledge)
        html_entries = [e for e in result if e["ext"] == "html"]
        assert len(html_entries) == 1
        assert html_entries[0]["support"] == "both"

    def test_detect_entries_excluded(self, tmp_path, knowledge):
        """Entries with support='detect' are excluded per FIX-06."""
        _write_formats(tmp_path, knowledge, [
            {"extension": "xyz", "support": "detect"},
        ])
        result = _load_known_formats(knowledge)
        assert not any(e["ext"] == "xyz" for e in result)

    def test_nonfunctional_entries_excluded(self, tmp_path, knowledge):
        """Entries with functional=False are excluded per FIX-13."""
        _write_formats(tmp_path, knowledge, [
            {"extension": "abc", "support": "export", "functional": False},
        ])
        result = _load_known_formats(knowledge)
        assert not any(e["ext"] == "abc" for e in result)

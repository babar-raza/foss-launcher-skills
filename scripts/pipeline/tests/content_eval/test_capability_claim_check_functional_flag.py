"""Regression tests for capability_claim_check.py's _load_formats() functional-flag
handling — duplicate implementation of the same bug fixed in format_truth.py.

See test_format_truth_functional_flag.py for the full bug narrative (found
2026-07-23 via words/net full-corpus batch-eval-fix, FIX-G30). This evaluator
has its own separate _load_formats() with the identical enum_only-only
functional check, and needed the identical fix.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from content_eval.evaluators import capability_claim_check as _ccc


def _write_formats(tmp_path, family, platform, entries, subdir="merged"):
    merged_dir = tmp_path / family / platform / subdir
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "formats.json").write_text(json.dumps(entries), encoding="utf-8")


class TestLoadFormatsFunctionalFlag:

    def test_functional_false_import_and_export_both_become_none(self, tmp_path, monkeypatch):
        """The real words/net shape: Pdf has both an import entry and an
        enum_only export entry, all functional=False — must merge to 'none'."""
        monkeypatch.setattr(_ccc, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Pdf", "direction": "import", "functional": False},
            {"format": "Pdf", "direction": "enum_only", "functional": False},
        ])
        result = _ccc._load_formats("words", "net")
        assert result.get("pdf") == "none", (
            f"Expected 'none' for a fully-gated format, got {result.get('pdf')!r}"
        )

    def test_functional_true_with_import_direction_still_import(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ccc, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Docx", "direction": "import", "functional": True},
        ])
        result = _ccc._load_formats("words", "net")
        assert result.get("docx") == "import"

    def test_functional_absent_unaffected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ccc, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Docx", "direction": "import"},
        ])
        result = _ccc._load_formats("words", "net")
        assert result.get("docx") == "import"

    def test_enum_only_functional_false_still_none_no_regression(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ccc, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Mhtml", "direction": "enum_only", "functional": False},
        ])
        result = _ccc._load_formats("words", "net")
        assert result.get("mhtml") == "none"

    def test_dispatch_gated_docm_style_functional_true_becomes_both(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ccc, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Docm", "direction": "import", "functional": True},
            {"format": "Docm", "direction": "export", "functional": True},
        ])
        result = _ccc._load_formats("words", "net")
        assert result.get("docm") == "both"

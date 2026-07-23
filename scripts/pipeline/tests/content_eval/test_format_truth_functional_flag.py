"""Regression tests for format_truth.py's _load_formats() functional-flag handling.

Bug (found 2026-07-23 via words/net full-corpus batch-eval-fix, FIX-G30):
_load_formats() only consulted an entry's `functional` field when its raw
`direction` was literally "enum_only" — a format entry whose `direction` was
already "import"/"export"/"both" but carried `functional: false` (a format
genuinely gated behind a throw at the dispatch layer, per formats.py's FOSS-gate
scanning) had its `functional` flag silently ignored, so the gated format was
reported as if it were really supported. This produced FAIL-level false
positives on 7 words/net reference pages that correctly stated HTML is
unsupported (formats.json's Html entries all have direction: "import"/"export"
with functional: false, since the reader/writer classes exist but throw).

No dedicated test file previously existed for _load_formats() at all — this
file provides baseline coverage as well as the specific regression case.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from content_eval.evaluators import format_truth as _ft


def _write_formats(tmp_path, family, platform, entries):
    merged_dir = tmp_path / family / platform / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "formats.json").write_text(json.dumps(entries), encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_knowledge_root(monkeypatch):
    yield  # each test sets its own KNOWLEDGE_ROOT via monkeypatch; nothing to reset after


class TestLoadFormatsFunctionalFlag:

    def test_functional_false_with_import_direction_becomes_none(self, tmp_path, monkeypatch):
        """The exact regression: direction='import' + functional=false must resolve to 'none'."""
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Html", "direction": "import", "functional": False},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("html") == "none"

    def test_functional_false_with_export_direction_becomes_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Html", "direction": "export", "functional": False},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("html") == "none"

    def test_functional_false_import_and_export_both_become_none(self, tmp_path, monkeypatch):
        """The real words/net shape: separate import and export entries for the
        same format, both gated — must merge to 'none', not 'both'."""
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Html", "direction": "import", "functional": False},
            {"format": "Html", "direction": "export", "functional": False},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("html") == "none", (
            f"Expected 'none' for a fully-gated format, got {result.get('html')!r} "
            "(regression: functional=False silently ignored, format reported as 'both')"
        )

    def test_functional_true_with_import_direction_still_import(self, tmp_path, monkeypatch):
        """Sanity: functional=True (or absent) must not be affected by this fix."""
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Docx", "direction": "import", "functional": True},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("docx") == "import"

    def test_functional_absent_with_import_direction_still_import(self, tmp_path, monkeypatch):
        """Sanity: entries with no functional key at all (older schema) unaffected."""
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Docx", "direction": "import"},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("docx") == "import"

    def test_mixed_functional_and_gated_entries_keeps_real_capability(self, tmp_path, monkeypatch):
        """If ONE entry for an ext is genuinely functional and another is gated,
        the real capability must survive (functional entry wins, not 'none')."""
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Docx", "direction": "import", "functional": False},
            {"format": "Docx", "direction": "import", "functional": True},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("docx") == "import"

    def test_enum_only_functional_false_still_none_no_regression(self, tmp_path, monkeypatch):
        """Pre-existing enum_only + functional=False path must still work
        (this fix must not alter that already-correct branch)."""
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Mhtml", "direction": "enum_only", "functional": False},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("mhtml") == "none"

    def test_enum_only_functional_true_still_import_no_regression(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Rtf", "direction": "enum_only", "functional": True},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("rtf") == "import"

    def test_dispatch_gated_docm_style_functional_true_becomes_both(self, tmp_path, monkeypatch):
        """Regression guard for the EARLIER same-session fix (dispatch-fallthrough
        functional detection): a format with real import+export entries, both
        functional=True, must still merge to 'both' — this fix must not break that."""
        monkeypatch.setattr(_ft, "KNOWLEDGE_ROOT", tmp_path)
        _write_formats(tmp_path, "words", "net", [
            {"format": "Docm", "direction": "import", "functional": True},
            {"format": "Docm", "direction": "export", "functional": True},
        ])
        result = _ft._load_formats("words", "net")
        assert result.get("docm") == "both"

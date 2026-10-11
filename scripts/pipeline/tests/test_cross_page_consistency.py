"""Tests for cross_page_consistency.py (TC-CONSIST-001)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from commands.content.cross_page_consistency import (
    _tokenize,
    _cosine,
    _has_negation,
    _has_direction_conflict,
    detect_contradictions,
)


class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("The Workbook class exports data")
        assert "workbook" in tokens
        assert "exports" in tokens
        assert "the" not in tokens

    def test_stopwords_filtered(self):
        tokens = _tokenize("a the and or but if")
        assert len(tokens) == 0

    def test_short_words_filtered(self):
        tokens = _tokenize("go to do it")
        assert len(tokens) == 0


class TestCosine:
    def test_identical(self):
        tokens = _tokenize("workbook spreadsheet cells export data")
        assert abs(_cosine(tokens, tokens) - 1.0) < 1e-9

    def test_empty(self):
        assert _cosine([], ["hello"]) == 0.0


class TestNegation:
    def test_has_negation(self):
        assert _has_negation("does not support PDF export")
        assert _has_negation("cannot read XLSX files")
        assert _has_negation("deprecated since version 2.0")

    def test_no_negation(self):
        assert not _has_negation("supports PDF export")
        assert not _has_negation("read and write XLSX files")


class TestDirectionConflict:
    def test_import_export_conflict(self):
        assert _has_direction_conflict(
            "supports import of PDF files",
            "supports export of PDF files",
        )

    def test_read_write_conflict(self):
        assert _has_direction_conflict(
            "can read XLSX spreadsheets",
            "can write XLSX spreadsheets",
        )

    def test_no_conflict_same_direction(self):
        assert not _has_direction_conflict(
            "supports import of PDF files",
            "supports import of XLSX files",
        )

    def test_no_conflict_both_directions(self):
        # Both texts mention both directions → not a conflict
        assert not _has_direction_conflict(
            "supports import and export of PDF",
            "provides import and export functionality",
        )


class TestDetectContradictions:
    def test_negation_contradiction(self):
        """Same topic + negation mismatch → contradiction."""
        claims = [
            {"claim_id": "CLM-1", "text": "workbook class supports spreadsheet PDF export output",
             "file": "page_a.md"},
            {"claim_id": "CLM-2", "text": "workbook class does not support spreadsheet PDF export output",
             "file": "page_b.md"},
        ]
        results = detect_contradictions(claims)
        assert len(results) >= 1
        assert "negation_mismatch" in results[0]["reasons"]

    def test_direction_contradiction(self):
        """Same topic + opposing direction verbs → contradiction."""
        claims = [
            {"claim_id": "CLM-1", "text": "document class provides import functionality for spreadsheet data files",
             "file": "page_a.md"},
            {"claim_id": "CLM-2", "text": "document class provides export functionality for spreadsheet data files",
             "file": "page_b.md"},
        ]
        results = detect_contradictions(claims)
        assert len(results) >= 1
        assert "direction_conflict" in results[0]["reasons"]

    def test_no_contradiction_different_topics(self):
        """Unrelated topics → no contradiction."""
        claims = [
            {"claim_id": "CLM-1", "text": "workbook exports spreadsheet data cells",
             "file": "page_a.md"},
            {"claim_id": "CLM-2", "text": "smtp client sends email messages authentication",
             "file": "page_b.md"},
        ]
        results = detect_contradictions(claims)
        assert len(results) == 0

    def test_no_contradiction_same_page(self):
        """Same-page claims are skipped."""
        claims = [
            {"claim_id": "CLM-1", "text": "workbook supports spreadsheet PDF export output data",
             "file": "page_a.md"},
            {"claim_id": "CLM-2", "text": "workbook does not support spreadsheet PDF export output data",
             "file": "page_a.md"},
        ]
        results = detect_contradictions(claims)
        assert len(results) == 0

    def test_empty_claims(self):
        assert detect_contradictions([]) == []

    def test_single_claim(self):
        claims = [{"claim_id": "CLM-1", "text": "supports export", "file": "a.md"}]
        assert detect_contradictions(claims) == []

    def test_no_text_skipped(self):
        claims = [
            {"claim_id": "CLM-1", "text": "", "file": "a.md"},
            {"claim_id": "CLM-2", "text": "", "file": "b.md"},
        ]
        assert detect_contradictions(claims) == []

    def test_contradiction_result_fields(self):
        """Contradiction result has all required fields."""
        claims = [
            {"claim_id": "CLM-1", "text": "workbook class supports spreadsheet PDF export output data",
             "file": "page_a.md"},
            {"claim_id": "CLM-2", "text": "workbook class does not support spreadsheet PDF export output data",
             "file": "page_b.md"},
        ]
        results = detect_contradictions(claims)
        assert len(results) >= 1
        r = results[0]
        assert "claim_a" in r
        assert "claim_b" in r
        assert "file_a" in r
        assert "file_b" in r
        assert "similarity" in r
        assert "reasons" in r
        assert isinstance(r["reasons"], list)

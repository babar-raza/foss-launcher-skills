"""Tests for semantic claim deduplication in promote.py (TC-KNOW-001)."""

import pytest

from commands.knowledge.promote import (
    _semantic_dedup_claims,
    _tfidf_cosine,
    _tfidf_tokenize,
    _SEMANTIC_DEDUP_THRESHOLD,
)


class TestTfidfTokenize:
    def test_basic(self):
        tokens = _tfidf_tokenize("exports PDF documents with embedded fonts")
        assert "exports" in tokens
        assert "pdf" in tokens
        assert "documents" in tokens
        assert "with" not in tokens  # stopword

    def test_empty(self):
        assert _tfidf_tokenize("") == []


class TestTfidfCosine:
    def test_identical(self):
        vec = {"pdf": 1.0, "export": 2.0}
        assert abs(_tfidf_cosine(vec, vec) - 1.0) < 1e-9

    def test_orthogonal(self):
        assert _tfidf_cosine({"a": 1.0}, {"b": 1.0}) == 0.0

    def test_empty(self):
        assert _tfidf_cosine({}, {"a": 1.0}) == 0.0


class TestSemanticDedupClaims:
    def test_threshold_is_090(self):
        assert _SEMANTIC_DEDUP_THRESHOLD == 0.90

    def test_near_duplicate_merged(self):
        """Two claims with identical text are merged."""
        claims = [
            {"claim_id": "CLM-001", "text": "exports PDF documents with embedded fonts to disk", "confidence": 0.95},
            {"claim_id": "CLM-002", "text": "exports PDF documents with embedded fonts to disk", "confidence": 0.90},
        ]
        result = _semantic_dedup_claims(claims)
        assert len(result) == 1
        assert result[0]["claim_id"] == "CLM-001"  # higher confidence
        assert "CLM-002" in result[0].get("merged_from", [])

    def test_different_claims_preserved(self):
        """Claims with distinct meanings are not merged."""
        claims = [
            {"claim_id": "CLM-001", "text": "exports PDF documents with embedded fonts", "confidence": 0.95},
            {"claim_id": "CLM-002", "text": "provides batch processing of spreadsheet files", "confidence": 0.90},
            {"claim_id": "CLM-003", "text": "supports watermark insertion on slides", "confidence": 0.85},
        ]
        result = _semantic_dedup_claims(claims)
        assert len(result) == 3

    def test_empty_list(self):
        assert _semantic_dedup_claims([]) == []

    def test_single_claim(self):
        claims = [{"claim_id": "CLM-001", "text": "exports PDF", "confidence": 1.0}]
        result = _semantic_dedup_claims(claims)
        assert len(result) == 1

    def test_lower_confidence_merged_into_higher(self):
        """The lower-confidence claim is always the one removed."""
        claims = [
            {"claim_id": "CLM-A", "text": "converts workbook spreadsheet data", "confidence": 0.70},
            {"claim_id": "CLM-B", "text": "converts workbook spreadsheet data", "confidence": 0.95},
        ]
        result = _semantic_dedup_claims(claims)
        assert len(result) == 1
        assert result[0]["claim_id"] == "CLM-B"
        assert "CLM-A" in result[0].get("merged_from", [])

    def test_merged_from_accumulates(self):
        """If a winner already has merged_from, new entries are appended."""
        claims = [
            {"claim_id": "CLM-A", "text": "converts workbook spreadsheet data format files", "confidence": 0.95,
             "merged_from": ["CLM-Z"]},
            {"claim_id": "CLM-B", "text": "converts workbook spreadsheet data format files", "confidence": 0.70},
        ]
        result = _semantic_dedup_claims(claims)
        assert len(result) == 1
        mf = result[0].get("merged_from", [])
        assert "CLM-Z" in mf
        assert "CLM-B" in mf

    def test_no_mutation_when_below_threshold(self):
        """Claims below threshold get no merged_from field."""
        claims = [
            {"claim_id": "CLM-001", "text": "exports PDF documents with embedded fonts", "confidence": 0.95},
            {"claim_id": "CLM-002", "text": "provides batch processing of spreadsheet files", "confidence": 0.90},
        ]
        result = _semantic_dedup_claims(claims)
        for c in result:
            assert "merged_from" not in c

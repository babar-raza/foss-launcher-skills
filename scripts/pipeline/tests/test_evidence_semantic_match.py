"""Tests for semantic evidence matching in mapper.py (TC-EVID-001)."""

import pytest

from evidence.mapper import (
    _semantic_match_claims,
    _sem_tokenize,
    _sem_cosine,
    _SEMANTIC_MATCH_THRESHOLD,
)


class TestSemTokenize:
    def test_basic(self):
        tokens = _sem_tokenize("The Workbook class supports exporting PDF documents")
        assert "workbook" in tokens
        assert "class" in tokens
        assert "supports" in tokens
        assert "the" not in tokens  # stopword

    def test_empty(self):
        assert _sem_tokenize("") == []


class TestSemCosine:
    def test_identical(self):
        vec = {"workbook": 1.0, "export": 2.0}
        assert abs(_sem_cosine(vec, vec) - 1.0) < 1e-9

    def test_orthogonal(self):
        assert _sem_cosine({"a": 1.0}, {"b": 1.0}) == 0.0


class TestSemanticMatchClaims:
    def test_threshold_is_085(self):
        assert _SEMANTIC_MATCH_THRESHOLD == 0.85

    def test_matching_claim_found(self):
        """Prose that closely matches a claim text returns its claim_id."""
        claims = [
            {"claim_id": "CLM-001", "text": "supports exporting PDF documents with embedded fonts"},
            {"claim_id": "CLM-002", "text": "provides batch processing of spreadsheet files"},
        ]
        # Prose that matches CLM-001 closely
        prose = "supports exporting PDF documents with embedded fonts"
        result = _semantic_match_claims(prose, claims)
        assert "CLM-001" in result

    def test_unrelated_prose_no_match(self):
        """Prose about a completely different topic returns no matches."""
        claims = [
            {"claim_id": "CLM-001", "text": "supports exporting PDF documents with embedded fonts"},
            {"claim_id": "CLM-002", "text": "provides batch processing of spreadsheet files"},
        ]
        prose = "The quick brown fox jumps over the lazy dog in the forest"
        result = _semantic_match_claims(prose, claims)
        assert len(result) == 0

    def test_empty_prose(self):
        claims = [{"claim_id": "CLM-001", "text": "supports PDF export"}]
        assert _semantic_match_claims("", claims) == []

    def test_empty_claims(self):
        assert _semantic_match_claims("some prose text here", []) == []

    def test_short_prose_skipped(self):
        """Prose with fewer than 3 tokens is skipped."""
        claims = [{"claim_id": "CLM-001", "text": "supports PDF export"}]
        assert _semantic_match_claims("hi", claims) == []

    def test_short_claim_skipped(self):
        """Claims with fewer than 2 tokens are skipped."""
        claims = [{"claim_id": "CLM-001", "text": "ok"}]
        prose = "This library supports exporting PDF documents with embedded fonts"
        result = _semantic_match_claims(prose, claims)
        assert "CLM-001" not in result

    def test_graceful_with_missing_fields(self):
        """Claims without claim_id or text don't crash."""
        claims = [
            {"text": "supports PDF export"},
            {"claim_id": "CLM-002"},
            {},
        ]
        prose = "This library supports exporting PDF documents"
        result = _semantic_match_claims(prose, claims)
        # Should not crash
        assert isinstance(result, list)

"""Unit tests for _claim_index.py — TF-IDF claim matching helper."""

import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

sys.path.insert(0, str(_SCRIPTS / "pipeline"))
from content_eval.evaluators._claim_index import (
    ClaimIndex,
    clear_claim_cache,
    get_claim_index,
    load_claims,
    tokenize,
    TFIDF_AVAILABLE,
)


class TestTokenize:
    def test_extracts_lowercase_words(self):
        result = tokenize("Hello World Test123")
        assert "hello" in result
        assert "world" in result
        assert "test123" in result

    def test_skips_single_char(self):
        result = tokenize("a b c hello")
        assert "hello" in result
        assert "a" not in result


class TestClaimIndex:
    def test_empty_claims(self):
        ci = ClaimIndex([])
        assert not ci.available
        assert ci.best_similarity("anything") == 0.0

    def test_available_with_claims(self):
        ci = ClaimIndex([{"text": "supports PDF conversion"}])
        assert ci.available

    @pytest.mark.skipif(not TFIDF_AVAILABLE, reason="embed.py not available")
    def test_high_similarity_for_matching_text(self):
        ci = ClaimIndex([
            {"text": "supports PDF to DOCX conversion"},
            {"text": "enables batch image processing"},
        ])
        sim = ci.best_similarity("PDF to DOCX conversion support")
        assert sim > 0.5

    @pytest.mark.skipif(not TFIDF_AVAILABLE, reason="embed.py not available")
    def test_low_similarity_for_unrelated_text(self):
        ci = ClaimIndex([
            {"text": "supports PDF to DOCX conversion"},
        ])
        sim = ci.best_similarity("database connection pooling")
        assert sim < 0.3

    def test_skips_empty_text_claims(self):
        ci = ClaimIndex([{"text": ""}, {"other": "field"}, {"text": "valid claim"}])
        assert ci.available  # Only the valid one counts


class TestLoadClaims:
    def test_returns_empty_for_missing_path(self):
        result = load_claims("nonexistent_family", "nonexistent_platform")
        assert result == []


class TestGetClaimIndex:
    def setup_method(self):
        clear_claim_cache()

    def test_returns_claim_index(self):
        ci = get_claim_index("nonexistent", "nonexistent")
        assert isinstance(ci, ClaimIndex)
        assert not ci.available  # No claims file exists

    def test_caches_result(self):
        ci1 = get_claim_index("test", "test")
        ci2 = get_claim_index("test", "test")
        assert ci1 is ci2

    def teardown_method(self):
        clear_claim_cache()

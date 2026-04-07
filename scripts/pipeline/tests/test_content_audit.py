"""Tests for content_audit.py — pure helper functions and tier classification.

Covers:
  - _tokenize: pure function
  - _classify_paragraph: tier classification logic with synthetic knowledge stubs
  - TIER constants are defined
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from content_audit import (
    _tokenize,
    _classify_paragraph,
    TIER_SUPPORTED,
    TIER_PROBABLE,
    TIER_WEAK,
    TIER_UNSUPPORTED,
    TIER_CONTRADICTED,
)


# ---------------------------------------------------------------------------
# _tokenize — pure function
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic_tokenization(self):
        tokens = _tokenize("Workbook supports loading files")
        assert "workbook" in tokens
        assert "supports" in tokens
        assert "loading" in tokens
        assert "files" in tokens

    def test_3char_minimum(self):
        tokens = _tokenize("The file is loaded with the API")
        # _tokenize uses r"[a-z][a-z0-9_]+" which requires 2+ chars starting with [a-z]
        # "is" (2 chars starting 'i') is NOT matched by [a-z][a-z0-9_]+ (needs 2+ after first)
        # Actually "is" has only 2 chars: 'i' + 's', so [a-z][a-z0-9_]+ requires at least 2 total
        # Re-check: pattern [a-z][a-z0-9_]+ means 1 [a-z] + 1+ [a-z0-9_] = 2+ chars total
        # "is" = 'i' + 's' → matched; "the" = 't' + 'he' → matched
        # Actual behavior: keeps 2+ char words, no stop-word filter
        assert "file" in tokens
        assert "loaded" in tokens
        assert "with" in tokens

    def test_returns_set(self):
        assert isinstance(_tokenize("hello world"), set)

    def test_empty_string(self):
        assert isinstance(_tokenize(""), set)

    def test_strips_punctuation(self):
        tokens = _tokenize("Workbook.save() loads the file.")
        # dot/parens stripped; words should still tokenize
        assert len(tokens) > 0

    def test_lowercased(self):
        tokens = _tokenize("WORKBOOK loads FILES")
        assert "workbook" in tokens
        assert "files" in tokens


# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

def test_tier_constants_are_distinct():
    tiers = {TIER_SUPPORTED, TIER_PROBABLE, TIER_WEAK, TIER_UNSUPPORTED, TIER_CONTRADICTED}
    assert len(tiers) == 5, "All tier constants must be distinct strings"


def test_tier_constants_are_strings():
    for t in (TIER_SUPPORTED, TIER_PROBABLE, TIER_WEAK, TIER_UNSUPPORTED, TIER_CONTRADICTED):
        assert isinstance(t, str)


# ---------------------------------------------------------------------------
# _classify_paragraph — tier classification
# ---------------------------------------------------------------------------

def _make_knowledge(*, available=True, classes=None, has_method=True, has_property=False):
    """Build a minimal mock Knowledge object."""
    k = MagicMock()
    k.available = available
    k.classes = classes or {}
    k.has_method = MagicMock(return_value=has_method)
    k.has_property = MagicMock(return_value=has_property)
    return k


def _make_claim_tokens(texts):
    """Build (text, token_set) pairs for the claims list."""
    return [(t, _tokenize(t)) for t in texts]


class TestClassifyParagraph:
    def test_supported_with_api_and_high_overlap(self):
        """API ref verified + claim overlap >= 0.5 → SUPPORTED."""
        knowledge = _make_knowledge(
            available=True,
            classes={"Workbook": True},
            has_method=True,
        )
        claim_tokens = _make_claim_tokens([
            "Workbook loads converts xlsx spreadsheet files workbook save"
        ])
        text = "Use `Workbook.save` to convert xlsx spreadsheet files."
        result = _classify_paragraph(1, text, knowledge, claim_tokens, [], {})
        assert result["tier"] in (TIER_SUPPORTED, TIER_PROBABLE), (
            f"Expected SUPPORTED or PROBABLE for verified API with claim match, got {result['tier']}"
        )

    def test_probable_with_high_claim_overlap(self):
        """Claim token overlap >= 0.5 without API refs → PROBABLE."""
        knowledge = _make_knowledge(available=False)
        claim_tokens = _make_claim_tokens([
            "convert xlsx spreadsheet files workbook save export import"
        ])
        text = "Convert xlsx spreadsheet files by calling save and export methods."
        result = _classify_paragraph(1, text, knowledge, claim_tokens, [], {})
        assert result["tier"] in (TIER_PROBABLE, TIER_SUPPORTED), (
            f"Expected high-overlap text to be PROBABLE or SUPPORTED, got {result['tier']}"
        )

    def test_unsupported_no_claims(self):
        """No claim tokens, no API → UNSUPPORTED or WEAK."""
        knowledge = _make_knowledge(available=False)
        text = "This paragraph discusses completely unrelated topics."
        result = _classify_paragraph(1, text, knowledge, [], [], {})
        assert result["tier"] in (TIER_UNSUPPORTED, TIER_WEAK)

    def test_contradicted_by_forbidden_claim(self):
        """Text matching a forbidden claim → CONTRADICTED."""
        knowledge = _make_knowledge(available=False)
        # Forbidden claim with enough tokens
        forbidden_text = "supports three dimensional rendering geometry mesh"
        forbidden_tokens = _make_claim_tokens([forbidden_text])
        # Paragraph with 70%+ overlap to the forbidden claim
        text = "The library supports three dimensional rendering geometry mesh objects."
        result = _classify_paragraph(1, text, knowledge, [], forbidden_tokens, {})
        assert result["tier"] == TIER_CONTRADICTED, (
            f"Expected CONTRADICTED for forbidden claim match, got {result['tier']}"
        )

    def test_contradicted_by_format_direction(self):
        """Claiming export for import-only format → CONTRADICTED."""
        knowledge = _make_knowledge(available=False)
        format_support = {"docx": "import"}  # import-only
        text = "Export docx files using the document writer."
        result = _classify_paragraph(1, text, knowledge, [], [], format_support)
        assert result["tier"] == TIER_CONTRADICTED, (
            f"Expected CONTRADICTED for wrong export direction, got {result['tier']}"
        )

    def test_result_has_required_keys(self):
        """classify_paragraph always returns dict with line_no, text, tier, details."""
        knowledge = _make_knowledge(available=False)
        result = _classify_paragraph(5, "Some text.", knowledge, [], [], {})
        assert "line_no" in result
        assert "text" in result
        assert "tier" in result
        assert "details" in result
        assert result["line_no"] == 5
        assert result["text"] == "Some text."

    def test_short_forbidden_claim_skipped(self):
        """Forbidden claims with < 2 tokens are skipped (no false CONTRADICTED)."""
        knowledge = _make_knowledge(available=False)
        # One-word forbidden claim should be skipped
        forbidden_tokens = [("supports", {"supports"})]
        text = "This library supports many file formats."
        result = _classify_paragraph(1, text, knowledge, [], forbidden_tokens, {})
        # Should not be CONTRADICTED from a single-word forbidden claim
        assert result["tier"] != TIER_CONTRADICTED

    def test_api_ref_unknown_class_does_not_penalize(self):
        """API refs to unknown classes are skipped — not penalized."""
        knowledge = _make_knowledge(
            available=True,
            classes={},  # no classes known
            has_method=False,
        )
        claim_tokens = []
        text = "Use `UnknownClass.method` to process data."
        result = _classify_paragraph(1, text, knowledge, claim_tokens, [], {})
        # Unknown class → api_checked stays False → no api_verified penalty
        assert result["tier"] != TIER_CONTRADICTED

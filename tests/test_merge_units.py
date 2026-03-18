"""Unit tests for pure functions in scripts/merge.py."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from merge import tokenize, token_overlap, find_semantic_match  # noqa: E402


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------

def test_tokenize_returns_set():
    result = tokenize("Hello World")
    assert isinstance(result, set)


def test_tokenize_lowercases():
    result = tokenize("Document Load")
    assert "document" in result
    assert "load" in result
    assert "Document" not in result


def test_tokenize_filters_short_words():
    result = tokenize("a to be the Document")
    assert "document" in result
    # short words (len <= 2) should be excluded
    for word in result:
        assert len(word) > 2


def test_tokenize_empty_string():
    result = tokenize("")
    assert result == set()


def test_tokenize_extracts_words():
    result = tokenize("Document.load loads a file")
    assert "document" in result
    assert "load" in result
    assert "loads" in result
    assert "file" in result


# ---------------------------------------------------------------------------
# token_overlap
# ---------------------------------------------------------------------------

def test_token_overlap_identical():
    score = token_overlap("Document load file", "Document load file")
    assert score == pytest.approx(1.0)


def test_token_overlap_no_match():
    score = token_overlap("Document load", "format convert export")
    assert score == pytest.approx(0.0)


def test_token_overlap_partial():
    score = token_overlap("Document load file path", "Document save file path")
    assert 0.0 < score < 1.0


def test_token_overlap_empty_strings():
    score = token_overlap("", "")
    assert score == pytest.approx(0.0)


def test_token_overlap_symmetric():
    s1 = "Document load file from path"
    s2 = "Document save output to disk"
    assert token_overlap(s1, s2) == token_overlap(s2, s1)


# ---------------------------------------------------------------------------
# find_semantic_match
# ---------------------------------------------------------------------------

def test_find_semantic_match_returns_none_when_no_candidates():
    scout_claim = {
        "kind": "api_method",
        "text": "Document.load loads a file",
    }
    result = find_semantic_match(scout_claim, {}, {})
    assert result is None


def test_find_semantic_match_finds_good_match():
    scout_claim = {
        "kind": "api_method",
        "text": "Document.load loads a file from path",
    }
    ext_claim = {
        "kind": "api",
        "text": "Document.load loads a document from a file path",
    }
    ext_by_kind = {"api": [(0, ext_claim)]}
    ext_class_index = {"Document": [(0, ext_claim)]}

    result = find_semantic_match(scout_claim, ext_by_kind, ext_class_index)
    # Should find a match since texts are semantically similar
    assert result is not None
    idx, claim, score = result
    assert score > 0.0


def test_find_semantic_match_no_match_for_unrelated():
    scout_claim = {
        "kind": "api_method",
        "text": "Document.load loads a file",
    }
    ext_claim = {
        "kind": "api",
        "text": "Format.export writes to disk",
    }
    ext_by_kind = {"api": [(0, ext_claim)]}
    ext_class_index = {}

    # Score should be low — may return None or a low-score match
    result = find_semantic_match(scout_claim, ext_by_kind, ext_class_index)
    if result is not None:
        _, _, score = result
        assert score < 0.8  # should not be a strong match

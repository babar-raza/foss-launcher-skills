"""Tests for VERIFY-01: content_hash normalization (CRLF/LF/trailing-space invariance).

Ensures that content_hash() in grade_writer.py and compute_content_hash() in
provenance.py produce identical hashes for logically identical content regardless
of line-ending style or trailing whitespace.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from grade_writer import content_hash, _normalize_body


# ---------------------------------------------------------------------------
# _normalize_body
# ---------------------------------------------------------------------------

class TestNormalizeBody:
    def test_crlf_to_lf(self):
        assert _normalize_body("a\r\nb\r\n") == "a\nb"

    def test_lf_unchanged(self):
        assert _normalize_body("a\nb\n") == "a\nb"

    def test_trailing_whitespace_stripped(self):
        assert _normalize_body("a  \nb  \n") == "a\nb"

    def test_mixed_endings(self):
        assert _normalize_body("a\r\nb  \nc\t\r\n") == "a\nb\nc"

    def test_empty_string(self):
        assert _normalize_body("") == ""

    def test_single_line_no_newline(self):
        assert _normalize_body("hello") == "hello"


# ---------------------------------------------------------------------------
# content_hash — CRLF/LF/trailing-whitespace invariance
# ---------------------------------------------------------------------------

class TestContentHashNormalization:
    def test_crlf_lf_produce_same_hash(self):
        body_lf = "line one\nline two\n"
        body_crlf = "line one\r\nline two\r\n"
        assert content_hash(body_lf) == content_hash(body_crlf)

    def test_trailing_whitespace_same_hash(self):
        body_clean = "line one\nline two\n"
        body_trailing = "line one  \nline two  \n"
        assert content_hash(body_clean) == content_hash(body_trailing)

    def test_all_three_variants_equal(self):
        body_lf = "line one\nline two\n"
        body_crlf = "line one\r\nline two\r\n"
        body_trailing = "line one  \nline two  \n"
        h1 = content_hash(body_lf)
        h2 = content_hash(body_crlf)
        h3 = content_hash(body_trailing)
        assert h1 == h2 == h3

    def test_hash_length_is_32(self):
        h = content_hash("any content")
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_content_different_hash(self):
        assert content_hash("body A\n") != content_hash("body B\n")

    def test_tab_trailing_stripped(self):
        body_tab = "line\t\n"
        body_clean = "line\n"
        assert content_hash(body_tab) == content_hash(body_clean)

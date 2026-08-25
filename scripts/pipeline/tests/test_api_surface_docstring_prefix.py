"""Tests for extraction/api_surface.py's _strip_string_prefix_and_quotes --
RC-tex-python-04 (MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL).

Regression coverage for a real, live-verified defect found by S-122 blind-spot-audit:
`_extract_doc_comment` used to strip only quote/space/newline characters from a
tree-sitter-captured docstring, which cannot remove a leading Python raw-string
prefix (the lowercase-r-prefixed triple-quote form). The prefix character blocks
.strip() from ever reaching the quote marks that follow, so both the prefix and
the quotes leaked verbatim into every downstream consumer -- confirmed live on
aspose-tex-python's TeXOptions class, whose docstring literally begins with an
r-prefixed triple-quoted string ("Configuration for a TeX processing job.") and
leaked that exact prefix into two generated reference pages.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extraction.api_surface import _strip_string_prefix_and_quotes  # noqa: E402


def test_raw_string_prefix_is_stripped():
    """The exact bug this fix closes: r\"\"\" leaking into the extracted doc."""
    raw = 'r"""Configuration for a TeX processing job.'
    assert _strip_string_prefix_and_quotes(raw) == "Configuration for a TeX processing job."


def test_uppercase_raw_prefix_is_stripped():
    raw = 'R"""Some docstring.'
    assert _strip_string_prefix_and_quotes(raw) == "Some docstring."


def test_plain_triple_quoted_docstring_still_works():
    """Negative control: the common, unprefixed case must be unaffected."""
    raw = '"""A plain docstring."""'
    assert _strip_string_prefix_and_quotes(raw) == "A plain docstring."


def test_single_quoted_docstring_still_works():
    raw = "'A single-quoted docstring.'"
    assert _strip_string_prefix_and_quotes(raw) == "A single-quoted docstring."


def test_raw_prefix_with_single_quotes():
    raw = "r'''Raw with single triple quotes.'''"
    assert _strip_string_prefix_and_quotes(raw) == "Raw with single triple quotes."


def test_empty_string_does_not_raise():
    assert _strip_string_prefix_and_quotes("") == ""

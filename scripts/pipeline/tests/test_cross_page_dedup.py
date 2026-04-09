"""Tests for cross-page deduplication checker."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from content_eval.cross_page.deduplication import (
    _extract_paragraphs,
    _jaccard,
    _tokenize,
    check_deduplication,
)
from content_eval.models import CodeBlock


# ---------------------------------------------------------------------------
# Lightweight stub — avoids full Page.load() / frontmatter parsing
# ---------------------------------------------------------------------------
@dataclass
class _StubPage:
    filepath: Path = Path("stub.md")
    raw_text: str = ""
    frontmatter: dict = field(default_factory=dict)
    body: str = ""
    body_offset: int = 0
    code_blocks: list = field(default_factory=list)
    headings: list = field(default_factory=list)
    links: list = field(default_factory=list)
    prose_lines: list = field(default_factory=list)
    family: str = ""
    platform: str = ""
    subdomain: str = ""
    page_role: str = ""


def _make_page(
    filepath: str,
    prose: str,
    family: str = "words",
    platform: str = "python",
    code_blocks: list | None = None,
) -> _StubPage:
    """Build a stub page with prose_lines derived from *prose*."""
    lines = prose.splitlines()
    prose_lines = [(i + 1, line) for i, line in enumerate(lines)]
    return _StubPage(
        filepath=Path(filepath),
        prose_lines=prose_lines,
        family=family,
        platform=platform,
        code_blocks=code_blocks or [],
    )


# ---------------------------------------------------------------------------
# Tokenizer / Jaccard unit tests
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("Hello world this is a test of tokenization")
        assert "hello" in tokens
        assert "world" in tokens
        assert "tokenization" in tokens
        # Single-char words excluded by regex [a-z][a-z0-9_]+
        assert "a" not in tokens

    def test_empty(self):
        assert _tokenize("") == set()


class TestJaccard:
    def test_identical(self):
        s = {"hello", "world", "test"}
        assert _jaccard(s, s) == 1.0

    def test_disjoint(self):
        assert _jaccard({"aaa", "bbb"}, {"ccc", "ddd"}) == 0.0

    def test_partial(self):
        a = {"hello", "world", "foo"}
        b = {"hello", "world", "bar"}
        # intersection=2, union=4 → 0.5
        assert abs(_jaccard(a, b) - 0.5) < 0.01

    def test_empty_sets(self):
        assert _jaccard(set(), {"hello"}) == 0.0
        assert _jaccard(set(), set()) == 0.0


# ---------------------------------------------------------------------------
# Paragraph extraction
# ---------------------------------------------------------------------------

class TestExtractParagraphs:
    def test_skips_short(self):
        page = _make_page("a.md", "short line only")
        assert _extract_paragraphs(page) == []

    def test_extracts_long_paragraph(self):
        words = " ".join(f"word{i}" for i in range(40))
        page = _make_page("a.md", words)
        paras = _extract_paragraphs(page)
        assert len(paras) == 1
        assert paras[0][0] == 1  # starts at line 1

    def test_skips_code_block_lines(self):
        """Lines inside code blocks should be excluded."""
        prose = " ".join(f"word{i}" for i in range(40))
        page = _make_page(
            "a.md",
            prose,
            code_blocks=[CodeBlock(lang="python", content="x=1", start_line=1, end_line=1)],
        )
        # Line 1 is inside code block → paragraph starts later or is empty
        paras = _extract_paragraphs(page)
        assert len(paras) == 0  # the only line is in a code block


# ---------------------------------------------------------------------------
# check_deduplication() integration tests
# ---------------------------------------------------------------------------

LONG_PARAGRAPH = (
    "This library provides comprehensive support for creating and manipulating "
    "presentation slides including adding shapes text images charts tables and "
    "other visual elements to slides using a simple and intuitive programming "
    "interface that works across multiple platforms and operating systems"
)


class TestCheckDeduplication:
    def test_identical_paragraphs_fail(self):
        """Two pages with identical long paragraph → FAIL finding."""
        pa = _make_page("content/docs/a.md", LONG_PARAGRAPH)
        pb = _make_page("content/docs/b.md", LONG_PARAGRAPH)
        findings = check_deduplication([pa, pb])
        assert len(findings) == 1
        assert findings[0].level == "FAIL"
        assert findings[0].category == "XD"
        assert findings[0].evaluator == "cross_dedup"

    def test_high_overlap_warn(self):
        """~75% word overlap → WARN."""
        words_a = [f"word{i}" for i in range(40)]
        words_b = words_a[:30] + [f"unique{i}" for i in range(10)]
        pa = _make_page("a.md", " ".join(words_a))
        pb = _make_page("b.md", " ".join(words_b))
        findings = check_deduplication([pa, pb])
        # Jaccard = 30/50 = 0.6 — below 0.70 threshold, no finding
        # Adjust to get into WARN range: need ~75% overlap
        # 35 shared out of 45 total → 35/45 ≈ 0.78
        words_b2 = words_a[:35] + [f"unique{i}" for i in range(5)]
        pb2 = _make_page("b.md", " ".join(words_b2))
        findings2 = check_deduplication([pa, pb2])
        assert len(findings2) == 1
        assert findings2[0].level == "WARN"

    def test_different_content_no_finding(self):
        """Completely different paragraphs → no findings."""
        pa = _make_page("a.md", " ".join(f"alpha{i}" for i in range(40)))
        pb = _make_page("b.md", " ".join(f"beta{i}" for i in range(40)))
        findings = check_deduplication([pa, pb])
        assert len(findings) == 0

    def test_short_paragraphs_skipped(self):
        """Paragraphs under 30 words are not compared."""
        short = "a few words only"
        pa = _make_page("a.md", short)
        pb = _make_page("b.md", short)
        findings = check_deduplication([pa, pb])
        assert len(findings) == 0

    def test_different_products_not_compared(self):
        """Pages from different family+platform groups are not compared."""
        pa = _make_page("a.md", LONG_PARAGRAPH, family="words", platform="python")
        pb = _make_page("b.md", LONG_PARAGRAPH, family="slides", platform="java")
        findings = check_deduplication([pa, pb])
        assert len(findings) == 0

    def test_same_page_not_compared(self):
        """Paragraphs within the same page should not trigger findings."""
        double = LONG_PARAGRAPH + "\n\n" + LONG_PARAGRAPH
        pa = _make_page("a.md", double)
        # Only one page — cross-page dedup won't flag same-page duplication
        findings = check_deduplication([pa])
        assert len(findings) == 0

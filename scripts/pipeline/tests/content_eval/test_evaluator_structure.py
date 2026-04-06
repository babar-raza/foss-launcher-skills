"""Unit tests for StructureEvaluator._check_blog_sections (P-07).

Coverage:
- All three required headings present → 0 WARNs
- Each required heading missing individually → 1 WARN each
- All missing → 3 WARNs
- Partial match works (e.g. "Introduction to Aspose.Note" matches "introduction")
- Case-insensitive matching
- Non-blog page_role → _check_blog_sections not called (0 findings from evaluate())

All tests are deterministic — no network, no file I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from content_eval.models import Page, Heading, CodeBlock, Link
from content_eval.evaluators.structure import StructureEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blog_page(headings: list[Heading], frontmatter: dict | None = None) -> Page:
    """Return a minimal Page with page_role='blog' and the given headings."""
    return Page(
        filepath=Path("content/blog.aspose.org/email/cpp/test-post/index.md"),
        raw_text="",
        frontmatter=frontmatter or {"title": "Test", "description": "Test desc"},
        body="placeholder",
        page_role="blog",
        subdomain="blog",
        headings=headings,
    )


def _h2(text: str, line_no: int = 1) -> Heading:
    return Heading(level=2, text=text, line_no=line_no)


# ===========================================================================
# _check_blog_sections
# ===========================================================================

class TestCheckBlogSections:
    ev = StructureEvaluator()

    def test_all_required_headings_present_no_warnings(self):
        page = _blog_page([
            _h2("Introduction"),
            _h2("Quick Start"),
            _h2("Getting Started"),
        ])
        findings = self.ev._check_blog_sections(page)
        assert findings == [], f"Expected no findings, got: {findings}"

    def test_missing_introduction_produces_one_warn(self):
        page = _blog_page([_h2("Quick Start"), _h2("Getting Started")])
        findings = self.ev._check_blog_sections(page)
        assert len(findings) == 1
        assert findings[0].level == "WARN"
        assert "Introduction" in findings[0].message

    def test_missing_quick_start_produces_one_warn(self):
        page = _blog_page([_h2("Introduction"), _h2("Getting Started")])
        findings = self.ev._check_blog_sections(page)
        assert len(findings) == 1
        assert "Quick Start" in findings[0].message

    def test_missing_getting_started_produces_one_warn(self):
        page = _blog_page([_h2("Introduction"), _h2("Quick Start")])
        findings = self.ev._check_blog_sections(page)
        assert len(findings) == 1
        assert "Getting Started" in findings[0].message

    def test_all_missing_produces_three_warnings(self):
        page = _blog_page([_h2("Installation"), _h2("API Reference")])
        findings = self.ev._check_blog_sections(page)
        assert len(findings) == 3
        assert all(f.level == "WARN" for f in findings)

    def test_no_headings_produces_three_warnings(self):
        page = _blog_page([])
        findings = self.ev._check_blog_sections(page)
        assert len(findings) == 3

    def test_partial_match_introduction_passes(self):
        """'Introduction to Aspose.Note' must satisfy the 'introduction' requirement."""
        page = _blog_page([
            _h2("Introduction to Aspose.Note"),
            _h2("Quick Start"),
            _h2("Getting Started Guide"),
        ])
        findings = self.ev._check_blog_sections(page)
        assert findings == []

    def test_case_insensitive_matching(self):
        page = _blog_page([
            _h2("INTRODUCTION"),
            _h2("quick start"),
            _h2("GETTING STARTED"),
        ])
        findings = self.ev._check_blog_sections(page)
        assert findings == []

    def test_h3_headings_do_not_satisfy_requirement(self):
        """Only H2 headings count; H3 'Introduction' must not satisfy the requirement."""
        page = _blog_page([
            Heading(level=3, text="Introduction", line_no=5),
            _h2("Quick Start"),
            _h2("Getting Started"),
        ])
        findings = self.ev._check_blog_sections(page)
        assert len(findings) == 1
        assert "Introduction" in findings[0].message


# ===========================================================================
# evaluate() — non-blog page must not call _check_blog_sections
# ===========================================================================

class TestEvaluateNonBlog:
    ev = StructureEvaluator()

    def test_non_blog_page_no_section_warnings(self):
        """A docs page with no headings must not produce section-related WARNs."""
        page = Page(
            filepath=Path("content/docs.aspose.org/en/email/cpp/reading-msg.md"),
            raw_text="---\ntitle: Reading MSG\ndescription: Desc.\n---\n\nContent.\n",
            frontmatter={"title": "Reading MSG", "description": "Desc."},
            body="Content.\n",
            page_role="docs",
            subdomain="docs",
            headings=[],
        )
        findings = self.ev.evaluate(page, knowledge=None)
        section_warns = [f for f in findings if "section" in f.message.lower()]
        assert section_warns == []

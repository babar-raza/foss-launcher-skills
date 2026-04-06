"""Unit tests for PageRoleEvaluator._check_blog — author FAIL upgrade (P-02).

Coverage:
- author correct ('Aspose') → 0 author-related findings
- author absent → 1 WARN (fixable; author may be forgotten)
- author present but wrong value → 1 FAIL (signals off-skill generation)
- author empty string → 1 FAIL (present but not 'Aspose')

All tests are deterministic — no network, no file I/O.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from content_eval.models import Page
from content_eval.evaluators.page_role import PageRoleEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blog_page(frontmatter: dict) -> Page:
    """Return a minimal blog Page with the given frontmatter."""
    return Page(
        filepath=Path("content/blog.aspose.org/email/cpp/test-post/index.md"),
        raw_text="",
        frontmatter=frontmatter,
        body="Some content with code.\n```python\nprint('hello')\n```\n",
        page_role="blog",
        subdomain="blog",
    )


def _author_findings(frontmatter: dict) -> list:
    """Run _check_blog and return only author-related findings."""
    ev = PageRoleEvaluator()
    page = _blog_page(frontmatter)
    findings = ev._check_blog(page)
    return [f for f in findings if "author" in f.message.lower()]


# ===========================================================================
# _check_blog — author field
# ===========================================================================

class TestCheckBlogAuthor:
    def test_correct_author_no_author_finding(self):
        findings = _author_findings({"author": "Aspose", "categories": ["Aspose.Email"]})
        assert findings == [], f"Correct author should produce no findings, got: {findings}"

    def test_missing_author_produces_warn(self):
        findings = _author_findings({"categories": ["Aspose.Email"]})
        assert len(findings) == 1
        assert findings[0].level == "WARN", (
            f"Missing author should be WARN (fixable), got level={findings[0].level}"
        )

    def test_wrong_author_string_produces_fail(self):
        findings = _author_findings({"author": "Babar Raza", "categories": ["Aspose.Email"]})
        assert len(findings) == 1
        assert findings[0].level == "FAIL", (
            f"Wrong author value should be FAIL, got level={findings[0].level}"
        )
        assert "Babar Raza" in findings[0].message

    def test_empty_string_author_produces_warn(self):
        """Empty string is falsy → treated as missing → WARN (not FAIL)."""
        findings = _author_findings({"author": "", "categories": ["Aspose.Email"]})
        # `if not author` catches empty string → same branch as absent → WARN
        assert len(findings) == 1
        assert findings[0].level == "WARN", (
            "Empty string author is falsy — treated as missing → WARN"
        )

    def test_author_with_leading_trailing_spaces_fails(self):
        """'  Aspose  ' strips to 'Aspose' → should NOT fail."""
        findings = _author_findings({"author": "  Aspose  ", "categories": ["Aspose.Email"]})
        assert findings == [], "Whitespace-padded 'Aspose' should pass after strip"

    def test_author_wrong_case_fails(self):
        """'aspose' (lowercase) != 'Aspose' → FAIL."""
        findings = _author_findings({"author": "aspose", "categories": ["Aspose.Email"]})
        assert len(findings) == 1
        assert findings[0].level == "FAIL"

    def test_author_none_value_produces_warn(self):
        """Explicit null/None in YAML is falsy → WARN (missing), not FAIL."""
        findings = _author_findings({"author": None, "categories": ["Aspose.Email"]})
        assert len(findings) == 1
        assert findings[0].level == "WARN"


# ===========================================================================
# Regression: WARN/FAIL distinction
# ===========================================================================

class TestAuthorWarnFailDistinction:
    """
    Key invariant from P-02:
    - WARN = author absent (fixable, possibly just forgotten)
    - FAIL = author present but wrong (signals off-skill generation path)
    These must never be swapped.
    """

    def test_missing_is_warn_not_fail(self):
        findings = _author_findings({})
        assert findings[0].level != "FAIL", "Missing author must be WARN, not FAIL"

    def test_wrong_value_is_fail_not_warn(self):
        findings = _author_findings({"author": "John Doe"})
        assert findings[0].level != "WARN", "Wrong author value must be FAIL, not WARN"

"""Tests for locale-filtering logic in simulate_pr_checks.sh.

SR-08: Verify that the EVAL_FILES construction correctly filters locale
content paths (content/(docs|kb).aspose.org/{non-en}/) from the strict
content eval step (TC-05) to prevent false harness failures.

These tests validate the filtering logic by importing a pure-Python
equivalent that mirrors the bash EVAL_FILES construction.
"""

from __future__ import annotations

import re

import pytest


# ---------------------------------------------------------------------------
# Python mirror of the bash EVAL_FILES filter in simulate_pr_checks.sh
# ---------------------------------------------------------------------------

_LOCALE_PATH_RE = re.compile(
    r"^content/(?:docs|kb)\.aspose\.org/([a-z]{2})/"
)


def _build_eval_files(changed_files: list[str]) -> list[str]:
    """Mirror of the EVAL_FILES bash logic in simulate_pr_checks.sh.

    Keeps:
      - All paths NOT under content/(docs|kb).aspose.org/{2-letter}/
      - English paths: content/(docs|kb).aspose.org/en/...

    Excludes:
      - Locale paths: content/(docs|kb).aspose.org/{non-en 2-letter}/...
    """
    result = []
    for f in changed_files:
        m = _LOCALE_PATH_RE.match(f)
        if m:
            if m.group(1) == "en":
                result.append(f)
        else:
            result.append(f)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvalFilesLocaleFilter:
    """EVAL_FILES construction filters locale paths from TC-05."""

    def test_english_docs_kept(self):
        files = ["content/docs.aspose.org/en/note/python/guide.md"]
        assert _build_eval_files(files) == files

    def test_english_kb_kept(self):
        files = ["content/kb.aspose.org/en/slides/java/faq.md"]
        assert _build_eval_files(files) == files

    def test_locale_docs_excluded(self):
        files = ["content/docs.aspose.org/ar/3d/net/scene-graph.md"]
        assert _build_eval_files(files) == []

    def test_locale_kb_excluded(self):
        files = ["content/kb.aspose.org/de/cells/java/faq.md"]
        assert _build_eval_files(files) == []

    def test_locale_many_excluded(self):
        locales = ["ar", "bg", "ca", "cs", "da", "de", "el", "es", "fr", "ja", "zh"]
        files = [f"content/docs.aspose.org/{lc}/3d/net/guide.md" for lc in locales]
        assert _build_eval_files(files) == []

    def test_blog_not_filtered(self):
        files = ["content/blog.aspose.org/note/python/extract-text/index.md"]
        assert _build_eval_files(files) == files

    def test_reference_not_filtered(self):
        files = ["content/reference.aspose.org/en/3d/typescript/VertexElement.md"]
        assert _build_eval_files(files) == files

    def test_products_not_filtered(self):
        files = ["content/products.aspose.org/en/note/python/_index.md"]
        assert _build_eval_files(files) == files

    def test_mixed_list_filters_only_locale(self):
        files = [
            "content/docs.aspose.org/en/note/python/guide.md",       # keep
            "content/docs.aspose.org/ar/note/python/guide.md",       # drop
            "content/kb.aspose.org/en/slides/java/faq.md",           # keep
            "content/kb.aspose.org/de/slides/java/faq.md",           # drop
            "content/blog.aspose.org/note/python/post/index.md",     # keep
            "content/reference.aspose.org/en/note/python/doc.md",    # keep
            "scripts/pipeline/content_eval/runner.py",                # keep (non-content)
        ]
        expected = [
            "content/docs.aspose.org/en/note/python/guide.md",
            "content/kb.aspose.org/en/slides/java/faq.md",
            "content/blog.aspose.org/note/python/post/index.md",
            "content/reference.aspose.org/en/note/python/doc.md",
            "scripts/pipeline/content_eval/runner.py",
        ]
        assert _build_eval_files(files) == expected

    def test_empty_list(self):
        assert _build_eval_files([]) == []

    def test_all_english_no_filtering(self):
        files = [
            "content/docs.aspose.org/en/3d/net/guide.md",
            "content/kb.aspose.org/en/3d/net/faq.md",
        ]
        assert _build_eval_files(files) == files

    def test_no_content_prefix_not_filtered(self):
        """Non-content paths pass through unchanged."""
        files = [
            "scripts/ci/simulate_pr_checks.sh",
            "scripts/pipeline/content_eval/runner.py",
        ]
        assert _build_eval_files(files) == files

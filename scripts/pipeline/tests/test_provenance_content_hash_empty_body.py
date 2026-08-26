"""Regression tests for provenance.compute_content_hash's empty-body fallback --
RC-tex-python-07 (MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL, found by
independent adversarial review of Batch 1's healing work).

Bug: whole-frontmatter page types (e.g. products.aspose.org "plugin" layout
pages -- all real content lives inside the frontmatter YAML, no body markdown
at all) always hashed to the same constant value, since only the (always
empty) body was ever hashed. Confirmed live: content/products.aspose.org's
tex/python page had an identical content_hash before and after a real content
edit that changed the plugin_description, overview, and content.block[] text.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.provenance import compute_content_hash


def _tmp_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


class TestEmptyBodyContentHash:
    def test_whole_frontmatter_page_changes_hash_on_real_edit(self):
        """The exact regression: a plugin-layout page with no body at all must
        produce a DIFFERENT hash when its frontmatter content changes."""
        page_a = _tmp_md("""\
            ---
            layout: plugin
            plugin_description: Original description.
            overview:
              content: Original overview text.
            ---
        """)
        page_b = _tmp_md("""\
            ---
            layout: plugin
            plugin_description: Completely different description.
            overview:
              content: Completely different overview text.
            ---
        """)
        try:
            hash_a = compute_content_hash(page_a)
            hash_b = compute_content_hash(page_b)
            assert hash_a != hash_b, (
                "Two whole-frontmatter pages with different content produced the "
                "same hash -- the empty-body fallback did not activate."
            )
            assert hash_a and hash_b, "Hashes must not be empty strings."
        finally:
            page_a.unlink()
            page_b.unlink()

    def test_whole_frontmatter_page_same_content_same_hash(self):
        """Determinism: identical whole-frontmatter content must hash identically."""
        content = """\
            ---
            layout: plugin
            plugin_description: Some description.
            ---
        """
        page_a = _tmp_md(content)
        page_b = _tmp_md(content)
        try:
            assert compute_content_hash(page_a) == compute_content_hash(page_b)
        finally:
            page_a.unlink()
            page_b.unlink()

    def test_normal_body_page_unaffected_by_fallback(self):
        """Negative control: a page WITH real body content must be completely
        unaffected by the fallback -- hash is still purely body-derived, and
        two pages with identical bodies but different frontmatter must still
        hash identically (the existing, unchanged contract)."""
        page_a = _tmp_md("""\
            ---
            title: Page A
            ---

            Shared body text.
        """)
        page_b = _tmp_md("""\
            ---
            title: Page B (completely different frontmatter)
            ---

            Shared body text.
        """)
        try:
            assert compute_content_hash(page_a) == compute_content_hash(page_b), (
                "Pages with real, identical body content must hash identically "
                "regardless of frontmatter differences -- the fallback must not "
                "activate when a real body is present."
            )
        finally:
            page_a.unlink()
            page_b.unlink()

    def test_no_frontmatter_at_all_still_works(self):
        """A file with no frontmatter fence at all must not crash -- body is the
        whole file, matching pre-existing behavior."""
        page = _tmp_md("Just plain text, no frontmatter.\n")
        try:
            result = compute_content_hash(page)
            assert result and len(result) == 32
        finally:
            page.unlink()

    def test_whitespace_only_body_treated_as_empty(self):
        """A body of only blank lines must still trigger the frontmatter
        fallback, not hash to a whitespace-derived constant."""
        page_a = _tmp_md("""\
            ---
            plugin_description: First.
            ---


        """)
        page_b = _tmp_md("""\
            ---
            plugin_description: Second.
            ---


        """)
        try:
            assert compute_content_hash(page_a) != compute_content_hash(page_b)
        finally:
            page_a.unlink()
            page_b.unlink()

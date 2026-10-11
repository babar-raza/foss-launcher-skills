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


class TestContentHashSelfReferenceConvergence:
    """Found live 2026-08-27 committing a real products.aspose.org page: the
    whole-frontmatter fallback (above) hashes `fm.group(2)` verbatim, which
    includes the page's OWN `content_hash:` line -- self-referential. Writing
    a freshly-computed hash into the frontmatter changes the frontmatter text,
    which changes the computed hash again on the next check, forever. Every
    `provenance_normalize_hash.py --apply` run reported the file freshly
    "stale" no matter how many times it was re-run, permanently blocking any
    whole-frontmatter page's commit once it needed a genuine content_hash
    update. Fixed by stripping the content_hash line itself before hashing.
    """

    def test_writing_the_computed_hash_back_produces_a_stable_fixed_point(self):
        """The exact regression: compute a hash, write it into the file's own
        content_hash field, then recompute -- the second computation must
        equal the first (a real fixed point), not a third, different value."""
        page = _tmp_md("""\
            ---
            layout: plugin
            plugin_description: Some real content that needs a hash.
            provenance:
              content_hash: 00000000000000000000000000000000
            ---
        """)
        try:
            first = compute_content_hash(page)
            # Simulate provenance_normalize_hash.py --apply writing `first`
            # into the file's own content_hash field.
            text = page.read_text(encoding="utf-8")
            text = text.replace(
                "content_hash: 00000000000000000000000000000000",
                f"content_hash: {first}",
            )
            page.write_text(text, encoding="utf-8")

            second = compute_content_hash(page)
            assert second == first, (
                f"Hash changed after writing itself back into the file "
                f"({first!r} -> {second!r}) -- self-referential, no fixed point."
            )

            # A third computation (nothing changed since the second write)
            # must also match -- true convergence, not accidental one-step luck.
            third = compute_content_hash(page)
            assert third == second
        finally:
            page.unlink()

    def test_two_different_content_hash_seed_values_converge_to_the_same_result(self):
        """Regardless of what stale content_hash value is already sitting in
        the file when compute_content_hash runs, the fallback must ignore it
        -- two files differing ONLY in their pre-existing (soon-to-be-
        overwritten) content_hash value must hash identically."""
        page_a = _tmp_md("""\
            ---
            layout: plugin
            plugin_description: Same real content.
            provenance:
              content_hash: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
            ---
        """)
        page_b = _tmp_md("""\
            ---
            layout: plugin
            plugin_description: Same real content.
            provenance:
              content_hash: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
            ---
        """)
        try:
            assert compute_content_hash(page_a) == compute_content_hash(page_b)
        finally:
            page_a.unlink()
            page_b.unlink()

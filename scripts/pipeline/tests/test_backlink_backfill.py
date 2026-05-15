"""test_backlink_backfill.py — Regression tests for backlink_backfill.py.

Focus: FU-4 — verify that target_type="family" and target_type="platform" produce
the correct anchor text, preventing the bug class where a family-fallback URL was
paired with a platform-level anchor (e.g., "for Python" on a family URL).

Tests cover:
- _build_see_also_entry: family/platform anchor rules
- _apply_overview_template: family/platform anchor rules for products YAML
- backfill_markdown: idempotency, section insertion, family-anchor rule end-to-end
- font/python family-fallback scenario (confirmed-404 platform -> family URL)
- reference family URL never produces "for Python / .NET / Java"
- URL and anchor both derive from the same resolution record (no stale reuse)

Run:
    python -m pytest scripts/pipeline/tests/test_backlink_backfill.py -v
"""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

import pytest

# Adjust path so commands/ops/ and lib/ are importable
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

import commands.ops.backlink_backfill as _bbm
from commands.ops.backlink_backfill import (
    _build_see_also_entry,
    _apply_overview_template,
    backfill_markdown,
)

# ── Shared fixtures ──────────────────────────────────────────────────────────

FAMILIES_MAP = {
    "words": "Aspose.Words",
    "cells": "Aspose.Cells",
    "font": "Aspose.Font",
    "3d": "Aspose.3D",
    "slides": "Aspose.Slides",
}

PLATFORMS_MAP = {
    "python": "Python",
    "net": ".NET",
    "java": "Java",
    "cpp": "C++",
    "typescript": "TypeScript",
}

# ── _build_see_also_entry ────────────────────────────────────────────────────


class TestBuildSeeAlsoEntry:
    """Unit tests for the See Also entry builder.

    The FAMILY-ANCHOR rule: when target_type == "family", the anchor must never
    include "for {Platform}" even if platform is present in the source metadata.
    """

    def test_family_target_type_omits_platform(self):
        """target_type='family' must not include 'for Python' in anchor."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/font/",
            family="font",
            platform="python",
            subdomain="blog.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "for Python" not in entry
        assert "for python" not in entry.lower()
        assert "Aspose.Font" in entry
        assert "https://products.aspose.com/font/" in entry

    def test_platform_target_type_includes_platform(self):
        """target_type='platform' must include 'for Python' in anchor."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/words/python/",
            family="words",
            platform="python",
            subdomain="docs.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "for Python" in entry
        assert "Aspose.Words" in entry
        assert "https://products.aspose.com/words/python/" in entry

    def test_family_target_type_omits_net(self):
        """target_type='family' must not include '.NET' even for net platform."""
        entry = _build_see_also_entry(
            target_url="https://reference.aspose.com/3d/",
            family="3d",
            platform="net",
            subdomain="reference.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "for .NET" not in entry
        assert "for net" not in entry.lower()
        assert "Aspose.3D" in entry

    def test_family_target_type_omits_java(self):
        """target_type='family' must not include 'for Java' even for java platform."""
        entry = _build_see_also_entry(
            target_url="https://reference.aspose.com/cells/",
            family="cells",
            platform="java",
            subdomain="reference.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "for Java" not in entry
        assert "Aspose.Cells" in entry

    def test_none_target_type_and_no_platform_is_family_anchor(self):
        """With no platform, anchor must always be family-level."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/words/",
            family="words",
            platform=None,
            subdomain="products.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type=None,
        )
        # No "for X" suffix at all
        assert not re.search(r'for (?:Python|\.NET|Java|C\+\+|TypeScript)', entry)
        assert "Aspose.Words" in entry

    def test_platform_target_net_produces_correct_anchor(self):
        """target_type='platform' with net must produce 'for .NET'."""
        entry = _build_see_also_entry(
            target_url="https://docs.aspose.com/slides/net/",
            family="slides",
            platform="net",
            subdomain="docs.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "for .NET" in entry
        assert "Aspose.Slides" in entry

    def test_entry_contains_commercial_edition_suffix(self):
        """The entry must always end with '-- Commercial Edition'."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/font/",
            family="font",
            platform="python",
            subdomain="blog.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "Commercial Edition" in entry

    def test_url_and_anchor_are_consistent(self):
        """The URL in the entry must match the target_url passed in.

        Guards against stale URL reuse: anchor and URL must both come from the
        same resolved target, never from a prior resolution.
        """
        platform_url = "https://products.aspose.com/words/python/"
        family_url = "https://products.aspose.com/words/"

        platform_entry = _build_see_also_entry(
            platform_url, "words", "python", "docs.aspose.org",
            FAMILIES_MAP, PLATFORMS_MAP, target_type="platform",
        )
        family_entry = _build_see_also_entry(
            family_url, "words", "python", "docs.aspose.org",
            FAMILIES_MAP, PLATFORMS_MAP, target_type="family",
        )

        # Platform entry: URL is platform URL, anchor includes "for Python"
        assert platform_url in platform_entry
        assert "for Python" in platform_entry

        # Family entry: URL is family URL, anchor does NOT include "for Python"
        assert family_url in family_entry
        assert "for Python" not in family_entry

        # Cross-check: platform URL must not appear in family entry
        # (check as full URL token followed by ) delimiter)
        assert f"({platform_url})" not in family_entry
        # Family-only URL must not appear as a standalone link target in platform entry
        # (platform URL is "words/python/", family is "words/" -- need exact match check)
        assert f"({family_url})" not in platform_entry


# ── Font/python family-fallback scenario ─────────────────────────────────────


class TestFontPythonFamilyFallback:
    """Regression: products.aspose.com/font/python/ is a confirmed 404.

    The resolver falls back to the family URL https://products.aspose.com/font/
    with chosen_type='family'. The anchor must be 'Aspose.Font -- Commercial Edition',
    not 'Aspose.Font for Python -- Commercial Edition'.
    """

    FAMILY_URL = "https://products.aspose.com/font/"

    def test_family_fallback_anchor_is_family_only(self):
        """When font/python resolves to family URL, anchor must not include 'for Python'."""
        entry = _build_see_also_entry(
            target_url=self.FAMILY_URL,
            family="font",
            platform="python",  # source has python platform...
            subdomain="blog.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",  # ...but target is family-level
        )
        assert "for Python" not in entry
        assert "Aspose.Font" in entry
        assert self.FAMILY_URL in entry

    def test_family_fallback_url_is_family_url(self):
        """The URL in the entry must be the family URL, not any platform URL."""
        entry = _build_see_also_entry(
            target_url=self.FAMILY_URL,
            family="font",
            platform="python",
            subdomain="blog.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        # Must contain the family URL
        assert "products.aspose.com/font/" in entry
        # Must NOT contain any platform URL pattern
        assert "products.aspose.com/font/python" not in entry


# ── Reference family URL anchor rule ─────────────────────────────────────────


class TestReferenceAnchorRule:
    """Reference pages: when target is reference.aspose.com/{family}/ (family-level),
    anchor must not include 'for Python', 'for .NET', 'for Java', 'for TypeScript'
    regardless of source platform.
    """

    @pytest.mark.parametrize("platform,display_name", [
        ("python", "Python"),
        ("net", ".NET"),
        ("java", "Java"),
        ("typescript", "TypeScript"),
        ("cpp", "C++"),
    ])
    def test_reference_family_url_no_platform_in_anchor(self, platform, display_name):
        """reference.aspose.com/{family}/ target with family target_type: no 'for X' in anchor."""
        entry = _build_see_also_entry(
            target_url="https://reference.aspose.com/3d/",
            family="3d",
            platform=platform,
            subdomain="reference.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert f"for {display_name}" not in entry, (
            f"Family-URL reference anchor must not contain 'for {display_name}'"
        )

    def test_reference_platform_url_includes_platform(self):
        """reference.aspose.com/{family}/{platform}/ target: anchor must include platform."""
        entry = _build_see_also_entry(
            target_url="https://reference.aspose.com/3d/net/",
            family="3d",
            platform="net",
            subdomain="reference.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "for .NET" in entry


# ── _apply_overview_template ──────────────────────────────────────────────────


class TestApplyOverviewTemplate:
    """Tests for the products YAML overview template generator.

    Same FAMILY-ANCHOR rule applies: target_type='family' must omit platform.
    """

    def test_family_target_type_omits_platform_in_overview(self):
        """target_type='family' must not produce 'for Python' in overview sentence."""
        content = (
            "Aspose.Font FOSS is an open-source font manipulation library. "
            "It is MIT-licensed and fully open-source on GitHub."
        )
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/font/",
            family="font",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "for Python" not in result
        assert "Aspose.Font" in result
        assert "https://products.aspose.com/font/" in result
        # Original content must be preserved
        assert "MIT-licensed" in result

    def test_platform_target_type_includes_platform_in_overview(self):
        """target_type='platform' must produce 'for Python' in overview sentence."""
        content = (
            "Aspose.Words FOSS is a document conversion library. "
            "It is MIT-licensed and available on GitHub."
        )
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/words/python/",
            family="words",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "for Python" in result
        assert "Aspose.Words" in result
        assert "https://products.aspose.com/words/python/" in result

    def test_family_page_no_platform(self):
        """Family page (no platform) must always use family-only anchor."""
        content = "Aspose.Words FOSS provides open-source document processing. MIT-licensed."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/words/",
            family="words",
            platform=None,
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type=None,
        )
        # No "for <Platform>" pattern
        assert not re.search(r'for (?:Python|\.NET|Java|C\+\+|TypeScript)', result)
        assert "products.aspose.com/words/" in result

    def test_original_content_retained_after_insert(self):
        """Original content must survive the template insertion (>= 80% retention)."""
        content = (
            "Aspose.Cells FOSS provides spreadsheet reading and writing. "
            "Read Excel, CSV, and ODS files. Write formula results to JSON. "
            "It is MIT-licensed and open on GitHub."
        )
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/cells/python/",
            family="cells",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        # Original sentences should all still be present
        assert "spreadsheet reading and writing" in result
        assert "MIT-licensed" in result


# ── backfill_markdown idempotency ─────────────────────────────────────────────


class TestBackfillMarkdownIdempotency:
    """backfill_markdown must not double-insert a backlink that already exists.

    backfill_markdown calls file_path.relative_to(_REPO_ROOT) internally.
    We patch the module-level _REPO_ROOT to tmp_path so temp files resolve correctly.
    """

    def _make_file(self, tmp_path: Path, body: str) -> Path:
        f = tmp_path / "page.md"
        fm = "---\ntitle: Test Page\nfamily: words\nplatform: python\n---\n"
        f.write_text(fm + body, encoding="utf-8")
        return f

    @pytest.fixture(autouse=True)
    def patch_repo_root(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_bbm, "_REPO_ROOT", tmp_path)

    def test_idempotent_when_url_already_present(self, tmp_path):
        """No second See Also entry if the target URL is already in the body."""
        body = textwrap.dedent("""\
            Some content here.

            ## See Also

            - [Aspose.Words for Python -- Commercial Edition](https://products.aspose.com/words/python/)
        """)
        f = self._make_file(tmp_path, body)
        change = backfill_markdown(
            file_path=f,
            target_url="https://products.aspose.com/words/python/",
            family="words",
            platform="python",
            subdomain="docs.aspose.org",
            page_type="docs-article",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            dry_run=True,
            target_type="platform",
        )
        assert change.skipped is True
        assert "Already" in change.skip_reason or "idempotent" in change.skip_reason.lower()

    def test_inserts_see_also_when_missing(self, tmp_path):
        """See Also section is added when not present."""
        body = "Some content here about Aspose.Words FOSS.\n"
        f = self._make_file(tmp_path, body)
        change = backfill_markdown(
            file_path=f,
            target_url="https://products.aspose.com/words/python/",
            family="words",
            platform="python",
            subdomain="docs.aspose.org",
            page_type="docs-article",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            dry_run=True,
            target_type="platform",
        )
        assert change.skipped is False
        assert "See Also" in change.after_snippet or "Commercial Edition" in change.after_snippet

    def test_second_run_is_idempotent_after_write(self, tmp_path):
        """Running backfill_markdown twice (write=True then dry_run=True) skips on second run."""
        body = "Content about Aspose.Words FOSS. It is MIT-licensed.\n"
        f = self._make_file(tmp_path, body)
        url = "https://products.aspose.com/words/python/"

        # First run: write
        backfill_markdown(
            file_path=f, target_url=url, family="words", platform="python",
            subdomain="docs.aspose.org", page_type="docs-article",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            dry_run=False, target_type="platform",
        )
        # Second run: should skip
        change2 = backfill_markdown(
            file_path=f, target_url=url, family="words", platform="python",
            subdomain="docs.aspose.org", page_type="docs-article",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            dry_run=True, target_type="platform",
        )
        assert change2.skipped is True

    def test_family_target_type_produces_family_anchor_in_written_file(self, tmp_path):
        """End-to-end: written file must contain family-level anchor, not 'for Python'."""
        body = "Content about Aspose.Font FOSS. MIT-licensed.\n"
        f = self._make_file(tmp_path, body)
        url = "https://products.aspose.com/font/"

        backfill_markdown(
            file_path=f, target_url=url, family="font", platform="python",
            subdomain="blog.aspose.org", page_type="blog-post",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            dry_run=False, target_type="family",
        )

        written = f.read_text(encoding="utf-8")
        assert "for Python" not in written
        assert "Aspose.Font" in written
        assert url in written


# ── No independent URL construction ──────────────────────────────────────────


class TestNoIndependentUrlConstruction:
    """Guard: the URL in the final entry must always come from the target_url
    argument, never be constructed independently from family/platform strings.

    This ensures that even if platform aliases differ, the exact resolved URL
    (which was HTTP-verified) is what gets inserted.
    """

    def test_custom_target_url_is_preserved_verbatim(self):
        """The exact target_url passed in must appear verbatim in the entry."""
        custom_url = "https://reference.aspose.com/3d/"
        entry = _build_see_also_entry(
            target_url=custom_url,
            family="3d",
            platform="net",
            subdomain="reference.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert custom_url in entry, (
            f"Expected verbatim URL '{custom_url}' in entry, got: {entry!r}"
        )
        # No independently-constructed platform URL
        assert "reference.aspose.com/3d/net" not in entry

    def test_family_url_not_reconstructed_as_platform_url(self):
        """When target_url is a family URL, no platform segment must be appended."""
        family_url = "https://products.aspose.com/cells/"
        entry = _build_see_also_entry(
            target_url=family_url,
            family="cells",
            platform="java",
            subdomain="docs.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "products.aspose.com/cells/java" not in entry
        assert family_url in entry

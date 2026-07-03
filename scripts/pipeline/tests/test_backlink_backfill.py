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
from lib.backlink_targets import build_enterprise_anchor_suffix

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

    def test_entry_contains_enterprise_product_family_suffix(self):
        """The entry must use 'Enterprise Product Family' suffix for family-type targets."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/font/",
            family="font",
            platform="python",
            subdomain="blog.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "Enterprise Product Family" in entry
        assert "Commercial Edition" not in entry

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
    with chosen_type='family'. The anchor must be 'Aspose.Font -- Enterprise Product Family',
    not 'Aspose.Font for Python -- Enterprise Product'.
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

    def test_family_fallback_uses_enterprise_product_family_anchor(self):
        """When platform source falls back to family URL (target_type='family'),
        the overview sentence must use 'Enterprise Product Family', not 'Enterprise Product'.

        Regression guard for: _apply_overview_template previously selected P-4 (platform
        template) whenever platform was truthy, even with target_type='family'.
        """
        content = "Aspose.Font FOSS."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/font/",
            family="font",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "Enterprise Product Family" in result
        assert "Enterprise Product" in result  # substring is fine
        assert "for Python" not in result
        assert "Commercial" not in result

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

            - [Aspose.Words for Python -- Enterprise Product](https://products.aspose.com/words/python/)
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
        assert "See Also" in change.after_snippet or "Enterprise Product" in change.after_snippet

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


# ── Dead code removal guard ───────────────────────────────────────────────────


class TestDeadCodeRemoved:
    """Guard: _get_link_sentence was dead code with a broken fallback path.

    It was removed in the Backlink QA Sprint (BQA-SYS-2). This test ensures it
    stays removed and is not accidentally re-introduced by future refactoring.
    """

    def test_get_link_sentence_does_not_exist(self):
        """_get_link_sentence must NOT be a member of the backlink_backfill module."""
        assert not hasattr(_bbm, "_get_link_sentence"), (
            "_get_link_sentence was dead code and has been removed. "
            "Do not re-introduce it — use _apply_overview_template or _build_see_also_entry instead."
        )


# ── Domain-aware anchor suffix (build_enterprise_anchor_suffix) ───────────────


class TestBuildEnterpriseAnchorSuffix:
    """Unit tests for build_enterprise_anchor_suffix in lib/backlink_targets.py.

    Policy:
    - products.aspose.com/family/ → "Enterprise Product Family"
    - products.aspose.com/family/platform/ → "Enterprise Product"
    - docs.aspose.com/* → "Enterprise Documentation"
    - reference.aspose.com/* → "Enterprise API Reference"
    - kb.aspose.com/* → "Enterprise Knowledge Base"
    - Unknown domain → "Enterprise Product" (safe fallback)
    """

    @pytest.mark.parametrize("url,target_type,expected", [
        # products.aspose.com family
        ("https://products.aspose.com/slides/", "family", "Enterprise Product Family"),
        ("https://products.aspose.com/words/", "family", "Enterprise Product Family"),
        # products.aspose.com platform
        ("https://products.aspose.com/slides/net/", "platform", "Enterprise Product"),
        ("https://products.aspose.com/words/python/", "platform", "Enterprise Product"),
        # docs.aspose.com — any path, any target_type → Documentation
        ("https://docs.aspose.com/slides/java/", "platform", "Enterprise Documentation"),
        ("https://docs.aspose.com/slides/net/", "platform", "Enterprise Documentation"),
        ("https://docs.aspose.com/slides/", "family", "Enterprise Documentation"),
        # reference.aspose.com — any path → API Reference
        ("https://reference.aspose.com/slides/net/", "platform", "Enterprise API Reference"),
        ("https://reference.aspose.com/slides/", "family", "Enterprise API Reference"),
        # kb.aspose.com
        ("https://kb.aspose.com/slides/net/", "platform", "Enterprise Knowledge Base"),
    ])
    def test_suffix_by_domain_and_type(self, url, target_type, expected):
        result = build_enterprise_anchor_suffix(url, target_type)
        assert result == expected, (
            f"URL={url!r} target_type={target_type!r}: "
            f"expected {expected!r}, got {result!r}"
        )

    def test_docs_never_enterprise_product_family(self):
        """REGRESSION: docs.aspose.com target must NEVER produce 'Enterprise Product Family'."""
        suffix = build_enterprise_anchor_suffix(
            "https://docs.aspose.com/slides/java/", "family"
        )
        assert suffix != "Enterprise Product Family", (
            "docs.aspose.com target produced 'Enterprise Product Family' — "
            "this was the anchor-target domain mismatch bug. Must be 'Enterprise Documentation'."
        )
        assert suffix == "Enterprise Documentation"

    def test_docs_never_enterprise_product(self):
        """docs.aspose.com platform target must NOT be 'Enterprise Product'."""
        suffix = build_enterprise_anchor_suffix(
            "https://docs.aspose.com/slides/net/", "platform"
        )
        assert suffix == "Enterprise Documentation"
        assert "Product" not in suffix

    def test_products_family_never_enterprise_product(self):
        """products.aspose.com family URL must be 'Enterprise Product Family', not 'Enterprise Product'."""
        suffix = build_enterprise_anchor_suffix(
            "https://products.aspose.com/slides/", "family"
        )
        assert suffix == "Enterprise Product Family"

    def test_unknown_domain_falls_back_to_enterprise_product(self):
        """Unknown domain uses safe fallback 'Enterprise Product'."""
        suffix = build_enterprise_anchor_suffix(
            "https://purchase.aspose.com/buy", "platform"
        )
        assert suffix == "Enterprise Product"


# ── Domain-aware See Also entries ─────────────────────────────────────────────


class TestDomainAwareSeeAlsoEntry:
    """Verify _build_see_also_entry produces correct anchors for each target domain.

    The critical regression: before this fix, docs.aspose.com targets produced
    'Enterprise Product Family' or 'Enterprise Product' anchors — wrong domain.
    """

    def test_docs_target_produces_enterprise_documentation_anchor(self):
        """docs.aspose.com target → 'Enterprise Documentation' in anchor text."""
        entry = _build_see_also_entry(
            target_url="https://docs.aspose.com/slides/java/",
            family="slides",
            platform="java",
            subdomain="docs.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "Enterprise Documentation" in entry
        assert "Enterprise Product" not in entry.replace("Enterprise Documentation", "")
        assert "docs.aspose.com/slides/java/" in entry

    def test_docs_target_never_enterprise_product_family(self):
        """REGRESSION: docs.aspose.com must NEVER produce 'Enterprise Product Family'."""
        entry = _build_see_also_entry(
            target_url="https://docs.aspose.com/slides/java/",
            family="slides",
            platform="java",
            subdomain="docs.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "Enterprise Product Family" not in entry, (
            f"docs.aspose.com entry must not contain 'Enterprise Product Family': {entry!r}"
        )
        assert "Enterprise Documentation" in entry

    def test_reference_platform_produces_api_reference_anchor(self):
        """reference.aspose.com platform target → 'Enterprise API Reference'."""
        entry = _build_see_also_entry(
            target_url="https://reference.aspose.com/slides/net/",
            family="slides",
            platform="net",
            subdomain="reference.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "Enterprise API Reference" in entry
        assert "Enterprise Product" not in entry.replace("Enterprise API Reference", "")

    def test_products_family_target_produces_enterprise_product_family(self):
        """products.aspose.com family target → 'Enterprise Product Family'."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/slides/",
            family="slides",
            platform="java",
            subdomain="products.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "Enterprise Product Family" in entry

    def test_products_platform_target_produces_enterprise_product(self):
        """products.aspose.com platform target → 'Enterprise Product'."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/slides/net/",
            family="slides",
            platform="net",
            subdomain="products.aspose.org",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "Enterprise Product" in entry
        assert "Enterprise Product Family" not in entry


# ── Domain-aware overview template ────────────────────────────────────────────


class TestDomainAwareOverviewTemplate:
    """Verify _apply_overview_template produces correct sentences for each target domain.

    Regression guard for the anchor-target semantic mismatch:
    [Aspose.Slides for Java — Enterprise Product Family](https://docs.aspose.com/slides/java/)
    ↑ anchor says "Enterprise Product Family" but target is docs.aspose.com → wrong
    """

    def test_docs_target_produces_enterprise_documentation_sentence(self):
        """docs.aspose.com target must produce 'Enterprise Documentation' in sentence."""
        content = "Aspose.Slides FOSS for Java is an open-source slides library. MIT-licensed."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://docs.aspose.com/slides/java/",
            family="slides",
            platform="java",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "Enterprise Documentation" in result
        assert "Enterprise Product Family" not in result, (
            "REGRESSION: docs.aspose.com overview must not contain 'Enterprise Product Family'"
        )
        assert "docs.aspose.com/slides/java/" in result

    def test_docs_family_target_never_enterprise_product_family(self):
        """REGRESSION: docs.aspose.com with target_type='family' must NOT produce 'Enterprise Product Family'."""
        content = "Aspose.Slides FOSS."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://docs.aspose.com/slides/java/",
            family="slides",
            platform="java",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "Enterprise Product Family" not in result, (
            f"docs.aspose.com overview must not contain 'Enterprise Product Family': {result!r}"
        )
        assert "Enterprise Documentation" in result

    def test_reference_target_produces_api_reference_sentence(self):
        """reference.aspose.com target must produce 'Enterprise API Reference'."""
        content = "Aspose.Slides FOSS for .NET is a presentation library. MIT-licensed."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://reference.aspose.com/slides/net/",
            family="slides",
            platform="net",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "Enterprise API Reference" in result
        assert "Enterprise Product Family" not in result

    def test_products_family_target_produces_enterprise_product_family_sentence(self):
        """products.aspose.com family target must produce 'Enterprise Product Family'."""
        content = "Aspose.Slides FOSS. MIT-licensed."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/slides/",
            family="slides",
            platform="java",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert "Enterprise Product Family" in result
        assert "docs.aspose.com" not in result

    def test_products_platform_target_produces_enterprise_product_sentence(self):
        """products.aspose.com platform target must produce 'Enterprise Product'."""
        content = (
            "Aspose.Slides FOSS for .NET is a presentation library with extensive format support. "
            "It handles PPTX, PPT, ODP, and more. MIT-licensed and open-source on GitHub."
        )
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/slides/net/",
            family="slides",
            platform="net",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert "Enterprise Product" in result
        assert "Enterprise Product Family" not in result
        assert "products.aspose.com/slides/net/" in result


# ── Em-dash style enforcement ─────────────────────────────────────────────────


class TestEmDashStyleEnforcement:
    """Anchor style consistency: BOTH _apply_overview_template and _build_see_also_entry
    MUST use em-dash (U+2014) between the display name and the Enterprise suffix.

    Canonical style: [Aspose.Slides for Java — Enterprise Documentation](...)
    Forbidden style: [Aspose.Slides for Java Enterprise Documentation](...)

    Style decision: em-dash is canonical (99% of all content links, 3293 vs 30).
    This class enforces the lock across all generation paths.
    """

    EM_DASH = "\u2014"

    def test_overview_template_uses_em_dash_for_products_family(self):
        """_apply_overview_template must use em-dash for products.aspose.com family target."""
        content = "Aspose.Slides FOSS. MIT-licensed."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/slides/",
            family="slides", platform="java",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        assert self.EM_DASH in result, (
            "STYLE_BUG: _apply_overview_template must use em-dash in anchor text. "
            f"Got: {result!r}"
        )
        assert "Aspose.Slides \u2014 Enterprise Product Family" in result

    def test_overview_template_uses_em_dash_for_products_platform(self):
        """_apply_overview_template must use em-dash for products.aspose.com platform target."""
        content = "Aspose.Slides FOSS for .NET. MIT-licensed and open-source on GitHub."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/slides/net/",
            family="slides", platform="net",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert self.EM_DASH in result, "em-dash missing from overview anchor"
        assert "Aspose.Slides for .NET \u2014 Enterprise Product" in result

    def test_overview_template_uses_em_dash_for_docs_target(self):
        """_apply_overview_template must use em-dash for docs.aspose.com target."""
        content = "Aspose.Slides FOSS for Java. MIT-licensed."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://docs.aspose.com/slides/java/",
            family="slides", platform="java",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert self.EM_DASH in result, "em-dash missing from docs overview anchor"
        assert "Aspose.Slides for Java \u2014 Enterprise Documentation" in result

    def test_overview_template_uses_em_dash_for_reference_target(self):
        """_apply_overview_template must use em-dash for reference.aspose.com target."""
        content = "Aspose.Slides FOSS for .NET. MIT-licensed."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://reference.aspose.com/slides/net/",
            family="slides", platform="net",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert self.EM_DASH in result, "em-dash missing from reference overview anchor"
        assert "Aspose.Slides for .NET \u2014 Enterprise API Reference" in result

    def test_see_also_entry_uses_em_dash(self):
        """_build_see_also_entry must use em-dash (already canonical — guard against regression)."""
        entry = _build_see_also_entry(
            target_url="https://products.aspose.com/slides/net/",
            family="slides", platform="net",
            subdomain="docs.aspose.org",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert self.EM_DASH in entry, "em-dash missing from See Also entry"
        assert "Aspose.Slides for .NET \u2014 Enterprise Product" in entry

    def test_both_generators_produce_em_dash_for_same_target(self):
        """Both generators must use em-dash — style consistency across generation paths."""
        overview = _apply_overview_template(
            current_content="Aspose.Slides FOSS for .NET. MIT-licensed on GitHub.",
            target_url="https://products.aspose.com/slides/net/",
            family="slides", platform="net",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        see_also = _build_see_also_entry(
            target_url="https://products.aspose.com/slides/net/",
            family="slides", platform="net",
            subdomain="products.aspose.org",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert self.EM_DASH in overview, f"No em-dash in overview: {overview!r}"
        assert self.EM_DASH in see_also, f"No em-dash in see_also: {see_also!r}"

    def test_no_space_before_em_dash_and_space_after(self):
        """Style: '{display} — {suffix}' — one space before, one space after em-dash."""
        entry = _build_see_also_entry(
            target_url="https://reference.aspose.com/slides/net/",
            family="slides", platform="net",
            subdomain="reference.aspose.org",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        # Pattern: " — " (space-emdash-space)
        assert " \u2014 " in entry, f"Expected ' — ' (space-em-space) in: {entry!r}"
        assert " —" not in entry and "  —" not in entry, f"Double-space before em-dash is forbidden in: {entry!r}"


# ── CTA end-placement enforcement ──────────────────────────────────────────────────────────────────────────────


class TestCtaEndPlacement:
    """_apply_overview_template must always produce the CTA as the final sentence.

    The enterprise CTA is an exit link. It must appear at the very end of overview.content
    so it never interrupts license terms, FOSS-identity statements, runtime requirements,
    or platform-compatibility paragraphs.

    Regression guard: the prior implementation inserted the CTA before MIT/GitHub closing
    sentences, producing FAIL_INTERRUPTS_LICENSE_FLOW and FAIL_WRONG_TRANSITION patterns
    across 11 product pages.
    """

    def test_cta_is_final_when_content_ends_with_mit_sentence(self):
        """CTA must follow (not precede) a trailing MIT license sentence."""
        content = (
            "Aspose.Cells FOSS for .NET runs on Windows, macOS, and Linux. "
            "The MIT License permits unrestricted commercial use with no royalties."
        )
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/cells/net/",
            family="cells", platform="net",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        mit_pos = result.find("MIT License")
        cta_pos = result.find("products.aspose.com/cells/net/")
        assert mit_pos >= 0 and cta_pos >= 0
        assert mit_pos < cta_pos, (
            f"MIT sentence (pos {mit_pos}) must precede CTA (pos {cta_pos}). Got: {result!r}"
        )

    def test_cta_is_final_when_content_ends_with_github_sentence(self):
        """CTA must follow (not precede) a trailing GitHub/open-source sentence."""
        content = (
            "Aspose.Words FOSS for Python converts documents programmatically. "
            "It is MIT-licensed and fully open-source on GitHub."
        )
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/words/python/",
            family="words", platform="python",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        github_pos = result.find("open-source on GitHub")
        cta_pos = result.find("products.aspose.com/words/python/")
        assert github_pos >= 0 and cta_pos >= 0
        assert github_pos < cta_pos, (
            f"GitHub sentence (pos {github_pos}) must precede CTA (pos {cta_pos}). Got: {result!r}"
        )

    def test_cta_is_final_with_no_closing_sentence(self):
        """CTA must be appended at end when there is no special closing sentence."""
        content = "Aspose.Slides FOSS for Java supports PPTX round-trip editing."
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/slides/java/",
            family="slides", platform="java",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="platform",
        )
        assert result.rstrip().endswith(")."), f"CTA must be final: {result!r}"
        assert result.count("products.aspose.com/slides/java/") == 1

    def test_cta_is_final_with_multiline_content(self):
        """CTA must be appended at end for multi-paragraph content."""
        content = (
            "Aspose.Font FOSS for Python loads TTF, OTF, and WOFF fonts.\n\n"
            "The library exposes a FontLoader API. "
            "Aspose.Font FOSS is MIT licensed and installable from PyPI with pip install."
        )
        result = _apply_overview_template(
            current_content=content,
            target_url="https://products.aspose.com/font/",
            family="font", platform="python",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            target_type="family",
        )
        mit_pos = result.find("MIT licensed")
        cta_pos = result.find("products.aspose.com/font/")
        assert mit_pos >= 0 and cta_pos >= 0
        assert mit_pos < cta_pos, (
            f"MIT sentence (pos {mit_pos}) must precede CTA (pos {cta_pos})"
        )


# ── TC-BF-NEG: Negative controls for prose integration (BL-REPAIR-001) ───────

class TestBackfillNegativeControls:
    """
    Negative-control tests for backfill prose integration.
    All tests pass after Phase 4 prose machinery implementation.
    """

    def _make_blog_file(self, tmp_path: Path, body: str) -> Path:
        """Create a minimal blog index.md for testing."""
        content = (
            "---\ntitle: Test Post\ncategories: [Aspose.Words]\nauthor: Test\n---\n"
            + body
        )
        f = tmp_path / "index.md"
        f.write_text(content, encoding="utf-8")
        return f

    def test_bf_neg_002_exact_url_idempotent_skip(self, tmp_path, monkeypatch):
        """TC-BF-NEG-002: exact URL already in body → idempotent skip, skipped=True."""
        monkeypatch.setattr(_bbm, "_REPO_ROOT", tmp_path)
        target_url = "https://blog.aspose.com/"
        body_content = (
            "## Related Resources\n\n"
            f"- [Aspose.Words — Enterprise Blog]({target_url})\n"
        )
        f = self._make_blog_file(tmp_path, body_content)
        result = backfill_markdown(
            file_path=f,
            target_url=target_url,
            family="words", platform="net",
            subdomain="blog.aspose.org",
            page_type="blog_post",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            dry_run=True,
        )
        assert result.skipped is True, f"Expected skipped=True; skip_reason={result.skip_reason!r}"
        assert "idempotent" in result.skip_reason.lower() or "already" in result.skip_reason.lower()

    def test_bf_neg_008_validate_overview_update_low_ratio(self):
        """TC-BF-NEG-008: products YAML: retained-text ratio < 0.80 → _validate_overview_update() False."""
        from commands.ops.backlink_backfill import _validate_overview_update
        original = "A" * 100  # 100 chars of prose
        # Updated has only 50% of original text remaining (ratio = 0.5 < 0.80)
        updated = ("A" * 50) + " [Enterprise Product](https://products.aspose.com/words/)"
        result = _validate_overview_update(original, updated, "https://products.aspose.com/words/")
        assert result is False, "Expected False for low retained-text ratio"

    def test_bf_neg_001_near_duplicate_warning_accumulated(self, tmp_path, monkeypatch):
        """TC-BF-NEG-001: near-duplicate in existing body → warning_messages non-empty, single link injected."""
        monkeypatch.setattr(_bbm, "_REPO_ROOT", tmp_path)
        from commands.ops.backlink_backfill import _detect_near_duplicate
        # Body sentence shares enough tokens with the entry to trigger Jaccard >= 0.65.
        # After URL-stripping, entry tokens ≈ {words, net, blog}.
        # Body below: tokens = {words, net, blog, resources} → similarity = 3/4 = 0.75 >= 0.65
        body_content = (
            "See Aspose.Words for .NET blog resources.\n\n"
            "## Related Resources\n\n"
        )
        f = self._make_blog_file(tmp_path, body_content)
        target_url = "https://blog.aspose.com/"
        result = backfill_markdown(
            file_path=f,
            target_url=target_url,
            family="words", platform="net",
            subdomain="blog.aspose.org",
            page_type="blog_post",
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
            dry_run=True,
        )
        assert result.skipped is False, "Should inject even when near-duplicate detected"
        assert hasattr(result, "warning_messages"), "BackfillChange must have warning_messages field"
        assert len(result.warning_messages) > 0, "Expected near-duplicate warning"
        assert any("NEAR_DUPLICATE" in w for w in result.warning_messages)

    def test_bf_neg_003_llm_output_missing_anchor_text(self):
        """TC-BF-NEG-003: LLM output missing anchor text → _validate_llm_output() returns errors."""
        from commands.ops.backlink_backfill import _validate_llm_output
        original = "Aspose.Words FOSS for .NET provides document conversion."
        updated = "Aspose.Words FOSS for .NET provides document conversion. For more, see https://blog.aspose.com/."
        errors = _validate_llm_output(original, updated, "https://blog.aspose.com/", "Aspose.Words — Enterprise Blog")
        assert any("anchor" in e.lower() for e in errors), f"Expected anchor error; got {errors}"

    def test_bf_neg_004_llm_output_missing_target_url(self):
        """TC-BF-NEG-004: LLM output missing target URL → _validate_llm_output() returns errors."""
        from commands.ops.backlink_backfill import _validate_llm_output
        original = "Aspose.Words FOSS for .NET provides document conversion."
        updated = "Aspose.Words FOSS for .NET provides document conversion. For more, see [Aspose.Words — Enterprise Blog](https://wrong.com/)."
        errors = _validate_llm_output(original, updated, "https://blog.aspose.com/", "Aspose.Words — Enterprise Blog")
        assert any("url" in e.lower() for e in errors), f"Expected URL error; got {errors}"

    def test_bf_neg_005_llm_output_unsupported_claim(self):
        """TC-BF-NEG-005: LLM output with 'industry-leading' → unsupported_claim error."""
        from commands.ops.backlink_backfill import _validate_llm_output
        original = "Aspose.Words FOSS for .NET provides document conversion."
        anchor_text = "Aspose.Words — Enterprise Blog"
        target_url = "https://blog.aspose.com/"
        updated = (
            f"Aspose.Words FOSS is an industry-leading library. "
            f"For enterprise tutorials, see [{anchor_text}]({target_url})."
        )
        errors = _validate_llm_output(original, updated, target_url, anchor_text)
        assert any("industry" in e.lower() or "unsupported" in e.lower() for e in errors), \
            f"Expected unsupported_claim error; got {errors}"

    def test_bf_neg_006_validate_prose_anchor_unchanged(self, tmp_path):
        """TC-BF-NEG-006: after injection, _validate_prose() confirms entry anchor unchanged."""
        from commands.ops.backlink_backfill import _validate_prose
        anchor_text = "Aspose.Words — Enterprise Blog"
        target_url = "https://blog.aspose.com/"
        entry = f"- [{anchor_text}]({target_url})"
        section_text = f"## Related Resources\n\n{entry}\n"
        errors = _validate_prose(section_text, entry, target_url)
        assert errors == [], f"Expected no errors for correct anchor; got {errors}"

    def test_bf_neg_007_validate_prose_url_unchanged(self, tmp_path):
        """TC-BF-NEG-007: after injection, _validate_prose() confirms entry URL unchanged."""
        from commands.ops.backlink_backfill import _validate_prose
        anchor_text = "Aspose.Words — Enterprise Blog"
        target_url = "https://blog.aspose.com/"
        entry = f"- [{anchor_text}]({target_url})"
        # Simulate a corrupted injection where URL differs
        bad_section = f"## Related Resources\n\n- [{anchor_text}](https://wrong.com/)\n"
        errors = _validate_prose(bad_section, entry, target_url)
        assert len(errors) > 0, "Expected errors when URL is missing from section"


# ── Oscillation guard tests (TC-BL-005) ──────────────────────────────────────

class TestOscillationGuard:
    """Tests for the oscillation guard added in TC-BL-005.

    The guard detects when an enterprise-backlink marker is present in YAML
    overview.content but the actual link URL has been removed externally.
    In that case, the backfill should WARN and SKIP (not silently re-inject).
    """

    _YAML_TMPL = """\
---
layout: plugin
family_name: Aspose.Test FOSS
{extra_fm}overview:
  enable: true
  content: '{content}'
---
"""

    def _make_yaml_file(self, tmp_path, content: str, extra_fm: dict | None = None) -> "Path":
        """Write a minimal YAML frontmatter file for oscillation guard tests.

        extra_fm: optional dict of extra top-level frontmatter keys to inject
                  (e.g. {"enterprise_backlink_injected": "https://..."}).
        """
        fm_lines = ""
        if extra_fm:
            for k, v in extra_fm.items():
                fm_lines += f'{k}: "{str(v)}"\n'
        text = self._YAML_TMPL.replace("{extra_fm}", fm_lines).replace("{content}", content)
        p = tmp_path / "_index.md"
        p.write_text(text, encoding="utf-8")
        return p

    def test_oscillation_guard_triggers_when_marker_present_url_absent(self, tmp_path, monkeypatch):
        """TC-BL-005-05-A: frontmatter field set but URL removed from content -> oscillation_guard."""
        monkeypatch.setattr(_bbm, "_REPO_ROOT", tmp_path)
        target_url = "https://products.aspose.com/3d/python-net/"
        # Frontmatter has the injected marker but content does NOT have the URL
        content = "Some overview text about Aspose.3D FOSS library. No enterprise link."
        fpath = self._make_yaml_file(
            tmp_path, content,
            extra_fm={"enterprise_backlink_injected": target_url},
        )

        result = _bbm.backfill_products_yaml(
            file_path=fpath,
            target_url=target_url,
            family="3d",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            dry_run=True,
        )

        assert result.skipped is True
        assert result.skip_reason == "oscillation_guard"

    def test_oscillation_guard_does_not_trigger_when_url_present(self, tmp_path, monkeypatch):
        """TC-BL-005-05-B: frontmatter field AND URL in content -> idempotent (not oscillation_guard)."""
        monkeypatch.setattr(_bbm, "_REPO_ROOT", tmp_path)
        target_url = "https://products.aspose.com/3d/python-net/"
        # Content has the actual link AND frontmatter has the injected field
        content = (
            "See [Aspose.3D for Python \u2014 Enterprise Product]"
            "(https://products.aspose.com/3d/python-net/) for enterprise features."
        )
        fpath = self._make_yaml_file(
            tmp_path, content,
            extra_fm={"enterprise_backlink_injected": target_url},
        )

        result = _bbm.backfill_products_yaml(
            file_path=fpath,
            target_url=target_url,
            family="3d",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            dry_run=True,
        )

        assert result.skipped is True
        assert result.skip_reason == "Already contains target URL (idempotent)"

    def test_oscillation_guard_does_not_trigger_without_marker(self, tmp_path, monkeypatch):
        """TC-BL-005-05-C: no frontmatter field, no URL -> injection proceeds (not oscillation_guard)."""
        monkeypatch.setattr(_bbm, "_REPO_ROOT", tmp_path)
        target_url = "https://products.aspose.com/3d/python-net/"
        content = "Some overview text about Aspose.3D FOSS library. No enterprise link yet."
        fpath = self._make_yaml_file(tmp_path, content)  # no extra_fm

        result = _bbm.backfill_products_yaml(
            file_path=fpath,
            target_url=target_url,
            family="3d",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            dry_run=True,
        )

        assert result.skipped is False
        assert result.skip_reason is None or result.skip_reason == ""

    def test_oscillation_guard_marker_embedded_on_write(self, tmp_path, monkeypatch):
        """TC-BL-005-05-D: after --write, frontmatter has enterprise_backlink_injected; no HTML comment in content."""
        monkeypatch.setattr(_bbm, "_REPO_ROOT", tmp_path)
        target_url = "https://products.aspose.com/3d/python-net/"
        content = "Some overview text about Aspose.3D FOSS library. No enterprise link yet."
        fpath = self._make_yaml_file(tmp_path, content)

        result = _bbm.backfill_products_yaml(
            file_path=fpath,
            target_url=target_url,
            family="3d",
            platform="python",
            families_map=FAMILIES_MAP,
            platforms_map=PLATFORMS_MAP,
            dry_run=False,
        )

        assert result.skipped is False
        written = fpath.read_text(encoding="utf-8")
        # Frontmatter must have the injected field
        assert "enterprise_backlink_injected" in written, (
            f"enterprise_backlink_injected not found in written file. Got:\n{written[:500]}"
        )
        # Content must NOT contain any HTML comment
        assert "<!--" not in written, (
            f"HTML comment found in written file (should use frontmatter only). Got:\n{written[:500]}"
        )

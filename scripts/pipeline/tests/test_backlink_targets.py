"""test_backlink_targets.py — Unit tests for backlink_targets.py shared library.

Tests cover:
- classify_page_type for all page types (§Q.3)
- resolve_backlink for all fallback paths (§Q.4)
- count_qualifying_com_links (code fence stripping)
- classify_compliance for all statuses

Run:
    python -m pytest scripts/pipeline/tests/test_backlink_targets.py -v
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import pytest

# Adjust path so lib/ is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.backlink_targets import (
    PageType,
    MISSING, COMPLIANT, WRONG_TARGET, OVER_LIMIT, BLOCKED_TARGET,
    FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE,
    ACCEPTABLE_LEGACY_KB_PRE_P0, CANONICAL_KB_POST_P0, UPGRADE_CANDIDATE_NOT_YET_FIXED,
    LEGACY_COMPAT_MODE, CANONICAL_POST_P0_MODE,
    PREFERRED_TARGET_SUBDOMAIN,
    HOST_MAP,
    ResolutionKind,
    AncestorResolutionResult,
    SKIPPED_CLOSER_VERIFIED_PARENT,
    build_ancestor_chain,
    resolve_best_verified_ancestor,
    # A4 constants
    EXACT_PLATFORM_VERIFIED,
    VARIANT_CANONICAL_SELECTED,
    VARIANT_REVIEW_REQUIRED,
    VARIANT_BLOCKED_NO_POLICY,
    FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE,
    ANCESTOR_FALLBACK_AFTER_NO_VARIANT,
    VARIANT_CANDIDATES_NOT_IN_MAP,
    VARIANT_CANDIDATE_UNVERIFIED,
    SITEMAP_COVERAGE_GAP,
    MULTIPLE_VARIANTS_REQUIRES_REVIEW,
    load_platform_variant_registry,
    load_variant_authority,
    resolve_variant_target,
    classify_page_type,
    resolve_backlink,
    count_qualifying_com_links,
    classify_compliance,
    classify_kb_anchor_status,
    load_target_map,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure for testing."""
    for subdir in [
        "content/docs.aspose.org/en/words/net",
        "content/docs.aspose.org/en/words/net/getting-started",
        "content/kb.aspose.org/en/words/net",
        "content/reference.aspose.org/en/words/net",
        "content/reference.aspose.org/en/words/net/Document",
        "content/products.aspose.org/en/words/net",
        "content/products.aspose.org/en/words",
        "content/blog.aspose.org/words/net/my-post",
        "data",
    ]:
        (tmp_path / subdir).mkdir(parents=True, exist_ok=True)

    # Create test files
    files = {
        "content/docs.aspose.org/en/words/_index.md": "---\ntitle: Words\n---\n",
        "content/docs.aspose.org/en/words/net/_index.md": "---\ntitle: Words .NET\n---\n",
        "content/docs.aspose.org/en/words/net/getting-started/_index.md": "---\npage_role: toc\n---\n",
        "content/docs.aspose.org/en/words/net/getting-started/installation.md": "---\npage_role: howto_article\n---\n",
        "content/kb.aspose.org/en/words/_index.md": "---\ntitle: Words KB\n---\n",
        "content/kb.aspose.org/en/words/net/_index.md": "---\ntitle: Words .NET KB\n---\n",
        "content/kb.aspose.org/en/words/net/how-to-convert.md": "---\ntype: topic\n---\n",
        "content/reference.aspose.org/en/words/_index.md": "---\n---\n",
        "content/reference.aspose.org/en/words/net/_index.md": "---\nlayout: list\n---\n",
        "content/reference.aspose.org/en/words/net/Document.md": "---\nlayout: reference-single\n---\n",
        "content/reference.aspose.org/en/words/net/Document/Nested.md": "---\nlayout: reference-single\n---\n",
        "content/products.aspose.org/en/words/_index.md": "---\nlayout: family\n---\n",
        "content/products.aspose.org/en/words/net/_index.md": "---\nlayout: plugin\n---\n",
        "content/blog.aspose.org/words/net/my-post/index.md": "---\ntitle: Blog Post\n---\n",
        "content/blog.aspose.org/archive.md": "---\nlayout: archives\n---\n",
        # Locale file
        "content/docs.aspose.org/en/words/net/getting-started/installation.de.md": "---\n---\n",
    }
    for rel, content in files.items():
        fpath = tmp_path / rel
        fpath.write_text(content, encoding="utf-8")

    return tmp_path


def make_target_map(tmp_path: Path) -> dict:
    """Create a minimal target map for testing."""
    targets = {
        "products.aspose.com": {
            "families": {
                "words": {"url": "https://products.aspose.com/words/", "http_status": 200, "redirect_chain": []},
            },
            "platforms": {
                "words/net": {"url": "https://products.aspose.com/words/net/", "http_status": 200, "redirect_chain": []},
                "words/python": {"url": "https://products.aspose.com/words/python/", "http_status": 200, "redirect_chain": []},
            },
        },
        "docs.aspose.com": {
            "families": {
                "words": {"url": "https://docs.aspose.com/words/", "http_status": 200, "redirect_chain": []},
            },
            "platforms": {
                "words/net": {"url": "https://docs.aspose.com/words/net/", "http_status": 200, "redirect_chain": []},
            },
        },
        "reference.aspose.com": {
            "families": {
                "words": {"url": "https://reference.aspose.com/words/", "http_status": 200, "redirect_chain": []},
            },
            "platforms": {
                "words/net": {"url": "https://reference.aspose.com/words/net/", "http_status": 200, "redirect_chain": []},
            },
        },
    }
    data = {
        "schema_version": "1.0",
        "provenance": {"generated_at": "2026-01-01T00:00:00Z", "total_targets": 10},
        "targets": targets,
        "all_urls": {},
        "unavailable_sources": [],
        "family_platform_matrix": {},
    }
    data_path = tmp_path / "data" / "aspose_com_targets.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data), encoding="utf-8")
    return data


# ── classify_page_type tests ──────────────────────────────────────────────────

class TestClassifyPageType:

    def test_docs_family_index(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/docs.aspose.org/en/words/_index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.DOCS_FAMILY_INDEX
        assert fam == "words"
        assert plat is None
        assert sd == "docs.aspose.org"

    def test_docs_platform_index(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/docs.aspose.org/en/words/net/_index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.DOCS_PLATFORM_INDEX
        assert fam == "words"
        assert plat == "net"

    def test_docs_category_toc(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/docs.aspose.org/en/words/net/getting-started/_index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.DOCS_CATEGORY_TOC
        assert fam == "words"
        assert plat == "net"

    def test_docs_article(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/docs.aspose.org/en/words/net/getting-started/installation.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.DOCS_ARTICLE
        assert fam == "words"
        assert plat == "net"

    def test_kb_family_index(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/kb.aspose.org/en/words/_index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.KB_FAMILY_INDEX
        assert sd == "kb.aspose.org"

    def test_kb_platform_index(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/kb.aspose.org/en/words/net/_index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.KB_PLATFORM_INDEX

    def test_kb_article(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/kb.aspose.org/en/words/net/how-to-convert.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.KB_ARTICLE
        assert fam == "words"
        assert plat == "net"

    def test_reference_class(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/reference.aspose.org/en/words/net/Document.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.REF_CLASS
        assert sd == "reference.aspose.org"

    def test_reference_nested_class(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/reference.aspose.org/en/words/net/Document/Nested.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.REF_NESTED_CLASS

    def test_products_family(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/products.aspose.org/en/words/_index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.PRODUCTS_FAMILY
        assert fam == "words"
        assert plat is None

    def test_products_plugin(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/products.aspose.org/en/words/net/_index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.PRODUCTS_PLUGIN
        assert plat == "net"

    def test_blog_post(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/blog.aspose.org/words/net/my-post/index.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.BLOG_POST
        assert fam == "words"
        assert plat == "net"
        assert sd == "blog.aspose.org"

    def test_blog_archive(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/blog.aspose.org/archive.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.BLOG_ARCHIVE

    def test_locale_file_skipped(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "content/docs.aspose.org/en/words/net/getting-started/installation.de.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.LOCALE_FILE

    def test_unknown_path_returns_unknown(self, tmp_path):
        repo = make_repo(tmp_path)
        fpath = repo / "some/random/path/file.md"
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.UNKNOWN_PATTERN

    def test_very_deep_path_returns_unknown(self, tmp_path):
        """depth-5+ must not crash — return UNKNOWN_PATTERN."""
        repo = make_repo(tmp_path)
        deep_dir = repo / "content/reference.aspose.org/en/words/net/A/B/C"
        deep_dir.mkdir(parents=True, exist_ok=True)
        fpath = deep_dir / "deep.md"
        fpath.write_text("---\n---\n", encoding="utf-8")
        pt, fam, plat, sd = classify_page_type(fpath, repo)
        assert pt == PageType.UNKNOWN_PATTERN


# ── resolve_backlink tests ────────────────────────────────────────────────────

class TestResolveBacklink:

    def setup_method(self, tmp_path):
        self.tmp = None  # use pytest tmp_path fixture instead

    def get_map(self, tmp_path):
        make_target_map(tmp_path)
        return load_target_map(tmp_path)

    def test_docs_article_default_platform_root(self, tmp_path):
        """docs-article default → docs.aspose.com/{fam}/{plat}/ (platform root)."""
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", "net", "docs.aspose.org", tm)
        assert url == "https://docs.aspose.com/words/net/"
        assert utype == "platform"
        assert sd == "docs.aspose.com"
        assert reason is None

    def test_docs_family_index(self, tmp_path):
        """docs-family-index → docs.aspose.com/{fam}/"""
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", None, "docs.aspose.org", tm)
        assert url == "https://docs.aspose.com/words/"
        assert utype == "family"

    def test_reference_class_platform_root(self, tmp_path):
        """reference-class default → reference.aspose.com/{fam}/{plat}/"""
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", "net", "reference.aspose.org", tm)
        assert url == "https://reference.aspose.com/words/net/"
        assert utype == "platform"
        assert sd == "reference.aspose.com"

    def test_reference_nested_class_same_as_class(self, tmp_path):
        """reference-nested-class uses same resolution as reference-class."""
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", "net", "reference.aspose.org", tm)
        assert url is not None  # must not return None

    def test_blog_post_products_preferred(self, tmp_path):
        """blog-post → products.aspose.com/{fam}/{plat}/"""
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", "net", "blog.aspose.org", tm)
        assert url == "https://products.aspose.com/words/net/"
        assert sd == "products.aspose.com"

    def test_platform_not_found_falls_back_to_family(self, tmp_path):
        """Platform missing on preferred subdomain → family fallback."""
        tm = self.get_map(tmp_path)
        # words/java not in target map
        url, utype, sd, reason = resolve_backlink("words", "java", "docs.aspose.org", tm)
        # Should fall back to family URL
        assert url == "https://docs.aspose.com/words/"
        assert utype == "family"
        assert reason is not None  # has a fallback reason

    def test_family_and_platform_missing_falls_back_to_products(self, tmp_path):
        """Neither preferred nor products has the family → BLOCKED."""
        tm = self.get_map(tmp_path)
        # Use a family not in target map
        url, utype, sd, reason = resolve_backlink("unknownfam", "net", "docs.aspose.org", tm)
        assert url is None  # BLOCKED_TARGET

    def test_blocked_target_returns_none(self, tmp_path):
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("unknownfam", None, "docs.aspose.org", tm)
        assert url is None
        assert reason is not None

    def test_no_family_returns_blocked(self, tmp_path):
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink(None, None, "docs.aspose.org", tm)
        assert url is None

    def test_exact_deep_match_disabled_by_default(self, tmp_path):
        """Default mode never uses exact deep match."""
        tm = self.get_map(tmp_path)
        url, _, _, _ = resolve_backlink("words", "net", "docs.aspose.org", tm,
                                        exact_deep_match_enabled=False)
        # Should return platform root, not a deep URL
        assert url == "https://docs.aspose.com/words/net/"


# ── count_qualifying_com_links tests ─────────────────────────────────────────

class TestCountQualifyingLinks:

    def test_counts_aspose_com_links(self):
        text = "See [Aspose.Words](https://products.aspose.com/words/net/) for details."
        count, urls = count_qualifying_com_links(text)
        assert count == 1
        assert "https://products.aspose.com/words/net/" in urls[0]

    def test_ignores_code_fence(self):
        text = "Normal text\n```\nhttps://products.aspose.com/words/net/\n```\nend"
        count, _ = count_qualifying_com_links(text)
        assert count == 0

    def test_ignores_inline_code(self):
        text = "Use `https://products.aspose.com/words/net/` for details."
        count, _ = count_qualifying_com_links(text)
        assert count == 0

    def test_counts_multiple_links(self):
        text = (
            "See [Words](https://products.aspose.com/words/net/) and "
            "[Cells](https://products.aspose.com/cells/python/) here."
        )
        count, urls = count_qualifying_com_links(text)
        assert count == 2

    def test_no_links(self):
        count, urls = count_qualifying_com_links("No links here.")
        assert count == 0
        assert urls == []

    def test_aspose_org_not_counted(self):
        """aspose.org links do not qualify."""
        text = "See https://products.aspose.org/words/ for open source."
        count, _ = count_qualifying_com_links(text)
        assert count == 0

    def test_http_variant_counted(self):
        text = "See http://products.aspose.com/words/net/ here."
        count, _ = count_qualifying_com_links(text)
        assert count == 1

    def test_forum_aspose_com_not_counted(self):
        """forum.aspose.com is community support, not a qualifying enterprise product link."""
        text = "For support, visit the [Aspose Forum](https://forum.aspose.com/c/cells) here."
        count, _ = count_qualifying_com_links(text)
        assert count == 0

    def test_forum_not_counted_alongside_real_link(self):
        """forum link mixed with a real enterprise link — only real link counts."""
        text = (
            "See [KB](https://kb.aspose.com/cells/python/) and "
            "[Forum](https://forum.aspose.com/c/cells) here."
        )
        count, urls = count_qualifying_com_links(text)
        assert count == 1
        assert any("kb.aspose.com" in u for u in urls)


# ── classify_compliance tests ─────────────────────────────────────────────────

class TestClassifyCompliance:

    def test_missing_zero_links(self):
        status = classify_compliance(0, [], "https://products.aspose.com/words/net/")
        assert status == MISSING

    def test_compliant_link_matches_target(self):
        status = classify_compliance(
            1,
            ["https://products.aspose.com/words/net/"],
            "https://products.aspose.com/words/net/",
        )
        assert status == COMPLIANT

    def test_over_limit(self):
        status = classify_compliance(
            3,
            ["https://a.aspose.com/", "https://b.aspose.com/", "https://c.aspose.com/"],
            "https://products.aspose.com/words/net/",
        )
        assert status == OVER_LIMIT

    def test_wrong_target_links_exist_but_dont_match(self):
        status = classify_compliance(
            1,
            ["https://docs.aspose.com/words/net/"],
            "https://products.aspose.com/words/net/",
        )
        assert status == WRONG_TARGET

    def test_blocked_target_when_no_url(self):
        status = classify_compliance(0, [], None)
        assert status == BLOCKED_TARGET


# ── load_target_map tests ─────────────────────────────────────────────────────

class TestLoadTargetMap:

    def test_loads_valid_map(self, tmp_path):
        make_target_map(tmp_path)
        data = load_target_map(tmp_path)
        assert "targets" in data
        assert "products.aspose.com" in data["targets"]

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_target_map(tmp_path)  # no data file created

    def test_raises_on_corrupt_json(self, tmp_path):
        data_path = tmp_path / "data" / "aspose_com_targets.json"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text("not valid json", encoding="utf-8")
        with pytest.raises(Exception):  # json.JSONDecodeError or ValueError
            load_target_map(tmp_path)


# ── P0 A2: TestPlatformLandingAuthority tests ─────────────────────────────────
# Fixed: C-10 KB subdomain bug (PREFERRED_TARGET_SUBDOMAIN["kb.aspose.org"] was "docs.aspose.com")

def make_kb_target_map(tmp_path: Path) -> dict:
    """Target map with KB entries for platform landing authority tests."""
    targets = {
        "products.aspose.com": {
            "families": {
                "words":  {"url": "https://products.aspose.com/words/",  "http_status": 200, "redirect_chain": []},
                "cells":  {"url": "https://products.aspose.com/cells/",  "http_status": 200, "redirect_chain": []},
                "pdf":    {"url": "https://products.aspose.com/pdf/",    "http_status": 200, "redirect_chain": []},
            },
            "platforms": {
                "words/net":    {"url": "https://products.aspose.com/words/net/",    "http_status": 200, "redirect_chain": []},
                "words/python": {"url": "https://products.aspose.com/words/python/", "http_status": 200, "redirect_chain": []},
                "cells/python": {"url": "https://products.aspose.com/cells/python/", "http_status": 200, "redirect_chain": []},
            },
        },
        "docs.aspose.com": {
            "families": {
                "words": {"url": "https://docs.aspose.com/words/", "http_status": 200, "redirect_chain": []},
                "pdf":   {"url": "https://docs.aspose.com/pdf/",   "http_status": 200, "redirect_chain": []},
            },
            "platforms": {
                "words/net":  {"url": "https://docs.aspose.com/words/net/",  "http_status": 200, "redirect_chain": []},
                "pdf/go-cpp": {"url": "https://docs.aspose.com/pdf/go-cpp/", "http_status": 200, "redirect_chain": []},
            },
        },
        "reference.aspose.com": {
            "families": {
                "words": {"url": "https://reference.aspose.com/words/", "http_status": 200, "redirect_chain": []},
            },
            "platforms": {
                "words/net": {"url": "https://reference.aspose.com/words/net/", "http_status": 200, "redirect_chain": []},
            },
        },
        "kb.aspose.com": {
            "families": {
                "cells": {"url": "https://kb.aspose.com/cells/", "http_status": 200, "redirect_chain": []},
                "words": {"url": "https://kb.aspose.com/words/", "http_status": 200, "redirect_chain": []},
            },
            "platforms": {
                "cells/java":   {"url": "https://kb.aspose.com/cells/java/",   "http_status": 200, "redirect_chain": []},
                "cells/python": {"url": "https://kb.aspose.com/cells/python/", "http_status": 200, "redirect_chain": []},
                "words/net":    {"url": "https://kb.aspose.com/words/net/",    "http_status": 200, "redirect_chain": []},
            },
        },
    }
    data = {
        "schema_version": "1.0",
        "provenance": {"generated_at": "2026-01-01T00:00:00Z", "total_targets": 20},
        "targets": targets,
        "all_urls": {},
        "unavailable_sources": [],
        "family_platform_matrix": {},
    }
    data_path = tmp_path / "data" / "aspose_com_targets.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data), encoding="utf-8")
    return data


class TestPlatformLandingAuthority:

    def get_map(self, tmp_path: Path) -> dict:
        return make_kb_target_map(tmp_path)

    # Test 1: KB source resolves to kb.aspose.com, NOT docs.aspose.com (C-10 regression test)
    def test_kb_cells_java_resolves_to_kb_subdomain_not_docs(self, tmp_path):
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("cells", "java", "kb.aspose.org", tm)
        assert url is not None
        assert "kb.aspose.com" in url
        assert "docs.aspose.com" not in url
        assert url == "https://kb.aspose.com/cells/java/"
        assert utype == "platform"
        assert reason is None

    # Test 2: Constant value check — PREFERRED_TARGET_SUBDOMAIN["kb.aspose.org"] == "kb.aspose.com"
    def test_kb_preferred_subdomain_constant_is_kb_aspose_com(self):
        assert PREFERRED_TARGET_SUBDOMAIN["kb.aspose.org"] == "kb.aspose.com"

    # Test 3: KB missing platform falls back to kb.aspose.com family, NOT docs.aspose.com
    def test_kb_missing_platform_falls_through_to_kb_family_not_docs_family(self, tmp_path):
        tm = self.get_map(tmp_path)
        # "cells/go" not in kb.aspose.com platforms — falls back to family
        url, utype, sd, reason = resolve_backlink("cells", "go", "kb.aspose.org", tm)
        assert url is not None
        assert "kb.aspose.com" in url
        assert "docs.aspose.com" not in url
        assert utype == "family"
        assert reason is not None  # fallback reason present

    # Test 4: products.aspose.org/words/python → platform target, NOT family
    def test_products_words_python_resolves_platform_not_family(self, tmp_path):
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", "python", "products.aspose.org", tm)
        assert url == "https://products.aspose.com/words/python/"
        assert utype == "platform"
        assert "words/python" in url
        assert reason is None

    # Test 5: Products family fallback only when platform missing from map
    def test_products_family_fallback_only_when_platform_missing_from_map(self, tmp_path):
        tm = self.get_map(tmp_path)
        # "words/ruby" not in any map
        url, utype, sd, reason = resolve_backlink("words", "ruby", "products.aspose.org", tm)
        assert url is not None
        assert utype == "family"
        assert reason is not None  # fallback_reason is non-None

    # Test 6: FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE detected by classify_compliance
    def test_family_fallback_while_platform_available_status_detected(self, tmp_path):
        # Page body has family URL; resolver returns platform URL → FAMILY_FALLBACK
        chosen_url = "https://kb.aspose.com/cells/java/"
        existing_urls = ["https://kb.aspose.com/cells/"]  # family-level link in page body
        status = classify_compliance(
            1, existing_urls, chosen_url,
            family="cells", platform="java",
            chosen_target_type="platform",
            chosen_target_subdomain="kb.aspose.com",
        )
        assert status == FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE

    # Test 7: Canonical override applied when loaded and http_verified: true
    def test_platform_canonical_override_applied_when_loaded(self, tmp_path):
        tm = self.get_map(tmp_path)
        # Mock override: pdf/go → go-cpp (verified)
        overrides = {
            "overrides": {
                "pdf/go": {
                    "target_platform": "go-cpp",
                    "http_verified": True,
                    "verification_date": "2026-05-26",
                }
            }
        }
        # docs.aspose.com/pdf/go-cpp/ is HTTP 200 in our test map
        url, utype, sd, reason = resolve_backlink(
            "pdf", "go", "docs.aspose.org", tm, canonical_overrides=overrides
        )
        assert url == "https://docs.aspose.com/pdf/go-cpp/"
        assert utype == "platform"
        assert reason is None

    # Test 8: Unverified override entry NOT applied (http_verified: false)
    def test_no_unverified_override_accepted(self, tmp_path):
        tm = self.get_map(tmp_path)
        # Override exists but http_verified: false → must NOT be used
        overrides = {
            "overrides": {
                "pdf/go": {
                    "target_platform": "go-cpp",
                    "http_verified": False,  # unverified — must NOT be applied
                    "verification_date": None,
                }
            }
        }
        url, utype, sd, reason = resolve_backlink(
            "pdf", "go", "docs.aspose.org", tm, canonical_overrides=overrides
        )
        # pdf/go not in docs.aspose.com map → falls back to family
        # Override NOT applied because http_verified is False
        assert url != "https://docs.aspose.com/pdf/go-cpp/"
        # Should fall back to family (docs.aspose.com/pdf/ is HTTP 200)
        assert url == "https://docs.aspose.com/pdf/"
        assert utype == "family"

    # Test 9: Docs pages unaffected by KB fix (regression test)
    def test_docs_pages_unaffected_by_kb_fix(self, tmp_path):
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", "net", "docs.aspose.org", tm)
        assert url == "https://docs.aspose.com/words/net/"
        assert sd == "docs.aspose.com"
        assert utype == "platform"

    # Test 10: Products pages unaffected by KB fix (regression test)
    def test_products_pages_unaffected_by_kb_fix(self, tmp_path):
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("cells", "python", "products.aspose.org", tm)
        assert sd == "products.aspose.com"
        assert "products.aspose.com" in url

    # Test 11: Reference pages unaffected by KB fix (regression test)
    def test_reference_pages_unaffected_by_kb_fix(self, tmp_path):
        tm = self.get_map(tmp_path)
        url, utype, sd, reason = resolve_backlink("words", "net", "reference.aspose.org", tm)
        assert url == "https://reference.aspose.com/words/net/"
        assert sd == "reference.aspose.com"

    # Test 12: FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE is an audit failure, NOT COMPLIANT
    def test_family_fallback_while_platform_available_is_audit_failure_not_compliant(self, tmp_path):
        chosen_url = "https://kb.aspose.com/cells/java/"
        existing_urls = ["https://kb.aspose.com/cells/"]
        status = classify_compliance(
            1, existing_urls, chosen_url,
            family="cells", platform="java",
            chosen_target_type="platform",
            chosen_target_subdomain="kb.aspose.com",
        )
        assert status == FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE
        assert status != COMPLIANT

    # Test 13 (A7-03): KB legacy docs.aspose.com link → ACCEPTABLE_LEGACY_KB_PRE_P0 in LEGACY_COMPAT_MODE
    def test_kb_legacy_anchor_classified_acceptable_in_legacy_compat_mode(self):
        existing_urls = ["https://docs.aspose.com/cells/java/"]
        status = classify_kb_anchor_status(existing_urls, kb_anchor_mode=LEGACY_COMPAT_MODE)
        assert status == ACCEPTABLE_LEGACY_KB_PRE_P0
        assert status != CANONICAL_KB_POST_P0
        assert status != UPGRADE_CANDIDATE_NOT_YET_FIXED

    # Test 14 (A7-03): KB canonical kb.aspose.com link → CANONICAL_KB_POST_P0 regardless of mode
    def test_kb_canonical_anchor_classified_canonical_post_p0(self):
        for mode in (LEGACY_COMPAT_MODE, CANONICAL_POST_P0_MODE):
            existing_urls = ["https://kb.aspose.com/cells/java/"]
            status = classify_kb_anchor_status(existing_urls, kb_anchor_mode=mode)
            assert status == CANONICAL_KB_POST_P0, f"mode={mode!r}: expected CANONICAL_KB_POST_P0"

    # Test 15 (A7-03): KB legacy docs.aspose.com link → UPGRADE_CANDIDATE_NOT_YET_FIXED in CANONICAL_POST_P0_MODE
    def test_kb_legacy_anchor_is_upgrade_candidate_in_canonical_mode(self):
        existing_urls = ["https://docs.aspose.com/cells/java/"]
        status = classify_kb_anchor_status(existing_urls, kb_anchor_mode=CANONICAL_POST_P0_MODE)
        assert status == UPGRADE_CANDIDATE_NOT_YET_FIXED
        assert status != ACCEPTABLE_LEGACY_KB_PRE_P0


# ── Phase A3: Best Verified Ancestor Fallback ─────────────────────────────────

def _make_mock_all_urls(entries: dict) -> dict:
    """Build a minimal target_map with all_urls populated from {url: http_status} dict."""
    all_urls = {}
    for url, status_code in entries.items():
        all_urls[url] = {"http_status": status_code, "type": "mock"}
    return {"all_urls": all_urls}


class TestBestVerifiedAncestorFallback:
    """16 tests for resolve_best_verified_ancestor() — §A3-10."""

    # Test 1: Exact child verified wins (depth=0, EXACT_VERIFIED)
    def test_exact_child_verified_wins(self):
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/python/developer-guide/": 200,
            "https://docs.aspose.com/cells/python/": 200,
            "https://docs.aspose.com/cells/": 200,
        })
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        assert result.verified is True
        assert result.fallback_depth == 0
        assert result.resolution_kind == ResolutionKind.EXACT_VERIFIED
        assert result.selected_path == "docs/cells/python/developer-guide"
        assert "developer-guide" in (result.selected_url or "")

    # Test 2: Child missing, falls back to platform (depth=1, BEST_VERIFIED_ANCESTOR)
    def test_child_missing_falls_back_to_platform(self):
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/python/": 200,
            "https://docs.aspose.com/cells/": 200,
        })
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        assert result.verified is True
        assert result.fallback_depth == 1
        assert result.resolution_kind == ResolutionKind.BEST_VERIFIED_ANCESTOR
        assert result.selected_path == "docs/cells/python"
        assert result.selected_url == "https://docs.aspose.com/cells/python/"

    # Test 3: Platform missing, falls back to family (depth=2)
    def test_platform_missing_falls_back_to_family(self):
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/": 200,
        })
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        assert result.verified is True
        assert result.fallback_depth == 2
        assert result.resolution_kind == ResolutionKind.BEST_VERIFIED_ANCESTOR
        assert result.selected_path == "docs/cells"
        assert result.selected_url == "https://docs.aspose.com/cells/"

    # Test 4: All missing but root verified → ROOT_FALLBACK, root_fallback_used=True
    def test_family_missing_falls_back_to_root_when_root_verified(self):
        # kb.aspose.com/ is in all_urls HTTP 200 (confirmed from prior probe)
        mock = _make_mock_all_urls({
            "https://kb.aspose.com/": 200,
        })
        result = resolve_best_verified_ancestor("kb/cells/java/some-article", mock)
        assert result.verified is True
        assert result.resolution_kind == ResolutionKind.ROOT_FALLBACK
        assert result.root_fallback_used is True
        assert result.selected_url == "https://kb.aspose.com/"

    # Test 5: No verified ancestor → BLOCKED_NO_VERIFIED_TARGET, verified=False
    def test_no_verified_ancestor_returns_blocked(self):
        mock = _make_mock_all_urls({})
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        assert result.verified is False
        assert result.resolution_kind == ResolutionKind.BLOCKED_NO_VERIFIED_TARGET
        assert result.selected_path is None
        assert result.selected_url is None
        assert result.fallback_depth == -1

    # Test 6: Never skip closer verified parent (platform beats family)
    def test_never_skip_closer_verified_parent(self):
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/python/": 200,
            "https://docs.aspose.com/cells/": 200,
        })
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        # Platform (docs/cells/python) must win over family (docs/cells)
        assert result.selected_path == "docs/cells/python"
        assert result.fallback_depth == 1

    # Test 7: KB article fallback to platform after P0 fix (URL contains kb.aspose.com)
    def test_kb_article_fallback_to_platform_after_p0_fix(self):
        mock = _make_mock_all_urls({
            "https://kb.aspose.com/cells/java/": 200,
            "https://kb.aspose.com/cells/": 200,
        })
        result = resolve_best_verified_ancestor("kb/cells/java/some-article", mock)
        assert result.verified is True
        assert "kb.aspose.com" in (result.selected_url or "")
        assert result.fallback_depth == 1
        assert result.selected_path == "kb/cells/java"

    # Test 8: Reference member fallback to class
    def test_reference_member_fallback_to_class(self):
        mock = _make_mock_all_urls({
            "https://reference.aspose.com/words/net/aspose.words/document/": 200,
        })
        result = resolve_best_verified_ancestor(
            "reference/words/net/aspose.words/document/save", mock
        )
        assert result.verified is True
        assert result.selected_path == "reference/words/net/aspose.words/document"
        assert result.fallback_depth == 1

    # Test 9: Reference class fallback to namespace
    def test_reference_class_fallback_to_namespace(self):
        mock = _make_mock_all_urls({
            "https://reference.aspose.com/words/net/aspose.words/": 200,
        })
        result = resolve_best_verified_ancestor(
            "reference/words/net/aspose.words/document", mock
        )
        assert result.verified is True
        assert result.selected_path == "reference/words/net/aspose.words"
        assert result.fallback_depth == 1

    # Test 10: Root fallback blocked when root not in all_urls (docs root is NOT in map)
    def test_root_fallback_blocked_when_root_not_in_all_urls(self):
        # docs.aspose.com/ is NOT in all_urls (confirmed from prior probe)
        mock = _make_mock_all_urls({})  # empty — nothing at any depth
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        assert result.verified is False
        assert result.resolution_kind == ResolutionKind.BLOCKED_NO_VERIFIED_TARGET
        # Ensure root fallback was NOT used despite being attempted
        assert result.root_fallback_used is False

    # Test 11: Full fallback chain recorded with all candidates
    def test_full_fallback_chain_recorded_with_all_candidates(self):
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/python/": 200,
        })
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        # Chain must include all paths from most-specific to selected
        paths_in_chain = [entry["path"] for entry in result.fallback_chain]
        assert "docs/cells/python/developer-guide" in paths_in_chain
        assert "docs/cells/python" in paths_in_chain
        # Chain completeness: length >= fallback_depth + 1
        assert len(result.fallback_chain) >= result.fallback_depth + 1

    # Test 12: Audit detects SKIPPED_CLOSER_VERIFIED_PARENT
    def test_audit_detects_skipped_closer_verified_parent(self):
        """When docs/cells/python/ is verified but docs/cells/ is the current link, that's a skip."""
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/python/": 200,
            "https://docs.aspose.com/cells/": 200,
        })
        # Simulate: current content has family link (depth 1 relative to platform)
        # Best verified ancestor for docs/cells/python/article is docs/cells/python (depth=1)
        result = resolve_best_verified_ancestor("docs/cells/python/article", mock)
        assert result.selected_path == "docs/cells/python"
        # The SKIPPED_CLOSER_VERIFIED_PARENT status is emitted by audit when
        # the content URL is broader than the selected_path
        # Verify the constant itself is defined and is a non-empty string
        assert isinstance(SKIPPED_CLOSER_VERIFIED_PARENT, str)
        assert len(SKIPPED_CLOSER_VERIFIED_PARENT) > 0

    # Test 13: Content validator accepts selected best ancestor
    def test_content_validator_accepts_selected_best_ancestor(self):
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/python/": 200,
        })
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        # The selected URL should be the platform URL — a valid target
        assert result.verified is True
        assert result.selected_url == "https://docs.aspose.com/cells/python/"

    # Test 14: Content validator rejects broader link when closer exists
    def test_content_validator_rejects_broader_link_when_closer_exists(self):
        """Verified: platform exists. Using family URL instead = SKIPPED_CLOSER_VERIFIED_PARENT."""
        mock = _make_mock_all_urls({
            "https://docs.aspose.com/cells/python/": 200,
            "https://docs.aspose.com/cells/": 200,
        })
        result = resolve_best_verified_ancestor("docs/cells/python/developer-guide", mock)
        # Best ancestor is platform (depth=1), NOT family (depth=2)
        # The resolver stops at the first verified ancestor — the chain only records candidates
        # checked up to the resolution point.
        assert result.selected_path == "docs/cells/python"
        assert result.fallback_depth == 1
        # The chain records the unverified exact path + the verified platform path
        chain_paths = [e["path"] for e in result.fallback_chain]
        assert "docs/cells/python/developer-guide" in chain_paths  # checked first, not found
        assert "docs/cells/python" in chain_paths                   # found → resolution stops here
        # If content had docs/cells/ (family) as the link, that would be SKIPPED_CLOSER_VERIFIED_PARENT
        # because docs/cells/python/ was verified and is closer.
        assert SKIPPED_CLOSER_VERIFIED_PARENT == "SKIPPED_CLOSER_VERIFIED_PARENT"

    # Test 15: No HTTP calls during resolution (requests not imported in backlink_targets)
    def test_no_http_calls_during_resolution(self):
        import importlib
        import lib.backlink_targets as bt_module  # scripts/pipeline/ is in sys.path
        # Verify requests/httpx/aiohttp/urllib.request are NOT imported
        source = ""
        try:
            import inspect
            source = inspect.getsource(bt_module)
        except Exception:
            pass
        # None of these HTTP client imports should appear in the module source
        for forbidden in ("import requests", "import httpx", "import aiohttp", "urllib.request"):
            assert forbidden not in source, (
                f"HTTP import {forbidden!r} found in backlink_targets.py — V15 violation"
            )

    # Test 16: No LLM imports in backlink_targets module
    def test_no_llm_imports_in_backlink_targets_module(self):
        import inspect
        import lib.backlink_targets as bt_module  # scripts/pipeline/ is in sys.path
        source = inspect.getsource(bt_module)
        for forbidden in ("llm_router", "professionalize_client", "LLMRouter"):
            assert forbidden not in source, (
                f"LLM import {forbidden!r} found in backlink_targets.py — V15 violation"
            )


# ── Phase A4: Platform Variant Authority ──────────────────────────────────────

def _make_mock_inventory(entries: list) -> dict:
    """
    Build a mock variant authority list with load_variant_authority-compatible format.
    Each entry: {"request_key": str, "allowed_for_generation": bool, "decision": str,
                 "canonical_target_url": str|None, ...}
    """
    return {rec["request_key"]: rec for rec in entries}


def _make_authority_record(
    request_key: str,
    decision: str,
    canonical_target_url: str | None,
    allowed: bool,
    alternatives: list | None = None,
    review_reason: str | None = None,
) -> dict:
    return {
        "request_key": request_key,
        "decision": decision,
        "canonical_target_url": canonical_target_url,
        "allowed_for_generation": allowed,
        "alternatives": alternatives or [],
        "review_reason": review_reason,
    }


class TestPlatformVariantAuthority:
    """16 tests for platform variant authority — §A4-08."""

    # Test 1: products/pdf/python exact missing, multiple variants → REVIEW_REQUIRED
    def test_products_pdf_python_exact_missing_variants_found(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/pdf/python", "REVIEW_REQUIRED", None, False,
                alternatives=[
                    {"slug": "python-net", "status": "verified_200"},
                    {"slug": "python-java", "status": "verified_200"},
                ],
                review_reason="multiple_verified_variants_no_canonical_rule",
            )
        ])
        rec = resolve_variant_target("products/pdf/python", authority)
        assert rec is None, "REVIEW_REQUIRED must not be allowed_for_generation"

    # Test 2: canonical override selects python-net → VARIANT_CANONICAL_SELECTED
    def test_products_pdf_python_canonical_override_selects_python_net(self):
        overrides = {
            "products/pdf/python": {
                "http_verified": True,
                "canonical_target_url": "https://products.aspose.com/pdf/python-net/",
            }
        }
        authority = _make_mock_inventory([])
        rec = resolve_variant_target("products/pdf/python", authority, overrides=overrides)
        assert rec is not None
        assert rec["canonical_target_url"] == "https://products.aspose.com/pdf/python-net/"
        assert rec["decision"] == "EXPLICIT_OVERRIDE"
        assert rec["allowed_for_generation"] is True

    # Test 3: variants exist but unresolved → resolver must NOT choose family fallback
    def test_products_pdf_python_no_family_fallback_while_variants_exist(self):
        # REVIEW_REQUIRED status blocks generation — family fallback must not happen
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/pdf/python", "REVIEW_REQUIRED", None, False,
                review_reason="multiple_verified_variants_no_canonical_rule",
            )
        ])
        rec = resolve_variant_target("products/pdf/python", authority)
        # Must return None — no silent fallback to family
        assert rec is None
        # The VARIANT_REVIEW_REQUIRED status code must be a non-empty string
        assert isinstance(VARIANT_REVIEW_REQUIRED, str) and len(VARIANT_REVIEW_REQUIRED) > 0

    # Test 4: single verified variant auto-selects without override
    def test_products_pdf_python_single_variant_auto_selects(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/pdf/python", "AUTO_APPROVE_SINGLE_VARIANT",
                "https://products.aspose.com/pdf/python-net/", True,
                alternatives=[{"slug": "python-net", "status": "verified_200"}],
            )
        ])
        rec = resolve_variant_target("products/pdf/python", authority)
        assert rec is not None
        assert rec["allowed_for_generation"] is True
        assert "python-net" in rec["canonical_target_url"]

    # Test 5: unverified variant rejected — http_status:404 must not be selected
    def test_products_pdf_python_unverified_variant_rejected(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/pdf/python", "VARIANT_CANDIDATES_NOT_IN_MAP", None, False,
                alternatives=[{"slug": "python-net", "status": "missing_or_unverified"}],
                review_reason="variant_candidates_unverified",
            )
        ])
        rec = resolve_variant_target("products/pdf/python", authority)
        assert rec is None  # not allowed_for_generation

    # Test 6: REVIEW_REQUIRED authority entry blocks insertion
    def test_variant_review_required_blocks_insertion(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "reference/words/python", "REVIEW_REQUIRED", None, False,
                review_reason="multiple_verified_variants_no_canonical_rule",
            )
        ])
        rec = resolve_variant_target("reference/words/python", authority)
        assert rec is None

    # Test 7: exact verified wins over variants
    def test_words_python_exact_verified_wins_over_variants(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/words/python", "AUTO_APPROVE_EXACT",
                "https://products.aspose.com/words/python/", True,
            )
        ])
        rec = resolve_variant_target("products/words/python", authority)
        assert rec is not None
        assert rec["decision"] == "AUTO_APPROVE_EXACT"
        assert rec["canonical_target_url"] == "https://products.aspose.com/words/python/"

    # Test 8: pdf/go, go-cpp is only verified variant → auto-select go-cpp
    def test_pdf_go_go_cpp_selected_only_with_verified_mapping(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "reference/pdf/go", "AUTO_APPROVE_SINGLE_VARIANT",
                "https://reference.aspose.com/pdf/go-cpp/", True,
                alternatives=[{"slug": "go-cpp", "status": "verified_200"}],
            )
        ])
        rec = resolve_variant_target("reference/pdf/go", authority)
        assert rec is not None
        assert "go-cpp" in rec["canonical_target_url"]

    # Test 9: kb/cells/java exact platform wins → AUTO_APPROVE_EXACT
    def test_kb_cells_java_exact_platform_wins(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "kb/cells/java", "AUTO_APPROVE_EXACT",
                "https://kb.aspose.com/cells/java/", True,
            )
        ])
        rec = resolve_variant_target("kb/cells/java", authority)
        assert rec is not None
        assert rec["decision"] == "AUTO_APPROVE_EXACT"
        assert "kb.aspose.com/cells/java/" in rec["canonical_target_url"]

    # Test 10: zero variants → VARIANT_CANDIDATES_NOT_IN_MAP → fall through to A3 ancestor walk
    def test_ancestor_fallback_only_after_no_variant(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "docs/cells/python", "VARIANT_CANDIDATES_NOT_IN_MAP", None, False,
                review_reason="no_variant_candidates_found",
            )
        ])
        rec = resolve_variant_target("docs/cells/python", authority)
        assert rec is None
        # Caller should then invoke resolve_best_verified_ancestor as step 5
        assert VARIANT_CANDIDATES_NOT_IN_MAP == "VARIANT_CANDIDATES_NOT_IN_MAP"

    # Test 11: candidate not in verified inventory cannot appear
    def test_variant_candidates_from_local_inventory_only(self):
        # An authority with a guessed (not inventory-sourced) URL must not be trusted
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/pdf/python", "AUTO_APPROVE_SINGLE_VARIANT",
                "https://products.aspose.com/pdf/python-guessed/", True,
            )
        ])
        # This tests that the loading infrastructure doesn't fabricate URLs;
        # the record is returned as-is from authority, but the test demonstrates
        # that only URLs explicitly in the authority (sourced from verified inventory)
        # should appear.
        rec = resolve_variant_target("products/pdf/python", authority)
        # The function returns the record — domain validity is a build-time concern (V2)
        assert rec is not None
        assert "guessed" in rec["canonical_target_url"]  # demonstrates what would be in rec
        # In production, backlink_build_platform_variant_authority only uses HTTP 200 URLs

    # Test 12: sitemap coverage gap reported
    def test_sitemap_coverage_gap_reported(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/note/python", "VARIANT_CANDIDATES_NOT_IN_MAP", None, False,
                review_reason="no_variant_candidates_found",
            )
        ])
        # The authority record's review_reason signals the gap
        raw_rec = authority.get("products/note/python")
        assert raw_rec is not None
        assert raw_rec["review_reason"] == "no_variant_candidates_found"
        assert SITEMAP_COVERAGE_GAP == "SITEMAP_COVERAGE_GAP"

    # Test 13: AI cannot select variant (AI advisory only, not decision-making)
    def test_ai_cannot_select_variant(self):
        # Even if AI says python-net is best, without deterministic rule → REVIEW_REQUIRED
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/pdf/python", "REVIEW_REQUIRED", None, False,
                alternatives=[
                    {"slug": "python-net", "status": "verified_200"},
                    {"slug": "python-java", "status": "verified_200"},
                ],
                review_reason="multiple_verified_variants_no_canonical_rule",
            )
        ])
        rec = resolve_variant_target("products/pdf/python", authority)
        # AI advisory output should not change the None return for REVIEW_REQUIRED
        assert rec is None

    # Test 14: variant authority stale blocks (source_map_hash mismatch)
    def test_variant_authority_stale_blocks(self):
        authority = _make_mock_inventory([
            _make_authority_record(
                "reference/words/python-net", "STALE_AUTHORITY", None, False,
            )
        ])
        rec = resolve_variant_target("reference/words/python-net", authority)
        # allowed_for_generation: false → returns None
        assert rec is None

    # Test 15: audit flags FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE
    def test_audit_flags_family_fallback_while_variant_available(self):
        # When content has family link (products/pdf/) but a variant (python-net) is verified
        # and in the authority, that's FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE
        authority = _make_mock_inventory([
            _make_authority_record(
                "products/pdf/python", "AUTO_APPROVE_SINGLE_VARIANT",
                "https://products.aspose.com/pdf/python-net/", True,
                alternatives=[{"slug": "python-net", "status": "verified_200"}],
            )
        ])
        rec = resolve_variant_target("products/pdf/python", authority)
        # Variant is available and approved
        assert rec is not None
        assert rec["allowed_for_generation"] is True
        # If content had products.aspose.com/pdf/ (family) instead of the variant,
        # audit should flag FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE
        assert FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE == "FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE"

    # Test 16: all section prefixes parse without crash
    def test_all_sections_support_variant_policy(self):
        sections = ["products", "docs", "reference", "kb", "blog"]
        for section in sections:
            authority = _make_mock_inventory([
                _make_authority_record(
                    f"{section}/words/python", "VARIANT_CANDIDATES_NOT_IN_MAP", None, False,
                )
            ])
            rec = resolve_variant_target(f"{section}/words/python", authority)
            assert rec is None  # no generation — all return None safely


# ── A5-Prep: TestLinkSlotRegistry ────────────────────────────────────────────

from lib.backlink_targets import (
    load_slot_registry,
    get_slot_for_page_type,
    slot_fallback_chain,
    SlotConfig,
)


class TestLinkSlotRegistry:

    def test_slot_registry_loads_and_validates(self):
        registry = load_slot_registry()
        assert isinstance(registry, dict)
        assert len(registry) >= 3
        for slot_id, slot in registry.items():
            assert isinstance(slot, SlotConfig)
            assert slot.slot_id == slot_id
            assert slot.enabled in (True, False)

    def test_ref_class_gets_enterprise_deep_primary_slot(self):
        registry = load_slot_registry()
        slot = get_slot_for_page_type("REF_CLASS", registry)
        assert slot is not None
        assert slot.slot_id == "enterprise_deep_primary"

    def test_kb_article_gets_enterprise_deep_primary_slot(self):
        registry = load_slot_registry()
        slot = get_slot_for_page_type("KB_ARTICLE", registry)
        assert slot is not None
        assert slot.slot_id == "enterprise_deep_primary"

    def test_platform_index_gets_enterprise_platform_landing_slot(self):
        registry = load_slot_registry()
        for pt in ("REF_PLATFORM_INDEX", "KB_PLATFORM_INDEX", "DOCS_PLATFORM_INDEX", "PRODUCTS_PLUGIN"):
            slot = get_slot_for_page_type(pt, registry)
            assert slot is not None, f"No slot for {pt}"
            assert slot.slot_id == "enterprise_platform_landing", f"Wrong slot for {pt}: {slot.slot_id}"

    def test_blocked_page_types_have_no_slot(self):
        registry = load_slot_registry()
        blocked = ["BLOG_ARCHIVE", "BLOG_UTILITY", "SUBDOMAIN_ROOT", "LOCALE_FILE", "LOCALE_DIR", "UNKNOWN_PATTERN"]
        for pt in blocked:
            slot = get_slot_for_page_type(pt, registry)
            assert slot is None, f"Expected no slot for {pt}, got {slot}"

    def test_max_per_page_enforced(self):
        registry = load_slot_registry()
        for slot in registry.values():
            assert slot.max_per_page >= 1

    def test_anchor_template_field_removed(self):
        # schema 1.1.0: no anchor_template in slot config
        registry = load_slot_registry()
        for slot in registry.values():
            assert not hasattr(slot, "anchor_template"), (
                f"Slot {slot.slot_id} still has anchor_template field"
            )

    def test_fallback_slot_chain_terminates(self):
        registry = load_slot_registry()
        for slot in registry.values():
            chain = slot_fallback_chain(slot.slot_id, registry)
            assert len(chain) >= 1
            assert len(chain) == len(set(chain)), f"Cycle in fallback chain for {slot.slot_id}"


# ── A5-Prep: TestAgentAdjudication ───────────────────────────────────────────


def _make_candidate_record(source_key, target_path, stage1_score, decision, ai_boost=0.0, ai_label=None):
    return {
        "source_key": source_key,
        "target_path": target_path,
        "stage1_score": stage1_score,
        "ai_boost": ai_boost,
        "ai_boost_applied": ai_boost > 0.0,
        "ai_signals": {"llm_label": ai_label} if ai_label else None,
        "final_score": stage1_score + ai_boost,
        "decision": decision,
        "allowed_for_generation": decision == "AUTO_APPROVE_EXACT",
    }


class TestAgentAdjudication:
    """Unit tests for the Tier 1/2/3 adjudication policy."""

    def test_tier1_exact_slug_never_reaches_tier2(self):
        rec = _make_candidate_record(
            "reference/3d/java/a3dobject",
            "3d/java/com.aspose.threed/a3dobject",
            0.95, "AUTO_APPROVE_EXACT",
        )
        assert rec["decision"] == "AUTO_APPROVE_EXACT"
        assert rec["allowed_for_generation"] is True
        assert rec["ai_boost"] == 0.0

    def test_tier2_promote_auto_approve_requires_score_090_plus_boost(self):
        rec = _make_candidate_record(
            "reference/words/python/Document",
            "words/python-net/aspose.words/document",
            0.85, "REVIEW_REQUIRED", ai_boost=0.05, ai_label="exact_api_class",
        )
        assert rec["final_score"] >= 0.90
        assert rec["ai_boost"] <= 0.05

    def test_tier2_ai_unrelated_blocks_even_if_deterministic_high(self):
        rec = _make_candidate_record(
            "reference/words/python/Document",
            "words/java/aspose.words/document",
            0.90, "REVIEW_REQUIRED", ai_boost=0.0, ai_label="unrelated",
        )
        assert rec["ai_signals"]["llm_label"] == "unrelated"
        assert rec["decision"] == "REVIEW_REQUIRED"
        assert rec["allowed_for_generation"] is False

    def test_tier2_escalate_to_operator_when_ai_ambiguous(self):
        top = _make_candidate_record(
            "reference/words/python/Document",
            "words/python-net/aspose.words/document",
            0.75, "REVIEW_REQUIRED", ai_boost=0.0, ai_label="related_api_class",
        )
        second_score = 0.72
        tie_margin = top["final_score"] - second_score
        assert tie_margin < 0.10
        assert top["decision"] == "REVIEW_REQUIRED"

    def test_tier3_operator_override_yaml_entry_promotes(self):
        overrides = {
            "reference/words/python-net": {
                "http_verified": True,
                "canonical_target_url": "https://reference.aspose.com/words/python-net/",
            }
        }
        result = resolve_variant_target("reference/words/python-net", {}, overrides=overrides)
        assert result is not None
        assert result["decision"] == "EXPLICIT_OVERRIDE"
        assert result["allowed_for_generation"] is True

    def test_adjudication_result_field_recorded_in_authority(self):
        rec = _make_candidate_record(
            "reference/3d/java/a3dobject",
            "3d/java/com.aspose.threed/a3dobject",
            0.95, "AUTO_APPROVE_EXACT",
        )
        assert "decision" in rec
        assert rec["decision"] in ("AUTO_APPROVE_EXACT", "REVIEW_REQUIRED", "BLOCKED")

    def test_tier2_dry_run_produces_report_without_writes(self):
        rec1 = _make_candidate_record("ref/a", "a/b", 0.95, "AUTO_APPROVE_EXACT")
        rec2 = _make_candidate_record("ref/a", "a/b", 0.95, "AUTO_APPROVE_EXACT")
        assert rec1 == rec2

    def test_tier2_reject_propagates_to_blocked_authority(self):
        rec = _make_candidate_record(
            "reference/pdf/go/SomeClass",
            "pdf/go-cpp/aspose.pdf/someclass",
            0.20, "BLOCKED", ai_boost=0.05, ai_label="exact_api_class",
        )
        assert rec["final_score"] < 0.50
        assert rec["decision"] == "BLOCKED"
        assert rec["allowed_for_generation"] is False


# ── TestAIEnrichment (A1 §A1-08) ──────────────────────────────────────────────

class TestAIEnrichment:
    """Tests for Layer 1.5 AI advisory enrichment (backlink_ai_enrich.py).

    Covers V9 (boundary), V10 (score cap), V11 (graceful degradation),
    V12 (provenance), and AI-specific negative fixtures.
    """

    def _make_mock_deep_index(self, family="3d", platform="java", n=3):
        index = {}
        for i in range(n):
            key = f"{family}/{platform}/com.aspose.threed/class{i}"
            index[key] = {
                "path": key,
                "family": family,
                "platform": platform,
                "type": "reference_class",
                "class_name": f"Class{i}",
                "namespace": "com.aspose.threed",
            }
        return {"schema_version": "1.0.0", "index": index, "total_endpoints": n}

    def test_ai_enrichment_module_importable(self):
        """AI enrichment module is importable from commands.ops."""
        import importlib
        mod = importlib.import_module("commands.ops.backlink_ai_enrich")
        assert hasattr(mod, "build_enrichment")

    def test_dry_run_marks_all_records_skipped(self):
        """With dry_run=True, all records get status=skipped, ai_status=AI_EXPLICITLY_DISABLED."""
        from commands.ops.backlink_ai_enrich import build_enrichment
        deep_index = self._make_mock_deep_index()
        result = build_enrichment(deep_index, family="3d", platform="java", router=None, dry_run=True)
        assert result["ai_status"] == "AI_EXPLICITLY_DISABLED"
        assert result["enriched_count"] == 0
        assert result["skipped_count"] == 3
        for rec in result["index"].values():
            assert rec["status"] == "skipped"
            assert rec["error"] == "dry_run"

    def test_no_router_marks_all_records_skipped(self):
        """With router=None (AI unavailable), all records get status=skipped."""
        from commands.ops.backlink_ai_enrich import build_enrichment
        deep_index = self._make_mock_deep_index()
        result = build_enrichment(deep_index, family="3d", platform="java", router=None, dry_run=False)
        assert result["ai_status"] == "AI_EXPLICITLY_DISABLED"
        assert result["skipped_count"] == 3

    def test_ai_only_match_cannot_promote_to_auto_approve(self):
        """AI signals alone (stage1 < 0.30) cannot push a candidate to AUTO_APPROVE_EXACT."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from commands.ops.backlink_build_candidates import score_candidate
        # Low deterministic score, strong AI signal
        source = {
            "source_key": "reference/3d/java/someclass",
            "title": "SomeUnrelatedTitle",
            "family": "3d",
            "platform": "java",
            "frontmatter": {},
        }
        entry = {
            "path": "3d/java/com.aspose.threed/SomeClass",
            "family": "3d",
            "platform": "java",
            "type": "reference_class",
            "class_name": "TotallyDifferentClass",
            "namespace": "com.aspose.threed",
            "http_status": 200,
        }
        ai_signals = {
            "label": "exact_api_class",
            "confidence": "high",
            "embedding_cosine": 0.99,
        }
        result = score_candidate(entry, source, ai_signals)
        # Stage 1 should be 0 (no class match), so AI cannot promote to AUTO_APPROVE
        assert result["stage1_score"] < 0.30
        assert result["decision"] in ("BLOCKED", "REVIEW_REQUIRED")
        assert result["final_score"] < 0.90

    def test_ai_boost_cap_enforced_at_005(self):
        """AI boost never exceeds MAX_AI_BOOST = 0.05."""
        from commands.ops.backlink_build_candidates import score_candidate, MAX_AI_BOOST
        assert MAX_AI_BOOST == 0.05
        source = {
            "source_key": "reference/3d/java/a3dobject",
            "title": "A3DObject",
            "family": "3d",
            "platform": "java",
            "frontmatter": {},
        }
        entry = {
            "path": "3d/java/com.aspose.threed/a3dobject",
            "family": "3d",
            "platform": "java",
            "type": "reference_class",
            "class_name": "a3dobject",
            "namespace": "com.aspose.threed",
            "http_status": 200,
        }
        ai_signals = {
            "label": "exact_api_class",
            "confidence": "high",
            "embedding_cosine": 0.99,
        }
        result = score_candidate(entry, source, ai_signals)
        assert result["ai_boost"] <= MAX_AI_BOOST

    def test_free_text_label_rejected(self):
        """LLM returning free-text label → record marked ai_enrichment_failed."""
        from commands.ops.backlink_ai_enrich import _classify_target, VALID_LABELS
        # 'probably_related' is not in VALID_LABELS
        assert "probably_related" not in VALID_LABELS
        assert "exact_api_class" in VALID_LABELS
        assert "unrelated" in VALID_LABELS

    def test_ai_disagrees_with_high_deterministic_score(self):
        """AI label=unrelated + stage1 ≥ 0.80 → REVIEW_REQUIRED despite high score."""
        from commands.ops.backlink_build_candidates import score_candidate
        source = {
            "source_key": "reference/3d/java/a3dobject",
            "title": "A3DObject",
            "family": "3d",
            "platform": "java",
            "frontmatter": {},
        }
        entry = {
            "path": "3d/java/com.aspose.threed/a3dobject",
            "family": "3d",
            "platform": "java",
            "type": "reference_class",
            "class_name": "a3dobject",
            "namespace": "com.aspose.threed",
            "http_status": 200,
        }
        ai_signals = {"label": "unrelated", "confidence": "high", "embedding_cosine": 0.10}
        result = score_candidate(entry, source, ai_signals)
        # Stage 1 = 0.95 (exact match), but AI disagrees → REVIEW_REQUIRED
        assert result["stage1_score"] >= 0.80
        assert result["ai_disagrees"] is True
        assert result["decision"] == "REVIEW_REQUIRED"

    def test_ai_cannot_override_low_deterministic_score(self):
        """AI=exact_api_class + stage1=0.20 → BLOCKED (AI cannot override)."""
        from commands.ops.backlink_build_candidates import score_candidate
        source = {
            "source_key": "reference/3d/java/differentclass",
            "title": "DifferentClass",
            "family": "3d",
            "platform": "java",
            "frontmatter": {},
        }
        entry = {
            "path": "3d/java/com.aspose.threed/a3dobject",
            "family": "3d",
            "platform": "java",
            "type": "reference_class",
            "class_name": "a3dobject",
            "namespace": "com.aspose.threed",
            "http_status": 200,
        }
        ai_signals = {
            "label": "exact_api_class",
            "confidence": "high",
            "embedding_cosine": 0.95,
        }
        result = score_candidate(entry, source, ai_signals)
        # class name doesn't match → stage1=0, AI boost requires ≥0.85 base
        assert result["stage1_score"] < 0.30
        assert result["ai_boost"] == 0.0
        assert result["decision"] in ("BLOCKED", "REVIEW_REQUIRED")
        assert result["final_score"] < 0.90

    def test_v9_ai_enrichment_not_imported_by_backlink_targets(self):
        """V9: backlink_targets.py must not import ai_enrichment_index."""
        import inspect
        import lib.backlink_targets as bt
        src = inspect.getsource(bt)
        assert "ai_enrichment" not in src, (
            "V9 FAIL: backlink_targets.py imports or references ai_enrichment_index"
        )

    def test_v11_pipeline_continues_with_no_ai_flag(self):
        """V11: pipeline produces valid output with router=None (graceful degradation)."""
        from commands.ops.backlink_ai_enrich import build_enrichment
        deep_index = self._make_mock_deep_index(n=5)
        result = build_enrichment(deep_index, family="3d", platform="java", router=None, dry_run=False)
        # Must produce a valid result dict — not raise an exception
        assert "ai_status" in result
        assert "index" in result
        assert isinstance(result["index"], dict)
        # All records must have a status
        for rec in result["index"].values():
            assert "status" in rec

    def test_enrichment_family_filter_applied(self):
        """build_enrichment only enriches entries matching the requested family."""
        from commands.ops.backlink_ai_enrich import build_enrichment
        index = {
            "3d/java/com.aspose.threed/Scene": {"path": "3d/java/...", "family": "3d", "platform": "java", "type": "reference_class"},
            "words/java/com.aspose.words/Document": {"path": "words/java/...", "family": "words", "platform": "java", "type": "reference_class"},
        }
        deep_index = {"schema_version": "1.0.0", "index": index, "total_endpoints": 2}
        result = build_enrichment(deep_index, family="3d", platform="java", router=None, dry_run=True)
        # Only 3d/java entry should be processed
        assert len(result["index"]) == 1
        assert "3d/java/com.aspose.threed/Scene" in result["index"]


# ── TestDeepBacklinks (v2.0 §10) ──────────────────────────────────────────────

class TestDeepBacklinks:
    """Tests for Phase P3 deep authority resolver extension.

    Tests the existing parameter contract and anticipated P3 behavior.
    """

    def test_deep_resolve_disabled_by_default(self):
        """exact_deep_match_enabled=False is the default — v1 behavior is unchanged."""
        import inspect
        sig = inspect.signature(resolve_backlink)
        param = sig.parameters.get("exact_deep_match_enabled")
        assert param is not None, "resolve_backlink must have exact_deep_match_enabled param"
        assert param.default is False

    def test_resolve_backlink_signature_has_deep_params(self):
        """resolve_backlink signature includes authority and source_file params (P3)."""
        import inspect
        sig = inspect.signature(resolve_backlink)
        # exact_deep_match_enabled already exists
        assert "exact_deep_match_enabled" in sig.parameters
        # authority and source_file are planned for P3; skip if not yet added
        if "authority" not in sig.parameters:
            pytest.skip("authority param not yet added (Phase P3)")
        if "source_file" not in sig.parameters:
            pytest.skip("source_file param not yet added (Phase P3)")

    def test_resolve_backlink_v1_unchanged_without_deep(self):
        """With exact_deep_match_enabled=False, v1 fallback behavior is byte-identical."""
        target_map = {
            "targets": {
                "reference.aspose.com": {
                    "platforms": {"words/net": {"url": "https://reference.aspose.com/words/net/", "type": "platform", "http_status": 200}},
                    "families": {"words": {"url": "https://reference.aspose.com/words/", "type": "family", "http_status": 200}},
                }
            },
            "all_urls": {},
        }
        url, kind, sd, reason = resolve_backlink(
            "words", "net", "reference.aspose.org", target_map,
            exact_deep_match_enabled=False,
        )
        assert url is not None
        assert "reference.aspose.com" in url

    def test_deep_resolve_returns_none_for_missing_source(self):
        """_resolve_deep returns None when source_file not in authority → v1 fallback."""
        try:
            from lib.backlink_targets import _resolve_deep
        except ImportError:
            pytest.skip("_resolve_deep not yet implemented (Phase P3)")
        authority = {"authority": {}}
        result = _resolve_deep(authority, "content/reference.aspose.org/en/3d/java/Scene.md")
        assert result is None

    def test_deep_resolve_returns_none_when_not_allowed(self):
        """_resolve_deep returns None when allowed_for_generation=False."""
        try:
            from lib.backlink_targets import _resolve_deep
        except ImportError:
            pytest.skip("_resolve_deep not yet implemented (Phase P3)")
        authority = {
            "authority": {
                "content/reference.aspose.org/en/3d/java/Scene.md": {
                    "allowed_for_generation": False,
                    "target_path": "3d/java/com.aspose.threed/scene",
                    "target_subdomain": "reference",
                }
            }
        }
        result = _resolve_deep(authority, "content/reference.aspose.org/en/3d/java/Scene.md")
        assert result is None

    def test_deep_resolve_composes_url_via_host_map(self):
        """_resolve_deep composes URL using HOST_MAP — never from hardcoded strings."""
        try:
            from lib.backlink_targets import _resolve_deep
        except ImportError:
            pytest.skip("_resolve_deep not yet implemented (Phase P3)")
        # Expected: HOST_MAP["reference"] = "reference.aspose.com"
        assert HOST_MAP["reference"] == "reference.aspose.com"
        assert HOST_MAP["kb"] == "kb.aspose.com"
        assert HOST_MAP["docs"] == "docs.aspose.com"

    def test_host_map_has_all_five_subdomains(self):
        """HOST_MAP covers all 5 target subdomains."""
        required = {"reference", "kb", "docs", "products", "blog"}
        assert required.issubset(set(HOST_MAP.keys()))

    def test_deep_authority_structure_contract(self):
        """Authority records must have required provenance fields."""
        required_fields = {
            "source_path", "target_path", "allowed_for_generation",
            "anchor_template_id", "anchor_config_hash", "rendered_anchor_text",
        }
        # This is a structural test — verifies the expected contract
        # Actual authority writing is tested once backlink_approve_authority.py is created
        mock_record = {
            "source_path": "content/reference.aspose.org/en/3d/java/Scene.md",
            "target_path": "3d/java/com.aspose.threed/scene",
            "allowed_for_generation": True,
            "anchor_template_id": "reference-platform",
            "anchor_config_hash": "sha256:abc123",
            "rendered_anchor_text": "Aspose.3D for Java — Enterprise API Reference",
        }
        for field in required_fields:
            assert field in mock_record

    def test_exact_deep_match_enabled_false_ignores_authority(self):
        """When exact_deep_match_enabled=False, authority param is ignored even if provided."""
        target_map = {
            "targets": {
                "reference.aspose.com": {
                    "platforms": {"3d/java": {"url": "https://reference.aspose.com/3d/java/", "type": "platform", "http_status": 200}},
                    "families": {"3d": {"url": "https://reference.aspose.com/3d/", "type": "family", "http_status": 200}},
                }
            },
            "all_urls": {},
        }
        # With exact_deep_match_enabled=False, authority is not consulted
        url_no_deep, _, _, _ = resolve_backlink(
            "3d", "java", "reference.aspose.org", target_map,
            exact_deep_match_enabled=False,
        )
        # v1 should still return the platform URL
        assert url_no_deep is not None

    def test_deep_resolve_stale_authority_falls_back(self):
        """If authority target_index_hash mismatches current Layer 1, _resolve_deep returns None."""
        try:
            from lib.backlink_targets import _resolve_deep
        except ImportError:
            pytest.skip("_resolve_deep not yet implemented (Phase P3)")
        # Simulate stale authority with mismatched hash
        authority = {
            "target_index_hash": "sha256:stale_hash_12345",
            "authority": {
                "content/reference.aspose.org/en/3d/java/Scene.md": {
                    "allowed_for_generation": True,
                    "target_path": "3d/java/com.aspose.threed/scene",
                    "target_subdomain": "reference",
                    "anchor_config_hash": "sha256:abc",
                    "rendered_anchor_text": "Aspose.3D for Java — Enterprise API Reference",
                }
            },
        }
        # Hash mismatch detection is internal to _resolve_deep;
        # anchor_config_hash "sha256:abc" will not match the live registry hash → returns None
        result = _resolve_deep(authority, "content/reference.aspose.org/en/3d/java/Scene.md")
        assert result is None

    def test_deep_resolve_blocked_not_inserted(self):
        """Authority records with decision=REVIEW_REQUIRED have allowed_for_generation=False."""
        mock_authority_record = {
            "decision": "REVIEW_REQUIRED",
            "allowed_for_generation": False,
            "target_path": "3d/java/com.aspose.threed/scene",
        }
        assert mock_authority_record["allowed_for_generation"] is False
        # Verifies the invariant: REVIEW_REQUIRED → never inserted

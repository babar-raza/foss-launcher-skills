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
    classify_page_type,
    resolve_backlink,
    count_qualifying_com_links,
    classify_compliance,
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

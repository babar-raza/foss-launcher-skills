"""Tests for content_discovery.py — pure functions and fixture-based discovery.

Covers:
  - infer_product: pure function, path parsing across all 5 sites
  - discover_content: uses temp directory fixture
  - discover_products: uses temp directory fixture
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from content_discovery import discover_content, discover_products, infer_product
import content_discovery as _cd


@pytest.fixture(autouse=True)
def _reset_cd():
    yield
    _cd.configure()


# ---------------------------------------------------------------------------
# infer_product — pure function (path parsing)
# ---------------------------------------------------------------------------

class TestInferProduct:
    def test_docs_site_en_path(self):
        p = Path("/repo/content/docs.aspose.org/en/cells/python/index.md")
        family, platform = infer_product(p)
        assert family == "cells"
        assert platform == "python"

    def test_blog_site_no_en(self):
        p = Path("/repo/content/blog.aspose.org/cells/python/post.md")
        family, platform = infer_product(p)
        assert family == "cells"
        assert platform == "python"

    def test_kb_site_en_path(self):
        p = Path("/repo/content/kb.aspose.org/en/words/java/article.md")
        family, platform = infer_product(p)
        assert family == "words"
        assert platform == "java"

    def test_products_site(self):
        p = Path("/repo/content/products.aspose.org/en/pdf/net/page.md")
        family, platform = infer_product(p)
        assert family == "pdf"
        assert platform == "net"

    def test_reference_site(self):
        p = Path("/repo/content/reference.aspose.org/en/slides/cpp/api.md")
        family, platform = infer_product(p)
        assert family == "slides"
        assert platform == "cpp"

    def test_unknown_site_returns_none(self):
        p = Path("/some/unrelated/path/file.md")
        family, platform = infer_product(p)
        assert family is None
        assert platform is None

    def test_site_with_no_platform_returns_none(self):
        # Only one component after stripping "en" — not enough
        p = Path("/repo/content/docs.aspose.org/en/cells")
        family, platform = infer_product(p)
        assert family is None
        assert platform is None

    def test_platform_map_applied(self):
        """PLATFORM_MAP is currently empty, so platform passes through unchanged."""
        p = Path("/repo/content/docs.aspose.org/en/cells/net/index.md")
        family, platform = infer_product(p)
        assert family == "cells"
        assert platform == "net"

    def test_returns_tuple(self):
        p = Path("/repo/content/docs.aspose.org/en/cells/python/index.md")
        result = infer_product(p)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# discover_content — fixture-based
# ---------------------------------------------------------------------------

class TestDiscoverContent:
    def test_returns_list(self, tmp_path):
        with patch.object(_cd, "SITE_PATHS", []):
            result = discover_content("cells", "python")
        assert isinstance(result, list)

    def test_empty_when_no_paths_exist(self, tmp_path):
        with patch.object(_cd, "SITE_PATHS", [
            ("docs.aspose.org", str(tmp_path / "nonexistent/{family}/{platform}")),
        ]):
            result = discover_content("cells", "python")
        assert result == []

    def test_finds_md_files(self, tmp_path):
        site_dir = tmp_path / "cells" / "python"
        site_dir.mkdir(parents=True)
        (site_dir / "index.md").write_text("# Index")
        (site_dir / "guide.md").write_text("# Guide")
        (site_dir / "data.json").write_text("{}")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs.aspose.org", pattern)]):
            result = discover_content("cells", "python")

        md_names = {f.name for f in result}
        assert "index.md" in md_names
        assert "guide.md" in md_names
        assert "data.json" not in md_names

    def test_skips_locale_files(self, tmp_path):
        site_dir = tmp_path / "cells" / "python"
        site_dir.mkdir(parents=True)
        (site_dir / "index.md").write_text("# English")
        (site_dir / "index.fr.md").write_text("# French")
        (site_dir / "index.de.md").write_text("# German")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs.aspose.org", pattern)]):
            result = discover_content("cells", "python")

        names = {f.name for f in result}
        assert "index.md" in names
        assert "index.fr.md" not in names
        assert "index.de.md" not in names

    def test_recurses_subdirectories(self, tmp_path):
        sub = tmp_path / "cells" / "python" / "subdir"
        sub.mkdir(parents=True)
        (sub / "nested.md").write_text("# Nested")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs.aspose.org", pattern)]):
            result = discover_content("cells", "python")

        names = {f.name for f in result}
        assert "nested.md" in names

    def test_aggregates_across_multiple_sites(self, tmp_path):
        for site in ("site1", "site2"):
            d = tmp_path / site / "cells" / "python"
            d.mkdir(parents=True)
            (d / f"{site}.md").write_text(f"# {site}")

        patterns = [
            ("site1", str(tmp_path / "site1/{family}/{platform}")),
            ("site2", str(tmp_path / "site2/{family}/{platform}")),
        ]
        with patch.object(_cd, "SITE_PATHS", patterns):
            result = discover_content("cells", "python")

        names = {f.name for f in result}
        assert "site1.md" in names
        assert "site2.md" in names


# ---------------------------------------------------------------------------
# discover_products — fixture-based
# ---------------------------------------------------------------------------

class TestDiscoverProducts:
    def test_returns_list(self, tmp_path):
        _cd.configure(knowledge_root=tmp_path)
        result = discover_products()
        assert isinstance(result, list)

    def test_empty_when_no_knowledge_root(self, tmp_path):
        empty = tmp_path / "empty_knowledge"
        empty.mkdir()
        _cd.configure(knowledge_root=empty)
        result = discover_products()
        assert result == []

    def test_finds_product_with_api_surface(self, tmp_path):
        merged = tmp_path / "cells" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("[]")

        _cd.configure(knowledge_root=tmp_path)
        result = discover_products()

        assert ("cells", "python") in result

    def test_skips_without_api_surface(self, tmp_path):
        merged = tmp_path / "cells" / "python" / "merged"
        merged.mkdir(parents=True)
        # No api_surface.json

        _cd.configure(knowledge_root=tmp_path)
        result = discover_products()

        assert ("cells", "python") not in result

    def test_skips_underscore_family(self, tmp_path):
        merged = tmp_path / "_internal" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("[]")

        _cd.configure(knowledge_root=tmp_path)
        result = discover_products()

        families = {f for f, _ in result}
        assert "_internal" not in families

    def test_multiple_products(self, tmp_path):
        for family, platform in [("cells", "python"), ("words", "java"), ("pdf", "net")]:
            merged = tmp_path / family / platform / "merged"
            merged.mkdir(parents=True)
            (merged / "api_surface.json").write_text("[]")

        _cd.configure(knowledge_root=tmp_path)
        result = discover_products()

        assert len(result) == 3
        assert ("cells", "python") in result
        assert ("words", "java") in result
        assert ("pdf", "net") in result

    def test_results_are_sorted(self, tmp_path):
        for family, platform in [("words", "python"), ("cells", "java"), ("cells", "python")]:
            merged = tmp_path / family / platform / "merged"
            merged.mkdir(parents=True)
            (merged / "api_surface.json").write_text("[]")

        _cd.configure(knowledge_root=tmp_path)
        result = discover_products()

        # Sorted by family dir first, then platform dir
        families = [f for f, _ in result]
        assert families == sorted(families)


# ---------------------------------------------------------------------------
# Migration complete (R-1b) — symbols now live only in content_discovery
# ---------------------------------------------------------------------------

class TestMigrationComplete:
    def test_discover_content_not_in_knowledge_core(self):
        """R-1b: re-export stubs removed; knowledge_core no longer exports this."""
        import importlib
        import knowledge_core as kc
        assert not hasattr(kc, "discover_content")

    def test_discover_products_not_in_knowledge_core(self):
        """R-1b: re-export stubs removed."""
        import knowledge_core as kc
        assert not hasattr(kc, "discover_products")

    def test_infer_product_not_in_knowledge_core(self):
        """R-1b: re-export stubs removed."""
        import knowledge_core as kc
        assert not hasattr(kc, "infer_product")

    def test_canonical_imports_still_work(self):
        """Canonical imports from content_discovery remain functional."""
        from content_discovery import discover_content, discover_products, infer_product
        assert callable(discover_content)
        assert callable(discover_products)
        assert callable(infer_product)


# ---------------------------------------------------------------------------
# skip_drafts — ST-020 draft filter
# ---------------------------------------------------------------------------

class TestDiscoverContentSkipDrafts:
    def _make_md(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_skip_drafts_false_includes_draft_pages(self, tmp_path):
        """Default behaviour: draft pages are included (backward compat)."""
        site = tmp_path / "cells" / "python"
        site.mkdir(parents=True)
        self._make_md(site / "draft_page.md", "---\ntitle: T\ndraft: true\n---\nBody.\n")
        self._make_md(site / "normal.md", "---\ntitle: N\n---\nBody.\n")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs", pattern)]):
            result = discover_content("cells", "python", skip_drafts=False)

        names = {f.name for f in result}
        assert "draft_page.md" in names
        assert "normal.md" in names

    def test_skip_drafts_true_excludes_draft_pages(self, tmp_path):
        """skip_drafts=True removes files with draft: true."""
        site = tmp_path / "cells" / "python"
        site.mkdir(parents=True)
        self._make_md(site / "draft_page.md", "---\ntitle: T\ndraft: true\n---\nBody.\n")
        self._make_md(site / "normal.md", "---\ntitle: N\n---\nBody.\n")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs", pattern)]):
            result = discover_content("cells", "python", skip_drafts=True)

        names = {f.name for f in result}
        assert "draft_page.md" not in names
        assert "normal.md" in names

    def test_skip_drafts_false_is_default(self, tmp_path):
        """Calling without skip_drafts includes draft pages (backward compat)."""
        site = tmp_path / "cells" / "python"
        site.mkdir(parents=True)
        self._make_md(site / "draft_page.md", "---\ntitle: T\ndraft: true\n---\nBody.\n")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs", pattern)]):
            result_default = discover_content("cells", "python")
            result_explicit = discover_content("cells", "python", skip_drafts=False)

        assert {f.name for f in result_default} == {f.name for f in result_explicit}

    def test_draft_false_not_excluded(self, tmp_path):
        """Pages with draft: false are not excluded by skip_drafts."""
        site = tmp_path / "cells" / "python"
        site.mkdir(parents=True)
        self._make_md(site / "not_draft.md", "---\ntitle: N\ndraft: false\n---\nBody.\n")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs", pattern)]):
            result = discover_content("cells", "python", skip_drafts=True)

        names = {f.name for f in result}
        assert "not_draft.md" in names

    def test_no_frontmatter_not_excluded(self, tmp_path):
        """Files without frontmatter are not excluded by skip_drafts."""
        site = tmp_path / "cells" / "python"
        site.mkdir(parents=True)
        self._make_md(site / "no_fm.md", "# Just a heading\nBody.\n")

        pattern = str(tmp_path / "{family}/{platform}")
        with patch.object(_cd, "SITE_PATHS", [("docs", pattern)]):
            result = discover_content("cells", "python", skip_drafts=True)

        names = {f.name for f in result}
        assert "no_fm.md" in names

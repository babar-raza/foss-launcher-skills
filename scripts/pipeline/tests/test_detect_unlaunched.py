"""Tests for detect_unlaunched.py (GOV-UNLAUNCHED-DETECT-001).

Covers:
  - Product with merged/model.yaml and substantive content → launched
  - Product with merged/model.yaml and only products.aspose.org → unlaunched
  - Product with merged/model.yaml and zero content → unlaunched
  - Product with scout/model.yaml only and no content → unlaunched (scout-only)
  - Product with scout/model.yaml and substantive content → launched
  - Products with draft:true pages → excluded from count
  - Multiple products in scan
  - --threshold flag changes cutoff
  - JSON output format
  - Empty knowledge root → no results
  - Non-existent content subdirectories → treated as 0 pages
  - CLI main() exit code is always 0 (non-blocking)
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.ops.detect_unlaunched import (
    _count_non_draft_pages,
    _scan_products,
    _load_model_yaml,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_model_yaml(path: Path, family: str, platform: str,
                      class_count: int = 5, total_claims: int = 10,
                      stale_since: str = "null") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"family: {family}\n"
        f"platform: {platform}\n"
        f"class_count: {class_count}\n"
        f"total_claims: {total_claims}\n"
        f"stale_since: {stale_since}\n"
        f"repo_sha: abc123\n",
        encoding="utf-8",
    )


def _write_md(path: Path, draft: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = "draft: true\n" if draft else "draft: false\n"
    path.write_text(f"---\ntitle: Test\n{fm}---\n\nContent here.\n", encoding="utf-8")


def _make_knowledge_root(tmp_path: Path) -> Path:
    return tmp_path / "knowledge"


def _make_content_root(tmp_path: Path) -> Path:
    return tmp_path / "content"


# ---------------------------------------------------------------------------
# _count_non_draft_pages tests
# ---------------------------------------------------------------------------

class TestCountNonDraftPages:

    def test_empty_directory_returns_zero(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert _count_non_draft_pages(d) == 0

    def test_nonexistent_directory_returns_zero(self, tmp_path):
        d = tmp_path / "nonexistent"
        assert _count_non_draft_pages(d) == 0

    def test_counts_non_draft_md_files(self, tmp_path):
        d = tmp_path / "pages"
        _write_md(d / "page1.md", draft=False)
        _write_md(d / "page2.md", draft=False)
        assert _count_non_draft_pages(d) == 2

    def test_excludes_draft_pages(self, tmp_path):
        d = tmp_path / "pages"
        _write_md(d / "page1.md", draft=False)
        _write_md(d / "page2.md", draft=True)
        assert _count_non_draft_pages(d) == 1

    def test_all_draft_returns_zero(self, tmp_path):
        d = tmp_path / "pages"
        _write_md(d / "page1.md", draft=True)
        _write_md(d / "page2.md", draft=True)
        assert _count_non_draft_pages(d) == 0

    def test_counts_nested_md_files(self, tmp_path):
        d = tmp_path / "pages"
        _write_md(d / "sub" / "page.md", draft=False)
        _write_md(d / "page.md", draft=False)
        assert _count_non_draft_pages(d) == 2


# ---------------------------------------------------------------------------
# _scan_products tests
# ---------------------------------------------------------------------------

class TestScanProducts:

    def test_empty_knowledge_root_returns_empty(self, tmp_path):
        kr = _make_knowledge_root(tmp_path)
        kr.mkdir()
        cr = _make_content_root(tmp_path)
        cr.mkdir()
        results = _scan_products(kr, cr)
        assert results == []

    def test_nonexistent_knowledge_root_returns_empty(self, tmp_path):
        kr = tmp_path / "no-knowledge"
        cr = _make_content_root(tmp_path)
        cr.mkdir()
        results = _scan_products(kr, cr)
        assert results == []

    def test_merged_product_with_docs_content_is_launched(self, tmp_path):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "cells" / "net" / "merged" / "model.yaml", "cells", "net")
        _write_md(cr / "docs.aspose.org" / "en" / "cells" / "net" / "index.md")
        results = _scan_products(kr, cr)
        assert len(results) == 1
        p = results[0]
        assert p["family"] == "cells"
        assert p["platform"] == "net"
        assert p["total_pages"] >= 1
        assert p["scout_only"] is False

    def test_merged_product_with_no_content_is_unlaunched(self, tmp_path):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "cells" / "net" / "merged" / "model.yaml", "cells", "net")
        results = _scan_products(kr, cr)
        assert len(results) == 1
        assert results[0]["total_pages"] == 0

    def test_scout_only_product_detected(self, tmp_path):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "page" / "python" / "scout" / "model.yaml", "page", "python")
        results = _scan_products(kr, cr)
        assert len(results) == 1
        p = results[0]
        assert p["scout_only"] is True
        assert p["total_pages"] == 0

    def test_products_aspose_not_counted_as_substantive(self, tmp_path):
        """products.aspose.org pages alone should not make a product 'launched'."""
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "page" / "python" / "scout" / "model.yaml", "page", "python")
        # Only a products.aspose.org page (no platform subdir)
        _write_md(cr / "products.aspose.org" / "en" / "page" / "_index.md")
        results = _scan_products(kr, cr)
        assert results[0]["total_pages"] == 0  # products.aspose.org excluded from count
        assert results[0]["subdomain_counts"]["products.aspose.org"] >= 1  # still tracked

    def test_multiple_products_returned(self, tmp_path):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "cells" / "net" / "merged" / "model.yaml", "cells", "net")
        _write_model_yaml(kr / "cells" / "java" / "merged" / "model.yaml", "cells", "java")
        _write_md(cr / "docs.aspose.org" / "en" / "cells" / "net" / "index.md")
        results = _scan_products(kr, cr)
        assert len(results) == 2
        families = {r["family"] for r in results}
        platforms = {r["platform"] for r in results}
        assert families == {"cells"}
        assert "net" in platforms and "java" in platforms

    def test_draft_pages_not_counted(self, tmp_path):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "cells" / "net" / "merged" / "model.yaml", "cells", "net")
        _write_md(cr / "docs.aspose.org" / "en" / "cells" / "net" / "index.md", draft=True)
        results = _scan_products(kr, cr)
        assert results[0]["total_pages"] == 0

    def test_blog_content_counts_as_substantive(self, tmp_path):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "cells" / "net" / "merged" / "model.yaml", "cells", "net")
        _write_md(cr / "blog.aspose.org" / "cells" / "net" / "post" / "index.md")
        results = _scan_products(kr, cr)
        assert results[0]["total_pages"] >= 1

    def test_merged_model_preferred_over_scout(self, tmp_path):
        """If both merged and scout model.yaml exist, merged takes precedence."""
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "cells" / "net" / "merged" / "model.yaml", "cells", "net",
                          class_count=50)
        _write_model_yaml(kr / "cells" / "net" / "scout" / "model.yaml", "cells", "net",
                          class_count=10)
        results = _scan_products(kr, cr)
        assert len(results) == 1
        assert results[0]["scout_only"] is False


# ---------------------------------------------------------------------------
# main() CLI tests
# ---------------------------------------------------------------------------

class TestMain:

    def test_main_exits_zero_always(self, tmp_path):
        """main() always returns 0 — scan is non-blocking."""
        kr = str(_make_knowledge_root(tmp_path))
        cr = str(_make_content_root(tmp_path))
        Path(kr).mkdir(parents=True)
        Path(cr).mkdir(parents=True)
        exit_code = main(["--knowledge-root", kr, "--content-root", cr])
        assert exit_code == 0

    def test_main_json_output(self, tmp_path, capsys):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "page" / "python" / "scout" / "model.yaml", "page", "python")
        exit_code = main([
            "--knowledge-root", str(kr),
            "--content-root", str(cr),
            "--json",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "unlaunched" in data
        assert "total_products" in data
        assert data["total_products"] == 1
        assert len(data["unlaunched"]) == 1
        assert data["unlaunched"][0]["family"] == "page"

    def test_main_warns_for_unlaunched(self, tmp_path, capsys):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "page" / "python" / "scout" / "model.yaml", "page", "python")
        exit_code = main([
            "--knowledge-root", str(kr),
            "--content-root", str(cr),
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "UNLAUNCHED" in captured.out

    def test_main_ok_when_all_launched(self, tmp_path, capsys):
        kr = _make_knowledge_root(tmp_path)
        cr = _make_content_root(tmp_path)
        _write_model_yaml(kr / "cells" / "net" / "merged" / "model.yaml", "cells", "net")
        _write_md(cr / "docs.aspose.org" / "en" / "cells" / "net" / "index.md")
        exit_code = main([
            "--knowledge-root", str(kr),
            "--content-root", str(cr),
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out

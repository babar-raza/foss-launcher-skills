"""Tests for locale evidence-staleness detection (Task 11d, §9.8, closes G8/sizes F7).

Verifies --include-locales is purely additive: the default (English-scoped) scan
and CLI behavior are provably unchanged, and the new locale-scoped detector
correctly sizes staleness across all 5 surfaces (directory-locale: docs/kb/
products/reference; filename-locale: blog) without blocking or remediating
anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from stale_detect import (
    discover_locale_content_files,
    main,
    scan_product,
    scan_product_locales,
)


def _write_page(path: Path, model_sha: str | None, extra_frontmatter: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if model_sha is None:
        evidence_block = ""
    else:
        evidence_block = f"evidence:\n  model_sha: {model_sha}\n"
    path.write_text(
        f"---\ntitle: Test\n{evidence_block}{extra_frontmatter}---\n\nBody.\n",
        encoding="utf-8",
    )


def _setup_knowledge(tmp_path: Path, repo_sha: str) -> None:
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    (merged / "claims.json").write_text("[]", encoding="utf-8")
    (merged / "model.yaml").write_text(
        yaml.safe_dump({"repo_sha": repo_sha, "version": "1.0"}), encoding="utf-8"
    )


class TestDiscoverLocaleContentFiles:
    def test_finds_directory_locale_files_across_all_four_surfaces(self, tmp_path):
        content = tmp_path / "content"
        for site in ("docs.aspose.org", "kb.aspose.org", "products.aspose.org", "reference.aspose.org"):
            _write_page(content / site / "fr" / "fake" / "python" / "page.md", "old_sha")
        by_surface = discover_locale_content_files(content, "fake", "python")
        assert len(by_surface["docs"]) == 1
        assert len(by_surface["kb"]) == 1
        assert len(by_surface["products"]) == 1
        assert len(by_surface["reference"]) == 1

    def test_english_directory_is_never_treated_as_locale(self, tmp_path):
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "en" / "fake" / "python" / "page.md", "old_sha")
        by_surface = discover_locale_content_files(content, "fake", "python")
        assert by_surface["docs"] == []

    def test_unknown_top_level_directory_is_not_treated_as_locale(self, tmp_path):
        content = tmp_path / "content"
        # A non-locale directory name (e.g. an accidental stray dir) must be ignored.
        _write_page(content / "docs.aspose.org" / "_scratch" / "fake" / "python" / "page.md", "old_sha")
        by_surface = discover_locale_content_files(content, "fake", "python")
        assert by_surface["docs"] == []

    def test_finds_blog_filename_suffix_locale_files_only(self, tmp_path):
        content = tmp_path / "content"
        blog_dir = content / "blog.aspose.org" / "fake" / "python" / "my-post"
        _write_page(blog_dir / "index.md", "old_sha")  # English -- must be excluded
        _write_page(blog_dir / "index.fr.md", "old_sha")  # locale -- must be included
        _write_page(blog_dir / "index.de.md", "old_sha")  # locale -- must be included
        by_surface = discover_locale_content_files(content, "fake", "python")
        assert len(by_surface["blog"]) == 2
        names = {p.name for p in by_surface["blog"]}
        assert names == {"index.fr.md", "index.de.md"}

    def test_draft_locale_pages_are_excluded(self, tmp_path):
        content = tmp_path / "content"
        _write_page(
            content / "docs.aspose.org" / "fr" / "fake" / "python" / "page.md",
            "old_sha",
            extra_frontmatter="draft: true\n",
        )
        by_surface = discover_locale_content_files(content, "fake", "python")
        assert by_surface["docs"] == []

    def test_missing_site_directory_yields_empty_list_not_error(self, tmp_path):
        content = tmp_path / "content"
        by_surface = discover_locale_content_files(content, "fake", "python")
        assert by_surface == {"docs": [], "kb": [], "products": [], "reference": [], "blog": []}


class TestScanProductLocales:
    def test_stale_and_fresh_locale_files_counted_correctly_by_surface(self, tmp_path):
        _setup_knowledge(tmp_path, repo_sha="current_sha")
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "fr" / "fake" / "python" / "a.md", "current_sha")
        _write_page(content / "docs.aspose.org" / "de" / "fake" / "python" / "b.md", "ancient_sha")
        _write_page(content / "kb.aspose.org" / "fr" / "fake" / "python" / "c.md", "ancient_sha")

        report = scan_product_locales(
            "fake", "python",
            content_root=content, knowledge_root=tmp_path / "knowledge",
        )
        assert report["knowledge_repo_sha"] == "current_sha"
        assert report["surfaces"]["docs"]["total"] == 2
        assert report["surfaces"]["docs"]["stale"] == 1
        assert report["surfaces"]["kb"]["total"] == 1
        assert report["surfaces"]["kb"]["stale"] == 1
        assert report["total_locale_files"] == 3
        assert report["total_stale"] == 2
        assert str(content / "docs.aspose.org" / "de" / "fake" / "python" / "b.md") in report["surfaces"]["docs"]["files"]

    def test_missing_model_sha_counts_as_stale(self, tmp_path):
        _setup_knowledge(tmp_path, repo_sha="current_sha")
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "fr" / "fake" / "python" / "a.md", model_sha=None)
        report = scan_product_locales(
            "fake", "python",
            content_root=content, knowledge_root=tmp_path / "knowledge",
        )
        assert report["surfaces"]["docs"]["stale"] == 1

    def test_no_locale_content_yields_zero_totals_not_error(self, tmp_path):
        _setup_knowledge(tmp_path, repo_sha="current_sha")
        report = scan_product_locales(
            "fake", "python",
            content_root=tmp_path / "content", knowledge_root=tmp_path / "knowledge",
        )
        assert report["total_locale_files"] == 0
        assert report["total_stale"] == 0

    def test_missing_knowledge_model_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            scan_product_locales(
                "fake", "python",
                content_root=tmp_path / "content", knowledge_root=tmp_path / "knowledge",
            )


class TestScanProductLocalesCaching:
    def test_same_repo_sha_reuses_cached_report_without_rescanning(self, tmp_path):
        _setup_knowledge(tmp_path, repo_sha="sha_a")
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "fr" / "fake" / "python" / "a.md", "old_sha")
        report_root = tmp_path / "reports" / "locale_staleness"

        first = scan_product_locales(
            "fake", "python",
            content_root=content, knowledge_root=tmp_path / "knowledge",
            report_root=report_root,
        )
        assert first["total_locale_files"] == 1
        # Write the cache file exactly where scan_product_locales expects to find it
        # (mirrors what the CLI/verify_run call site does after computing a result).
        report_root.mkdir(parents=True, exist_ok=True)
        (report_root / "fake-python.json").write_text(json.dumps(first), encoding="utf-8")

        # Add a second locale file on disk -- if the cache were bypassed, the next
        # call would see 2 files instead of 1.
        _write_page(content / "docs.aspose.org" / "de" / "fake" / "python" / "b.md", "old_sha")
        second = scan_product_locales(
            "fake", "python",
            content_root=content, knowledge_root=tmp_path / "knowledge",
            report_root=report_root,
        )
        assert second["total_locale_files"] == 1  # cache hit -- rescans not triggered

    def test_force_true_always_rescans_ignoring_cache(self, tmp_path):
        _setup_knowledge(tmp_path, repo_sha="sha_a")
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "fr" / "fake" / "python" / "a.md", "old_sha")
        report_root = tmp_path / "reports" / "locale_staleness"
        report_root.mkdir(parents=True)
        (report_root / "fake-python.json").write_text(
            json.dumps({"knowledge_repo_sha": "sha_a", "total_locale_files": 999, "total_stale": 999, "surfaces": {}}),
            encoding="utf-8",
        )

        result = scan_product_locales(
            "fake", "python",
            content_root=content, knowledge_root=tmp_path / "knowledge",
            report_root=report_root, force=True,
        )
        assert result["total_locale_files"] == 1  # real scan, cache ignored

    def test_different_repo_sha_invalidates_cache(self, tmp_path):
        _setup_knowledge(tmp_path, repo_sha="sha_b")  # knowledge has moved on
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "fr" / "fake" / "python" / "a.md", "old_sha")
        report_root = tmp_path / "reports" / "locale_staleness"
        report_root.mkdir(parents=True)
        (report_root / "fake-python.json").write_text(
            json.dumps({"knowledge_repo_sha": "sha_a", "total_locale_files": 999, "total_stale": 999, "surfaces": {}}),
            encoding="utf-8",
        )

        result = scan_product_locales(
            "fake", "python",
            content_root=content, knowledge_root=tmp_path / "knowledge",
            report_root=report_root,
        )
        assert result["total_locale_files"] == 1  # stale cache (old sha) correctly ignored
        assert result["knowledge_repo_sha"] == "sha_b"


class TestExistingBehaviorUnchanged:
    def test_scan_product_never_sees_locale_files(self, tmp_path):
        """Negative control: locale files must never leak into the English-scoped
        default scan_product() path -- --include-locales is purely additive."""
        _setup_knowledge(tmp_path, repo_sha="current_sha")
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "en" / "fake" / "python" / "a.md", "current_sha")
        _write_page(content / "docs.aspose.org" / "fr" / "fake" / "python" / "b.md", "ancient_sha")
        blog_dir = content / "blog.aspose.org" / "fake" / "python" / "post"
        _write_page(blog_dir / "index.md", "current_sha")
        _write_page(blog_dir / "index.fr.md", "ancient_sha")

        report = scan_product("fake", "python", content_root=content, knowledge_root=tmp_path / "knowledge")
        assert report["files_scanned"] == 2  # only the two English pages
        assert report["stale_pages"] == 0  # both English pages match repo_sha


class TestCLI:
    def test_default_cli_never_writes_locale_report(self, tmp_path, monkeypatch):
        _setup_knowledge(tmp_path, repo_sha="sha1")
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "en" / "fake" / "python" / "a.md", "sha1")
        monkeypatch.chdir(tmp_path)
        exit_code = main([
            "fake", "python",
            "--content-root", str(content),
            "--knowledge-root", str(tmp_path / "knowledge"),
            "--json",
        ])
        assert exit_code == 0
        assert not (tmp_path / "reports" / "locale_staleness").exists()

    def test_include_locales_writes_report_and_preserves_exit_code(self, tmp_path, monkeypatch):
        _setup_knowledge(tmp_path, repo_sha="sha1")
        content = tmp_path / "content"
        _write_page(content / "docs.aspose.org" / "en" / "fake" / "python" / "a.md", "sha1")
        _write_page(content / "docs.aspose.org" / "fr" / "fake" / "python" / "b.md", "old_sha")
        monkeypatch.chdir(tmp_path)
        exit_code = main([
            "fake", "python",
            "--content-root", str(content),
            "--knowledge-root", str(tmp_path / "knowledge"),
            "--json", "--include-locales",
        ])
        # English scope is clean (repo_sha matches) -- exit code reflects ONLY the
        # English-scoped result, never locale staleness (detection-only, no gate).
        assert exit_code == 0
        report_path = tmp_path / "reports" / "locale_staleness" / "fake-python.json"
        assert report_path.exists()
        locale_report = json.loads(report_path.read_text(encoding="utf-8"))
        assert locale_report["total_locale_files"] == 1
        assert locale_report["total_stale"] == 1

"""Tests for link_validator._build_slug_index and validate_files.

Covers the two code paths added in the 2026-04-17 fix:
  - index.md leaf bundles: dir/index.md → /dir/  (was /dir/index/)
  - Hugo auto-section directories: every subdir → /dir/  (even without _index.md)

Uses tmp_path + monkeypatch to inject a minimal content tree without touching real content.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.pipeline.link_validator as lv


@pytest.fixture(autouse=True)
def _reset_lv():
    yield
    lv.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_content(tmp_path: Path, *rel_paths: str) -> Path:
    """Create a minimal content root under tmp_path with the given relative files."""
    content = tmp_path / "content"
    content.mkdir()
    for rel in rel_paths:
        p = content / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\ntitle: test\n---\n", encoding="utf-8")
    return content


def _index(content_root: Path) -> dict[str, set[str]]:
    """Set CONTENT_ROOT and return the slug index."""
    lv.configure(content_root=content_root)
    return lv._build_slug_index()


# ---------------------------------------------------------------------------
# Phase 1: markdown file slug derivation
# ---------------------------------------------------------------------------

class TestSlugFromMarkdownFiles:

    def test_underscore_index_md_becomes_parent_slug(self, tmp_path, monkeypatch):
        """_index.md inside a directory → slug is /dir/."""
        content = _make_content(tmp_path, "blog.aspose.org/note/python/my-post/_index.md")
        idx = _index(content)
        assert "/note/python/my-post/" in idx["blog.aspose.org"]
        assert "/note/python/my-post" in idx["blog.aspose.org"]

    def test_leaf_bundle_index_md_becomes_parent_slug(self, tmp_path, monkeypatch):
        """index.md (no underscore) leaf bundle → slug is /dir/, NOT /dir/index/."""
        content = _make_content(tmp_path, "blog.aspose.org/note/python/my-post/index.md")
        idx = _index(content)
        # Must be the parent directory slug
        assert "/note/python/my-post/" in idx["blog.aspose.org"]
        assert "/note/python/my-post" in idx["blog.aspose.org"]
        # Must NOT be the wrong /index/ slug
        assert "/note/python/my-post/index/" not in idx["blog.aspose.org"]
        assert "/note/python/my-post/index" not in idx["blog.aspose.org"]

    def test_bare_md_file_slug(self, tmp_path, monkeypatch):
        """A regular .md file → slug is /path/to/stem/."""
        content = _make_content(tmp_path, "docs.aspose.org/en/cells/python/developer-guide/features.md")
        idx = _index(content)
        # /en/ is stripped → /cells/python/developer-guide/features/
        assert "/cells/python/developer-guide/features/" in idx["docs.aspose.org"]

    def test_en_prefix_stripped_from_docs(self, tmp_path, monkeypatch):
        """/en/ prefix stripped so Hugo URL matches."""
        content = _make_content(tmp_path, "docs.aspose.org/en/cells/python/_index.md")
        idx = _index(content)
        assert "/cells/python/" in idx["docs.aspose.org"]
        # Raw /en/ path must NOT appear
        assert "/en/cells/python/" not in idx["docs.aspose.org"]

    def test_en_prefix_stripped_from_reference(self, tmp_path, monkeypatch):
        content = _make_content(tmp_path, "reference.aspose.org/en/words/python/Document.md")
        idx = _index(content)
        assert "/words/python/document/" in idx["reference.aspose.org"]

    def test_blog_no_en_prefix(self, tmp_path, monkeypatch):
        """Blog content has no /en/ prefix — slug stays as-is."""
        content = _make_content(tmp_path, "blog.aspose.org/cells/python/intro/index.md")
        idx = _index(content)
        assert "/cells/python/intro/" in idx["blog.aspose.org"]

    def test_unknown_subdomain_ignored(self, tmp_path, monkeypatch):
        """Files under unknown subdomains are not indexed."""
        content = _make_content(tmp_path, "other.aspose.org/some/file.md")
        idx = _index(content)
        assert "other.aspose.org" not in idx

    def test_trailing_slash_and_no_trailing_slash_both_added(self, tmp_path, monkeypatch):
        """Both /path/ and /path (no slash) are added for every slug."""
        content = _make_content(tmp_path, "kb.aspose.org/en/note/python/howto.md")
        idx = _index(content)
        slugs = idx["kb.aspose.org"]
        # At least one slug should have trailing slash and one without
        with_slash = {s for s in slugs if s.endswith("/")}
        without_slash = {s for s in slugs if not s.endswith("/")}
        assert len(with_slash) > 0
        assert len(without_slash) > 0


# ---------------------------------------------------------------------------
# Phase 2: Hugo auto-section directory slugs
# ---------------------------------------------------------------------------

class TestDirectoryAutoSlug:

    def test_directory_without_index_file_is_indexed(self, tmp_path, monkeypatch):
        """A directory containing only leaf files (no _index.md) → dir slug added."""
        content = _make_content(
            tmp_path,
            "blog.aspose.org/note/python/post-1/index.md",
            "blog.aspose.org/note/python/post-2/index.md",
        )
        idx = _index(content)
        # blog.aspose.org/note/python/ has no _index.md but should still be valid
        assert "/note/python/" in idx["blog.aspose.org"]
        assert "/note/python" in idx["blog.aspose.org"]

    def test_section_root_without_index_md_is_valid(self, tmp_path, monkeypatch):
        """Top-level section dir without _index.md is still indexed."""
        content = _make_content(tmp_path, "blog.aspose.org/cells/python/intro/index.md")
        idx = _index(content)
        # /cells/python/ must be valid even though there's no _index.md there
        assert "/cells/python/" in idx["blog.aspose.org"]

    def test_en_prefix_stripped_from_directory_slugs(self, tmp_path, monkeypatch):
        """Directories under /en/ have the prefix stripped in Phase 2."""
        content = _make_content(tmp_path, "docs.aspose.org/en/words/python/getting-started/quickstart.md")
        idx = _index(content)
        # Directory /en/words/python/getting-started/ → /words/python/getting-started/
        assert "/words/python/getting-started/" in idx["docs.aspose.org"]
        assert "/en/words/python/getting-started/" not in idx["docs.aspose.org"]


# ---------------------------------------------------------------------------
# End-to-end: validate_files
# ---------------------------------------------------------------------------

class TestValidateFiles:

    def test_valid_link_not_reported(self, tmp_path, monkeypatch):
        """A link to an existing slug produces no findings."""
        content = _make_content(
            tmp_path,
            "blog.aspose.org/note/python/parse-tables/index.md",
        )
        lv.configure(content_root=content)
        # Create a source file in a docs directory
        src_dir = content / "docs.aspose.org" / "en" / "note" / "python"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_file = src_dir / "tables.md"
        src_file.write_text(
            "See [blog post](https://blog.aspose.org/note/python/parse-tables/) for details.\n",
            encoding="utf-8",
        )
        idx = lv._build_slug_index()
        findings = lv.validate_files([src_file], idx)
        assert findings == [], f"Expected no findings but got: {findings}"

    def test_broken_link_reported(self, tmp_path, monkeypatch):
        """A link to a missing slug is reported as BROKEN."""
        content = tmp_path / "content"
        content.mkdir()
        lv.configure(content_root=content, repo_root=tmp_path)
        # No content files — empty index
        (content / "docs.aspose.org").mkdir()
        # Source file must be inside REPO_ROOT for relative_to() to work
        src_file = tmp_path / "source.md"
        src_file.write_text(
            "See [missing](https://blog.aspose.org/note/python/nonexistent-post/) for details.\n",
            encoding="utf-8",
        )
        idx = lv._build_slug_index()
        findings = lv.validate_files([src_file], idx)
        assert len(findings) == 1
        assert findings[0].level == "BROKEN"
        assert "blog.aspose.org" in findings[0].subdomain
        assert "nonexistent-post" in findings[0].slug

    def test_fragment_and_query_stripped_before_lookup(self, tmp_path, monkeypatch):
        """Anchors (#) and query params (?) are stripped before slug lookup."""
        content = _make_content(tmp_path, "docs.aspose.org/en/cells/python/features.md")
        lv.configure(content_root=content)
        src_dir = content / "kb.aspose.org" / "en" / "cells" / "python"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_file = src_dir / "howto.md"
        src_file.write_text(
            "See [features](https://docs.aspose.org/cells/python/features/#section) for more.\n",
            encoding="utf-8",
        )
        idx = lv._build_slug_index()
        findings = lv.validate_files([src_file], idx)
        assert findings == [], f"Fragment should be stripped; got: {findings}"

    def test_leaf_bundle_link_resolves(self, tmp_path, monkeypatch):
        """Regression: link to blog leaf bundle (index.md) resolves correctly."""
        content = _make_content(
            tmp_path,
            "blog.aspose.org/cells/python/introducing-cells-foss-python/index.md",
        )
        lv.configure(content_root=content)
        src_dir = content / "docs.aspose.org" / "en" / "cells" / "python"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_file = src_dir / "guide.md"
        src_file.write_text(
            "See [intro](https://blog.aspose.org/cells/python/introducing-cells-foss-python/) for details.\n",
            encoding="utf-8",
        )
        idx = lv._build_slug_index()
        findings = lv.validate_files([src_file], idx)
        assert findings == [], (
            "Leaf bundle link should resolve after index.md fix; "
            f"got: {findings}"
        )

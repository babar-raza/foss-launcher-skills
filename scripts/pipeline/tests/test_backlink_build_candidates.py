"""test_backlink_build_candidates.py — Tests for blog.aspose.org path support.

Tests cover:
- scan_source_page() with blog path (no /en/ segment) → correct family/platform
- scan_source_page() with reference path (has /en/) → existing behaviour unchanged
- Locale-variant filter: stem contains dot → skipped by rglob filter

Uses real content files already present in the repo (no tmp_path) to avoid
the REPO_ROOT.relative_to() constraint in scan_source_page().

Run:
    python -m pytest scripts/pipeline/tests/test_backlink_build_candidates.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make commands.ops importable
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from commands.ops.backlink_build_candidates import scan_source_page


# ── Real file anchors ─────────────────────────────────────────────────────────

_BLOG_FONT_PYTHON = (
    _REPO_ROOT / "content" / "blog.aspose.org" / "font" / "python"
    / "brotli-font-compression-python" / "index.md"
)

_BLOG_FONT_PYTHON_ALT = (
    _REPO_ROOT / "content" / "blog.aspose.org" / "font" / "python"
    / "ttf-fonts-in-python" / "index.md"
)

_REFERENCE_FONT_PYTHON = (
    _REPO_ROOT / "content" / "reference.aspose.org" / "en" / "font" / "python"
    / "_index.md"
)


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Required file missing: {path.relative_to(_REPO_ROOT)}")
    return path


# ── Tests: scan_source_page() blog path (no /en/) ────────────────────────────

class TestScanSourcePageBlogPath:
    """blog.aspose.org uses content/{subdomain}/{family}/{platform}/{slug}/index.md"""

    def test_blog_path_returns_correct_family(self):
        md = _require(_BLOG_FONT_PYTHON)
        result = scan_source_page(md)
        assert result is not None, "Expected non-None for blog path without /en/"
        assert result["family"] == "font"

    def test_blog_path_returns_correct_platform(self):
        md = _require(_BLOG_FONT_PYTHON)
        result = scan_source_page(md)
        assert result is not None
        assert result["platform"] == "python"

    def test_blog_path_returns_correct_subdomain(self):
        md = _require(_BLOG_FONT_PYTHON_ALT)
        result = scan_source_page(md)
        assert result is not None
        assert result["subdomain"] == "blog.aspose.org"

    def test_blog_path_source_key_has_no_en_segment(self):
        md = _require(_BLOG_FONT_PYTHON)
        result = scan_source_page(md)
        assert result is not None
        key_segments = result["source_key"].split("/")
        assert "en" not in key_segments, (
            f"source_key should not contain 'en': {result['source_key']}"
        )


# ── Tests: scan_source_page() reference path (/en/ present) ──────────────────

class TestScanSourcePageReferencePath:
    """reference.aspose.org uses content/{subdomain}/en/{family}/{platform}/..."""

    def test_reference_path_resolves_family(self):
        md = _require(_REFERENCE_FONT_PYTHON)
        result = scan_source_page(md)
        assert result is not None, "Expected non-None for reference path with /en/"
        assert result["family"] == "font"

    def test_reference_path_resolves_platform(self):
        md = _require(_REFERENCE_FONT_PYTHON)
        result = scan_source_page(md)
        assert result is not None
        assert result["platform"] == "python"


# ── Tests: locale file filter logic ──────────────────────────────────────────

class TestLocaleFileFilter:
    """Locale variants (index.ar.md) must be filtered before scan_source_page is called.
    The filter is: `if '.' in md_file.stem: continue`
    """

    def test_english_index_stem_has_no_dot(self):
        assert "." not in Path("index.md").stem

    def test_section_index_stem_has_no_dot(self):
        assert "." not in Path("_index.md").stem

    def test_arabic_locale_stem_has_dot(self):
        assert "." in Path("index.ar.md").stem

    def test_french_locale_stem_has_dot(self):
        assert "." in Path("index.fr.md").stem

    def test_chinese_hans_locale_stem_has_dot(self):
        assert "." in Path("index.zh-hans.md").stem

    def test_filter_separates_locale_from_english(self):
        all_files = [
            Path("index.md"),
            Path("_index.md"),
            Path("index.ar.md"),
            Path("index.fr.md"),
            Path("index.pt.md"),
            Path("index.zh-hans.md"),
        ]
        kept = [f for f in all_files if "." not in f.stem]
        skipped = [f for f in all_files if "." in f.stem]

        assert {f.name for f in kept} == {"index.md", "_index.md"}
        assert len(skipped) == 4, f"Expected 4 locale files skipped, got: {[f.name for f in skipped]}"

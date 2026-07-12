"""Tests for feature_list_extender.py (TC-07)."""
import json
import pytest
from pathlib import Path

from commands.content.feature_list_extender import (
    configure,
    _compute_class_importance,
    _is_english_path,
    _find_feature_list_pages,
    _extract_neighbouring_bullets,
    _find_first_bullet_position,
    extend_feature_page,
    R_DRY_RUN,
    R_NOOP,
    R_SKIPPED_LOCALE,
    R_SKIPPED_NO_CHANGE,
)


@pytest.fixture(autouse=True)
def reset_config():
    configure(repo_root=None, llm_router_class=None)
    yield
    configure(repo_root=None, llm_router_class=None)


# ── Fixtures ───────────────────────────────────────────────────────────────

def _make_feature_page(root: Path, family: str, platform: str, slug: str) -> Path:
    """Write a feature-list docs page using a slug keyword in the filename."""
    page_dir = root / "content" / "docs.aspose.org" / "en" / family / platform
    page_dir.mkdir(parents=True, exist_ok=True)
    # Use slug as filename so slug-keyword matching finds it (e.g. "features.md")
    page = page_dir / f"{slug}.md"
    page.write_text(
        "---\npage_role: feature-list\ntitle: Features\n---\n\n"
        "## Key Features\n\n"
        "- Load and save FBX files\n"
        "- Export to OBJ format\n"
        "- Work with scene graphs\n",
        encoding="utf-8",
    )
    return page


# ── _compute_class_importance ──────────────────────────────────────────────

class TestComputeClassImportance:
    def test_high_method_count_near_one(self):
        score = _compute_class_importance({"method_count": 20, "property_count": 5})
        assert score >= 0.9

    def test_zero_counts_low_score(self):
        score = _compute_class_importance({"method_count": 0, "property_count": 0})
        assert score < 0.5

    def test_has_doc_increases_score(self):
        without = _compute_class_importance({"method_count": 5, "property_count": 0})
        with_doc = _compute_class_importance(
            {"method_count": 5, "property_count": 0, "has_doc": True}
        )
        assert with_doc > without

    def test_single_method_reduces_score(self):
        # mc <= 1 and pc == 0 applies a penalty
        single = _compute_class_importance({"method_count": 1, "property_count": 0})
        multi = _compute_class_importance({"method_count": 5, "property_count": 0})
        assert single < multi


# ── _is_english_path ───────────────────────────────────────────────────────

class TestIsEnglishPath:
    def test_en_path_is_english(self, tmp_path):
        p = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "net" / "f.md"
        assert _is_english_path(p) is True

    def test_non_en_path_is_not_english(self, tmp_path):
        p = tmp_path / "content" / "docs.aspose.org" / "fr" / "3d" / "net" / "f.md"
        assert _is_english_path(p) is False

    def test_locale_suffix_is_not_english(self, tmp_path):
        p = tmp_path / "content" / "blog.aspose.org" / "3d" / "net" / "post" / "index.fr.md"
        assert _is_english_path(p) is False

    def test_no_locale_suffix_is_english(self, tmp_path):
        p = tmp_path / "content" / "blog.aspose.org" / "3d" / "net" / "post" / "index.md"
        assert _is_english_path(p) is True


# ── _extract_neighbouring_bullets ─────────────────────────────────────────

class TestExtractNeighbouringBullets:
    CONTENT = (
        "## Key Features\n\n"
        "- Bullet one\n"
        "- Bullet two\n"
        "- Bullet three\n"
        "- Bullet four\n"
        "- Bullet five\n"
    )

    def test_returns_up_to_n_bullets(self):
        pos = self.CONTENT.index("- Bullet")
        bullets = _extract_neighbouring_bullets(self.CONTENT, pos, n=3)
        assert len(bullets) <= 3

    def test_returns_list_of_strings(self):
        pos = self.CONTENT.index("- Bullet")
        bullets = _extract_neighbouring_bullets(self.CONTENT, pos, n=3)
        assert all(isinstance(b, str) for b in bullets)


# ── _find_first_bullet_position ───────────────────────────────────────────

class TestFindFirstBulletPosition:
    def test_finds_bullet(self):
        content = "# Title\n\n- First bullet\n- Second\n"
        pos = _find_first_bullet_position(content)
        # pos should be >= 0 (found), and should be less than len(content)
        assert 0 <= pos < len(content)

    def test_no_bullets_returns_end_of_content(self):
        content = "# Title\n\nNo bullets here.\n"
        pos = _find_first_bullet_position(content)
        # Returns len(content) when no bullet found
        assert pos == len(content)


# ── _find_feature_list_pages ───────────────────────────────────────────────

class TestFindFeatureListPages:
    def test_finds_feature_list_page(self, tmp_path):
        configure(repo_root=tmp_path)
        page = _make_feature_page(tmp_path, "3d", "net", "features")
        pages = _find_feature_list_pages("3d", "net", tmp_path)
        assert page in pages

    def test_ignores_non_feature_list_pages(self, tmp_path):
        configure(repo_root=tmp_path)
        dir_ = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "net" / "other"
        dir_.mkdir(parents=True, exist_ok=True)
        (dir_ / "index.md").write_text(
            "---\ntitle: Other\n---\n\n- Some bullet\n", encoding="utf-8"
        )
        pages = _find_feature_list_pages("3d", "net", tmp_path)
        assert not any("other" in str(p) for p in pages)


# ── extend_feature_page (dry-run) ─────────────────────────────────────────

class TestExtendFeaturePageDryRun:
    def _make_page(self, tmp_path: Path) -> Path:
        """Return a feature-list page at an English path."""
        page_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "net"
        page_dir.mkdir(parents=True, exist_ok=True)
        page = page_dir / "features.md"
        page.write_text(
            "---\npage_role: feature-list\ntitle: Features\n---\n\n"
            "## Key Features\n\n"
            "- Load and save FBX files\n"
            "- Export to OBJ format\n"
            "- Work with scene graphs\n",
            encoding="utf-8",
        )
        return page

    def test_dry_run_does_not_modify_file(self, tmp_path):
        configure(repo_root=tmp_path)
        page = self._make_page(tmp_path)
        original_text = page.read_text(encoding="utf-8")

        result = extend_feature_page(
            page_path=page,
            api_name="WatermarkAnnotation",
            claim_text="Adds a watermark to the document.",
            family="3d",
            platform="net",
            dry_run=True,
        )

        assert result["result"] == R_DRY_RUN
        assert page.read_text(encoding="utf-8") == original_text

    def test_already_mentioned_api_returns_skipped(self, tmp_path):
        configure(repo_root=tmp_path)
        page = self._make_page(tmp_path)
        # "FBX" is already in the page content
        result = extend_feature_page(
            page_path=page,
            api_name="FBX",
            claim_text="Load and save FBX files.",
            family="3d",
            platform="net",
            dry_run=True,
        )
        assert result["result"] == R_SKIPPED_NO_CHANGE


# ── English-only enforcement ───────────────────────────────────────────────

class TestEnglishOnlyEnforcement:
    def test_non_english_page_returns_skipped_locale(self, tmp_path):
        configure(repo_root=tmp_path)
        fr_dir = tmp_path / "content" / "docs.aspose.org" / "fr" / "3d" / "net"
        fr_dir.mkdir(parents=True, exist_ok=True)
        # locale-suffixed file is detected as non-English by _is_english_path
        fr_page = fr_dir / "features.fr.md"
        fr_page.write_text(
            "---\npage_role: feature-list\ntitle: Features\n---\n\n- Bullet\n",
            encoding="utf-8",
        )
        original = fr_page.read_text(encoding="utf-8")

        result = extend_feature_page(
            page_path=fr_page,
            api_name="SomeClass",
            claim_text="Does something.",
            family="3d",
            platform="net",
            dry_run=False,
        )
        # Non-English page must not be modified and must return SKIPPED_LOCALE
        assert result["result"] == R_SKIPPED_LOCALE
        assert fr_page.read_text(encoding="utf-8") == original

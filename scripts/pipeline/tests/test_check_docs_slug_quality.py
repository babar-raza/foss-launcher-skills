"""Tests for check_docs_slug_quality.py (SQ-08 / D1 check)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ci" / "checks"))
import check_docs_slug_quality as sq  # noqa: E402


# ---------------------------------------------------------------------------
# check_slug — D1 detection
# ---------------------------------------------------------------------------

class TestCheckSlugD1:
    """D1: single-token slug > 12 chars without hyphens."""

    def test_javascriptextensions_is_d1_fail(self):
        result = sq.check_slug("javascriptextensions")
        assert result is not None
        check_id, _ = result
        assert check_id == "D1"

    def test_logicalstructure_is_d1_fail(self):
        result = sq.check_slug("logicalstructure")
        assert result is not None
        check_id, _ = result
        assert check_id == "D1"

    def test_javascript_extensions_hyphenated_passes(self):
        assert sq.check_slug("javascript-extensions") is None

    def test_logical_structure_hyphenated_passes(self):
        assert sq.check_slug("logical-structure") is None

    def test_working_with_xml_processing_passes(self):
        assert sq.check_slug("working-with-xml-processing") is None

    def test_short_single_word_passes(self):
        # "parsing" is 7 chars < 12 — should pass
        assert sq.check_slug("parsing") is None

    def test_exactly_12_chars_no_hyphen_passes(self):
        # 12 chars exactly — boundary: NOT > 12, so should pass
        assert sq.check_slug("a" * 12) is None

    def test_13_chars_no_hyphen_fails(self):
        result = sq.check_slug("a" * 13)
        assert result is not None
        assert result[0] == "D1"


class TestCheckSlugSkips:
    """Structural pages and allowed long slugs must not be flagged."""

    def test_index_page_skipped(self):
        assert sq.check_slug("_index") is None

    def test_features_skipped(self):
        assert sq.check_slug("features") is None

    def test_installation_skipped(self):
        assert sq.check_slug("installation") is None

    def test_license_skipped(self):
        assert sq.check_slug("license") is None

    def test_quickstart_skipped(self):
        assert sq.check_slug("quickstart") is None

    def test_underscore_prefix_skipped(self):
        assert sq.check_slug("_sidebar") is None

    def test_linearization_allowed(self):
        # 14 chars, no hyphen — but in allowlist
        assert sq.check_slug("linearization") is None

    def test_configuration_allowed(self):
        assert sq.check_slug("configuration") is None

    def test_authentication_allowed(self):
        assert sq.check_slug("authentication") is None

    def test_authorization_allowed(self):
        assert sq.check_slug("authorization") is None


# ---------------------------------------------------------------------------
# _is_developer_guide_page
# ---------------------------------------------------------------------------

class TestIsDeveloperGuidePage:
    def test_developer_guide_page_detected(self):
        assert sq._is_developer_guide_page(
            "content/docs.aspose.org/en/pdf/net/developer-guide/javascriptextensions.md"
        ) is True

    def test_getting_started_page_not_matched(self):
        assert sq._is_developer_guide_page(
            "content/docs.aspose.org/en/pdf/net/getting-started/installation.md"
        ) is False

    def test_index_page_not_matched(self):
        assert sq._is_developer_guide_page(
            "content/docs.aspose.org/en/pdf/net/_index.md"
        ) is False

    def test_blog_page_not_matched(self):
        assert sq._is_developer_guide_page(
            "content/blog.aspose.org/pdf/net/some-post/index.md"
        ) is False


# ---------------------------------------------------------------------------
# check_files — staged-file mode
# ---------------------------------------------------------------------------

class TestCheckFiles:
    def test_returns_1_on_d1_file(self, tmp_path):
        # Create a fake directory structure with the path containing developer-guide
        p = tmp_path / "developer-guide" / "javascriptextensions.md"
        p.parent.mkdir(parents=True)
        p.write_text("---\ntitle: test\n---\n")
        result = sq.check_files([str(p)])
        assert result == 1

    def test_returns_0_on_good_file(self, tmp_path):
        p = tmp_path / "developer-guide" / "javascript-extensions.md"
        p.parent.mkdir(parents=True)
        p.write_text("---\ntitle: test\n---\n")
        result = sq.check_files([str(p)])
        assert result == 0

    def test_non_developer_guide_file_skipped(self, tmp_path):
        p = tmp_path / "getting-started" / "javascriptextensions.md"
        p.parent.mkdir(parents=True)
        p.write_text("---\ntitle: test\n---\n")
        result = sq.check_files([str(p)])
        assert result == 0

    def test_returns_0_on_empty_list(self):
        assert sq.check_files([]) == 0


# ---------------------------------------------------------------------------
# scan_root — full scan mode
# ---------------------------------------------------------------------------

class TestScanRoot:
    def _make_docs_tree(self, tmp_path: Path, slugs: list[str]) -> Path:
        """Create a minimal docs tree under tmp_path."""
        guide = tmp_path / "developer-guide"
        guide.mkdir(parents=True)
        for slug in slugs:
            (guide / f"{slug}.md").write_text(f"---\ntitle: {slug}\n---\n")
        return tmp_path

    def test_scan_finds_two_known_bad_slugs(self, tmp_path):
        self._make_docs_tree(tmp_path, [
            "javascriptextensions",
            "logicalstructure",
            "javascript-extensions",
            "logical-structure",
        ])
        failures = sq.scan_root(tmp_path)
        bad_slugs = {f[0].stem for f in failures}
        assert "javascriptextensions" in bad_slugs
        assert "logicalstructure" in bad_slugs

    def test_scan_ignores_good_slugs(self, tmp_path):
        self._make_docs_tree(tmp_path, [
            "working-with-formulas",
            "cell-formatting",
            "pivot-tables",
        ])
        failures = sq.scan_root(tmp_path)
        assert failures == []

    def test_scan_ignores_structural_pages(self, tmp_path):
        self._make_docs_tree(tmp_path, ["_index", "features", "installation"])
        failures = sq.scan_root(tmp_path)
        assert failures == []

    def test_scan_ignores_allowed_long_slugs(self, tmp_path):
        self._make_docs_tree(tmp_path, [
            "linearization", "configuration", "authentication", "authorization",
        ])
        failures = sq.scan_root(tmp_path)
        assert failures == []

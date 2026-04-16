"""Tests for version_claim_check and capability_claim_check evaluators.

Proves these evaluators correctly detect version and capability mismatches
using synthetic pages with known errors.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from content_eval.evaluators import _ensure_loaded, get_evaluator
from content_eval.models import Page


_ensure_loaded()


def _make_products_page(
    family: str, platform: str, frontmatter_extra: str = "", body: str = ""
) -> Page:
    """Create a synthetic products page with frontmatter content fields."""
    raw = textwrap.dedent(f"""\
        ---
        layout: plugin
        plugin_description: "Test product for {family}/{platform}"
        overview:
          enable: true
          content: |
            {frontmatter_extra}
        ---
        {body}
    """)
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8",
        prefix=f"products_{family}_{platform}_",
    ) as f:
        f.write(raw)
        f.flush()
        page = Page.load(Path(f.name))
        # Override inferred metadata since path won't match real structure
        page.family = family
        page.platform = platform
        page.subdomain = "products"
        return page


def _make_kb_page(family: str, platform: str, body: str) -> Page:
    """Create a synthetic KB page with body content."""
    raw = textwrap.dedent(f"""\
        ---
        title: "Test KB for {family}/{platform}"
        type: kb
        ---
        {body}
    """)
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8",
    ) as f:
        f.write(raw)
        f.flush()
        page = Page.load(Path(f.name))
        page.family = family
        page.platform = platform
        page.subdomain = "kb"
        return page


class TestVersionClaimCheck:

    def setup_method(self):
        self.evaluator = get_evaluator("version_claim_check")()

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_detects_java_version_mismatch(self, mock_req):
        """Should flag 'Java 11' when requirement is '21'."""
        mock_req.return_value = "21"
        page = _make_products_page("slides", "java",
            frontmatter_extra="This library requires Java 11 or later.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "VC"
        assert "11" in findings[0].message
        assert "21" in findings[0].message

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_correct_version_no_finding(self, mock_req):
        """Should NOT flag 'Java 21' when requirement is '21'."""
        mock_req.return_value = "21"
        page = _make_products_page("slides", "java",
            frontmatter_extra="This library requires Java 21 or later.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_detects_python_version_mismatch(self, mock_req):
        """Should flag 'Python 3.6' when requirement is '>=3.10'."""
        mock_req.return_value = ">=3.10"
        page = _make_kb_page("slides", "python",
            body="Requires Python 3.6 or later to run.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "VC"

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_detects_dotnet_version_mismatch(self, mock_req):
        """Should flag '.NET 8.0' when requirement is 'net10.0'."""
        mock_req.return_value = "net10.0"
        page = _make_products_page("3d", "net",
            frontmatter_extra="Built for .NET 8.0 applications.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "VC"

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_no_runtime_requirement_no_findings(self, mock_req):
        """No findings when runtime_requirement is empty."""
        mock_req.return_value = ""
        page = _make_products_page("slides", "java",
            frontmatter_extra="Requires Java 11.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_negation_context_skipped(self, mock_req):
        """Should NOT flag version in negation context."""
        mock_req.return_value = "21"
        page = _make_products_page("slides", "java",
            frontmatter_extra="This library does not require Java 11.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_severity_is_fail_on_products(self, mock_req):
        """Products pages should get FAIL severity."""
        mock_req.return_value = "21"
        page = _make_products_page("slides", "java",
            frontmatter_extra="Requires JDK 11.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].level == "FAIL"


class TestCapabilityClaimCheck:

    def setup_method(self):
        self.evaluator = get_evaluator("capability_claim_check")()

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_detects_false_export_claim(self, mock_formats):
        """Should flag 'export FBX' when FBX is import-only."""
        mock_formats.return_value = {"fbx": "import"}
        page = _make_products_page("3d", "java",
            frontmatter_extra="Export your scenes to FBX format easily.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "CF"
        assert "fbx" in findings[0].message.lower()

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_correct_import_claim_no_finding(self, mock_formats):
        """Should NOT flag 'import FBX' when FBX is import-only."""
        mock_formats.return_value = {"fbx": "import"}
        page = _make_products_page("3d", "java",
            frontmatter_extra="Load and import FBX files easily.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_detect_only_blocks_io_claims(self, mock_formats):
        """Should flag both import and export when direction is 'detect'."""
        mock_formats.return_value = {"ppt": "detect"}
        page = _make_products_page("slides", "java",
            frontmatter_extra="Load PPT files for processing.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_both_direction_allows_all(self, mock_formats):
        """Should NOT flag when format supports both directions."""
        mock_formats.return_value = {"obj": "both"}
        page = _make_products_page("3d", "java",
            frontmatter_extra="Import and export OBJ files.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_negation_skipped(self, mock_formats):
        """Should NOT flag when claim is negated."""
        mock_formats.return_value = {"fbx": "import"}
        page = _make_products_page("3d", "java",
            frontmatter_extra="FBX export is not supported.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_no_formats_no_findings(self, mock_formats):
        """No findings when formats.json is empty."""
        mock_formats.return_value = {}
        page = _make_products_page("3d", "java",
            frontmatter_extra="Export FBX files.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

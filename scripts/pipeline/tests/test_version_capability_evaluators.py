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


class TestCapabilityClaimCheckNormalization:
    """Regression tests for VBD-02: enum_only normalization and read(?!-only) regex gap."""

    def setup_method(self):
        self.evaluator = get_evaluator("capability_claim_check")()

    # ------------------------------------------------------------------
    # Gap 1: enum_only + functional:false must normalize to "none"
    # ------------------------------------------------------------------

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_enum_only_functional_false_import_claim_is_flagged(self, mock_formats):
        """enum_only+functional:false → direction='none'; claiming import must be flagged."""
        mock_formats.return_value = {"docx": "none"}
        page = _make_kb_page("words", "python",
            body="Load and parse DOCX files using the library.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "CF"

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_enum_only_functional_true_import_claim_not_flagged(self, mock_formats):
        """enum_only+functional:true → direction='import'; claiming import must NOT be flagged."""
        mock_formats.return_value = {"tsv": "import"}
        page = _make_kb_page("cells", "python",
            body="Load and parse TSV files for analysis.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_load_formats_enum_only_functional_false_normalizes_to_none(self):
        """_load_formats must normalize enum_only+functional:false to 'none'."""
        import json
        import tempfile
        from pathlib import Path
        import content_eval.evaluators.capability_claim_check as mod

        data = [{"format": "docx", "direction": "enum_only", "functional": False}]
        with tempfile.TemporaryDirectory() as tmp:
            merged = Path(tmp) / "knowledge" / "words" / "python" / "merged"
            merged.mkdir(parents=True)
            (merged / "formats.json").write_text(json.dumps(data), encoding="utf-8")
            original_root = mod.KNOWLEDGE_ROOT
            mod.KNOWLEDGE_ROOT = Path(tmp) / "knowledge"
            try:
                result = mod._load_formats("words", "python")
            finally:
                mod.KNOWLEDGE_ROOT = original_root
        assert result.get("docx") == "none"

    def test_load_formats_enum_only_no_functional_normalizes_to_import(self):
        """_load_formats must normalize enum_only (no functional field) to 'import'."""
        import json
        import tempfile
        from pathlib import Path
        import content_eval.evaluators.capability_claim_check as mod

        data = [{"format": "tsv", "direction": "enum_only"}]
        with tempfile.TemporaryDirectory() as tmp:
            merged = Path(tmp) / "knowledge" / "cells" / "python" / "merged"
            merged.mkdir(parents=True)
            (merged / "formats.json").write_text(json.dumps(data), encoding="utf-8")
            original_root = mod.KNOWLEDGE_ROOT
            mod.KNOWLEDGE_ROOT = Path(tmp) / "knowledge"
            try:
                result = mod._load_formats("cells", "python")
            finally:
                mod.KNOWLEDGE_ROOT = original_root
        assert result.get("tsv") == "import"

    def test_load_formats_none_aware_merge_keeps_functional_direction(self):
        """When two entries exist — first 'none', second 'import' — result must be 'import'."""
        import json
        import tempfile
        from pathlib import Path
        import content_eval.evaluators.capability_claim_check as mod

        data = [
            {"format": "docx", "direction": "enum_only", "functional": False},
            {"format": "docx", "direction": "import"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            merged = Path(tmp) / "knowledge" / "words" / "python" / "merged"
            merged.mkdir(parents=True)
            (merged / "formats.json").write_text(json.dumps(data), encoding="utf-8")
            original_root = mod.KNOWLEDGE_ROOT
            mod.KNOWLEDGE_ROOT = Path(tmp) / "knowledge"
            try:
                result = mod._load_formats("words", "python")
            finally:
                mod.KNOWLEDGE_ROOT = original_root
        assert result.get("docx") == "import"

    # ------------------------------------------------------------------
    # Gap 2: read(?!-only) — "read-only" must not trigger import claim
    # ------------------------------------------------------------------

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_read_only_phrase_does_not_trigger_import_claim(self, mock_formats):
        """'read-only' must not be parsed as an import verb — no false positive."""
        mock_formats.return_value = {"doc": "export"}
        page = _make_kb_page("words", "python",
            body="The DOC format is read-only in this context.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_read_verb_alone_still_triggers_import_claim(self, mock_formats):
        """Plain 'read' (not 'read-only') must still match as an import verb."""
        mock_formats.return_value = {"doc": "export"}
        page = _make_kb_page("words", "python",
            body="Read and process DOC files from the filesystem.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "CF"

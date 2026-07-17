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

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_severity_is_fail_on_kb(self, mock_req):
        """KB pages should get FAIL severity (upgraded from WARN — ISSUE-02)."""
        mock_req.return_value = ">=3.10"
        page = _make_kb_page("font", "python",
            body="Make sure Python 3.8 is installed before running this example.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].level == "FAIL", (
            f"Expected FAIL for KB page version mismatch, got {findings[0].level}"
        )

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_detects_python_version_in_faq_answer(self, mock_req):
        """Wrong version in faq.list[].answer must be detected (ISSUE-02 regression)."""
        mock_req.return_value = ">=3.10"
        raw = textwrap.dedent("""\
            ---
            layout: plugin
            faq:
              enable: true
              list:
                - question: "What Python version is required?"
                  answer: "This library requires Python 3.8 or later."
            ---
        """)
        import tempfile as _tf
        with _tf.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8",
            prefix="products_font_python_faq_",
        ) as f:
            f.write(raw)
            f.flush()
            from content_eval.models import Page as _Page
            page = _Page.load(Path(f.name))
            page.family = "font"
            page.platform = "python"
            page.subdomain = "products"
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1, (
            "Expected VC finding for wrong version in faq.list[].answer — ISSUE-02"
        )
        assert any("3.8" in f.message or "3.10" in f.message for f in findings)

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_netstandard2_compat_with_dotnet6(self, mock_req):
        """netstandard2.0 target is compatible with .NET 6.0 — no finding (TC-VERSION-CLAIM-FP)."""
        mock_req.return_value = "netstandard2.0"
        page = _make_products_page("cells", "net",
            frontmatter_extra="Supports .NET 6.0 and .NET 8.0 applications.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0, (
            f"Expected no findings for .NET 6.0/8.0 with netstandard2.0 target, got {findings}"
        )

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_net8_forward_compat_with_net9(self, mock_req):
        """net8.0 target is forward-compatible with .NET 9.0 runtime — no finding."""
        mock_req.return_value = "net8.0"
        page = _make_products_page("email", "net",
            frontmatter_extra="Works with .NET 9.0 applications.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0, (
            f"Expected no findings for .NET 9.0 with net8.0 target (forward compat), got {findings}"
        )

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_upgrade_context_skipped(self, mock_req):
        """Upgrade-context mention should be skipped by negation regex."""
        mock_req.return_value = ">=3.10"
        page = _make_kb_page("email", "python",
            body="If you are on Python 3.9 or earlier, upgrade to 3.10.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0, (
            f"Expected no findings for upgrade-context mention, got {findings}"
        )

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_dotnet_downgrade_still_flagged(self, mock_req):
        """.NET 7.0 claim with net8.0 target must still be flagged (downgrade)."""
        mock_req.return_value = "net8.0"
        page = _make_products_page("email", "net",
            frontmatter_extra="Built for .NET 7.0 applications.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1, (
            "Expected FAIL for .NET 7.0 with net8.0 target (downgrade claim)"
        )
        assert findings[0].category == "VC"

    @patch("content_eval.evaluators.version_claim_check._load_runtime_requirement")
    def test_correct_version_in_faq_answer_passes(self, mock_req):
        """Correct version in faq.list[].answer must not be flagged."""
        mock_req.return_value = ">=3.10"
        raw = textwrap.dedent("""\
            ---
            layout: plugin
            faq:
              enable: true
              list:
                - question: "What Python version is required?"
                  answer: "This library requires Python 3.10 or later."
            ---
        """)
        import tempfile as _tf
        with _tf.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8",
            prefix="products_font_python_faq_ok_",
        ) as f:
            f.write(raw)
            f.flush()
            from content_eval.models import Page as _Page
            page = _Page.load(Path(f.name))
            page.family = "font"
            page.platform = "python"
            page.subdomain = "products"
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0, (
            f"Expected no findings for correct version in faq.list[].answer, got {findings}"
        )


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

    # --- ST-029 regression: identifier-as-format false positives (RPR-J-09) ---

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_st029_doc_variable_member_access_not_flagged(self, mock_formats):
        """`doc.Save(ms)` / `doc.ToArray()` is a member access on a variable named `doc`,
        NOT a claim that the DOC (Word) format is exported. Must produce NO CF finding even
        though DOC is enum_only/none. (Measured: 39 such FPs across 19 pdf/net pages.)"""
        mock_formats.return_value = {"doc": "none"}
        page = _make_kb_page("pdf", "net",
            "When reading back from a `MemoryStream` after `doc.Save(ms)`, reset the position. "
            "You can also call `doc.ToArray()` to serialise the current state.")
        findings = self.evaluator.evaluate(page, None)
        assert findings == [], f"variable member access must not be a format claim; got {findings}"

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_st029_genuine_doc_export_claim_still_flagged(self, mock_formats):
        """The fix must NOT suppress a REAL false capability claim: prose that actually claims
        DOC export when DOC is not exportable must still fire (no over-correction)."""
        mock_formats.return_value = {"doc": "none"}
        page = _make_kb_page("pdf", "net",
            "The library can export your document to DOC format for editing in Word.")
        findings = self.evaluator.evaluate(page, None)
        assert any(f.category == "CF" and "doc" in f.message.lower() for f in findings), (
            f"a genuine false DOC-export claim must still be flagged; got {findings}")

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


class TestFormatTruthCheck:
    """Regression tests for ST-029 patterns (2) and (3) in format_truth.py (RPR-J-09)."""

    def setup_method(self):
        self.evaluator = get_evaluator("format_truth")()

    # --- ST-029 pattern (2): product-name + negation ---

    @patch("content_eval.evaluators.format_truth._load_formats")
    def test_st029_aspose_pdf_dotnet_negation_not_flagged(self, mock_formats):
        """Real sentence: 'Aspose.PDF FOSS ... does not support .NET Framework,
        .NET Standard' was misread as 'PDF format is not supported' — the
        negated subject is the .NET runtime, not the PDF format. formats.json
        genuinely shows pdf as fully supported ('both'); must produce NO
        finding for it."""
        mock_formats.return_value = {"pdf": "both"}
        page = _make_kb_page("pdf", "net",
            "Aspose.PDF FOSS for .NET does not support .NET Framework, .NET Standard "
            "runtimes older than the minimum required version.")
        findings = self.evaluator.evaluate(page, None)
        assert not any("pdf" in f.message.lower() for f in findings), (
            f"Aspose.PDF product-name mention must not be read as a format negation; got {findings}")

    @patch("content_eval.evaluators.format_truth._load_formats")
    def test_st029_genuine_pdf_negation_still_flagged(self, mock_formats):
        """The fix must NOT suppress a REAL false negative-limitation claim:
        prose that genuinely says the PDF format itself is unsupported, with
        no 'Aspose.' product-name prefix, must still fire."""
        mock_formats.return_value = {"pdf": "both"}
        page = _make_kb_page("pdf", "net",
            "Note that PDF is not supported in this configuration.")
        findings = self.evaluator.evaluate(page, None)
        assert any("pdf" in f.message.lower() for f in findings), (
            f"a genuine false PDF-unsupported claim must still be flagged; got {findings}")

    # --- ST-029 pattern (3): export-framing read as bidirectional ---

    @patch("content_eval.evaluators.format_truth._load_formats")
    def test_st029_image_output_supports_is_export_only(self, mock_formats):
        """The exact real sentence from content/kb.aspose.org/en/pdf/net/faq.md:206
        (a single line holding an EARLIER, unrelated 'reads and writes the PDF
        format' clause followed by the 'Image output ... supports BMP, GIF,
        JPEG, PNG, TIFF' clause) was misread as a bidirectional claim for every
        format in the list except possibly the first — GIF/JPEG/PNG/TIFF fall
        outside _claim_direction's narrow window entirely, and a naive
        whole-line widening would wrongly pick up 'reads'/'writes' from the
        earlier, unrelated PDF clause. Must resolve to export-only for all
        five, using only the current sentence's own framing."""
        mock_formats.return_value = {
            "pdf": "both", "bmp": "export", "gif": "export",
            "jpeg": "export", "png": "export", "tiff": "export",
        }
        page = _make_kb_page("pdf", "net",
            "The library reads and writes the PDF format. The `Document.Open` method accepts "
            "byte arrays, file paths, and streams. The `Document.Save` and `Document.ToArray` "
            "methods produce PDF output. Image output (for rendering pages) is governed by the "
            "`ImageFormat` enum, which supports BMP, GIF, JPEG, PNG, TIFF, and other raster formats.")
        findings = self.evaluator.evaluate(page, None)
        bidirectional_findings = [f for f in findings if "bidirectional" in f.message.lower()]
        assert bidirectional_findings == [], (
            f"'output ... supports BMP, GIF, JPEG, PNG, TIFF' must resolve every format in the "
            f"list to export-only, not bidirectional; got {bidirectional_findings}")

    @patch("content_eval.evaluators.format_truth._load_formats")
    def test_st029_genuine_bidirectional_overclaim_still_flagged(self, mock_formats):
        """The fix must NOT suppress a REAL false bidirectional claim: prose
        that explicitly claims both import and export when only export is
        supported must still fire."""
        mock_formats.return_value = {"bmp": "export"}
        page = _make_kb_page("pdf", "net",
            "The library supports both import and export of BMP images.")
        findings = self.evaluator.evaluate(page, None)
        assert any("bmp" in f.message.lower() for f in findings), (
            f"a genuine false bidirectional BMP claim must still be flagged; got {findings}")


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
            mod.configure(knowledge_root=Path(tmp) / "knowledge")
            try:
                result = mod._load_formats("words", "python")
            finally:
                mod.configure()
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
            mod.configure(knowledge_root=Path(tmp) / "knowledge")
            try:
                result = mod._load_formats("cells", "python")
            finally:
                mod.configure()
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
            mod.configure(knowledge_root=Path(tmp) / "knowledge")
            try:
                result = mod._load_formats("words", "python")
            finally:
                mod.configure()
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


class TestCapabilityClaimCheckHardening:
    """Task 2 hardening tests: _BOTH_VERB_RE, _TABLE_ACCESS_COL_RE, prose guards.

    These cover the 3 in-scope adjacent gaps identified in §13 of the VBD-02 plan
    (serialized-waddling-kahn.md).  Code-block guards are intentionally omitted —
    capability_claim_check is prose-only by design (uses _extract_scannable_lines).
    """

    def setup_method(self):
        self.evaluator = get_evaluator("capability_claim_check")()

    # ------------------------------------------------------------------
    # Gap 1: _BOTH_VERB_RE — bidirectional verbs ("support", "handle", etc.)
    # ------------------------------------------------------------------

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_support_verb_flags_when_import_only(self, mock_formats):
        """'can support FBX' near import-only FBX must be flagged (both > import).

        _BOTH_VERB_RE matches both 'support' and 'supports' (optional trailing s).
        """
        mock_formats.return_value = {"fbx": "import"}
        page = _make_kb_page("3d", "java",
            body="This library can support FBX files for 3D data exchange.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "CF"

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_support_verb_not_flagged_when_both(self, mock_formats):
        """'supports OBJ' near direction=both OBJ must NOT flag."""
        mock_formats.return_value = {"obj": "both"}
        page = _make_kb_page("3d", "java",
            body="This library supports OBJ files for import and export.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_handle_verb_flags_when_export_only(self, mock_formats):
        """'can handle PDF' near export-only PDF must be flagged (both > export)."""
        mock_formats.return_value = {"pdf": "export"}
        page = _make_kb_page("words", "python",
            body="The API can handle PDF documents as both input and output.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "CF"

    # ------------------------------------------------------------------
    # Gap 2: _TABLE_ACCESS_COL_RE — table header "| Read |" / "| Write |" columns
    # ------------------------------------------------------------------

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_table_write_column_does_not_false_positive(self, mock_formats):
        """'| CSV | Read | Write |' — both Write and Read cells must be neutralized.

        Uses lookahead/lookbehind so shared | delimiter doesn't block matching
        both cells in a single re.sub pass.
        """
        mock_formats.return_value = {"csv": "import"}
        page = _make_kb_page("cells", "python",
            body="| CSV | Read | Write |")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_table_read_write_column_does_not_false_positive(self, mock_formats):
        """'| CSV | Read/Write |' — combined column must NOT trigger export claim for import-only CSV."""
        mock_formats.return_value = {"csv": "import"}
        page = _make_kb_page("cells", "python",
            body="| CSV | Read/Write |")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    # ------------------------------------------------------------------
    # Gap 3: Prose guards — type annotations and inline formatting spans
    # ------------------------------------------------------------------

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_type_annotation_does_not_trigger_claim(self, mock_formats):
        """'doc: Document' type annotation must not be parsed as a capability claim."""
        mock_formats.return_value = {"doc": "export"}
        page = _make_kb_page("words", "python",
            body="The doc: Document parameter accepts a loaded document object.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_backtick_inline_span_does_not_trigger_claim(self, mock_formats):
        """'`csv`' in backtick inline span must not be parsed as a capability claim."""
        mock_formats.return_value = {"csv": "export"}
        page = _make_kb_page("cells", "python",
            body="The `csv` module is used internally for configuration parsing.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_plain_format_mention_with_verb_still_triggers(self, mock_formats):
        """Regression: plain 'parse CSV' (no inline span) must still flag when CSV is export-only."""
        mock_formats.return_value = {"csv": "export"}
        page = _make_kb_page("cells", "python",
            body="Parse CSV files and extract the header row.")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == "CF"


class TestCapabilityClaimCheckCodeFenceFiltering:
    """FP-001 regression tests: code blocks in frontmatter YAML must not trigger claims.

    Root cause: _extract_scannable_lines processes frontmatter text fields without
    code-fence filtering. A C# variable 'doc' in 'using var doc = Document.Open(...)'
    inside a fenced code block matched the DOC format token with direction='none',
    producing 4 false-positive FAILs on the pdf/net products page.

    Fix: code-fence tracking added to frontmatter text field processing in
    _extract_scannable_lines (version_claim_check.py, 2026-06-12).
    """

    def setup_method(self):
        self.evaluator = get_evaluator("capability_claim_check")()

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_code_block_variable_name_does_not_trigger(self, mock_formats):
        """FP-001: 'using var doc = Document.Open(...)' in a fenced code block must not flag.

        The variable 'doc' inside a ```csharp block matches the DOC format token
        and Open() matches the import verb, but this is a code context, not a prose claim.
        """
        mock_formats.return_value = {"doc": "none"}
        page = _make_products_page("pdf", "net",
            frontmatter_extra=textwrap.dedent("""\
                Open PDF documents easily.
                ```csharp
                using var doc = Document.Open("sample.pdf");
                Console.WriteLine(doc.Pages.Count);
                ```
                Simple and reliable.
            """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0, (
            f"Expected 0 findings for code-block variable, got {len(findings)}: "
            f"{[f.message for f in findings]}"
        )

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_prose_claim_after_code_block_still_triggers(self, mock_formats):
        """Prose claims following a code block must still be evaluated."""
        mock_formats.return_value = {"doc": "none"}
        page = _make_products_page("pdf", "net",
            frontmatter_extra=textwrap.dedent("""\
                ```csharp
                using var doc = Document.Open("file.pdf");
                ```
                This library can open and parse DOC files directly.
            """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 1, "Expected FAIL for prose claim after code block"

    @patch("content_eval.evaluators.capability_claim_check._load_formats")
    def test_multiple_code_blocks_all_filtered(self, mock_formats):
        """Multiple fenced code blocks in one frontmatter field are all filtered."""
        mock_formats.return_value = {"doc": "none", "csv": "export"}
        page = _make_products_page("pdf", "net",
            frontmatter_extra=textwrap.dedent("""\
                Example one:
                ```csharp
                var doc = new Document("file.pdf");
                ```
                Example two:
                ```python
                import csv
                with open("data.csv") as f:
                    reader = csv.reader(f)
                ```
                Both examples show API usage.
            """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0, (
            f"Code-block lines must not trigger: {[f.message for f in findings]}"
        )

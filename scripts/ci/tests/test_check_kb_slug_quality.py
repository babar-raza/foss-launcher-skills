"""Tests for scripts/ci/checks/check_kb_slug_quality.py.

Coverage:
  Unit — check_slug() rule table: C1 (CamelCase leak), C2 (verb-noun dup),
          C3 (generic noun), C4 (compound noun without product-family keyword)
  Unit — _extract_family(): family extraction from KB content paths
  Integration — CLI staged-file mode, scan mode, exit codes
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_kb_slug_quality.py"

# Import the module-level functions for unit tests
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))
from check_kb_slug_quality import check_slug, _extract_family  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER)] + list(args),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _make_kb_file(tmp_path: Path, stem: str) -> Path:
    """Create a fake KB how-to file under a tmp content tree."""
    p = tmp_path / "content" / "kb.aspose.org" / "en" / "pdf" / "net" / f"{stem}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\ntitle: test\n---\n", encoding="utf-8")
    return p


# ===========================================================================
# Unit tests — check_slug()
# ===========================================================================

class TestCheckSlugC1CamelCaseLeak:
    def test_javascriptextensions_fails(self):
        result = check_slug("how-to-work-with-javascriptextensions-dotnet")
        assert result is not None
        check_id, _ = result
        assert check_id == "C1"

    def test_internalvalidation_fails(self):
        result = check_slug("how-to-work-with-internalvalidation-cpp")
        assert result is not None
        check_id, _ = result
        assert check_id == "C1"

    def test_short_noun_passes_c1(self):
        """Noun <= 12 chars is not flagged as C1."""
        result = check_slug("how-to-work-with-annotations-dotnet")
        # annotations = 11 chars — should not be C1
        if result:
            assert result[0] != "C1"

    def test_presentations_allowed_not_c1(self):
        """'presentations' is a known real English word, exempt from C1."""
        result = check_slug("how-to-create-presentations-dotnet")
        # Should not be C1 (it's in _ALLOWED_LONG_NOUNS or ≤12 chars)
        if result:
            assert result[0] != "C1"

    def test_non_how_to_slug_passes(self):
        assert check_slug("use-cases") is None

    def test_faq_slug_passes(self):
        assert check_slug("faq") is None


class TestCheckSlugC2VerbNounDuplication:
    def test_text_extraction_with_extract_fails(self):
        result = check_slug("how-to-extract-text-extraction-dotnet")
        assert result is not None
        check_id, _ = result
        assert check_id == "C2"

    def test_convert_converters_fails(self):
        result = check_slug("how-to-convert-converters-python")
        assert result is not None
        check_id, _ = result
        assert check_id == "C2"

    def test_extract_text_passes(self):
        """'how-to-extract-text-dotnet' — no duplication."""
        result = check_slug("how-to-extract-text-dotnet")
        assert result is None

    def test_create_pdf_document_passes(self):
        result = check_slug("how-to-create-pdf-document-dotnet")
        assert result is None

    def test_work_with_annotations_passes(self):
        result = check_slug("how-to-work-with-annotations-dotnet")
        assert result is None


class TestCheckSlugC3GenericNoun:
    def test_core_fails(self):
        result = check_slug("how-to-work-with-core-dotnet")
        assert result is not None
        check_id, _ = result
        assert check_id == "C3"

    def test_content_fails(self):
        result = check_slug("how-to-work-with-content-dotnet")
        assert result is not None
        check_id, _ = result
        assert check_id == "C3"

    def test_utilities_fails(self):
        result = check_slug("how-to-work-with-utilities-java")
        assert result is not None
        check_id, _ = result
        assert check_id == "C3"

    def test_specific_noun_passes(self):
        result = check_slug("how-to-work-with-digital-signatures-dotnet")
        assert result is None

    def test_data_validation_passes(self):
        """'data-validation' — primary word 'data' is generic but not primary here."""
        # 'data-validation' — primary = 'data' which IS in the generic list → should fail
        # This tests that the check fires appropriately
        result = check_slug("how-to-work-with-data-validation-dotnet")
        # 'data' is in _KB_GENERIC_NOUNS, so this SHOULD fail C3
        assert result is not None
        check_id, _ = result
        assert check_id == "C3"

    def test_xlsx_packaging_passes(self):
        result = check_slug("how-to-work-with-xlsx-packaging-dotnet")
        assert result is None


class TestCheckSlugPlatformSuffix:
    def test_java_suffix_stripped(self):
        """Platform suffix doesn't affect noun extraction."""
        result = check_slug("how-to-work-with-core-java")
        assert result is not None
        assert result[0] == "C3"

    def test_python_suffix_stripped(self):
        result = check_slug("how-to-extract-text-extraction-python")
        assert result is not None
        assert result[0] == "C2"

    def test_go_suffix_stripped(self):
        result = check_slug("how-to-work-with-core-go")
        assert result is not None
        assert result[0] == "C3"


# ===========================================================================
# Integration tests — CLI
# ===========================================================================

class TestCLIStageMode:
    def test_bad_slug_exits_1(self, tmp_path):
        p = _make_kb_file(tmp_path, "how-to-work-with-javascriptextensions-dotnet")
        result = _run(str(p))
        assert result.returncode == 1, result.stdout + result.stderr

    def test_bad_slug_output_has_fail(self, tmp_path):
        p = _make_kb_file(tmp_path, "how-to-work-with-javascriptextensions-dotnet")
        result = _run(str(p))
        assert "FAIL" in result.stdout

    def test_good_slug_exits_0(self, tmp_path):
        p = _make_kb_file(tmp_path, "how-to-extract-text-dotnet")
        result = _run(str(p))
        assert result.returncode == 0, result.stdout + result.stderr

    def test_non_kb_file_exits_0(self, tmp_path):
        """Non-how-to files are silently skipped."""
        p = _make_kb_file(tmp_path, "faq")
        result = _run(str(p))
        assert result.returncode == 0, result.stdout + result.stderr

    def test_multiple_files_one_bad_exits_1(self, tmp_path):
        good = _make_kb_file(tmp_path, "how-to-extract-text-dotnet")
        bad = _make_kb_file(tmp_path, "how-to-work-with-javascriptextensions-dotnet")
        result = _run(str(good), str(bad))
        assert result.returncode == 1

    def test_c2_verb_noun_dup_exits_1(self, tmp_path):
        p = _make_kb_file(tmp_path, "how-to-extract-text-extraction-dotnet")
        result = _run(str(p))
        assert result.returncode == 1

    def test_c3_generic_noun_exits_1(self, tmp_path):
        p = _make_kb_file(tmp_path, "how-to-work-with-core-dotnet")
        result = _run(str(p))
        assert result.returncode == 1


class TestCLIScanMode:
    def test_scan_exits_0_even_with_defects(self, tmp_path):
        """Scan mode always exits 0 (report only)."""
        kb_root = tmp_path / "content" / "kb.aspose.org" / "en" / "pdf" / "net"
        kb_root.mkdir(parents=True)
        bad = kb_root / "how-to-work-with-javascriptextensions-dotnet.md"
        bad.write_text("---\ntitle: test\n---\n", encoding="utf-8")
        result = _run("--scan", "--root", str(tmp_path / "content"))
        assert result.returncode == 0, result.stderr

    def test_scan_reports_warn_not_fail(self, tmp_path):
        kb_root = tmp_path / "content" / "kb.aspose.org" / "en" / "pdf" / "net"
        kb_root.mkdir(parents=True)
        bad = kb_root / "how-to-work-with-javascriptextensions-dotnet.md"
        bad.write_text("---\ntitle: test\n---\n", encoding="utf-8")
        result = _run("--scan", "--root", str(tmp_path / "content"))
        assert "WARN" in result.stdout
        assert "FAIL" not in result.stdout

    def test_scan_clean_tree_exits_0(self, tmp_path):
        kb_root = tmp_path / "content" / "kb.aspose.org" / "en" / "pdf" / "net"
        kb_root.mkdir(parents=True)
        good = kb_root / "how-to-extract-text-dotnet.md"
        good.write_text("---\ntitle: test\n---\n", encoding="utf-8")
        result = _run("--scan", "--root", str(tmp_path / "content"))
        assert result.returncode == 0

    def test_scan_missing_root_exits_2(self, tmp_path):
        result = _run("--scan", "--root", str(tmp_path / "nonexistent"))
        assert result.returncode == 2


class TestCLINoArgsDefaultsScanMode:
    def test_no_args_exits_0_on_empty_kb(self, tmp_path):
        """No-args mode falls through to scan; exits 0."""
        kb_root = tmp_path / "content" / "kb.aspose.org"
        kb_root.mkdir(parents=True)
        # Change to tmp directory so --root default resolves to tmp/content
        result = subprocess.run(
            [sys.executable, str(CHECKER)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0


# ===========================================================================
# Unit tests — C4 check (compound noun without product-family keyword)
# TC-KBS-019: these tests verify regression safety for C4 logic in the
# CI gate (check_kb_slug_quality.py). The check_slug() function receives
# an explicit `family` arg when called from check_files() / scan_root(),
# which derive it from the file path via _extract_family().
# ===========================================================================

class TestCheckSlugC4ProductKeyword:
    def test_c4_old_rc5_annotations_forms_fails_for_pdf(self):
        """Original RC-5 slug: 'annotations-forms' has no pdf keyword → C4 FAIL."""
        result = check_slug("how-to-add-annotations-forms-dotnet", family="pdf")
        assert result is not None, "Expected C4 violation for old RC-5 slug"
        check_id, msg = result
        assert check_id == "C4", f"Expected C4, got {check_id}: {msg}"
        assert "pdf" in msg

    def test_c4_old_rc5_graphics_drawing_fails_for_pdf(self):
        """Original RC-5 slug: 'graphics-drawing' has no pdf keyword → C4 FAIL."""
        result = check_slug("how-to-add-graphics-drawing-dotnet", family="pdf")
        assert result is not None
        assert result[0] == "C4"

    def test_c4_old_rc5_metadata_utilities_fails_for_pdf(self):
        """Original RC-5 slug: 'metadata-utilities' has no pdf keyword → C4 FAIL."""
        result = check_slug("how-to-extract-metadata-utilities-dotnet", family="pdf")
        assert result is not None
        assert result[0] == "C4"

    def test_c4_qualified_pdf_annotations_passes(self):
        """New qualified slug: 'pdf-annotations' — 'pdf' is a pdf keyword → PASS."""
        result = check_slug("how-to-add-pdf-annotations-dotnet", family="pdf")
        assert result is None, f"Expected PASS, got: {result}"

    def test_c4_qualified_pdf_graphics_passes(self):
        """New qualified slug: 'pdf-graphics' — 'pdf' is a pdf keyword → PASS."""
        result = check_slug("how-to-add-pdf-graphics-dotnet", family="pdf")
        assert result is None

    def test_c4_qualified_pdf_metadata_passes(self):
        """New qualified slug: 'pdf-metadata' — 'pdf' is a pdf keyword → PASS."""
        result = check_slug("how-to-extract-pdf-metadata-dotnet", family="pdf")
        assert result is None

    def test_c4_without_family_arg_does_not_trigger(self):
        """C4 is skipped when no family is provided (e.g. path without en/ segment)."""
        # Without family, only C1/C2/C3 apply. annotations-forms passes all three.
        result = check_slug("how-to-add-annotations-forms-dotnet")
        # May be None or fail C1/C2/C3, but NOT C4
        if result:
            assert result[0] != "C4"

    def test_c4_cells_xlsx_keyword_passes(self):
        """cells family slug with 'xlsx' keyword → PASS (xlsx is in cells keyword set)."""
        result = check_slug("how-to-work-with-xlsx-packaging-dotnet", family="cells")
        assert result is None

    def test_c4_3d_materials_prefix_match_passes(self):
        """3d family slug: 'materials-shading' — 'materials'.startswith('material') → PASS."""
        result = check_slug("how-to-add-materials-shading-python", family="3d")
        assert result is None


# ===========================================================================
# Unit tests — _extract_family()
# Verifies that the family-extraction helper correctly parses KB content paths.
# ===========================================================================

class TestExtractFamily:
    def test_extract_family_pdf_net(self):
        path = "content/kb.aspose.org/en/pdf/net/how-to-add-pdf-annotations-dotnet.md"
        assert _extract_family(path) == "pdf"

    def test_extract_family_cells_java(self):
        path = "content/kb.aspose.org/en/cells/java/how-to-work-with-cell-model-java.md"
        assert _extract_family(path) == "cells"

    def test_extract_family_email_cpp(self):
        path = "content/kb.aspose.org/en/email/cpp/how-to-convert-eml-to-msg-cpp.md"
        assert _extract_family(path) == "email"

    def test_extract_family_no_en_segment_returns_empty(self):
        path = "some/other/path/to/file.md"
        assert _extract_family(path) == ""

    def test_extract_family_windows_style_path(self):
        """Windows backslash paths (from scan mode on Windows) are handled."""
        import os
        path = str(Path("content") / "kb.aspose.org" / "en" / "slides" / "net" / "how-to-apply-3d-effects-dotnet.md")
        assert _extract_family(path) == "slides"


# ===========================================================================
# Integration tests — C4 via CLI (staged-file mode)
# Verifies that the CLI correctly propagates family context and applies C4.
# The _make_kb_file helper creates files under en/pdf/net/ so family="pdf".
# ===========================================================================

class TestCLIStageC4:
    def test_c4_old_rc5_slug_via_cli_exits_1(self, tmp_path):
        """CLI exits 1 on old RC-5 slug with pdf family context from path."""
        p = _make_kb_file(tmp_path, "how-to-add-annotations-forms-dotnet")
        result = _run(str(p))
        assert result.returncode == 1, result.stdout + result.stderr
        assert "C4" in result.stdout, f"Expected C4 in output:\n{result.stdout}"

    def test_c4_qualified_pdf_slug_via_cli_exits_0(self, tmp_path):
        """CLI exits 0 on new qualified pdf slug."""
        p = _make_kb_file(tmp_path, "how-to-add-pdf-annotations-dotnet")
        result = _run(str(p))
        assert result.returncode == 0, result.stdout + result.stderr

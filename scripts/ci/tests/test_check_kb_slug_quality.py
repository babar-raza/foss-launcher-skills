"""Tests for scripts/ci/checks/check_kb_slug_quality.py.

Coverage:
  Unit — check_slug() rule table: C1 (CamelCase leak), C2 (verb-noun dup), C3 (generic noun)
  Integration — CLI staged-file mode, scan mode, exit codes
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_kb_slug_quality.py"

# Import the module-level function for unit tests
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))
from check_kb_slug_quality import check_slug  # noqa: E402


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

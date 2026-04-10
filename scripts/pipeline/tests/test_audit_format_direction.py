"""Unit tests for audit/formats.py — verify_format_direction check.

Tests that:
- enum_only SaveFormat rows WITHOUT a warning produce FAIL findings (FD-01)
- enum_only SaveFormat rows WITH a warning produce no findings
- Non-enum-only SaveFormat rows are never flagged
- Missing formats.json causes graceful skip (no findings, no crash)
- Files with no SaveFormat table rows produce no findings

Root cause guarded: GAP-01 words/python 2026-04-10 — Document.md Output
Formats table listed SaveFormat.DOCX/DOC without ValueError notes.
"""
import json
import tempfile
import unittest
from pathlib import Path


class TestVerifyFormatDirection(unittest.TestCase):
    """Tests for audit.formats.verify_format_direction."""

    def _write_formats_json(self, tmpdir: Path, entries: list[dict]) -> None:
        merged = tmpdir / "knowledge" / "words" / "python" / "merged"
        merged.mkdir(parents=True, exist_ok=True)
        (merged / "formats.json").write_text(
            json.dumps(entries), encoding="utf-8"
        )

    def _write_content(self, tmpdir: Path, body: str) -> Path:
        f = tmpdir / "Document.md"
        f.write_text(body, encoding="utf-8")
        return f

    def _run(self, tmpdir: Path, body: str, formats: list[dict]):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        # Patch KNOWLEDGE_ROOT to tmpdir
        import audit.formats as fmt_mod
        original_root = fmt_mod.KNOWLEDGE_ROOT
        fmt_mod.KNOWLEDGE_ROOT = tmpdir / "knowledge"
        try:
            self._write_formats_json(tmpdir, formats)
            fp = self._write_content(tmpdir, body)
            return fmt_mod.verify_format_direction(str(fp), "words", "python")
        finally:
            fmt_mod.KNOWLEDGE_ROOT = original_root

    # ------------------------------------------------------------------
    # Failing cases — should produce FAIL findings
    # ------------------------------------------------------------------

    def test_enum_only_without_warning_is_fail(self):
        """A SaveFormat.DOCX row without any warning note → FAIL."""
        formats = [
            {"name": "DOCX", "direction": "enum_only"},
            {"name": "PDF", "direction": "export"},
        ]
        body = (
            "## Output Formats\n\n"
            "| Format | `SaveFormat` Constant | Save Options |\n"
            "|--------|----------------------|-------------|\n"
            "| PDF | `SaveFormat.PDF` | `PdfSaveOptions` |\n"
            "| DOCX | `SaveFormat.DOCX` | — |\n"
        )
        with tempfile.TemporaryDirectory() as td:
            findings = self._run(Path(td), body, formats)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")
        self.assertIn("SaveFormat.DOCX", findings[0].message)
        self.assertIn("enum_only", findings[0].message)

    def test_multiple_enum_only_without_warning_produces_multiple_fails(self):
        """DOC and DOCX both missing warnings → two FAIL findings."""
        formats = [
            {"name": "DOCX", "direction": "enum_only"},
            {"name": "DOC", "direction": "enum_only"},
            {"name": "PDF", "direction": "export"},
        ]
        body = (
            "### Output Formats\n\n"
            "| Format | `SaveFormat` Constant | Notes |\n"
            "|--------|----------------------|-------|\n"
            "| PDF | `SaveFormat.PDF` | — |\n"
            "| DOCX | `SaveFormat.DOCX` | — |\n"
            "| DOC | `SaveFormat.DOC` | — |\n"
        )
        with tempfile.TemporaryDirectory() as td:
            findings = self._run(Path(td), body, formats)
        self.assertEqual(len(findings), 2)
        names = {f.message.split("SaveFormat.")[1].split(" ")[0] for f in findings}
        self.assertIn("DOCX", names)
        self.assertIn("DOC", names)

    # ------------------------------------------------------------------
    # Passing cases — should produce zero findings
    # ------------------------------------------------------------------

    def test_enum_only_with_valueerror_note_passes(self):
        """Row mentioning 'raises ValueError' → no FAIL."""
        formats = [{"name": "DOCX", "direction": "enum_only"}]
        body = (
            "### Output Formats\n\n"
            "| Format | `SaveFormat` Constant | Notes |\n"
            "|--------|----------------------|-------|\n"
            "| DOCX | `SaveFormat.DOCX` | Read-only constant — raises `ValueError`. |\n"
        )
        with tempfile.TemporaryDirectory() as td:
            findings = self._run(Path(td), body, formats)
        self.assertEqual(findings, [])

    def test_enum_only_with_not_implemented_note_passes(self):
        """Row mentioning 'not implemented' → no FAIL."""
        formats = [{"name": "DOCX", "direction": "enum_only"}]
        body = (
            "### Output Formats\n\n"
            "| Format | `SaveFormat` Constant | Notes |\n"
            "|--------|----------------------|-------|\n"
            "| DOCX | `SaveFormat.DOCX` | Not implemented — do not use. |\n"
        )
        with tempfile.TemporaryDirectory() as td:
            findings = self._run(Path(td), body, formats)
        self.assertEqual(findings, [])

    def test_non_enum_only_format_never_flagged(self):
        """A row for a format with direction:export is never a FAIL."""
        formats = [{"name": "PDF", "direction": "export"}]
        body = (
            "### Output Formats\n\n"
            "| Format | `SaveFormat` Constant | Notes |\n"
            "|--------|----------------------|-------|\n"
            "| PDF | `SaveFormat.PDF` | — |\n"
        )
        with tempfile.TemporaryDirectory() as td:
            findings = self._run(Path(td), body, formats)
        self.assertEqual(findings, [])

    def test_no_saveformat_rows_produces_no_findings(self):
        """A file with no SaveFormat table rows → no findings."""
        formats = [{"name": "DOCX", "direction": "enum_only"}]
        body = "## Overview\n\nThis page has no format table.\n"
        with tempfile.TemporaryDirectory() as td:
            findings = self._run(Path(td), body, formats)
        self.assertEqual(findings, [])

    def test_missing_formats_json_produces_no_findings(self):
        """If formats.json does not exist, no findings and no crash."""
        import sys
        import audit.formats as fmt_mod
        original_root = fmt_mod.KNOWLEDGE_ROOT
        # Point to a directory with no formats.json
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fmt_mod.KNOWLEDGE_ROOT = td_path / "knowledge"
            body = (
                "### Output Formats\n\n"
                "| Format | `SaveFormat` Constant | Notes |\n"
                "|--------|----------------------|-------|\n"
                "| DOCX | `SaveFormat.DOCX` | — |\n"
            )
            fp = td_path / "Document.md"
            fp.write_text(body, encoding="utf-8")
            try:
                findings = fmt_mod.verify_format_direction(str(fp), "words", "python")
            finally:
                fmt_mod.KNOWLEDGE_ROOT = original_root
        self.assertEqual(findings, [])

    def test_words_python_document_md_passes_after_gap01_fix(self):
        """Integration smoke: words/python Document.md (post-fix) must pass FD check."""
        import sys
        import audit.formats as fmt_mod

        doc_path = Path("content/reference.aspose.org/en/words/python/Document.md")
        if not doc_path.exists():
            self.skipTest("Document.md not found in repo")
        findings = fmt_mod.verify_format_direction(str(doc_path), "words", "python")
        self.assertEqual(
            findings, [],
            msg=f"Expected 0 FD findings after GAP-01 fix; got: {findings}"
        )


if __name__ == "__main__":
    unittest.main()

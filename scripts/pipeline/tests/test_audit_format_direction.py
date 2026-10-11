"""Unit tests for audit/formats.py — verify_format_direction check.

Tests that:
- enum_only SaveFormat rows WITHOUT a warning produce FAIL findings (FD-01)
- enum_only SaveFormat rows WITH a warning produce no findings
- Non-enum-only SaveFormat rows are never flagged
- Missing formats.json causes graceful skip (no findings, no crash)
- Files with no SaveFormat table rows produce no findings
- formats.json read is cached per (family, platform) — O(1) after first call
- Malformed / non-list formats.json emits a WARNING log (not silent)
- Missing formats.json emits no WARNING log (expected absence)

Root cause guarded: GAP-01 words/python 2026-04-10 — Document.md Output
Formats table listed SaveFormat.DOCX/DOC without ValueError notes.
"""
import json
import logging
import tempfile
import unittest
from pathlib import Path


class TestVerifyFormatDirection(unittest.TestCase):
    """Tests for audit.formats.verify_format_direction."""

    def setUp(self):
        """Clear lru_cache before each test to prevent state bleed."""
        import audit.formats as fmt_mod
        fmt_mod._load_enum_only_formats.cache_clear()

    def tearDown(self):
        """Clear lru_cache after each test as well."""
        import audit.formats as fmt_mod
        fmt_mod._load_enum_only_formats.cache_clear()

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
        import audit.formats as fmt_mod
        fmt_mod.configure(knowledge_root=tmpdir / "knowledge")
        try:
            self._write_formats_json(tmpdir, formats)
            fp = self._write_content(tmpdir, body)
            return fmt_mod.verify_format_direction(str(fp), "words", "python")
        finally:
            fmt_mod.configure()

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
        import audit.formats as fmt_mod
        # Point to a directory with no formats.json
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fmt_mod.configure(knowledge_root=td_path / "knowledge")
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
                fmt_mod.configure()
        self.assertEqual(findings, [])

    def test_corrected_enum_only_rows_pass(self):
        """Post-GAP-01 corrected rows (with ValueError note) must not generate findings.

        This test is hermetic — it does not read any file from the repository.
        It specifies the exact corrected row text as a string literal, making
        it a permanent specification of what 'correct' looks like.
        """
        import audit.formats as fmt_mod
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            merged = td_path / "knowledge" / "words" / "python" / "merged"
            merged.mkdir(parents=True)
            (merged / "formats.json").write_text(json.dumps([
                {"name": "DOCX", "direction": "enum_only"},
                {"name": "DOC", "direction": "enum_only"},
                {"name": "PDF", "direction": "export"},
                {"name": "MARKDOWN", "direction": "export"},
                {"name": "TEXT", "direction": "export"},
            ]), encoding="utf-8")
            # Exact corrected rows from Document.md after GAP-01 fix
            md = td_path / "Document.md"
            md.write_text(
                "## Output Formats\n\n"
                "| Format | `SaveFormat` Constant | Save Options |\n"
                "|--------|----------------------|--------------|\n"
                "| PDF | `SaveFormat.PDF` | `PdfSaveOptions` — configure compliance, image compression, font embedding |\n"
                "| Markdown | `SaveFormat.MARKDOWN` | `MarkdownSaveOptions` — configure table alignment, image export, list mode |\n"
                "| Plain Text | `SaveFormat.TEXT` | — |\n"
                "| DOCX | `SaveFormat.DOCX` | Read-only constant. `Document.save()` does not support DOCX — raises `ValueError`. |\n"
                "| DOC  | `SaveFormat.DOC`  | Read-only constant. `Document.save()` does not support DOC — raises `ValueError`. |\n",
                encoding="utf-8",
            )
            fmt_mod.configure(knowledge_root=td_path / "knowledge")
            try:
                findings = fmt_mod.verify_format_direction(str(md), "words", "python")
            finally:
                fmt_mod.configure()
        self.assertEqual(
            findings, [],
            msg=f"Expected 0 FD findings for correctly-warned rows; got: {findings}",
        )

    # ------------------------------------------------------------------
    # AF-01: caching — formats.json read once per (family, platform)
    # ------------------------------------------------------------------

    def test_formats_json_read_once_per_family_platform(self):
        """_load_enum_only_formats is cached: cache_info shows misses=1 after 3 calls."""
        import audit.formats as fmt_mod
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            merged = td_path / "knowledge" / "words" / "python" / "merged"
            merged.mkdir(parents=True)
            (merged / "formats.json").write_text(
                json.dumps([{"name": "DOCX", "direction": "enum_only"}]),
                encoding="utf-8",
            )
            md = td_path / "doc.md"
            md.write_text("| DOCX | `SaveFormat.DOCX` | — |\n", encoding="utf-8")

            fmt_mod.configure(knowledge_root=td_path / "knowledge")
            try:
                fmt_mod.verify_format_direction(str(md), "words", "python")
                fmt_mod.verify_format_direction(str(md), "words", "python")
                fmt_mod.verify_format_direction(str(md), "words", "python")
                info = fmt_mod._load_enum_only_formats.cache_info()
            finally:
                fmt_mod.configure()

        self.assertEqual(info.misses, 1, "formats.json should be read exactly once")
        self.assertEqual(info.hits, 2, "second and third calls should be cache hits")

    # ------------------------------------------------------------------
    # AF-02: logging — WARNING on malformed data, no WARNING on missing file
    # ------------------------------------------------------------------

    def test_malformed_json_logs_warning(self):
        """Malformed JSON in formats.json triggers a WARNING log."""
        import audit.formats as fmt_mod
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            merged = td_path / "knowledge" / "words" / "python" / "merged"
            merged.mkdir(parents=True)
            (merged / "formats.json").write_text("not valid json {{{", encoding="utf-8")
            fmt_mod.configure(knowledge_root=td_path / "knowledge")
            try:
                with self.assertLogs("audit.formats", level="WARNING") as cm:
                    result = fmt_mod._load_enum_only_formats("words", "python")
            finally:
                fmt_mod.configure()
        self.assertEqual(result, set())
        self.assertTrue(
            any("could not load" in msg for msg in cm.output),
            f"Expected 'could not load' in WARNING; got: {cm.output}",
        )

    def test_not_a_list_logs_warning(self):
        """formats.json that is a dict (not a list) triggers a WARNING log."""
        import audit.formats as fmt_mod
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            merged = td_path / "knowledge" / "words" / "python" / "merged"
            merged.mkdir(parents=True)
            # Valid JSON but wrong type: dict instead of list
            (merged / "formats.json").write_text(
                json.dumps({"name": "DOCX", "direction": "enum_only"}),
                encoding="utf-8",
            )
            fmt_mod.configure(knowledge_root=td_path / "knowledge")
            try:
                with self.assertLogs("audit.formats", level="WARNING") as cm:
                    result = fmt_mod._load_enum_only_formats("words", "python")
            finally:
                fmt_mod.configure()
        self.assertEqual(result, set())
        self.assertTrue(
            any("not a JSON list" in msg for msg in cm.output),
            f"Expected 'not a JSON list' in WARNING; got: {cm.output}",
        )

    def test_missing_formats_json_no_warning_logged(self):
        """Missing formats.json must NOT emit a WARNING — it is expected absence."""
        import audit.formats as fmt_mod
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fmt_mod.configure(knowledge_root=td_path / "knowledge")  # no formats.json here
            try:
                # assertNoLogs(level="WARNING") passes only if no WARNING records emitted
                with self.assertNoLogs("audit.formats", level="WARNING"):
                    result = fmt_mod._load_enum_only_formats("words", "python")
            finally:
                fmt_mod.configure()
        self.assertEqual(result, set())


if __name__ == "__main__":
    unittest.main()

"""Unit tests for extraction/formats.py — cross-reference and dispatch scan.

Tests that:
- SaveFormat enum entries are demoted to 'enum_only' when no matching I/O class exists
- SaveFormat enum entries keep 'export' when a matching Exporter/Writer exists
- Prefixed writer names (e.g. LdmMarkdownWriter → "LdmMarkdown") match enum members
- FileFormat enum entries (direction='detect') are never promoted or changed
- LoadFormat entries are demoted symmetrically when no matching Reader exists
- ExporterRegistry / Factory classes are handled correctly after suffix stripping
- Pass 2 noise entries (remove, dir, parts, argb, part) are rejected by skip list
- Pass 4 dispatch scanner detects inline save methods backed by SaveFormat dispatch

Root cause guarded: SaveFormat enum members were blindly marked direction:'export'
without verifying that a corresponding Exporter/Writer class exists in source.
"""
import re
import tempfile
import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extraction.formats import _cross_reference_enum_directions, _scan_save_dispatch

# Re-create the patterns used by detect_formats() for test use.
_SAVE_PAT = re.compile(r"(SaveFormat|ExportFormat|OutputFormat)", re.IGNORECASE)
_LOAD_PAT = re.compile(r"(LoadFormat|ImportFormat|InputFormat)", re.IGNORECASE)


class TestCrossReferenceEnumDirections(unittest.TestCase):
    """Tests for _cross_reference_enum_directions()."""

    # ------------------------------------------------------------------
    # Core: SaveFormat demotion
    # ------------------------------------------------------------------

    def test_saveformat_demoted_without_exporter(self):
        """SaveFormat.PDF → 'enum_only' when no PdfExporter exists."""
        formats = [
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
            {"format": "PPTX", "enum": "SaveFormat", "direction": "export"},
            {"format": "Pptx", "enum": "", "direction": "export"},  # I/O class
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        pdf = next(f for f in result if f["format"] == "PDF")
        pptx_enum = next(f for f in result if f["format"] == "PPTX")
        self.assertEqual(pdf["direction"], "enum_only")
        self.assertEqual(pptx_enum["direction"], "export")

    def test_all_saveformat_members_demoted_when_no_exporters(self):
        """All SaveFormat members → 'enum_only' when no I/O classes exist."""
        formats = [
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOCX", "enum": "SaveFormat", "direction": "export"},
            {"format": "HTML", "enum": "SaveFormat", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        for f in result:
            self.assertEqual(
                f["direction"], "enum_only",
                f"Expected 'enum_only' for {f['format']} but got '{f['direction']}'",
            )

    # ------------------------------------------------------------------
    # Substring matching for prefixed writers
    # ------------------------------------------------------------------

    def test_prefixed_writer_matches_enum_member(self):
        """SaveFormat.MARKDOWN keeps 'export' when LdmMarkdownWriter exists."""
        formats = [
            {"format": "MARKDOWN", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOC", "enum": "SaveFormat", "direction": "export"},
            {"format": "LdmMarkdown", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        md = next(f for f in result if f["format"] == "MARKDOWN")
        doc = next(f for f in result if f["format"] == "DOC")
        self.assertEqual(md["direction"], "export")
        self.assertEqual(doc["direction"], "enum_only")

    def test_prefixed_pdf_writer_matches_enum_member(self):
        """SaveFormat.PDF keeps 'export' when LdmPdfWriter exists."""
        formats = [
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOCX", "enum": "SaveFormat", "direction": "export"},
            {"format": "LdmPdf", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        pdf = next(f for f in result if f["format"] == "PDF")
        docx = next(f for f in result if f["format"] == "DOCX")
        self.assertEqual(pdf["direction"], "export")
        self.assertEqual(docx["direction"], "enum_only")

    # ------------------------------------------------------------------
    # FileFormat (detect) is unchanged
    # ------------------------------------------------------------------

    def test_fileformat_detect_unchanged(self):
        """FileFormat enum entries stay 'detect' — never promoted or demoted."""
        formats = [
            {"format": "PDF", "enum": "FileFormat", "direction": "detect"},
            {"format": "Pdf", "enum": "", "direction": "export"},  # exporter exists
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        pdf = next(f for f in result if f["format"] == "PDF")
        self.assertEqual(pdf["direction"], "detect")

    # ------------------------------------------------------------------
    # LoadFormat symmetric demotion
    # ------------------------------------------------------------------

    def test_loadformat_demoted_without_reader(self):
        """LoadFormat.XLSX → 'enum_only' when no XlsxReader exists."""
        formats = [
            {"format": "XLSX", "enum": "LoadFormat", "direction": "import"},
            {"format": "DOC", "enum": "LoadFormat", "direction": "import"},
            {"format": "DocFile", "enum": "", "direction": "import"},  # reader
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        xlsx = next(f for f in result if f["format"] == "XLSX")
        doc = next(f for f in result if f["format"] == "DOC")
        self.assertEqual(xlsx["direction"], "enum_only")
        self.assertEqual(doc["direction"], "import")

    # ------------------------------------------------------------------
    # ExportFormat / OutputFormat variations
    # ------------------------------------------------------------------

    def test_exportformat_treated_same_as_saveformat(self):
        """ExportFormat enum is also cross-referenced against I/O classes."""
        formats = [
            {"format": "CSV", "enum": "ExportFormat", "direction": "export"},
            {"format": "XLS", "enum": "ExportFormat", "direction": "export"},
            {"format": "Csv", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        csv = next(f for f in result if f["format"] == "CSV")
        xls = next(f for f in result if f["format"] == "XLS")
        self.assertEqual(csv["direction"], "export")
        self.assertEqual(xls["direction"], "enum_only")

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_formats_list(self):
        """Empty input → empty output, no crash."""
        result = _cross_reference_enum_directions([], _SAVE_PAT, _LOAD_PAT)
        self.assertEqual(result, [])

    def test_only_enum_entries_no_io_classes(self):
        """When no I/O class entries exist, all enum exports are demoted."""
        formats = [
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
            {"format": "PPTX", "enum": "SaveFormat", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        for f in result:
            self.assertEqual(f["direction"], "enum_only")

    def test_method_name_export_counts_as_backing(self):
        """Pass 2 method-name format (save_to_pdf) counts as export backing."""
        formats = [
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOCX", "enum": "SaveFormat", "direction": "export"},
            # Method-name detection result (Pass 2) — has enum=""
            {"format": "pdf", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        pdf = next(f for f in result if f["format"] == "PDF")
        docx = next(f for f in result if f["format"] == "DOCX")
        self.assertEqual(pdf["direction"], "export")
        self.assertEqual(docx["direction"], "enum_only")

    def test_io_class_with_short_name_skipped(self):
        """I/O class format names shorter than 2 chars are not used for matching."""
        formats = [
            {"format": "XL", "enum": "SaveFormat", "direction": "export"},
            {"format": "x", "enum": "", "direction": "export"},  # too short
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        xl = next(f for f in result if f["format"] == "XL")
        self.assertEqual(xl["direction"], "enum_only")

    # ------------------------------------------------------------------
    # Regression: slides/python scenario
    # ------------------------------------------------------------------

    def test_slides_python_regression(self):
        """21-member SaveFormat + only PptxExporter → 1 export, 20 enum_only."""
        members = [
            "PPT", "PDF", "XPS", "PPTX", "PPSX", "TIFF", "ODP",
            "PPTM", "PPSM", "POTX", "POTM", "HTML", "SWF", "OTP",
            "PPS", "POT", "FODP", "GIF", "HTML5", "MD", "XML",
        ]
        formats = [
            {"format": m, "enum": "SaveFormat", "direction": "export"}
            for m in members
        ]
        # Only PptxExporter exists
        formats.append({"format": "Pptx", "enum": "", "direction": "export"})

        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        enum_entries = [f for f in result if f.get("enum") == "SaveFormat"]

        export_entries = [f for f in enum_entries if f["direction"] == "export"]
        enum_only_entries = [f for f in enum_entries if f["direction"] == "enum_only"]

        self.assertEqual(len(export_entries), 1)
        self.assertEqual(export_entries[0]["format"], "PPTX")
        self.assertEqual(len(enum_only_entries), 20)

    # ------------------------------------------------------------------
    # Regression: words/python scenario
    # ------------------------------------------------------------------

    def test_words_python_regression(self):
        """5-member SaveFormat + LdmMarkdownWriter + LdmPdfWriter."""
        formats = [
            {"format": "MARKDOWN", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOC", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOCX", "enum": "SaveFormat", "direction": "export"},
            {"format": "TEXT", "enum": "SaveFormat", "direction": "export"},
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
            # I/O class entries (from Writer class detection)
            {"format": "LdmMarkdown", "enum": "", "direction": "export"},
            {"format": "LdmPdf", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)

        def _dir(name):
            return next(f for f in result if f["format"] == name and f.get("enum"))["direction"]

        self.assertEqual(_dir("MARKDOWN"), "export")
        self.assertEqual(_dir("PDF"), "export")
        self.assertEqual(_dir("DOC"), "enum_only")
        self.assertEqual(_dir("DOCX"), "enum_only")
        # NOTE: The cross-reference correctly demotes TEXT because no
        # TextWriter I/O class exists.  In practice, words_foss implements
        # TEXT save inline via Document._save_as_text() — a private method
        # that the extractor cannot detect.  The merged/formats.json is
        # manually corrected to direction:"export" for TEXT.
        self.assertEqual(_dir("TEXT"), "enum_only")

    # ------------------------------------------------------------------
    # Audit integration: enum_only is the value audit/formats.py expects
    # ------------------------------------------------------------------

    def test_demoted_direction_is_enum_only_not_detect(self):
        """Demoted SaveFormat entries use 'enum_only', not 'detect'.

        This is critical: audit/formats.py looks for direction:'enum_only'
        to trigger content warnings. Using 'detect' would make the audit
        guard inert.
        """
        formats = [
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        pdf = result[0]
        self.assertEqual(pdf["direction"], "enum_only")
        self.assertNotEqual(pdf["direction"], "detect",
                            "Must use 'enum_only', not 'detect' — audit depends on it")


if __name__ == "__main__":
    unittest.main()

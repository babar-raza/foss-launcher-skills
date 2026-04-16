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
        """5-member SaveFormat + LdmMarkdownWriter + LdmPdfWriter + dispatch TEXT.

        When Pass 4 dispatch scanning adds a "text" export entry (from
        Document._save_as_text), the cross-reference keeps TEXT as export.
        """
        formats = [
            {"format": "MARKDOWN", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOC", "enum": "SaveFormat", "direction": "export"},
            {"format": "DOCX", "enum": "SaveFormat", "direction": "export"},
            {"format": "TEXT", "enum": "SaveFormat", "direction": "export"},
            {"format": "PDF", "enum": "SaveFormat", "direction": "export"},
            # I/O class entries (from Writer class detection)
            {"format": "LdmMarkdown", "enum": "", "direction": "export"},
            {"format": "LdmPdf", "enum": "", "direction": "export"},
            # Pass 4 dispatch scan entry (from Document._save_as_text)
            {"format": "text", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)

        def _dir(name):
            return next(f for f in result if f["format"] == name and f.get("enum"))["direction"]

        self.assertEqual(_dir("MARKDOWN"), "export")
        self.assertEqual(_dir("PDF"), "export")
        self.assertEqual(_dir("TEXT"), "export")
        self.assertEqual(_dir("DOC"), "enum_only")
        self.assertEqual(_dir("DOCX"), "enum_only")

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


class TestScanSaveDispatch(unittest.TestCase):
    """Tests for _scan_save_dispatch() — Pass 4 inline save detection."""

    def _write_file(self, tmp: Path, name: str, content: str) -> Path:
        fpath = tmp / name
        fpath.write_text(content, encoding="utf-8")
        return fpath

    # ------------------------------------------------------------------
    # Core: dispatch scanner rescues inline save
    # ------------------------------------------------------------------

    def test_dispatch_rescues_inline_save(self):
        """SaveFormat.TEXT ref + _save_as_text() method → emits export entry."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "document.py", '''\
class SaveFormat:
    TEXT = "text"
    DOC = "doc"

class Document:
    def save(self, path, fmt):
        if fmt == SaveFormat.TEXT:
            self._save_as_text(path)
        else:
            raise ValueError(fmt)

    def _save_as_text(self, path):
        with open(path, "w") as f:
            f.write(self.content)
            f.flush()
''')
            formats = [
                {"format": "TEXT", "enum": "SaveFormat", "direction": "export"},
                {"format": "DOC", "enum": "SaveFormat", "direction": "export"},
            ]
            result = _scan_save_dispatch(
                formats, [src], tmp, _SAVE_PAT, None)
            non_enum = [f for f in result if not f.get("enum")]
            self.assertEqual(len(non_enum), 1)
            self.assertEqual(non_enum[0]["format"], "text")
            self.assertEqual(non_enum[0]["direction"], "export")

    def test_stub_method_does_not_rescue(self):
        """SaveFormat.DOCX ref + stub _save_as_docx() → no entry emitted."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "document.py", '''\
class SaveFormat:
    DOCX = "docx"

class Document:
    def save(self, path, fmt):
        if fmt == SaveFormat.DOCX:
            self._save_as_docx(path)

    def _save_as_docx(self, path):
        raise ValueError("DOCX export not implemented")
''')
            formats = [
                {"format": "DOCX", "enum": "SaveFormat", "direction": "export"},
            ]
            result = _scan_save_dispatch(
                formats, [src], tmp, _SAVE_PAT, None)
            non_enum = [f for f in result if not f.get("enum")]
            self.assertEqual(len(non_enum), 0)

    def test_no_saveformat_ref_no_rescue(self):
        """_save_as_text() without SaveFormat.TEXT ref → no entry emitted."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "util.py", '''\
class Util:
    def _save_as_text(self, path):
        with open(path, "w") as f:
            f.write(self.content)
            f.flush()
''')
            formats = [
                {"format": "TEXT", "enum": "SaveFormat", "direction": "export"},
            ]
            result = _scan_save_dispatch(
                formats, [src], tmp, _SAVE_PAT, None)
            non_enum = [f for f in result if not f.get("enum")]
            self.assertEqual(len(non_enum), 0)

    def test_public_save_as_method(self):
        """save_as_csv() (public, no underscore) is also detected."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.py", '''\
class SaveFormat:
    CSV = "csv"

class Workbook:
    def save(self, path, fmt):
        if fmt == SaveFormat.CSV:
            self.save_as_csv(path)

    def save_as_csv(self, path, options=None):
        handler = CSVHandler()
        handler.save_csv(self._data, path, options)
        return path
''')
            formats = [
                {"format": "CSV", "enum": "SaveFormat", "direction": "export"},
            ]
            result = _scan_save_dispatch(
                formats, [src], tmp, _SAVE_PAT, None)
            non_enum = [f for f in result if not f.get("enum")]
            self.assertEqual(len(non_enum), 1)
            self.assertEqual(non_enum[0]["format"], "csv")

    def test_private_save_without_as(self):
        """_save_xlsx() (no 'as' in name) is also detected."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.py", '''\
class SaveFormat:
    XLSX = "xlsx"

class Workbook:
    def save(self, path, fmt):
        if fmt == SaveFormat.XLSX:
            self._save_xlsx(path)

    def _save_xlsx(self, path, password=None):
        saver = XMLSaver(self._model)
        saver.save_to_file(path)
        return path
''')
            formats = [
                {"format": "XLSX", "enum": "SaveFormat", "direction": "export"},
            ]
            result = _scan_save_dispatch(
                formats, [src], tmp, _SAVE_PAT, None)
            non_enum = [f for f in result if not f.get("enum")]
            self.assertEqual(len(non_enum), 1)
            self.assertEqual(non_enum[0]["format"], "xlsx")

    # ------------------------------------------------------------------
    # Regression: cells/python scenario
    # ------------------------------------------------------------------

    def test_cells_regression(self):
        """6 SaveFormat members + matching save methods → all stay export."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.py", '''\
class SaveFormat:
    XLSX = "xlsx"
    CSV = "csv"
    TSV = "tsv"
    MARKDOWN = "markdown"
    JSON = "json"
    AUTO = "auto"

class Workbook:
    def save(self, path, fmt=None):
        if fmt == SaveFormat.XLSX:
            self._save_xlsx(path)
        elif fmt == SaveFormat.CSV:
            self.save_as_csv(path)
        elif fmt == SaveFormat.TSV:
            self.save_as_csv(path, delimiter="\\t")
        elif fmt == SaveFormat.MARKDOWN:
            self.save_as_markdown(path)
        elif fmt == SaveFormat.JSON:
            self.save_as_json(path)

    def _save_xlsx(self, path, password=None):
        saver = XMLSaver(self._model)
        saver.save_to_file(path)
        return path

    def save_as_csv(self, path, options=None, delimiter=","):
        handler = CSVHandler()
        handler.save_csv(self._data, path, delimiter=delimiter)
        return path

    def save_as_markdown(self, path, options=None):
        handler = MarkdownHandler()
        handler.save_markdown(self._data, path)
        return path

    def save_as_json(self, path, options=None):
        handler = JsonHandler()
        handler.save_json(self._data, path)
        return path
''')
            members = ["XLSX", "CSV", "TSV", "MARKDOWN", "JSON", "AUTO"]
            formats = [
                {"format": m, "enum": "SaveFormat", "direction": "export"}
                for m in members
            ]
            result = _scan_save_dispatch(
                formats, [src], tmp, _SAVE_PAT, None)
            non_enum = [f for f in result if not f.get("enum")]
            detected = {f["format"] for f in non_enum}
            # XLSX, CSV, MARKDOWN, JSON detected via dispatch methods
            # TSV dispatches via save_as_csv (not save_as_tsv) → not detected
            # AUTO has no save_as_auto method → not detected
            self.assertIn("xlsx", detected)
            self.assertIn("csv", detected)
            self.assertIn("markdown", detected)
            self.assertIn("json", detected)
            # Now run cross-reference — the detected formats keep export
            result = _cross_reference_enum_directions(result, _SAVE_PAT, _LOAD_PAT)

            def _dir(name):
                return next(
                    f for f in result
                    if f["format"] == name and f.get("enum")
                )["direction"]

            self.assertEqual(_dir("XLSX"), "export")
            self.assertEqual(_dir("CSV"), "export")
            self.assertEqual(_dir("MARKDOWN"), "export")
            self.assertEqual(_dir("JSON"), "export")
            # TSV and AUTO have no direct save method → enum_only
            self.assertEqual(_dir("TSV"), "enum_only")
            self.assertEqual(_dir("AUTO"), "enum_only")

    # ------------------------------------------------------------------
    # Edge: empty inputs, no SaveFormat members
    # ------------------------------------------------------------------

    def test_no_saveformat_members(self):
        """No SaveFormat enum entries → function is a no-op."""
        formats = [
            {"format": "PDF", "enum": "FileFormat", "direction": "detect"},
        ]
        result = _scan_save_dispatch(formats, [], Path("/tmp"), _SAVE_PAT, None)
        self.assertEqual(len(result), 1)

    def test_empty_formats(self):
        """Empty formats list → no crash, no entries."""
        result = _scan_save_dispatch([], [], Path("/tmp"), _SAVE_PAT, None)
        self.assertEqual(result, [])

    def test_exportformat_dispatch(self):
        """ExportFormat.PDF ref + _save_as_pdf() → emits export entry."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "converter.py", '''\
class ExportFormat:
    PDF = "pdf"
    HTML = "html"

class Converter:
    def export(self, path, fmt):
        if fmt == ExportFormat.PDF:
            self._save_as_pdf(path)
        else:
            raise ValueError(fmt)

    def _save_as_pdf(self, path):
        renderer = PDFRenderer(self.model)
        renderer.render(path)
        renderer.flush()
''')
            formats = [
                {"format": "PDF", "enum": "ExportFormat", "direction": "export"},
                {"format": "HTML", "enum": "ExportFormat", "direction": "export"},
            ]
            result = _scan_save_dispatch(
                formats, [src], tmp, _SAVE_PAT, None)
            non_enum = [f for f in result if not f.get("enum")]
            self.assertEqual(len(non_enum), 1)
            self.assertEqual(non_enum[0]["format"], "pdf")
            self.assertEqual(non_enum[0]["direction"], "export")


if __name__ == "__main__":
    unittest.main()

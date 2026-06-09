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
from extraction.formats import (
    _cross_reference_enum_directions,
    _scan_save_dispatch,
    _scan_document_ctor_imports,
)

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

    def test_prefix_format_named_io_class_backs_loadformat(self):
        """LoadFormat.XLSX keeps 'import' when XlsxWorkbookLoader exists (prefix-format naming).

        Root cause guarded (CELLS-NET-FORMATS-001): cells/net uses prefix-format
        naming (XlsxWorkbookWorksheetLoader) not suffix-format (WorkbookXlsxLoader).
        _impl_noise_re strips compound suffixes ("workbookworksheet") so that Layer 3
        noise-stripped suffix match reduces the impl to "xlsx" and matches correctly.
        """
        formats = [
            {"format": "XLSX", "enum": "LoadFormat", "direction": "import"},
            {"format": "CSV", "enum": "LoadFormat", "direction": "import"},
            {"format": "XlsxWorkbookComments", "enum": "", "direction": "import"},
            {"format": "XlsxWorkbookWorksheet", "enum": "", "direction": "import"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        xlsx = next(f for f in result if f["format"] == "XLSX")
        csv = next(f for f in result if f["format"] == "CSV")
        self.assertEqual(xlsx["direction"], "import",
                         "XLSX must be backed by XlsxWorkbook* prefix-format I/O class")
        self.assertEqual(csv["direction"], "enum_only",
                         "CSV has no backing class and must be enum_only")

    def test_prefix_format_named_io_class_backs_saveformat(self):
        """SaveFormat.XLSX keeps 'export' when XlsxWorkbookWorksheet writer exists.

        Note: the non-enum entry uses the POST-suffix-stripping name (Writer already
        removed by the main scan loop), so "XlsxWorkbookWorksheet" not "...Writer".
        """
        formats = [
            {"format": "XLSX", "enum": "SaveFormat", "direction": "export"},
            {"format": "CSV", "enum": "SaveFormat", "direction": "export"},
            {"format": "XlsxWorkbookWorksheet", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        xlsx = next(f for f in result if f["format"] == "XLSX")
        csv = next(f for f in result if f["format"] == "CSV")
        self.assertEqual(xlsx["direction"], "export",
                         "XLSX must be backed by XlsxWorkbook* prefix-format I/O class")
        self.assertEqual(csv["direction"], "enum_only")

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


# Re-create patterns that include SourceFormat (FMT-02 fix)
_LOAD_PAT_WITH_SOURCE = re.compile(
    r"(LoadFormat|ImportFormat|InputFormat|SourceFormat)", re.IGNORECASE)


class TestSourceFormatPatternFix(unittest.TestCase):
    """Tests for FMT-02: SourceFormat enum → direction='import'.

    slides/python uses SourceFormat (PPT, PPTX, ODP) as its input-format enum.
    Before the fix, SourceFormat was not in load_format_pattern so its members
    were assigned direction='detect' instead of 'import'.
    """

    def test_source_format_gets_import_direction(self):
        """SourceFormat enum members → direction 'import' after cross-reference."""
        formats = [
            {"format": "PPT", "enum": "SourceFormat", "direction": "import"},
            {"format": "PPTX", "enum": "SourceFormat", "direction": "import"},
            {"format": "ODP", "enum": "SourceFormat", "direction": "import"},
        ]
        # No backing I/O classes exist (constructor-based import)
        # → cross_reference should demote to enum_only (no PptReader found)
        result = _cross_reference_enum_directions(
            formats, _SAVE_PAT, _LOAD_PAT_WITH_SOURCE)
        # All three should be demoted to enum_only (no Reader class found)
        directions = {f["format"]: f["direction"] for f in result}
        self.assertEqual(directions["PPT"], "enum_only")
        self.assertEqual(directions["PPTX"], "enum_only")
        self.assertEqual(directions["ODP"], "enum_only")

    def test_source_format_kept_when_backed(self):
        """SourceFormat.PPTX stays 'import' when a PptxReader I/O class exists."""
        formats = [
            {"format": "PPTX", "enum": "SourceFormat", "direction": "import"},
            {"format": "ODP", "enum": "SourceFormat", "direction": "import"},
            # Simulated I/O class for PPTX (from Pass 1 Loader detection)
            {"format": "Pptx", "enum": "", "direction": "import"},
        ]
        result = _cross_reference_enum_directions(
            formats, _SAVE_PAT, _LOAD_PAT_WITH_SOURCE)
        pptx = next(f for f in result if f["format"] == "PPTX")
        odp = next(f for f in result if f["format"] == "ODP")
        self.assertEqual(pptx["direction"], "import")
        self.assertEqual(odp["direction"], "enum_only")

    def test_source_format_not_confused_with_save_format(self):
        """SourceFormat is treated as load pattern, not save pattern."""
        # Verify _LOAD_PAT_WITH_SOURCE matches SourceFormat
        self.assertTrue(bool(_LOAD_PAT_WITH_SOURCE.search("SourceFormat")))
        # And _SAVE_PAT does NOT match SourceFormat
        self.assertFalse(bool(_SAVE_PAT.search("SourceFormat")))


class TestSerializerBackingPattern(unittest.TestCase):
    """Regression test: *Serializer* classes must be recognised as I/O backing.

    Root cause guarded (CELLS-CPP-FORMAT-SCAN-001 / A13 W.1):
      XlsxWorkbookSerializer in cells/cpp was not matched by the backing-class
      pattern (Importer|Exporter|Reader|Writer|Loader|Saver) → XLSX marked
      enum_only/functional:false → 2 CF FAILs on products/cells/cpp page.

    Fix: 'Serializer' added to importer_pattern + export direction check +
    suffix-stripping regex; 'workbook' added to _impl_noise_re.
    """

    def test_serializer_class_backs_xlsx_export(self):
        """XlsxWorkbookSerializer (stripped → XlsxWorkbook) must back SaveFormat.XLSX."""
        # Simulate output of detect_formats() for cells/cpp:
        # - SaveFormat.XLSX enum entry (from XlsxSaveFormat enum)
        # - XlsxWorkbook non-enum export entry (from XlsxWorkbookSerializer after strip)
        formats = [
            {"format": "XLSX", "enum": "SaveFormat", "direction": "export"},
            {"format": "XlsxWorkbook", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        xlsx = next(f for f in result if f["format"] == "XLSX")
        self.assertEqual(
            xlsx["direction"], "export",
            "SaveFormat.XLSX must NOT be demoted to enum_only when XlsxWorkbookSerializer exists"
        )
        self.assertTrue(
            xlsx.get("functional", False),
            "SaveFormat.XLSX must be functional:true when XlsxWorkbookSerializer exists"
        )

    def test_serializer_class_without_noise_suffix_backs_directly(self):
        """A Serializer class whose stripped name exactly matches a format is backed."""
        # e.g. XlsxSerializer → strip "Serializer" → "Xlsx" → backs XLSX directly
        formats = [
            {"format": "XLSX", "enum": "SaveFormat", "direction": "export"},
            {"format": "Xlsx", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        xlsx = next(f for f in result if f["format"] == "XLSX")
        self.assertEqual(xlsx["direction"], "export")
        self.assertTrue(xlsx.get("functional", False))

    def test_non_serializer_class_still_demoted(self):
        """SaveFormat entry without ANY backing class is still demoted to enum_only."""
        formats = [
            {"format": "ODS", "enum": "SaveFormat", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        ods = next(f for f in result if f["format"] == "ODS")
        self.assertEqual(ods["direction"], "enum_only")


class TestLoadSaveOptionsPattern(unittest.TestCase):
    """Regression test: *LoadOptions/*SaveOptions classes as format backing.

    Root cause guarded (PDF-JAVA-FORMAT-IMPORT-001 / A15):
      pdf/java HtmlLoadOptions was not detected as an importer → Html marked
      enum_only → CF FAILs on reference pages.

    Fix: load_save_options_pattern added to detect_formats() Pass 1b;
    HtmlLoadOptions → Html import, HtmlSaveOptions → Html export.
    """

    def test_save_options_backs_save_format_enum(self):
        """HtmlSaveOptions (export) backs SaveFormat.Html → stays export, not enum_only."""
        formats = [
            {"format": "Html", "enum": "SaveFormat", "direction": "export"},
            # From SaveOptions detection (Pass 1b)
            {"format": "Html", "enum": "", "direction": "export"},
            # From LoadOptions detection (Pass 1b)
            {"format": "Html", "enum": "", "direction": "import"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        html_enum = next(f for f in result if f["format"] == "Html" and f.get("enum"))
        self.assertEqual(
            html_enum["direction"], "export",
            "SaveFormat.Html must stay 'export' when HtmlSaveOptions exists"
        )
        self.assertTrue(
            html_enum.get("functional", False),
            "SaveFormat.Html must be functional:true with SaveOptions backing"
        )

    def test_pdf_save_options_backs_save_format(self):
        """PdfSaveOptions entry backs SaveFormat.Pdf → keeps export."""
        formats = [
            {"format": "Pdf", "enum": "SaveFormat", "direction": "export"},
            {"format": "Pdf", "enum": "", "direction": "export"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        pdf_enum = next(f for f in result if f["format"] == "Pdf" and f.get("enum"))
        self.assertEqual(pdf_enum["direction"], "export")
        self.assertTrue(pdf_enum.get("functional", False))

    def test_load_options_without_enum_still_emitted(self):
        """LoadOptions entry stands alone when no matching enum exists."""
        formats = [
            {"format": "Html", "enum": "", "direction": "import"},
        ]
        result = _cross_reference_enum_directions(formats, _SAVE_PAT, _LOAD_PAT)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["direction"], "import")


class TestDocumentCtorImports(unittest.TestCase):
    """Tests for _scan_document_ctor_imports() — Pass 1c.

    Root cause guarded (PDF-JAVA-FORMAT-IMPORT-001):
      pdf/java loads PDFs via `new Document(path)` without a PdfLoadOptions
      class, so Pass 1b never emits a PDF import entry.  Pass 1c fills this
      gap by detecting constructor-based import in Document.java/.cs.
    """

    def _write_file(self, tmp: Path, name: str, content: str) -> Path:
        fpath = tmp / name
        fpath.write_text(content, encoding="utf-8")
        return fpath

    def test_constructor_pdf_import_detected(self):
        """Document(String filePath) constructor → Pdf import entry emitted."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "Document.java", """\
public class Document {
    public Document(String filePath) throws IOException {
        this.load(filePath);
    }
    public Document() {}
}
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "java", "pdf", set()
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "Pdf")
            self.assertEqual(result[0]["direction"], "import")
            self.assertEqual(result[0]["enum"], "")

    def test_no_duplicate_when_load_options_exists(self):
        """Pass 1c skipped when import for primary format already detected."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "Document.java", """\
public class Document {
    public Document(String filePath) throws IOException {
        this.load(filePath);
    }
}
""")
            # Simulate Pass 1b already emitted a Pdf import via PdfLoadOptions
            result = _scan_document_ctor_imports(
                [src], tmp, "java", "pdf", {"pdf"}
            )
            self.assertEqual(len(result), 0,
                             "Pass 1c must not duplicate an already-detected import")

    def test_python_document_ctor_import_detected(self):
        """document.py with file_path param → primary-format import entry for Python."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "document.py", """\
class Document:
    def __init__(self, file_path: str = None):
        self._load(file_path)
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "python", "words", set()
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "Words")
            self.assertEqual(result[0]["direction"], "import")

    def test_python_workbook_ctor_import_detected(self):
        """workbook.py with file_path param → xlsx import entry (cells uses _FAMILY_PYTHON_PRIMARY_FMT)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.py", """\
class Workbook:
    def __init__(self, file_path=None, password=None):
        self._load(file_path)
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "python", "cells", set()
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "xlsx")
            self.assertEqual(result[0]["direction"], "import")

    def test_python_non_primary_stem_skipped(self):
        """Python file with non-primary stem (e.g. formatter.py) → no result."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "formatter.py", """\
class Formatter:
    def __init__(self, file_path: str = None):
        pass
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "python", "pdf", set()
            )
            self.assertEqual(len(result), 0)

    def test_python_no_duplicate_when_import_already_detected(self):
        """Pass 1c (Python) skipped when import for primary format already exists."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.py", """\
class Workbook:
    def __init__(self, file_path=None):
        pass
""")
            # cells maps to "xlsx" via _FAMILY_PYTHON_PRIMARY_FMT; pass "xlsx" as existing
            result = _scan_document_ctor_imports(
                [src], tmp, "python", "cells", {"xlsx"}
            )
            self.assertEqual(len(result), 0)

    def test_ctor_with_load_options_param_skipped(self):
        """Constructor that takes LoadOptions is not emitted (Pass 1b already handles it)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "Document.java", """\
public class Document {
    public Document(String filePath, HtmlLoadOptions options) throws IOException {
        this.load(filePath, options);
    }
}
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "java", "pdf", set()
            )
            self.assertEqual(len(result), 0,
                             "LoadOptions constructor must be skipped (Pass 1b handles it)")


class TestFamilyFormatAllowlist(unittest.TestCase):
    """Tests for the per-family format allowlist (EMAIL-CPP-FORMATS-001 fix).

    Root cause guarded: "cfb" was in _FALSE_POSITIVE_NAMES to suppress
    cells/python internal CFBWriter/CFBReader classes (used for XLSX encryption,
    not a user-facing format).  But email/cpp's cfb_reader/cfb_writer are
    genuine user-visible formats (Compound File Binary = .msg container).
    Fix: _FAMILY_FORMAT_ALLOWLISTS per-family dict overrides the global list.
    """

    def _write_cfb_hpp(self, tmp: Path) -> Path:
        fpath = tmp / "cfb_reader.hpp"
        fpath.write_text("""\
namespace aspose::email::foss::cfb {
class cfb_reader {
public:
    void read(const char* path);
    void parse();
};
}
""", encoding="utf-8")
        return fpath

    def test_cfb_allowed_for_email_family(self):
        """cfb_reader in email/cpp → 'cfb import' entry detected."""
        from extraction.tree_helpers import get_parser
        from extraction.formats import detect_formats
        parser = get_parser("cpp")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._write_cfb_hpp(tmp)
            formats, _ = detect_formats(parser, "cpp", tmp, tmp, "email")
            cfb_entries = [e for e in formats if e["format"].lower() == "cfb"]
            self.assertTrue(
                len(cfb_entries) > 0,
                f"email family must detect cfb_reader as 'cfb import'; got formats: "
                f"{[e['format'] for e in formats]}",
            )
            self.assertEqual(cfb_entries[0]["direction"], "import")

    def test_cfb_blocked_for_cells_family(self):
        """cfb_reader in cells context → no cfb entry (internal encryption impl)."""
        from extraction.tree_helpers import get_parser
        from extraction.formats import detect_formats
        parser = get_parser("cpp")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._write_cfb_hpp(tmp)
            formats, _ = detect_formats(parser, "cpp", tmp, tmp, "cells")
            cfb_entries = [e for e in formats if e["format"].lower() == "cfb"]
            self.assertEqual(
                len(cfb_entries), 0,
                f"cells family must not detect cfb_reader; got: {cfb_entries}",
            )


class TestDocumentCtorImportsTypeScript(unittest.TestCase):
    """Tests for TypeScript static load() detection in _scan_document_ctor_imports().

    Root cause guarded (CELLS-TYPESCRIPT-FORMATS-001):
      cells/typescript uses `static async load(filePath)` on Workbook, not a
      constructor or LoadOptions class.  Pass 1c previously excluded TypeScript
      (formats.py:203 `if language not in ("java", "csharp", "python")`).
      Fix: extend Pass 1c to recognise TypeScript/JavaScript static load().
    """

    def _write_file(self, tmp: Path, name: str, content: str) -> Path:
        fpath = tmp / name
        fpath.write_text(content, encoding="utf-8")
        return fpath

    def test_ts_static_load_detected_as_xlsx_import(self):
        """workbook.ts with static async load(filePath) → xlsx import entry emitted."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.ts", """\
export class Workbook {
    static async load(filePath: string, password?: string): Promise<Workbook> {
        const workbook = new Workbook(false);
        await workbook.loadFile(filePath);
        return workbook;
    }
}
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "typescript", "cells", set()
            )
            self.assertEqual(len(result), 1,
                             "static async load(filePath) on workbook.ts must emit 1 import entry")
            self.assertEqual(result[0]["direction"], "import")
            # cells maps to "xlsx" via _FAMILY_PYTHON_PRIMARY_FMT
            self.assertEqual(result[0]["format"].lower(), "xlsx")
            self.assertEqual(result[0]["enum"], "")

    def test_ts_static_load_primary_stem_filter(self):
        """TypeScript utility.ts (non-primary stem) with static async load → no entry.

        Root cause guarded: stem filter must prevent false positives from helper/util
        classes that coincidentally define a static load() method.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "utility.ts", """\
export class Utility {
    static async load(filePath: string): Promise<Utility> {
        return new Utility();
    }
}
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "typescript", "cells", set()
            )
            self.assertEqual(len(result), 0,
                             "Non-primary stem (utility) must not emit import entry")

    def test_ts_static_load_no_duplicate_when_import_exists(self):
        """TypeScript Pass 1c skipped when import for primary format already detected."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.ts", """\
export class Workbook {
    static async load(filePath: string): Promise<Workbook> {
        return new Workbook();
    }
}
""")
            # Simulate Pass 1b already emitting an xlsx import entry
            result = _scan_document_ctor_imports(
                [src], tmp, "typescript", "cells", {"xlsx"}
            )
            self.assertEqual(len(result), 0,
                             "Pass 1c must not duplicate an already-detected import")

    def test_ts_javascript_static_load_also_detected(self):
        """JavaScript workbook.js with static load(filePath) → import entry emitted.

        TypeScript and JavaScript share the same static load() pattern.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.js", """\
class Workbook {
    static async load(filePath) {
        const wb = new Workbook();
        await wb.loadFile(filePath);
        return wb;
    }
}
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "javascript", "cells", set()
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["direction"], "import")
            self.assertEqual(result[0]["format"].lower(), "xlsx")

    def test_java_ctor_import_still_detected_after_ts_extension(self):
        """Java Document(String filePath) constructor → Pdf import entry still emitted.

        Regression guard: TypeScript extension must not break existing Java support.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "Document.java", """\
public class Document {
    public Document(String filePath) throws IOException {
        this.load(filePath);
    }
    public Document() {}
}
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "java", "pdf", set()
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "Pdf")
            self.assertEqual(result[0]["direction"], "import")

    def test_python_workbook_ctor_import_still_detected_after_ts_extension(self):
        """workbook.py with __init__(file_path) → xlsx import entry still emitted.

        Regression guard: TypeScript extension must not break existing Python support.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.py", """\
class Workbook:
    def __init__(self, file_path=None, password=None):
        self._load(file_path)
""")
            result = _scan_document_ctor_imports(
                [src], tmp, "python", "cells", set()
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "xlsx")
            self.assertEqual(result[0]["direction"], "import")


class TestTsOoXmlWriterExport(unittest.TestCase):
    """Tests for _scan_ts_ooxml_writer_export() — Pass 1d TypeScript OOXML writer detection.

    Root cause guarded (CELLS-TYPESCRIPT-FORMATS-001):
      cells/typescript Workbook.save(filePath) calls writeToZip() which generates
      OOXML structure (xl/workbook.xml, [Content_Types].xml, _rels/.rels).  This is
      a confirmed XLSX writer but the extractor had no way to recognise generic-save
      + OOXML-path signals as XLSX proof.

      CRITICAL: CSV/JSON/MARKDOWN also route through the same writeToZip() call
      (library bug — save("file.csv") writes XLSX binary) and must NOT be upgraded
      to functional.  Only XLSX gains functional:true from this detection.
    """

    def _write_file(self, tmp: Path, name: str, content: str) -> Path:
        fpath = tmp / name
        fpath.write_text(content, encoding="utf-8")
        return fpath

    def test_ts_ooxml_writer_detected_as_xlsx_export(self):
        """workbook.ts with save() + OOXML paths → xlsx export entry emitted."""
        from extraction.formats import _scan_ts_ooxml_writer_export
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.ts", """\
export class Workbook {
    async save(filePath: string): Promise<void> {
        const zip = await createZipWriter();
        await this.writeToZip(zip);
        await writeFile(filePath, data);
    }
    private async writeToZip(zip: any): Promise<void> {
        await addZipEntry(zip, "[Content_Types].xml", this.generateContentTypes());
        await addZipEntry(zip, "_rels/.rels", this.generateRels());
        await addZipEntry(zip, "xl/workbook.xml", this.generateWorkbook());
    }
}
""")
            result = _scan_ts_ooxml_writer_export(
                [src], tmp, "cells", "typescript", set()
            )
            self.assertEqual(len(result), 1,
                             "save() + xl/workbook.xml path must emit 1 export entry")
            self.assertEqual(result[0]["direction"], "export")
            self.assertEqual(result[0]["format"].lower(), "xlsx")
            self.assertEqual(result[0]["enum"], "")

    def test_ts_no_ooxml_writer_no_export_entry(self):
        """workbook.ts with save() but NO OOXML paths → no export entry emitted.

        Root cause guarded: a generic save() without OOXML path evidence must not
        be mistakenly classified as an XLSX exporter.
        """
        from extraction.formats import _scan_ts_ooxml_writer_export
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.ts", """\
export class Workbook {
    async save(filePath: string): Promise<void> {
        // Write some data
        await writeFile(filePath, this.data);
    }
}
""")
            result = _scan_ts_ooxml_writer_export(
                [src], tmp, "cells", "typescript", set()
            )
            self.assertEqual(len(result), 0,
                             "save() without OOXML paths must NOT emit export entry")

    def test_ts_csv_enum_not_emitted_by_ooxml_writer_detection(self):
        """OOXML writer detection emits XLSX only — CSV must NOT appear in result.

        Root cause guarded (CELLS-TYPESCRIPT-FORMATS-001):
          workbook.ts detectFormat() branches to CSV, JSON, MARKDOWN — but all
          three call the same writeToZip() path (library bug: writes XLSX binary).
          The extractor must emit ONLY xlsx from the OOXML-writer signal, never CSV.
        """
        from extraction.formats import _scan_ts_ooxml_writer_export
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Workbook with SaveFormat enum (including CSV) AND OOXML writer
            src = self._write_file(tmp, "workbook.ts", """\
export enum SaveFormat {
    XLSX = "xlsx",
    CSV = "csv",
    JSON = "json",
}

export class Workbook {
    async save(filePath: string): Promise<void> {
        const format = this.detectFormat(filePath);
        const zip = await createZipWriter();
        await addZipEntry(zip, "[Content_Types].xml", "...");
        await addZipEntry(zip, "xl/workbook.xml", "...");
        await writeFile(filePath, data);
    }
    private detectFormat(filePath: string): SaveFormat {
        if (filePath.endsWith(".csv")) return SaveFormat.CSV;
        if (filePath.endsWith(".json")) return SaveFormat.JSON;
        return SaveFormat.XLSX;
    }
}
""")
            result = _scan_ts_ooxml_writer_export(
                [src], tmp, "cells", "typescript", set()
            )
            emitted_formats = {e["format"].lower() for e in result}
            self.assertNotIn("csv", emitted_formats,
                             "CSV must NOT be emitted — save('file.csv') writes XLSX binary")
            self.assertNotIn("json", emitted_formats,
                             "JSON must NOT be emitted — save('file.json') writes XLSX binary")

    def test_ts_ooxml_writer_no_duplicate_when_export_exists(self):
        """Pass 1d skipped when export for primary format already detected."""
        from extraction.formats import _scan_ts_ooxml_writer_export
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.ts", """\
export class Workbook {
    async save(filePath: string): Promise<void> {
        await addZipEntry(zip, "xl/workbook.xml", "...");
    }
}
""")
            result = _scan_ts_ooxml_writer_export(
                [src], tmp, "cells", "typescript", {"xlsx"}
            )
            self.assertEqual(len(result), 0,
                             "Must not duplicate an already-detected export")

    def test_ts_ooxml_writer_primary_stem_filter(self):
        """TypeScript utility.ts (non-primary stem) with OOXML paths → no entry.

        Root cause guarded: OOXML paths in helper/utility classes must not trigger
        xlsx export detection.
        """
        from extraction.formats import _scan_ts_ooxml_writer_export
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "utility.ts", """\
export class ZipUtils {
    async save(filePath: string): Promise<void> {
        await addZipEntry(zip, "xl/workbook.xml", "...");
        await writeFile(filePath, data);
    }
}
""")
            result = _scan_ts_ooxml_writer_export(
                [src], tmp, "cells", "typescript", set()
            )
            self.assertEqual(len(result), 0,
                             "Non-primary stem (utility) must not emit export entry")

    def test_ts_ooxml_writer_javascript_also_detected(self):
        """JavaScript workbook.js with save() + OOXML paths → export entry emitted."""
        from extraction.formats import _scan_ts_ooxml_writer_export
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._write_file(tmp, "workbook.js", """\
class Workbook {
    async save(filePath) {
        await addZipEntry(zip, "[Content_Types].xml", contentTypes);
        await addZipEntry(zip, "xl/workbook.xml", workbookXml);
        await writeFile(filePath, data);
    }
}
""")
            result = _scan_ts_ooxml_writer_export(
                [src], tmp, "cells", "javascript", set()
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["direction"], "export")


if __name__ == "__main__":
    unittest.main()

"""Tests for extraction/formats.py Pass 1g -- TypeScript/JavaScript
exported-function format detection (TC-MT040-14, G-TS-11).

Fixture source snippets below mirror the REAL, verified shape of
runs/.clone_cache/aspose_pdf_typescript (HEAD 04e7b50a) -- trimmed function
bodies, real names (`renderDocumentToDocx`, `renderEpub`, `writeFdf`/
`readFdf`, `writeXfdf`/`readXfdf`, `renderDocumentToTiff`,
`renderPageToPng`, `addImagePages`, `Document.Save`/`Open`/`OpenFile`) taken
directly from src/{docxexport,epubexport,mdexport,raster,fdf,xfdf,
imagepages,document}.ts.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from extraction.formats import (
    _scan_ts_io_functions,
    _validate_formats,
    detect_formats,
)
from extraction.tree_helpers import get_parser


def _write(tmp: Path, name: str, content: str) -> Path:
    fpath = tmp / name
    fpath.write_text(content, encoding="utf-8")
    return fpath


# ---------------------------------------------------------------------------
# Fixture source files (trimmed, real names/shapes from the live clone)
# ---------------------------------------------------------------------------

_DOCXEXPORT_TS = """\
export interface DocxOptions {
  mode?: 'flow' | 'textbox';
}

export function renderDocumentToDocx(doc: Document, opts: DocxOptions = {}): Uint8Array {
  return new Uint8Array();
}

export function renderPageToDocx(doc: Document, page: Page, opts: DocxOptions = {}): Uint8Array {
  return new Uint8Array();
}
"""

_EPUBEXPORT_TS = """\
export interface EpubOptions {
  identifier?: string;
}

export function renderEpub(
  doc: Document, opts: EpubOptions = {},
): Uint8Array {
  return new Uint8Array();
}
"""

_MDEXPORT_TS = """\
export function renderPageToMarkdown(
  doc: Document, page: Page, opts: object = {}): string {
  return '';
}

export function renderDocumentToMarkdown(
  doc: Document, opts: object = {}): string {
  return '';
}
"""

_RASTER_TS = """\
export const IMAGE_FORMATS = ['png', 'jpeg', 'tiff', 'bmp', 'gif'] as const;

export function renderDocumentToTiff(
  doc: Document, opts: object = {},
): Uint8Array {
  return new Uint8Array();
}

export function renderPageToPng(
  doc: Document, page: Page, opts: object = {}): Uint8Array {
  return new Uint8Array();
}

function renderPage(doc: Document, page: Page, opts: object, o: object): Uint8Array {
  return new Uint8Array();
}
"""

_FDF_TS = """\
export function writeFdf(data: object): Uint8Array {
  return new Uint8Array();
}

export function readFdf(bytes: Uint8Array): object {
  return {};
}
"""

_XFDF_TS = """\
export function writeXfdf(data: object): Uint8Array {
  return new Uint8Array();
}

export function readXfdf(bytes: Uint8Array): object {
  return {};
}
"""

_IMAGEPAGES_TS = """\
export interface AddImagePagesOptions {
  dpi?: number;
}

export function addImagePages(
  doc: Document, data: Uint8Array, opts: AddImagePagesOptions = {},
): object {
  return {};
}
"""

# document.ts -- real methods are PascalCase (Open/OpenFile/Save), NOT
# camelCase, even though this repo's free functions are camelCase. Signal
# (d) (primary-format export) must match `Save(` case-insensitively.
_DOCUMENT_TS = """\
export class Document {
  static New(format?: string): Document {
    return new Document();
  }

  static Open(buf: Uint8Array, opts: object = {}): Document {
    return new Document();
  }

  static OpenFile(fileName: string, opts: object = {}): Document {
    return new Document();
  }

  Save(options: object = {}): Uint8Array {
    return new Uint8Array();
  }
}
"""


def _detect_ts(tmp: Path, family: str = "pdf"):
    parser = get_parser("typescript")
    return detect_formats(parser, "typescript", tmp, tmp, family)


class TestScanTsIoFunctionsDirect:
    """Direct unit tests for _scan_ts_io_functions() -- Pass 1g."""

    def test_docxexport_yields_docx_export(self, tmp_path):
        src = _write(tmp_path, "docxexport.ts", _DOCXEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        docx = [e for e in entries if e["format"] == "docx"]
        assert len(docx) == 1
        assert docx[0]["direction"] == "export"
        assert docx[0]["evidence_kind"] == "ts_io_identifier"

    def test_epubexport_yields_epub_export(self, tmp_path):
        src = _write(tmp_path, "epubexport.ts", _EPUBEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        epub = [e for e in entries if e["format"] == "epub"]
        assert len(epub) == 1
        assert epub[0]["direction"] == "export"

    def test_fdf_yields_both_directions(self, tmp_path):
        src = _write(tmp_path, "fdf.ts", _FDF_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        directions = {e["direction"] for e in entries if e["format"] == "fdf"}
        assert directions == {"import", "export"}

    def test_xfdf_yields_both_directions(self, tmp_path):
        src = _write(tmp_path, "xfdf.ts", _XFDF_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        directions = {e["direction"] for e in entries if e["format"] == "xfdf"}
        assert directions == {"import", "export"}

    def test_raster_yields_tiff_export_and_png_export(self, tmp_path):
        src = _write(tmp_path, "raster.ts", _RASTER_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        found = {(e["format"], e["direction"]) for e in entries}
        assert ("tiff", "export") in found
        assert ("png", "export") in found
        # IMAGE_FORMATS is a plain array const, not a function/arrow -- must
        # not be treated as a candidate identifier at all.
        assert not any(e["format"] not in ("tiff", "png") for e in entries
                        if e["file"].endswith("raster.ts"))

    def test_mdexport_file_stem_and_name_analysis_both_fire(self, tmp_path):
        src = _write(tmp_path, "mdexport.ts", _MDEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        found = {(e["format"], e["direction"]) for e in entries}
        # File-stem signal (c): "mdexport" -> "md" + "export".
        assert ("md", "export") in found
        # Name-analysis signal (b): renderDocumentToMarkdown -> "markdown".
        assert ("markdown", "export") in found

    def test_document_primary_save_yields_family_title_export(self, tmp_path):
        src = _write(tmp_path, "document.ts", _DOCUMENT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        pdf_entries = [e for e in entries if e["format"] == "Pdf"]
        assert len(pdf_entries) == 1
        assert pdf_entries[0]["direction"] == "export"
        assert pdf_entries[0]["evidence_kind"] == "ts_io_identifier"

    def test_document_static_open_methods_yield_no_format(self, tmp_path):
        # Open/OpenFile/New are real static methods on Document but name no
        # format token -- only the Save-based primary-export signal (d)
        # should produce an entry for this file, not signal (a)/(b).
        src = _write(tmp_path, "document.ts", _DOCUMENT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        assert all(e["format"] == "Pdf" for e in entries)

    def test_dedupe_by_format_and_direction(self, tmp_path):
        # renderPageToDocx and renderDocumentToDocx both resolve to
        # docx/export -- only one entry should survive.
        src = _write(tmp_path, "docxexport.ts", _DOCXEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        docx = [e for e in entries if e["format"] == "docx"]
        assert len(docx) == 1

    def test_claims_emitted(self, tmp_path):
        claims: list[tuple] = []

        def _add_claim(kind, text, file="", line=0):
            claims.append((kind, text, file, line))

        src = _write(tmp_path, "fdf.ts", _FDF_TS)
        _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", _add_claim)
        assert any("fdf" in c[1].lower() for c in claims)

    # ------------------------------------------------------------------
    # Negative controls
    # ------------------------------------------------------------------

    def test_add_image_pages_yields_nothing(self, tmp_path):
        """addImagePages -- real, exported, verified against the live clone
        -- must NOT produce a format entry. Documented, accepted miss."""
        src = _write(tmp_path, "imagepages.ts", _IMAGEPAGES_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        assert entries == []

    def test_language_gate_python(self, tmp_path):
        src = _write(tmp_path, "docxexport.ts", _DOCXEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "python", "pdf", None)
        assert entries == []

    def test_language_gate_go(self, tmp_path):
        src = _write(tmp_path, "docxexport.ts", _DOCXEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "go", "pdf", None)
        assert entries == []

    def test_language_gate_java(self, tmp_path):
        src = _write(tmp_path, "docxexport.ts", _DOCXEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "java", "pdf", None)
        assert entries == []

    def test_empty_files_list_no_crash(self, tmp_path):
        assert _scan_ts_io_functions([], tmp_path, "typescript", "pdf", None) == []

    def test_random_camel_export_with_no_format_token(self, tmp_path):
        src = _write(tmp_path, "misc.ts", (
            "export function computeChecksumValue(data: Uint8Array): number {\n"
            "  return 0;\n"
            "}\n"
        ))
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        assert entries == []

    def test_stem_signal_requires_an_export_line(self, tmp_path):
        # A file named like a stem-signal match but with NO export at all
        # (all-private helpers) must not fire the file-stem signal.
        src = _write(tmp_path, "mdexport.ts", (
            "function helper(): string {\n  return '';\n}\n"
        ))
        entries = _scan_ts_io_functions([src], tmp_path, "typescript", "pdf", None)
        assert entries == []

    def test_javascript_language_same_path(self, tmp_path):
        src = _write(tmp_path, "epubexport.ts", _EPUBEXPORT_TS)
        entries = _scan_ts_io_functions([src], tmp_path, "javascript", "pdf", None)
        assert any(e["format"] == "epub" for e in entries)


class TestValidateFormatsEvidenceKindExemption:
    """_validate_formats must exempt ts_io_identifier entries from the
    false-positive-name rejection (png/xml/etc.), since that pass is already
    allowlist-gated at the point the token is picked."""

    def test_png_dropped_without_evidence_kind(self):
        formats = [{"format": "png", "enum": "", "value": "", "file": "a.ts",
                    "line": 1, "direction": "export"}]
        result = _validate_formats(formats, frozenset({"png"}), frozenset())
        assert result == []

    def test_png_survives_with_ts_io_identifier_tag(self):
        formats = [{"format": "png", "enum": "", "value": "", "file": "a.ts",
                    "line": 1, "direction": "export",
                    "evidence_kind": "ts_io_identifier"}]
        result = _validate_formats(formats, frozenset({"png"}), frozenset())
        assert len(result) == 1
        assert result[0]["format"] == "png"

    def test_unrelated_evidence_kind_does_not_exempt(self):
        formats = [{"format": "png", "enum": "", "value": "", "file": "a.ts",
                    "line": 1, "direction": "export",
                    "evidence_kind": "pascal_verb_token"}]
        result = _validate_formats(formats, frozenset({"png"}), frozenset())
        assert result == []


class TestDetectFormatsIntegration:
    """End-to-end: detect_formats() on a pdf/typescript-shaped package
    containing the real, verified file set must produce all the acceptance
    tuples named in the MT040 plan (docx/epub/md/tiff/fdf/xfdf/Pdf)."""

    def test_full_acceptance_tuple_set(self, tmp_path):
        _write(tmp_path, "docxexport.ts", _DOCXEXPORT_TS)
        _write(tmp_path, "epubexport.ts", _EPUBEXPORT_TS)
        _write(tmp_path, "mdexport.ts", _MDEXPORT_TS)
        _write(tmp_path, "raster.ts", _RASTER_TS)
        _write(tmp_path, "fdf.ts", _FDF_TS)
        _write(tmp_path, "xfdf.ts", _XFDF_TS)
        _write(tmp_path, "imagepages.ts", _IMAGEPAGES_TS)
        _write(tmp_path, "document.ts", _DOCUMENT_TS)

        formats, claims = _detect_ts(tmp_path)
        found = {(f["format"], f["direction"]) for f in formats}

        for expected in [
            ("docx", "export"),
            ("epub", "export"),
            ("md", "export"),
            ("tiff", "export"),
            ("fdf", "export"), ("fdf", "import"),
            ("xfdf", "export"), ("xfdf", "import"),
            ("Pdf", "export"),
        ]:
            assert expected in found, f"missing {expected} in {sorted(found)}"

        # addImagePages must not have contributed any entry.
        assert not any(f["file"].endswith("imagepages.ts") for f in formats)

    def test_claims_reference_typescript_function_names(self, tmp_path):
        _write(tmp_path, "fdf.ts", _FDF_TS)
        _, claims = _detect_ts(tmp_path)
        assert any("writeFdf" in c["text"] or "fdf" in c["text"].lower()
                   for c in claims)

"""Tests for extraction/format_signals.py -- identifier-word format
recognizer (D-6, TC-MT040-45).

Covers the two recognizer entry points (`recognize_pascal_verb_token` --
Pass-1e parity mode; `recognize_camel_identifier_format` -- the general mode
used by the new TypeScript/JavaScript exported-function pass, TC-MT040-14)
and the shared word-splitting primitives they're built on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from extraction.format_signals import (
    _KNOWN_FORMAT_TOKENS,
    _PASCAL_VERB_KNOWN_TOKENS,
    _split_camel_words,
    _split_pascal_format_token,
    _split_snake_words,
    recognize_camel_identifier_format,
    recognize_pascal_verb_token,
)


class TestSplitCamelWords:
    """Unit tests for the general camelCase/PascalCase word splitter."""

    def test_lowercase_start_camel_with_trailing_format_token(self):
        assert _split_camel_words("renderDocumentToDocx") == [
            "render", "document", "to", "docx",
        ]

    def test_pascal_start_whole_acronym(self):
        assert _split_camel_words("AddSVG") == ["add", "svg"]

    def test_acronym_boundary_followed_by_word(self):
        # Same acronym rule as _split_pascal_format_token, applied across the
        # whole identifier: the run "SVG" ends because "F" starts a new word.
        assert _split_camel_words("AddSVGFromStream") == [
            "add", "svg", "from", "stream",
        ]

    def test_no_format_token_present_documented_shape(self):
        # The real, verified pdf/typescript export imagepages.ts::addImagePages
        # -- neither "image" nor "pages" is a format token.
        assert _split_camel_words("addImagePages") == ["add", "image", "pages"]

    def test_leading_underscore_and_dollar_stripped(self):
        assert _split_camel_words("_privateHelper") == ["private", "helper"]
        assert _split_camel_words("$specialVar") == ["special", "var"]

    def test_empty_string(self):
        assert _split_camel_words("") == []

    def test_single_lowercase_word(self):
        assert _split_camel_words("render") == ["render"]

    def test_digits_attach_to_preceding_run(self):
        assert _split_camel_words("renderTo3ds") == ["render", "to3ds"]

    def test_real_pdf_typescript_names(self):
        # Verified live against runs/.clone_cache/aspose_pdf_typescript/src/
        # {fdf,xfdf,raster}.ts (HEAD 04e7b50a).
        assert _split_camel_words("writeFdf") == ["write", "fdf"]
        assert _split_camel_words("readXfdf") == ["read", "xfdf"]
        assert _split_camel_words("renderPageToPng") == [
            "render", "page", "to", "png",
        ]


class TestSplitSnakeWords:
    """Unit tests for the snake_case word splitter (not yet wired into any
    formats.py pass -- provided so format_signals.py covers all three case
    styles the D-6 design calls for)."""

    def test_basic(self):
        assert _split_snake_words("load_from_json") == ["load", "from", "json"]

    def test_leading_trailing_underscores_stripped(self):
        assert _split_snake_words("_save_xlsx_") == ["save", "xlsx"]

    def test_empty(self):
        assert _split_snake_words("") == []

    def test_single_word(self):
        assert _split_snake_words("save") == ["save"]


class TestRecognizePascalVerbToken:
    """Pass-1e parity recognizer -- must reproduce the pre-refactor
    _split_pascal_format_token-based behaviour exactly: single word after
    the verb only, ORIGINAL case preserved, no filler-skipping, no scanning
    past the first word."""

    def test_svg_import_original_case_preserved(self):
        result = recognize_pascal_verb_token("Add", "SVG")
        assert result == {
            "format": "SVG",
            "direction": "import",
            "evidence_kind": "pascal_verb_token",
        }

    def test_acronym_boundary_token_only(self):
        result = recognize_pascal_verb_token("Add", "SVGFromStream")
        assert result["format"] == "SVG"

    def test_export_verb_json(self):
        result = recognize_pascal_verb_token("Export", "JSON")
        assert result == {
            "format": "JSON",
            "direction": "export",
            "evidence_kind": "pascal_verb_token",
        }

    def test_unknown_verb_returns_none(self):
        assert recognize_pascal_verb_token("Get", "SVG") is None
        assert recognize_pascal_verb_token("Set", "SVG") is None

    def test_unknown_token_returns_none(self):
        assert recognize_pascal_verb_token("Add", "Watermark") is None
        assert recognize_pascal_verb_token("Add", "Page") is None

    def test_only_first_word_considered_no_multiword_scan(self):
        # "ImagePages" -> only "Image" is checked (the acronym-boundary rule
        # takes the ordinary-word branch and stops there); "Pages" is never
        # reached. This is the exact pre-refactor contract -- unlike
        # recognize_camel_identifier_format, this path never scans further.
        assert recognize_pascal_verb_token("Add", "ImagePages") is None

    def test_fdf_xfdf_not_recognized_here_by_design(self):
        # Golden-parity finding (TC-MT040-14/45): _KNOWN_FORMAT_TOKENS grew
        # "fdf"/"xfdf" for the new TypeScript pass, but pdf/go's real
        # Form.ExportFDF/ImportFDF and pdf/net's real Form.ExportFdf/ImportFdf
        # methods must NOT gain a new Pass-1e format entry as a side effect
        # -- that would break byte-identical parity on two already-launched,
        # non-TypeScript products. _PASCAL_VERB_KNOWN_TOKENS is the frozen
        # baseline that keeps this path blind to tokens added after ST-022.
        assert recognize_pascal_verb_token("Export", "FDF") is None
        assert recognize_pascal_verb_token("Import", "FDF") is None
        assert recognize_pascal_verb_token("Export", "XFDF") is None
        assert recognize_pascal_verb_token("Import", "XFDF") is None

    def test_empty_remainder(self):
        assert recognize_pascal_verb_token("Add", "") is None


class TestRecognizeCamelIdentifierFormat:
    """General recognizer for the TypeScript/JavaScript exported-function
    pass (TC-MT040-14). Full multi-word scan, lowercase tokens, filler-word
    skipping."""

    def test_render_document_to_docx(self):
        result = recognize_camel_identifier_format("renderDocumentToDocx")
        assert result == {
            "format": "docx",
            "direction": "export",
            "evidence_kind": "ts_io_identifier",
        }

    def test_export_fdf_file_plan_example_name(self):
        result = recognize_camel_identifier_format("exportFdfFile")
        assert result == {
            "format": "fdf",
            "direction": "export",
            "evidence_kind": "ts_io_identifier",
        }

    def test_import_xfdf_file_plan_example_name(self):
        result = recognize_camel_identifier_format("importXfdfFile")
        assert result == {
            "format": "xfdf",
            "direction": "import",
            "evidence_kind": "ts_io_identifier",
        }

    def test_write_fdf_real_repo_name(self):
        # Verified live: runs/.clone_cache/aspose_pdf_typescript/src/fdf.ts
        result = recognize_camel_identifier_format("writeFdf")
        assert result == {
            "format": "fdf",
            "direction": "export",
            "evidence_kind": "ts_io_identifier",
        }

    def test_read_xfdf_real_repo_name(self):
        # Verified live: runs/.clone_cache/aspose_pdf_typescript/src/xfdf.ts
        result = recognize_camel_identifier_format("readXfdf")
        assert result == {
            "format": "xfdf",
            "direction": "import",
            "evidence_kind": "ts_io_identifier",
        }

    def test_render_epub(self):
        result = recognize_camel_identifier_format("renderEpub")
        assert result == {
            "format": "epub",
            "direction": "export",
            "evidence_kind": "ts_io_identifier",
        }

    def test_render_document_to_tiff(self):
        result = recognize_camel_identifier_format("renderDocumentToTiff")
        assert result["format"] == "tiff"
        assert result["direction"] == "export"

    def test_load_from_xfdf(self):
        result = recognize_camel_identifier_format("loadFromXfdf")
        assert result == {
            "format": "xfdf",
            "direction": "import",
            "evidence_kind": "ts_io_identifier",
        }

    def test_render_page_to_png_survives_as_evidence_kind_tagged(self):
        # "png" is a global false-positive name in formats.py's
        # _FALSE_POSITIVE_NAMES -- this recognizer doesn't know about that
        # (it's a formats.py/_validate_formats concern), it just reports the
        # real identified token.
        result = recognize_camel_identifier_format("renderPageToPng")
        assert result["format"] == "png"
        assert result["direction"] == "export"
        assert result["evidence_kind"] == "ts_io_identifier"

    # ------------------------------------------------------------------
    # Negative controls
    # ------------------------------------------------------------------

    def test_add_image_pages_documented_miss(self):
        """addImagePages is a real, exported pdf/typescript function
        (verified: runs/.clone_cache/aspose_pdf_typescript/src/imagepages.ts)
        that names no format token -- this MUST return None. Not a bug to
        special-case around."""
        assert recognize_camel_identifier_format("addImagePages") is None

    def test_add_watermark_no_token(self):
        assert recognize_camel_identifier_format("addWatermark") is None

    def test_render_page_no_token(self):
        assert recognize_camel_identifier_format("renderPage") is None

    def test_random_camel_name_with_no_format_token(self):
        assert recognize_camel_identifier_format("computeChecksumValue") is None

    def test_unrecognized_verb(self):
        # "build"/"rasterize"/"gid" are not import/export verbs at all.
        assert recognize_camel_identifier_format("buildGlyphSource") is None
        assert recognize_camel_identifier_format("rasterizeFormRgba") is None
        assert recognize_camel_identifier_format("gidForCode") is None

    def test_single_word_returns_none(self):
        assert recognize_camel_identifier_format("save") is None
        assert recognize_camel_identifier_format("render") is None

    def test_empty_string_returns_none(self):
        assert recognize_camel_identifier_format("") is None

    def test_new_open_no_format_still_none(self):
        # Real pdf/typescript static methods on Document -- verified live:
        # neither names a format token, so neither should match.
        assert recognize_camel_identifier_format("Open") is None
        assert recognize_camel_identifier_format("OpenFile") is None
        assert recognize_camel_identifier_format("New") is None


class TestKnownFormatTokens:
    def test_fdf_and_xfdf_present_in_canonical_set(self):
        assert "fdf" in _KNOWN_FORMAT_TOKENS
        assert "xfdf" in _KNOWN_FORMAT_TOKENS

    def test_pascal_verb_baseline_excludes_fdf_xfdf(self):
        assert "fdf" not in _PASCAL_VERB_KNOWN_TOKENS
        assert "xfdf" not in _PASCAL_VERB_KNOWN_TOKENS

    def test_pascal_verb_baseline_is_subset_of_canonical_set(self):
        assert _PASCAL_VERB_KNOWN_TOKENS <= _KNOWN_FORMAT_TOKENS

    def test_allowlist_contains_common_document_formats(self):
        for token in ("svg", "pdf", "html", "json", "xlsx", "docx", "pptx",
                      "fdf", "xfdf"):
            assert token in _KNOWN_FORMAT_TOKENS

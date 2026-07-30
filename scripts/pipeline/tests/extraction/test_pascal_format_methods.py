"""Tests for extraction/formats.py Pass 1e -- PascalCase verb+format-token
method-name detection (ST-022, 2026-07-30).

Root cause guarded (ST-022, found via the 2026-07-14 pdf/go truth audit,
reports/audit/pdf-go-truth-2026-07-14.md, Page.md format_truth FAIL):
formats.json recorded ``svg: export`` (from the unrelated ``svgDevice`` HTML
export backend, matched via the "Device" substring in the class-name pass)
but never ``svg: import``, even though ``Page.AddSVG``, ``Page.AddSVGFromStream``,
``Page.AddSVGObject``, ``Document.LoadSVG``, and ``Document.LoadSVGFromStream``
are real, verified import methods (confirmed against
runs/.clone_cache/aspose_pdf_go/svg.go and knowledge/pdf/go/merged/
api_surface.json). Every prior detection pass ties format evidence to either
an enum class name, a class NAME matching Importer/Exporter/Reader/Writer/
Loader/Saver/Serializer/Device/Renderer, a single primary-format constructor,
or a snake_case method-name convention -- none of which fire for a PascalCase
secondary-format method on the library's own primary type (Go has no
class-nested methods at all: `func (p *Page) AddSVG(...)` is a top-level
declaration linked to Page only by receiver, not a child node of Page's own
type_spec).

This must be a generic fix (not Go-only, not pdf/go-only): the new pass
(_scan_pascal_verb_format_methods) is a plain regex scan over raw file text,
independent of language-specific tree-sitter node shapes, and is gated by an
ALLOWLIST of known short format tokens (_KNOWN_FORMAT_TOKENS) rather than a
denylist -- "Add"/"Insert" are used constantly for non-format operations in
these APIs (AddPage, AddAnnotation, AddWatermark, ...), so accepting any
capitalized suffix would flood every product with false positives.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from extraction.formats import (
    _KNOWN_FORMAT_TOKENS,
    _split_pascal_format_token,
    _scan_pascal_verb_format_methods,
    detect_formats,
)
from extraction.tree_helpers import get_parser


def _write(tmp: Path, name: str, content: str) -> Path:
    fpath = tmp / name
    fpath.write_text(content, encoding="utf-8")
    return fpath


# Real method bodies from runs/.clone_cache/aspose_pdf_go/svg.go, trimmed to
# the signatures relevant to this test (verified live against the actual
# FOSS repo before writing this fixture).
_PDF_GO_SVG_SOURCE = """\
package asposepdf

import (
\t"io"
\t"os"
)

// AddSVG reads an SVG file and renders it into the given rectangle on the page.
func (p *Page) AddSVG(path string, rect Rectangle) error {
\tf, err := os.Open(path)
\tif err != nil {
\t\treturn err
\t}
\tdefer func() { _ = f.Close() }()
\treturn p.AddSVGFromStream(f, rect)
}

// AddSVGFromStream renders an SVG from any io.Reader into the given rectangle.
func (p *Page) AddSVGFromStream(r io.Reader, rect Rectangle) error {
\tsvg, err := parseSVGReader(r)
\tif err != nil {
\t\treturn err
\t}
\treturn p.AddSVGObject(svg, rect)
}

// AddSVGObject renders a pre-parsed SVG into the given rectangle on the page.
func (p *Page) AddSVGObject(svg *SVG, rect Rectangle) error {
\treturn renderSVG(p, svg, rect)
}

// LoadSVG reads and parses an SVG file once, returning a *SVG.
func (d *Document) LoadSVG(path string) (*SVG, error) {
\tf, err := os.Open(path)
\tif err != nil {
\t\treturn nil, err
\t}
\tdefer func() { _ = f.Close() }()
\treturn d.LoadSVGFromStream(f)
}

// LoadSVGFromStream is the io.Reader variant of LoadSVG.
func (d *Document) LoadSVGFromStream(r io.Reader) (*SVG, error) {
\treturn parseSVGReader(r)
}

// AddPage appends a new blank page to the document.
func (d *Document) AddPage() *Page {
\treturn d.addPageInternal()
}

// AddWatermark stamps a text watermark on every page -- not a format claim.
func (d *Document) AddWatermark(text string) error {
\treturn d.stampWatermark(text)
}

// AddAnnotation attaches an annotation object to the page -- not a format claim.
func (p *Page) AddAnnotation(a *Annotation) error {
\treturn p.attach(a)
}

// InsertBookmark inserts a bookmark node into the outline tree -- not a format claim.
func (d *Document) InsertBookmark(title string, pageNum int) error {
\treturn d.outline.insert(title, pageNum)
}
"""


class TestSplitPascalFormatToken(unittest.TestCase):
    """Unit tests for the acronym-boundary word splitter."""

    def test_whole_remainder_is_acronym(self):
        self.assertEqual(_split_pascal_format_token("SVG"), "SVG")

    def test_acronym_followed_by_word(self):
        self.assertEqual(_split_pascal_format_token("SVGFromStream"), "SVG")
        self.assertEqual(_split_pascal_format_token("SVGObject"), "SVG")

    def test_ordinary_capitalized_word(self):
        self.assertEqual(_split_pascal_format_token("Watermark"), "Watermark")
        self.assertEqual(_split_pascal_format_token("Page"), "Page")

    def test_empty_remainder(self):
        self.assertEqual(_split_pascal_format_token(""), "")

    def test_http_style_acronym_boundary(self):
        # Same rule as the docstring example: HTTPServer -> HTTP (not HTTPS).
        self.assertEqual(_split_pascal_format_token("HTTPServer"), "HTTP")


class TestScanPascalVerbFormatMethods(unittest.TestCase):
    """Tests for _scan_pascal_verb_format_methods() -- Pass 1e."""

    # ------------------------------------------------------------------
    # (a) Positive case: the real ST-022 gap -- AddSVG/LoadSVG-style
    # secondary-format methods must register the correct (import) direction.
    # ------------------------------------------------------------------

    def test_addsvg_registers_svg_import(self):
        """Page.AddSVG(path string, ...) -- a real file-path-reading method --
        must register svg:import even though Page is not an Importer-named
        class and SVG is not pdf/go's primary/constructor format."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = _write(tmp, "svg.go", _PDF_GO_SVG_SOURCE)
            entries = _scan_pascal_verb_format_methods([src], tmp, None)
            svg_entries = [e for e in entries if e["format"].lower() == "svg"]
            self.assertEqual(len(svg_entries), 1,
                              f"expected exactly one svg entry, got: {entries}")
            self.assertEqual(svg_entries[0]["direction"], "import")
            self.assertEqual(svg_entries[0]["enum"], "")

    def test_loadsvg_also_backs_the_same_entry(self):
        """Document.LoadSVG / LoadSVGFromStream are additional evidence for
        the same svg:import claim -- deduplicated, not double-counted."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = _write(tmp, "svg.go", _PDF_GO_SVG_SOURCE)
            entries = _scan_pascal_verb_format_methods([src], tmp, None)
            svg_entries = [e for e in entries if e["format"].lower() == "svg"]
            self.assertEqual(len(svg_entries), 1)

    def test_full_detect_formats_integration_yields_svg_import(self):
        """End-to-end: detect_formats() on a Go package containing svg.go
        must produce an svg:import entry via the real public entry point,
        not just the isolated pass function."""
        parser = get_parser("go")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write(tmp, "svg.go", _PDF_GO_SVG_SOURCE)
            formats, claims = detect_formats(parser, "go", tmp, tmp, "pdf")
            svg_entries = [f for f in formats if f["format"].lower() == "svg"]
            self.assertTrue(
                any(e["direction"] == "import" for e in svg_entries),
                f"expected an svg import entry from detect_formats(); got: {formats}",
            )
            # A claim documenting the import capability must also be emitted.
            svg_claims = [c for c in claims if "svg" in c["text"].lower()
                          and "import" in c["text"].lower()]
            self.assertTrue(svg_claims, f"expected an svg import claim; got: {claims}")

    def test_export_verb_registers_export_direction(self):
        """A Save/Write/Export-prefixed method with a known format token
        registers direction='export' (the complementary case to import)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = _write(tmp, "export_json.go", """\
package asposepdf

func (f *Form) ExportJSON(path string) error {
\treturn writeJSONFile(f, path)
}
""")
            entries = _scan_pascal_verb_format_methods([src], tmp, None)
            json_entries = [e for e in entries if e["format"].lower() == "json"]
            self.assertEqual(len(json_entries), 1)
            self.assertEqual(json_entries[0]["direction"], "export")

    # ------------------------------------------------------------------
    # (b) Negative controls: no false positives on unrelated method names
    # that happen to contain format-like or common-noun suffixes, and no
    # interference with the existing bidirectional-format detection passes.
    # ------------------------------------------------------------------

    def test_addpage_is_not_a_format(self):
        """AddPage/AddWatermark/AddAnnotation/InsertBookmark must NOT produce
        format entries -- 'Page', 'Watermark', 'Annotation', 'Bookmark' are
        not in the known-format-token allowlist. This is the core false-
        positive risk of allowing 'Add'/'Insert' as I/O verbs at all."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = _write(tmp, "svg.go", _PDF_GO_SVG_SOURCE)
            entries = _scan_pascal_verb_format_methods([src], tmp, None)
            bad_tokens = {"page", "watermark", "annotation", "bookmark"}
            found = {e["format"].lower() for e in entries}
            self.assertFalse(
                found & bad_tokens,
                f"non-format nouns leaked through as format entries: {found & bad_tokens}",
            )

    def test_unknown_short_acronym_is_rejected(self):
        """AddXYZ (a plausible-looking but unrecognized acronym) must not be
        accepted -- the allowlist gate must actually reject unknown tokens."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = _write(tmp, "misc.go", """\
package asposepdf

func (p *Page) AddXYZ(path string) error {
\treturn nil
}
""")
            entries = _scan_pascal_verb_format_methods([src], tmp, None)
            self.assertEqual(entries, [])

    def test_getter_verb_not_treated_as_io(self):
        """GetSVG / SetSVG (not in the recognized verb set) must not register
        -- only the specific Add/Insert/Load/Read/Import/Open/Parse/Save/
        Write/Export/Serialize verbs are treated as I/O signals."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = _write(tmp, "getset.go", """\
package asposepdf

func (p *Page) GetSVG() *SVG {
\treturn p.svg
}

func (p *Page) SetSVG(svg *SVG) {
\tp.svg = svg
}
""")
            entries = _scan_pascal_verb_format_methods([src], tmp, None)
            self.assertEqual(entries, [])

    def test_lowercase_private_function_not_matched(self):
        """Unexported/private helper functions like renderSVG (lowercase
        first letter) must not match the PascalCase verb regex."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = _write(tmp, "render.go", """\
package asposepdf

func renderSVG(p *Page, svg *SVG, rect Rectangle) error {
\treturn nil
}

func addSvgInternal(p *Page) error {
\treturn nil
}
""")
            entries = _scan_pascal_verb_format_methods([src], tmp, None)
            self.assertEqual(entries, [])

    def test_empty_files_list_no_crash(self):
        """Empty input -> empty output, no crash."""
        with tempfile.TemporaryDirectory() as tmp:
            entries = _scan_pascal_verb_format_methods([], Path(tmp), None)
            self.assertEqual(entries, [])

    def test_full_detect_formats_no_regression_on_bidirectional_java_case(self):
        """Existing bidirectional-format detection (LoadOptions/SaveOptions
        pattern, Pass 1b) on a Java-style fixture must be unaffected by the
        new Pass 1e -- html stays both import and export, and no unrelated
        Pass-1e entries appear for a language/fixture with no PascalCase
        verb+known-format-token methods at all."""
        parser = get_parser("java")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write(tmp, "HtmlLoadOptions.java", """\
public class HtmlLoadOptions extends LoadOptions {
    public HtmlLoadOptions() {}
}
""")
            _write(tmp, "HtmlSaveOptions.java", """\
public class HtmlSaveOptions extends SaveOptions {
    public HtmlSaveOptions() {}
}
""")
            formats, _ = detect_formats(parser, "java", tmp, tmp, "pdf")
            html_entries = [f for f in formats if f["format"].lower() == "html"]
            directions = {e["direction"] for e in html_entries}
            self.assertEqual(
                directions, {"import", "export"},
                f"expected both import and export Html entries, got: {formats}",
            )

    def test_allowlist_contains_svg_and_common_document_formats(self):
        """Sanity: the allowlist actually includes the formats this pass
        exists to detect (svg, plus the broader document-format vocabulary
        used across Aspose families, not just pdf/go)."""
        for token in ("svg", "pdf", "html", "json", "xlsx", "docx", "pptx"):
            self.assertIn(token, _KNOWN_FORMAT_TOKENS)


if __name__ == "__main__":
    unittest.main()

"""HARDEN-cpp-namespace-collision (MT012): api_completeness must resolve
namespace-disambiguated reference pages against the RIGHT api_surface entry.

Found live while launching pdf/cpp: two unrelated C++ classes both named
`Rectangle` exist in different namespaces (`Aspose::Pdf::Rectangle` and
`Aspose::Pdf::Drawing::Rectangle`). batch_reference.py disambiguates the
filename as `Rectangle-Aspose_Pdf.md` / `Rectangle-Aspose_Pdf_Drawing.md`, but
the evaluator matched candidates by bare class name only (`next(c for c in
api_surface if c["name"] == class_name)`), always picking whichever entry
happened to be first in api_surface.json -- so `Rectangle-Aspose_Pdf.md` was
checked against `Aspose::Pdf::Drawing::Rectangle`'s member list and flagged as
missing methods (`Bottom`, `Left`, `CheckBounds`, `RoundedCornerRadius`) that
the page never claimed to document at all.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from content_eval.evaluators.api_completeness import ApiCompletenessEvaluator
from content_eval.models import Page


def _make_ref_page(tmp_path: Path, body: str, filename_stem: str, link_title: str) -> Page:
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "cpp"
    ref_dir.mkdir(parents=True, exist_ok=True)
    md_file = ref_dir / f"{filename_stem}.md"
    frontmatter = f"---\ntitle: {link_title}\nlinkTitle: {link_title}\n---\n\n"
    md_file.write_text(frontmatter + body, encoding="utf-8")
    return Page.load(md_file)


_TWO_RECTANGLES = [
    {
        "name": "Rectangle",
        "canonical_namespace": "Aspose::Pdf::Drawing",
        "methods": [{"name": m} for m in ("Bottom", "Left", "CheckBounds", "RoundedCornerRadius")],
        "properties": [],
    },
    {
        "name": "Rectangle",
        "canonical_namespace": "Aspose::Pdf",
        "methods": [{"name": m} for m in ("Equals", "Width", "Height")],
        "properties": [],
    },
]


class TestNamespaceDisambiguation:
    def test_page_checked_against_correct_namespace_entry(self, tmp_path):
        """Rectangle-Aspose_Pdf.md documents Equals/Width/Height (the
        Aspose::Pdf entry) -- must NOT be flagged for the unrelated
        Aspose::Pdf::Drawing entry's Bottom/Left/CheckBounds/RoundedCornerRadius."""
        body = (
            "## Methods\n\n"
            "| Signature | Description |\n"
            "|-----------|-------------|\n"
            "| `Equals(other)` | Compares. |\n"
            "| `Width()` | Returns width. |\n"
            "| `Height()` | Returns height. |\n"
        )
        page = _make_ref_page(tmp_path, body, "Rectangle-Aspose_Pdf", "Rectangle")

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_TWO_RECTANGLES):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            f"Page fully documents the Aspose::Pdf Rectangle entry, must not be "
            f"cross-checked against the unrelated Drawing::Rectangle entry, got: {findings}"
        )

    def test_other_namespace_page_checked_against_its_own_entry(self, tmp_path):
        body = (
            "## Methods\n\n"
            "| Signature | Description |\n"
            "|-----------|-------------|\n"
            "| `Bottom()` | Returns bottom. |\n"
            "| `Left()` | Returns left. |\n"
            "| `CheckBounds()` | Checks bounds. |\n"
            "| `RoundedCornerRadius()` | Returns radius. |\n"
        )
        page = _make_ref_page(tmp_path, body, "Rectangle-Aspose_Pdf_Drawing", "Rectangle")

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_TWO_RECTANGLES):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == []

    def test_genuinely_incomplete_disambiguated_page_still_fails(self, tmp_path):
        """Regression guard: disambiguation resolves the RIGHT entry, but a
        genuinely incomplete page must still fail against it."""
        body = "This page barely documents anything.\n"
        page = _make_ref_page(tmp_path, body, "Rectangle-Aspose_Pdf", "Rectangle")

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_TWO_RECTANGLES):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1
        assert findings[0].level == "FAIL"
        assert "Bottom" not in findings[0].message  # must not leak the OTHER class's members


# ---------------------------------------------------------------------------
# ST-121: file-stem-based collision suffix (flat TypeScript packages)
#
# The namespace-collision fix above only matches an EXACT normalized
# canonical_namespace against the filename suffix -- correct for C++'s
# multi-segment namespaces, but batch_reference.py's OTHER disambiguation
# convention for flat TS packages (no directory nesting) suffixes by the
# SOURCE FILE STEM instead, e.g. cells/typescript's "Style" interface (in
# types.ts) vs "Style" class (in style.ts) -> Style-types.md / Style-style.md.
# canonical_namespace for these is "aspose_cells.types" / "aspose_cells.style"
# -- normalizing the WHOLE string never equals the bare suffix "types", so
# disambiguation silently fell through to candidates[0], reporting one
# entity's members as missing from the other's page. Confirmed live
# 2026-08-30 (MT040 Phase I, cells/typescript refresh_run): Style-types.md's
# real 6-property interface was checked against the 36-method class, reporting
# 36 "missing" members it never claimed to document.
# ---------------------------------------------------------------------------

_STYLE_INTERFACE_AND_CLASS = [
    {
        "name": "Style",
        "kind": "class_declaration",
        "canonical_namespace": "aspose_cells.style",
        "file": "aspose_cells/style.ts",
        "methods": [{"name": m} for m in ("getFont", "getFill", "getBorder", "setFont")],
        "properties": [],
    },
    {
        "name": "Style",
        "kind": "interface_declaration",
        "canonical_namespace": "aspose_cells.types",
        "file": "aspose_cells/types.ts",
        "methods": [],
        "properties": [{"name": n} for n in ("font", "fill", "border", "alignment", "numberFormat", "protection")],
    },
]


class TestFileStemSuffixDisambiguation:
    def test_interface_page_checked_against_interface_entry_not_class(self, tmp_path):
        """Style-types.md (the interface, 6 properties) must not be checked
        against the unrelated 4-method class entry."""
        body = (
            "## Properties\n\n"
            "| Name | Type | Access | Description |\n"
            "|------|------|--------|-------------|\n"
            "| `font` | `: Font` | Read | Gets the font. |\n"
            "| `fill` | `: Fill` | Read | Gets the fill. |\n"
            "| `border` | `: Border` | Read | Gets the border. |\n"
            "| `alignment` | `: Alignment` | Read | Gets the alignment. |\n"
            "| `numberFormat` | `: string` | Read | Gets the number format. |\n"
            "| `protection` | `: Protection` | Read | Gets the protection. |\n"
        )
        page = _make_ref_page(tmp_path, body, "Style-types", "Style")

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_STYLE_INTERFACE_AND_CLASS):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == [], (
            f"interface page fully documents its own 6 properties, must not be "
            f"cross-checked against the unrelated class's methods, got: {findings}"
        )

    def test_class_page_checked_against_class_entry_not_interface(self, tmp_path):
        """Style-style.md (the class, 4 methods) must not be checked against
        the unrelated 6-property interface entry."""
        body = (
            "## Methods\n\n"
            "| Signature | Description |\n"
            "|-----------|-------------|\n"
            "| `getFont()` | Gets the font. |\n"
            "| `getFill()` | Gets the fill. |\n"
            "| `getBorder()` | Gets the border. |\n"
            "| `setFont(f)` | Sets the font. |\n"
        )
        page = _make_ref_page(tmp_path, body, "Style-style", "Style")

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_STYLE_INTERFACE_AND_CLASS):
            findings = ev.evaluate(page, knowledge=None)

        assert findings == []

    def test_genuinely_incomplete_stem_disambiguated_page_still_fails(self, tmp_path):
        """Regression guard: stem-based disambiguation resolves the RIGHT
        entry, but a genuinely incomplete page must still fail against it."""
        body = "This page barely documents anything.\n"
        page = _make_ref_page(tmp_path, body, "Style-types", "Style")

        ev = ApiCompletenessEvaluator()
        with patch.object(ev, "_load_api_surface", return_value=_STYLE_INTERFACE_AND_CLASS):
            findings = ev.evaluate(page, knowledge=None)

        assert len(findings) == 1
        assert findings[0].level == "FAIL"
        assert "getFont" not in findings[0].message  # must not leak the class's members

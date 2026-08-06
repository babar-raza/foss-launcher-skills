"""Ground-truth pytest suite for scripts/pipeline/commands/foss/readme_refresh_checks.py.

Closes the "not yet written, ad hoc corpus validation only" gap check_diagram_connectivity's
own module docstring named -- fixtures below are real "## At a glance" Mermaid blocks captured
verbatim from reports/repo-presenter/{family}/{platform}/readme.md during the MT021 readiness
audit (2026-08-06), before any capability-dependency fix was applied to them. 3 confirmed-defective
products (barcode/python, tex/python, email/python) plus 3 confirmed-clean comparators (cells/cpp,
pdf/cpp, slides/python) -- see plan section "Capability-dependency edges" /
C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md for the
source evidence behind each defect.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "foss"))

import readme_refresh_checks as checks  # noqa: E402


def _wrap(mermaid_body: str, extra_section: str = "") -> str:
    return (
        "# Some Product\n\n"
        "## At a glance\n\n"
        f"```mermaid\n{mermaid_body}\n```\n\n"
        "## Key capabilities\n\n"
        f"{extra_section or '- Does a thing.'}\n"
    )


# --- Confirmed-defective fixtures (pre-fix, captured 2026-08-06) -----------------------------

DEFECTIVE_BARCODE_PYTHON = _wrap(
    """flowchart LR
  subgraph Inputs["Input data and options"]
    I1["Text and binary payload data"]
    I2["Per-symbology encode options"]
  end

  PRODUCT["Aspose.BarCode FOSS for Python"]

  subgraph Capabilities["Core capabilities"]
    C1["Code 128 encoding with Set A/B/C selection"]
    C2["Code 39 and Code 39 Extended encoding"]
    C3["EAN-13, EAN-8, UPC-A, and UPC-E encoding"]
    C4["QR Code Model 2 encoding"]
    C5["SVG and PNG rendering"]
    C6["RenderOptions styling and layout"]
  end

  subgraph Outputs["Outputs"]
    O1["SVG strings"]
    O2["PNG bytes"]
  end

  I1 --- PRODUCT
  I2 --- PRODUCT
  PRODUCT --- C1
  PRODUCT --- C2
  PRODUCT --- C3
  PRODUCT --- C4
  PRODUCT --- C5
  PRODUCT --- C6
  C1 --- C5
  C2 --- C5
  C3 --- C5
  C4 --- C5
  C5 --- O1
  C5 --- O2
  C6 --- O1
  C6 --- O2"""
)

# Corrected redraw from the plan's "barcode/python, fully redrawn" block -- used to prove the
# blocking check also PASSES clean input, not just always fails.
CORRECTED_BARCODE_PYTHON = _wrap(
    """flowchart LR
  subgraph Inputs["Input data and options"]
    I1["Text and binary payload data"]
    I2a["Code128Options: mode selection and GS1"]
    I2b["Code39Options: full ASCII and check digit"]
    I2c["EAN/UPC check-digit and number-system options"]
    I2d["QrOptions: version, mask, ECC level, and encoding mode"]
    I3["RenderOptions: scale, colors, quiet zone, and text styling"]
  end

  PRODUCT["Aspose.BarCode FOSS for Python"]

  subgraph Capabilities["Core capabilities"]
    C1["Code 128 encoding with Set A/B/C selection"]
    C2["Code 39 and Code 39 Extended encoding"]
    C3["EAN-13, EAN-8, UPC-A, and UPC-E encoding"]
    C4["QR Code Model 2 encoding"]
    C5["SVG and PNG rendering, styled by RenderOptions"]
  end

  subgraph Outputs["Outputs"]
    O1["SVG strings"]
    O2["PNG bytes"]
  end

  I1 --- PRODUCT
  I2a --- PRODUCT
  I2b --- PRODUCT
  I2c --- PRODUCT
  I2d --- PRODUCT
  I3 --- PRODUCT
  PRODUCT --- C1
  PRODUCT --- C2
  PRODUCT --- C3
  PRODUCT --- C4
  C1 --- C5
  C2 --- C5
  C3 --- C5
  C4 --- C5
  C5 --- O1
  C5 --- O2"""
)

BARCODE_PIPELINE_EDGES = [["C1", "C5"], ["C2", "C5"], ["C3", "C5"], ["C4", "C5"]]

DEFECTIVE_TEX_PYTHON = _wrap(
    """flowchart LR
  subgraph Inputs["Inputs and formats"]
    I1["TeX/LaTeX markup (string)"]
    I2["TeX source files"]
  end

  PRODUCT["Aspose.TeX FOSS for Python"]

  subgraph Capabilities["Core capabilities"]
    C1["TeX interpretation and typesetting"]
    C2["Font and glyph metric resolution"]
    C3["Page building and box layout"]
    C4["PDF / DVI / SVG output devices"]
  end

  subgraph Outputs["Outputs"]
    O1["PDF documents"]
    O2["DVI files"]
    O3["SVG 1.1 documents (single- or multi-page)"]
  end

  I1 --- PRODUCT
  I2 --- PRODUCT
  PRODUCT --- C1
  PRODUCT --- C2
  PRODUCT --- C3
  PRODUCT --- C4
  C1 --- O1
  C1 --- O2
  C1 --- O3
  C2 --- O1
  C2 --- O2
  C2 --- O3
  C3 --- O1
  C3 --- O2
  C3 --- O3
  C4 --- O1
  C4 --- O2
  C4 --- O3"""
)

DEFECTIVE_EMAIL_PYTHON = _wrap(
    """flowchart LR
  subgraph Inputs["Inputs and formats"]
    I1["Outlook .msg files"]
    I2["Compound File Binary (CFB) containers"]
    I3["Python email.message.EmailMessage objects"]
  end

  PRODUCT["Aspose.Email FOSS for Python"]

  subgraph Capabilities["Core capabilities"]
    C1["CFB container parsing and writing"]
    C2["Low-level MSG reading and writing"]
    C3["High-level mutable message model (MapiMessage)"]
    C4["MAPI property read/write by ID or name"]
    C5["Recipients, attachments, and embedded messages"]
    C6["MSG and EmailMessage conversion"]
  end

  subgraph Outputs["Outputs"]
    O1["CFB storages and streams"]
    O2["New or edited .msg files"]
    O3["MAPI properties, recipients, and attachments"]
    O4["Embedded message attachments"]
    O5["email.message.EmailMessage objects"]
  end

  I1 --- PRODUCT
  I2 --- PRODUCT
  I3 --- PRODUCT
  PRODUCT --- C1
  PRODUCT --- C2
  PRODUCT --- C3
  PRODUCT --- C4
  PRODUCT --- C5
  PRODUCT --- C6
  C1 --- O1
  C2 --- O2
  C3 --- O3
  C4 --- O3
  C5 --- O4
  C6 --- O5
  C6 --- O2"""
)

# --- Confirmed-clean comparator fixtures (captured 2026-08-06) -------------------------------

CLEAN_CELLS_CPP = _wrap(
    """flowchart LR
  subgraph Inputs["Inputs and formats"]
    I1["Existing .xlsx files (path)"]
    I2["Existing .xlsx files (binary stream)"]
  end

  PRODUCT["Aspose.Cells FOSS for C++"]

  subgraph Capabilities["Core capabilities"]
    C1["Workbook and worksheet management"]
    C2["Cell values and formulas"]
    C3["Style, font, fill, and alignment"]
    C4["Page setup and print settings"]
    C5["Named range management (DefinedNameCollection)"]
  end

  subgraph Outputs["Outputs"]
    O1[".xlsx workbook (file path or binary stream)"]
  end

  I1 --- PRODUCT
  I2 --- PRODUCT
  PRODUCT --- C1
  PRODUCT --- C2
  PRODUCT --- C3
  PRODUCT --- C4
  PRODUCT --- C5
  C1 --- O1
  C2 --- O1
  C3 --- O1
  C4 --- O1
  C5 --- O1"""
)

CLEAN_PDF_CPP = _wrap(
    """flowchart LR
  subgraph Inputs["Inputs and formats"]
    I1["Existing PDF documents (incl. encrypted)"]
    I2["SVG content (import)"]
    I3["PNG / JPEG image bytes (for AddImage)"]
  end

  subgraph FromScratch["New content authored from scratch"]
    S1["Positioned, word-wrapped text"]
    S2["Tables, vector graphics, and watermarks"]
    S3["Annotations, AcroForm fields, and outline (bookmark) trees"]
  end

  PRODUCT["Aspose.PDF FOSS for C++"]

  subgraph Capabilities["Core capabilities"]
    C1["Text extraction"]
    C2["Page rendering (raster devices)"]
    C3["Document creation from scratch"]
    C4["Encryption and digital signing"]
    C5["Facades (converter/extractor/security/signature/bookmarks)"]
  end

  subgraph Outputs["Outputs"]
    O1["PDF documents (save / incremental update)"]
    O2["PNG / JPEG / BMP / TIFF raster images"]
    O3["Plain text"]
  end

  I1 --- PRODUCT
  I2 --- PRODUCT
  I3 --- PRODUCT
  S1 --- PRODUCT
  S2 --- PRODUCT
  S3 --- PRODUCT
  PRODUCT --- C1
  PRODUCT --- C2
  PRODUCT --- C3
  PRODUCT --- C4
  PRODUCT --- C5
  C1 --- O3
  C2 --- O2
  C3 --- O1
  C4 --- O1
  C5 --- O1"""
)

CLEAN_SLIDES_PYTHON = _wrap(
    """flowchart LR
  subgraph Inputs["Inputs and formats"]
    I1["PPTX + OOXML variants (PPTM/PPSX/PPSM/POTX/POTM)"]
  end

  PRODUCT["Aspose.Slides FOSS for Python"]

  subgraph Capabilities["Core capabilities"]
    C1["Slide and shape creation and management"]
    C2["Text formatting"]
    C3["Charts (70+ types)"]
    C4["Animations and transitions"]
    C5["Themes, fills, and effects"]
    C6["Tables, notes, and comments"]
  end

  subgraph Outputs["Outputs"]
    O1["PPTX + OOXML variants (PPTM/PPSX/PPSM/POTX/POTM)"]
    O2["Markdown (.md, write-only)"]
  end

  I1 --- PRODUCT
  PRODUCT --- C1
  PRODUCT --- C2
  PRODUCT --- C3
  PRODUCT --- C4
  PRODUCT --- C5
  PRODUCT --- C6
  C1 --- O1
  C2 --- O1
  C3 --- O1
  C4 --- O1
  C5 --- O1
  C6 --- O1
  C1 --- O2"""
)

CLEAN_FIXTURES = {
    "cells/cpp": CLEAN_CELLS_CPP,
    "pdf/cpp": CLEAN_PDF_CPP,
    "slides/python": CLEAN_SLIDES_PYTHON,
}

DEFECTIVE_FIXTURES = {
    "barcode/python": DEFECTIVE_BARCODE_PYTHON,
    "tex/python": DEFECTIVE_TEX_PYTHON,
    "email/python": DEFECTIVE_EMAIL_PYTHON,
}


# --- check_diagram_connectivity ---------------------------------------------------------------


def test_connectivity_clean_products_have_no_orphans():
    for name, text in CLEAN_FIXTURES.items():
        assert checks.check_diagram_connectivity(text) == [], name


def test_connectivity_defective_products_also_have_no_orphans():
    # Documents a real, load-bearing fact: the capability-dependency defect class (contradictory
    # dual-path edges) is invisible to check_diagram_connectivity -- every node still reaches an
    # Output, so orphan-checking alone does not catch this defect class. This is exactly why
    # check_diagram_matches_capability_dependencies exists as a separate check.
    for name, text in DEFECTIVE_FIXTURES.items():
        assert checks.check_diagram_connectivity(text) == [], name


# --- check_diagram_known_subgraph_ids -----------------------------------------------------------


def test_known_subgraph_ids_all_fixtures_clean():
    for name, text in {**CLEAN_FIXTURES, **DEFECTIVE_FIXTURES}.items():
        assert checks.check_diagram_known_subgraph_ids(text) == [], name


def test_known_subgraph_ids_flags_unrecognized_id():
    text = _wrap(
        """flowchart LR
  subgraph Weird["Something new"]
    X1["A node"]
  end
  PRODUCT["P"]
  subgraph Capabilities["Core"]
    C1["Cap"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  X1 --- PRODUCT
  PRODUCT --- C1
  C1 --- O1"""
    )
    assert checks.check_diagram_known_subgraph_ids(text) == ["Weird"]


# --- check_diagram_suspicious_direct_product_edge -----------------------------------------------


def test_suspicious_direct_product_edge_catches_barcode_c5_only():
    # Honest recall, per spec: catches exactly the 1-of-5 known real defects that has *some*
    # existing Capability-to-Capability edge to contradict (barcode's C5). Misses C6 (no sibling
    # edge exists to contradict it) and both tex/email cases (same "edge never drawn" shape).
    findings = checks.check_diagram_suspicious_direct_product_edge(DEFECTIVE_BARCODE_PYTHON)
    assert [f["node_id"] for f in findings] == ["C5"]


def test_suspicious_direct_product_edge_misses_tex_and_email():
    assert checks.check_diagram_suspicious_direct_product_edge(DEFECTIVE_TEX_PYTHON) == []
    assert checks.check_diagram_suspicious_direct_product_edge(DEFECTIVE_EMAIL_PYTHON) == []


def test_suspicious_direct_product_edge_clean_on_comparators():
    for name, text in CLEAN_FIXTURES.items():
        assert checks.check_diagram_suspicious_direct_product_edge(text) == [], name


def test_suspicious_direct_product_edge_clean_on_corrected_barcode():
    assert checks.check_diagram_suspicious_direct_product_edge(CORRECTED_BARCODE_PYTHON) == []


# --- check_diagram_capability_unreachable_from_product ------------------------------------------


def test_unreachable_from_product_harmless_noop_pre_fix():
    for name, text in {**CLEAN_FIXTURES, **DEFECTIVE_FIXTURES}.items():
        assert checks.check_diagram_capability_unreachable_from_product(text) == [], name


def test_unreachable_from_product_catches_dropped_edge_regression():
    # The specific slip Rule 1b warns about: deleting a PRODUCT edge per the Direct-edge-test
    # without wiring the real upstream Capability in its place.
    text = _wrap(
        """flowchart LR
  PRODUCT["P"]
  subgraph Capabilities["Core"]
    C1["Cap one"]
    C2["Cap two, should be fed by C1 but isn't"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  PRODUCT --- C1
  C1 --- O1
  C2 --- O1"""
    )
    findings = checks.check_diagram_capability_unreachable_from_product(text)
    assert [f["node_id"] for f in findings] == ["C2"]


# --- check_diagram_matches_capability_dependencies -----------------------------------------------


def test_matches_capability_dependencies_none_is_noop():
    for name, text in {**CLEAN_FIXTURES, **DEFECTIVE_FIXTURES}.items():
        assert checks.check_diagram_matches_capability_dependencies(text, None) == [], name


def test_matches_capability_dependencies_fails_closed_on_defective_barcode():
    # The real "prove the gate actually fires" test -- same discipline already required for
    # check_no_undisclosed_blocking_commands. Must FAIL (non-empty) on the known-defective diagram.
    findings = checks.check_diagram_matches_capability_dependencies(
        DEFECTIVE_BARCODE_PYTHON, BARCODE_PIPELINE_EDGES
    )
    assert findings, "blocking check must fail closed on the known-defective diagram"
    assert {"type": "contradictory_direct_edge", "from": "PRODUCT", "to": "C5"} in findings


def test_matches_capability_dependencies_passes_on_corrected_barcode():
    # Same recorded pipeline_edges, corrected diagram -- must PASS (empty), proving this isn't
    # an always-fail check.
    findings = checks.check_diagram_matches_capability_dependencies(
        CORRECTED_BARCODE_PYTHON, BARCODE_PIPELINE_EDGES
    )
    assert findings == []


def test_matches_capability_dependencies_missing_edge():
    text = _wrap(
        """flowchart LR
  PRODUCT["P"]
  subgraph Capabilities["Core"]
    C1["Cap one"]
    C2["Cap two"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  PRODUCT --- C1
  C1 --- O1
  C2 --- O1"""
    )
    # Recorded: C1 -> C2 should exist but doesn't (no C1---C2 edge drawn).
    findings = checks.check_diagram_matches_capability_dependencies(text, [["C1", "C2"]])
    assert {"type": "missing_edge", "from": "C1", "to": "C2"} in findings


def test_matches_capability_dependencies_undeclared_edge():
    text = _wrap(
        """flowchart LR
  PRODUCT["P"]
  subgraph Capabilities["Core"]
    C1["Cap one"]
    C2["Cap two"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  PRODUCT --- C1
  C1 --- C2
  C2 --- O1"""
    )
    # An empty recorded list means "traced, confirmed no dependencies" -- a real drawn C1---C2
    # edge with nothing recorded is undeclared drift, and must be flagged even though [] is not
    # None (this is the None-vs-[] asymmetric-absence distinction the store design depends on).
    findings = checks.check_diagram_matches_capability_dependencies(text, [])
    assert {"type": "undeclared_edge", "from": "C1", "to": "C2"} in findings


# --- check_only_mermaid_block_changed -----------------------------------------------------------


def test_only_mermaid_block_changed_true_for_identical_text():
    assert checks.check_only_mermaid_block_changed(DEFECTIVE_BARCODE_PYTHON, DEFECTIVE_BARCODE_PYTHON)


def test_only_mermaid_block_changed_true_when_only_diagram_edited():
    new_text = DEFECTIVE_BARCODE_PYTHON.replace("C5 --- O1", "C5 --- O1\n  %% a comment")
    assert new_text != DEFECTIVE_BARCODE_PYTHON
    assert checks.check_only_mermaid_block_changed(DEFECTIVE_BARCODE_PYTHON, new_text)


def test_only_mermaid_block_changed_false_when_prose_also_edited():
    new_text = DEFECTIVE_BARCODE_PYTHON.replace(
        "C5 --- O1", "C5 --- O1\n  %% a comment"
    ).replace("- Does a thing.", "- Does a different thing.")
    assert checks.check_only_mermaid_block_changed(DEFECTIVE_BARCODE_PYTHON, new_text) is False


def test_only_mermaid_block_changed_false_when_only_prose_edited():
    new_text = DEFECTIVE_BARCODE_PYTHON.replace("- Does a thing.", "- Does a different thing.")
    assert checks.check_only_mermaid_block_changed(DEFECTIVE_BARCODE_PYTHON, new_text) is False


def test_only_mermaid_block_changed_false_when_block_disappears():
    new_text = DEFECTIVE_BARCODE_PYTHON.split("## At a glance")[0] + "## Key capabilities\n\n- Does a thing.\n"
    assert checks.check_only_mermaid_block_changed(DEFECTIVE_BARCODE_PYTHON, new_text) is False

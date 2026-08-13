"""Ground-truth pytest suite for scripts/pipeline/commands/foss/readme_refresh_checks.py.

Rewritten 2026-08-08 (Tenth incident, MT024) for the simplified diagram model: every
`## At a glance` diagram is now exactly `Product -> Core Capabilities -> Outputs`, with an
optional 2-line `Starting Points -> Product` prefix for hybrid-archetype products only.
The pre-2026-08-08 per-node-edge model (`Inputs`/`FromScratch` subgraphs, individual
`Cx --- Oy` edges, `check_diagram_suspicious_direct_product_edge`/`check_diagram_
capability_unreachable_from_product`) is retired along with its fixtures -- those two
heuristics no longer apply once there are no per-node edges to be suspicious/unreachable
through. `check_diagram_connectivity` (orphan-reachability) is replaced by
`check_diagram_shape` (fixed-container-chain structure) and `check_diagram_column_balance`
(<=5 capabilities = 1 column, >=6 = 2 balanced columns).
"""

import json
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


# --- 2026-08-08 simplified-model fixtures -------------------------------------------------

# Hybrid archetype: a Starting Points container, 4 capabilities (1 column).
HYBRID_PDF_CPP = _wrap(
    """flowchart TD
  subgraph StartingPoints["Starting Points"]
    I1["An existing PDF document"]
    I2["Nothing -- authored from scratch"]
  end

  PRODUCT["Aspose.PDF FOSS for C++"]

  subgraph Capabilities["Core Capabilities"]
    C1["Text extraction and page rendering"]
    C2["Document creation and editing"]
    C3["Encryption and digital signing"]
    C4["Facades: convert, extract, secure, sign, bookmark"]
  end

  subgraph Outputs["Outputs"]
    O1["PDF documents"]
    O2["PNG, JPEG, BMP, and TIFF images"]
    O3["Plain text"]
  end

  StartingPoints --> PRODUCT --> Capabilities --> Outputs"""
)

# Transform archetype: no Starting Points, 5 capabilities (1 column, the ceiling).
TRANSFORM_CELLS_CPP = _wrap(
    """flowchart TD
  PRODUCT["Aspose.Cells FOSS for C++"]

  subgraph Capabilities["Core Capabilities"]
    C1["Workbook and worksheet management"]
    C2["Cell values and formulas"]
    C3["Style, font, fill, and alignment"]
    C4["Page setup and print settings"]
    C5["Named range management"]
  end

  subgraph Outputs["Outputs"]
    O1[".xlsx workbook (file path or binary stream)"]
  end

  PRODUCT --> Capabilities --> Outputs"""
)

# Transform archetype, 6 capabilities: must split into 2 balanced columns.
TRANSFORM_WORDS_NET = _wrap(
    """flowchart TD
  PRODUCT["Aspose.Words FOSS for .NET"]

  subgraph Capabilities["Core Capabilities"]
    direction LR
    subgraph capl[" "]
      direction TB
      c1["Document creation and editing"]
      c2["Text, styles, tables, and lists"]
      c3["Tracked-changes engine"]
    end
    subgraph capr[" "]
      direction TB
      c4["Field evaluation"]
      c5["Protection and signatures"]
      c6["DOCX, Markdown, and text conversion"]
    end
  end

  subgraph Outputs["Outputs"]
    direction TB
    o1["DOCX / DOCM / DOTX / DOTM"]
    o2["Flat OPC, Markdown, and plain text"]
  end

  PRODUCT --> Capabilities --> Outputs"""
)

WORDS_NET_PIPELINE_EDGES = [["c1", "c3"]]

CLEAN_FIXTURES = {
    "pdf/cpp": HYBRID_PDF_CPP,
    "cells/cpp": TRANSFORM_CELLS_CPP,
    "words/net": TRANSFORM_WORDS_NET,
}


# --- check_diagram_shape --------------------------------------------------------------------


def test_shape_clean_fixtures_all_pass():
    for name, text in CLEAN_FIXTURES.items():
        assert checks.check_diagram_shape(text) == [], name


def test_shape_flags_missing_outputs_container():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    C1["Cap"]
  end
  PRODUCT --> Capabilities"""
    )
    findings = checks.check_diagram_shape(text)
    assert any("Outputs container" in f["reason"] for f in findings)


def test_shape_flags_duplicate_capabilities_container():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    C1["Cap A"]
  end
  subgraph Capabilities["Core Capabilities"]
    C2["Cap B"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_shape(text)
    assert any("exactly 1 Capabilities container" in f["reason"] for f in findings)


def test_shape_flags_individual_node_edge_outside_the_chain():
    # The whole point of the 2026-08-08 simplification: no individual capability-to-output
    # wiring is allowed anymore, even if it's factually harmless.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    C1["Cap"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  PRODUCT --> Capabilities --> Outputs
  C1 --- O1"""
    )
    findings = checks.check_diagram_shape(text)
    assert any("outside the fixed container chain" in f["reason"] for f in findings)


def test_shape_flags_missing_product_node():
    text = _wrap(
        """flowchart TD
  subgraph Capabilities["Core Capabilities"]
    C1["Cap"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_shape(text)
    assert any("no PRODUCT node" in f["reason"] for f in findings)


def test_shape_no_mermaid_block_is_a_finding_not_a_silent_pass():
    assert checks.check_diagram_shape("# No diagram here\n") == [
        {"reason": "no mermaid block found"}
    ]


# --- check_diagram_column_balance -----------------------------------------------------------


def test_column_balance_clean_fixtures_all_pass():
    for name, text in CLEAN_FIXTURES.items():
        assert checks.check_diagram_column_balance(text) == [], name


def test_column_balance_flags_six_capabilities_in_one_column():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["A"]
    c2["B"]
    c3["C"]
    c4["D"]
    c5["E"]
    c6["F"]
  end
  subgraph Outputs["Outputs"]
    o1["Out"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_column_balance(text)
    assert findings and "should split into exactly 2 balanced columns" in findings[0]["reason"]


def test_column_balance_flags_unbalanced_split():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    subgraph capl[" "]
      c1["A"]
      c2["B"]
      c3["C"]
      c4["D"]
      c5["E"]
    end
    subgraph capr[" "]
      c6["F"]
    end
  end
  subgraph Outputs["Outputs"]
    o1["Out"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_column_balance(text)
    assert findings and "not balanced" in findings[0]["reason"]


# --- check_diagram_known_subgraph_ids ---------------------------------------------------------


def test_known_subgraph_ids_clean_fixtures_all_pass():
    for name, text in CLEAN_FIXTURES.items():
        assert checks.check_diagram_known_subgraph_ids(text) == [], name


def test_known_subgraph_ids_ignores_nested_column_ids():
    # capl/capr are expected, valid nested column markers -- must never be flagged.
    assert checks.check_diagram_known_subgraph_ids(TRANSFORM_WORDS_NET) == []


def test_known_subgraph_ids_flags_unrecognized_top_level_id():
    text = _wrap(
        """flowchart TD
  subgraph Weird["Something new"]
    X1["A node"]
  end
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    C1["Cap"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  Weird --> PRODUCT --> Capabilities --> Outputs"""
    )
    assert checks.check_diagram_known_subgraph_ids(text) == ["Weird"]


def test_known_subgraph_ids_flags_retired_inputs_id():
    # Inputs/FromScratch are retired 2026-08-08 -- a diagram still using them must be
    # flagged for re-rendering, not silently accepted as before.
    text = _wrap(
        """flowchart LR
  subgraph Inputs["Inputs and formats"]
    I1["Old-style input"]
  end
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    C1["Cap"]
  end
  subgraph Outputs["Outputs"]
    O1["Out"]
  end
  I1 --- PRODUCT
  PRODUCT --- C1
  C1 --- O1"""
    )
    assert checks.check_diagram_known_subgraph_ids(text) == ["Inputs"]


# --- check_diagram_matches_capability_dependencies (rewritten: column order, not edges) -------


def test_matches_capability_dependencies_none_or_empty_is_noop():
    for name, text in CLEAN_FIXTURES.items():
        assert checks.check_diagram_matches_capability_dependencies(text, None) == [], name
        assert checks.check_diagram_matches_capability_dependencies(text, []) == [], name


def test_matches_capability_dependencies_passes_correct_order():
    # c1 genuinely appears before c3 within the left column of TRANSFORM_WORDS_NET.
    findings = checks.check_diagram_matches_capability_dependencies(
        TRANSFORM_WORDS_NET, WORDS_NET_PIPELINE_EDGES
    )
    assert findings == []


def test_matches_capability_dependencies_fails_closed_on_wrong_order():
    # Deliberately-wrong fixture: c3 recorded as upstream of c1, but c1 is listed first.
    findings = checks.check_diagram_matches_capability_dependencies(
        TRANSFORM_WORDS_NET, [["c3", "c1"]]
    )
    assert findings, "must fail closed on a genuinely wrong-order fixture"
    assert findings[0]["type"] == "wrong_order"


def test_matches_capability_dependencies_flags_unknown_capability_id():
    findings = checks.check_diagram_matches_capability_dependencies(
        TRANSFORM_WORDS_NET, [["c1", "does_not_exist"]]
    )
    assert findings[0]["type"] == "capability_not_found"


def test_matches_capability_dependencies_cross_column_is_unconstrained():
    # c1 (left column) and c4 (right column) -- cross-column order is never checked.
    findings = checks.check_diagram_matches_capability_dependencies(
        TRANSFORM_WORDS_NET, [["c4", "c1"]]
    )
    assert findings == []


# --- check_diagram_hybrid_reverification -------------------------------------------------------


def test_hybrid_reverification_noop_when_no_starting_points():
    assert checks.check_diagram_hybrid_reverification(
        TRANSFORM_CELLS_CPP, None, "2026-08-08"
    ) == []


def test_hybrid_reverification_no_longer_flags_missing_archetype_entry():
    # Eleventh incident / MT025: this function used to hard-reject a Starting Points
    # container whenever archetype_entry was None (the default/transform case) -- the exact
    # coded mechanism that blocked transform-archetype products from ever having one. That
    # presence/absence judgment moved entirely to check_diagram_starting_points_presence;
    # this function is now a no-op for a missing archetype entry, regardless of the diagram.
    assert checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, None, "2026-08-08") == []


def test_hybrid_reverification_no_longer_flags_non_hybrid_archetype():
    # Same narrowing: a non-hybrid archetype with a Starting Points container is no longer
    # this function's concern (check_diagram_starting_points_presence owns that now).
    entry = {"archetype": "transform", "evidence": "x", "decided_at": "2026-08-08"}
    assert checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, entry, "2026-08-08") == []


def test_hybrid_reverification_flags_stale_decided_at():
    entry = {"archetype": "hybrid", "evidence": "real evidence", "decided_at": "2026-08-06"}
    findings = checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, entry, "2026-08-08")
    assert findings and "was not refreshed" in findings[0]["reason"]


def test_hybrid_reverification_passes_fresh_entry():
    entry = {"archetype": "hybrid", "evidence": "real evidence", "decided_at": "2026-08-08"}
    assert checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, entry, "2026-08-08") == []


# --- Twelfth incident / MT025 Phase 0c (2026-08-09): parse_formats_table, direction signals,
# check_diagram_verified_format_claims -- replaces the retired check_diagram_format_support_
# claims. Fixtures below reproduce the 4 real formats.md-vs-reality contradictions found during
# the forensic investigation (tex/python, 3d/net's PLY, pdf/cpp, html/python), captured with
# enough real detail to prove the check reaches the correct verdict on each, not just a
# plausible-looking one. -------------------------------------------------------------------------


def test_parse_formats_table_reads_directional_flags():
    text = "# Format Support\n\n| Format | Import | Export |\n|---|---|---|\n| PDF | - | Yes |\n| OBJ | Yes | Yes |\n"
    table = checks.parse_formats_table(text)
    assert table["PDF"] == {"import": False, "export": True}
    assert table["OBJ"] == {"import": True, "export": True}


def test_parse_formats_table_empty_on_blank_input():
    assert checks.parse_formats_table("") == {}
    assert checks.parse_formats_table(None) == {}


def test_parse_formats_table_tolerates_descriptive_text_in_format_cell():
    # Regression test: found live during MT025 Phase 2 batch C -- real email/cpp formats.md
    # writes "| CFB (Compound File Binary) | Yes | Yes |", and the original regex required the
    # format token to be immediately followed by the closing "|", silently matching zero rows
    # for every email product regardless of real content.
    text = (
        "# Format Support\n\n| Format | Import | Export |\n|---|---|---|\n"
        "| CFB (Compound File Binary) | Yes | Yes |\n| EML (RFC 5322 / MIME) | Yes | Yes |\n"
    )
    table = checks.parse_formats_table(text)
    assert table["CFB"] == {"import": True, "export": True}
    assert table["EML"] == {"import": True, "export": True}


def test_prose_direction_signal_true_on_plain_mention():
    assert checks._prose_direction_signal(
        "This library produces PDF documents.", "PDF", "export"
    ) is True


def test_prose_direction_signal_false_when_token_absent():
    assert checks._prose_direction_signal(
        "This library produces DOCX documents.", "PDF", "export"
    ) is False


def test_prose_direction_signal_negation_override_real_3d_net_case():
    # The real, confirmed 3d/net sentence: PLY is import-only. Must negate the EXPORT claim...
    prose = "PLY is import-only, unlike OBJ and STL which support both load and save."
    assert checks._prose_direction_signal(prose, "PLY", "export") is False
    # ...while still confirming the IMPORT claim from the same sentence.
    assert checks._prose_direction_signal(prose, "PLY", "import") is True


def test_prose_direction_signal_semicolon_bounds_the_window():
    # Regression test: found live during MT025 Phase 2's portfolio-wide rollup -- the real 3d/net
    # sentence "...COLLADA, and 3MF; PLY is import-only." let PLY's own negation wrongly bleed
    # into 3MF's window because only ". "/newline were treated as boundaries, not ";".
    prose = "Load and save OBJ, COLLADA, and 3MF; PLY is import-only."
    assert checks._prose_direction_signal(prose, "3MF", "export") is True
    assert checks._prose_direction_signal(prose, "PLY", "export") is False


def test_prose_direction_signal_checks_every_occurrence_not_just_the_first():
    # Regression test: the real, original motivating sentence mentions PLY TWICE -- a neutral
    # first mention, then the real negation in a later clause. Fixing the semicolon-boundary
    # bug above (by narrowing each occurrence's window) initially broke this case because only
    # the FIRST occurrence's window was ever checked; the negation lives in the SECOND mention's
    # own window.
    prose = "Loads OBJ, STL, and PLY; PLY is import-only, unlike OBJ and STL."
    assert checks._prose_direction_signal(prose, "PLY", "export") is False
    assert checks._prose_direction_signal(prose, "PLY", "import") is True


def test_prose_direction_signal_negation_does_not_bleed_to_a_different_format():
    # Regression test: found live during MT025 Phase 2's portfolio-wide rollup -- the real
    # pdf/net sentence "...beyond PDF/HTML/SVG/Markdown (import-only XML via ...)" must NOT
    # negate Markdown's export claim -- "import-only" here is grammatically about XML (the word
    # immediately following it), not Markdown, even though both sit in the same clause.
    prose = "Format converters beyond PDF/HTML/SVG/Markdown (import-only XML via BindXml)."
    assert checks._prose_direction_signal(prose, "MARKDOWN", "export") is True
    # But a negation phrase with no differently-named trailing word still applies normally.
    assert checks._prose_direction_signal("XML is import-only here.", "XML", "export") is False


def test_source_direction_signal_resolves_via_format_name_alias():
    # Regression test: 3d/typescript's real "3MF" support is implemented as ThreeMf-named
    # classes (most languages can't start an identifier with a digit) -- a literal "3MF"
    # substring search alone would never find it.
    names = ["ThreeMfLoadOptions", "ThreeMfSaveOptions"]
    assert checks._source_direction_signal(names, "3MF", "import") is True
    assert checks._source_direction_signal(names, "3MF", "export") is True


def test_prose_direction_signal_negation_override_export_only():
    prose = "The HTML5 writer is export-only; there is no HTML5 parser."
    assert checks._prose_direction_signal(prose, "HTML5", "import") is False
    assert checks._prose_direction_signal(prose, "HTML5", "export") is True


def test_prose_direction_signal_never_sees_the_mermaid_block():
    # A diagram must not be able to corroborate itself -- callers are required to strip the
    # mermaid block before calling this function; this test documents that contract directly.
    full_text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Outputs["Outputs"]
    o1["FAKEFORMAT files"]
  end
  PRODUCT --> Outputs""",
        extra_section="- Does a thing.",
    )
    prose_only = checks._MERMAID_BLOCK_FULL_RE.sub("", full_text)
    assert "FAKEFORMAT" not in prose_only


def test_load_api_surface_names_extracts_name_and_file_fields():
    text = json.dumps([
        {"name": "PdfWriter", "file": "src/pdf_writer.py", "kind": "class"},
        {"name": "DviWriter", "file": "src/dvi_writer.py", "kind": "class"},
        "not-a-dict",
    ])
    names = checks._load_api_surface_names(text)
    assert "PdfWriter" in names and "src/pdf_writer.py" in names and "DviWriter" in names


def test_load_api_surface_names_tolerates_malformed_input():
    assert checks._load_api_surface_names("") == []
    assert checks._load_api_surface_names("not json") == []
    assert checks._load_api_surface_names('{"not": "a list"}') == []


def test_source_direction_signal_export_suffix_match():
    # Real tex/python evidence: PdfWriter/DviWriter/SvgWriter prove export capability directly.
    names = ["PdfWriter", "TeXInterpreter", "DviFontDef"]
    assert checks._source_direction_signal(names, "PDF", "export") is True
    assert checks._source_direction_signal(names, "PDF", "import") is False


def test_source_direction_signal_import_suffix_match():
    names = ["ObjLoadOptions"]
    assert checks._source_direction_signal(names, "OBJ", "import") is True
    assert checks._source_direction_signal(names, "OBJ", "export") is False


def test_source_direction_signal_generic_match_counts_for_both_directions():
    # Real pdf/cpp evidence: PdfConverter/PdfFormat have no Load/Save-style suffix at all.
    names = ["PdfConverter", "PdfFormat"]
    assert checks._source_direction_signal(names, "PDF", "import") is True
    assert checks._source_direction_signal(names, "PDF", "export") is True


def test_source_direction_signal_short_token_never_matches():
    assert checks._source_direction_signal(["MdWriter"], "MD", "export") is False


def test_source_direction_signal_no_match_returns_false():
    assert checks._source_direction_signal(["Workbook", "Worksheet"], "PDF", "export") is False


def test_verified_format_claims_real_tex_python_case_overrides_stale_formats_md():
    # Real tex/python: formats.md marks PDF/DVI/SVG Export=No, but the product genuinely
    # produces all three -- prose + PdfWriter/DviWriter/SvgWriter source evidence must override.
    text = _wrap(
        """flowchart TD
  PRODUCT["Aspose.TeX FOSS for Python"]
  subgraph Capabilities["Core Capabilities"]
    c1["Typesetting"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF documents"]
    o2["DVI files"]
    o3["SVG documents"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section=(
            "- Typesets TeX/LaTeX source and produces PDF documents, DVI files, and SVG "
            "documents via dedicated output devices."
        ),
    )
    formats_md = "| PDF | - | - |\n| DVI | - | - |\n| SVG | - | - |\n"
    api_surface = json.dumps([
        {"name": "PdfWriter", "file": "_output/pdf_writer.py"},
        {"name": "DviWriter", "file": "_output/dvi_writer.py"},
        {"name": "SvgWriter", "file": "_output/svg_writer.py"},
    ])
    findings = checks.check_diagram_verified_format_claims(
        text, formats_md, api_surface, {"PDF", "DVI", "SVG"}
    )
    assert findings == [], findings


def test_verified_format_claims_real_3d_net_ply_case_discards_bad_export_keeps_good_import():
    # Real 3d/net: formats.md wrongly claims PLY Export=Yes; the file's own prose says
    # "PLY is import-only" -- export must be discarded, import must be kept.
    text = _wrap(
        """flowchart TD
  subgraph StartingPoints["Starting Points"]
    i1["A PLY file"]
  end
  PRODUCT["Aspose.3D FOSS for .NET"]
  subgraph Capabilities["Core Capabilities"]
    c1["Multi-format load and save"]
  end
  subgraph Outputs["Outputs"]
    o1["PLY files"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs""",
        extra_section="- Loads OBJ, STL, and PLY; PLY is import-only, unlike OBJ and STL.",
    )
    formats_md = "| PLY | Yes | Yes |\n"
    findings = checks.check_diagram_verified_format_claims(
        text, formats_md, None, {"PLY"}
    )
    assert len(findings) == 1
    assert findings[0]["format"] == "PLY"
    assert findings[0]["direction"] == "export"


def test_verified_format_claims_real_3d_net_3mf_case_resolves_via_alias():
    # Real 3d/net: formats.md records the same format under "MICROSOFT3MF", not "3MF" -- the
    # name every product's own prose and diagram actually use. Found live during the
    # portfolio-wide rollup: an exact-match table lookup silently treated a real, Yes-flagged
    # row as absent, and the fix (a real, already-shipped one) is _formats_table_lookup's alias
    # resolution, exercised here end to end via the real function under test.
    text = _wrap(
        """flowchart TD
  PRODUCT["Aspose.3D FOSS for .NET"]
  subgraph Capabilities["Core Capabilities"]
    c1["Multi-format load and save"]
  end
  subgraph Outputs["Outputs"]
    o1["FBX, COLLADA, and 3MF files"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="- Loads and saves FBX, COLLADA, and 3MF.",
    )
    formats_md = "| MICROSOFT3MF | Yes | Yes |\n"
    findings = checks.check_diagram_verified_format_claims(
        text, formats_md, None, {"3MF"}
    )
    assert findings == [], findings


def test_verified_format_claims_real_pdf_cpp_case_missing_formats_md_row():
    # Real pdf/cpp: formats.md has no PDF row at all (only BMP/JPEG/SCRATCH/SVG/TEXT/TIFF/
    # UNICODE) despite PDF being the product's own primary format -- prose + source evidence
    # must still verify it despite formats.md's total silence.
    text = _wrap(
        """flowchart TD
  subgraph StartingPoints["Starting Points"]
    i1["An existing PDF document"]
  end
  PRODUCT["Aspose.PDF FOSS for C++"]
  subgraph Capabilities["Core Capabilities"]
    c1["Open and save"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF documents"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs""",
        extra_section="- Opens and saves PDF documents; text extraction and rendering included.",
    )
    formats_md = "| BMP | - | Yes |\n| JPEG | - | Yes |\n"
    api_surface = json.dumps([{"name": "PdfConverter", "file": "pdf_converter.hpp"}])
    findings = checks.check_diagram_verified_format_claims(
        text, formats_md, api_surface, {"PDF"}
    )
    assert findings == [], findings


def test_verified_format_claims_discards_uncorroborated_fabrication():
    # Regression proof: the original defect class check_diagram_format_support_claims existed
    # to catch (a fabricated, uncorroborated format claim) is still caught by the replacement.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["XLSX workbook"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="- Does a thing.",
    )
    findings = checks.check_diagram_verified_format_claims(text, "", None, {"XLSX"})
    assert len(findings) == 1
    assert findings[0]["format"] == "XLSX"
    assert findings[0]["signals"] == {"formats_md": False, "prose": False, "source": False}


def test_verified_format_claims_ignores_capabilities_container():
    # Deliberately scoped to Starting Points/Outputs only -- a Capabilities-only mention (no
    # Starting Points/Outputs claim) is never checked by this function.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Convert to FAKEFORMAT"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="- Does a thing.",
    )
    findings = checks.check_diagram_verified_format_claims(text, "", None, {"FAKEFORMAT"})
    assert findings == []


def test_verified_format_claims_recognizes_digit_leading_format_tokens():
    # Regression test: found live during MT025 Phase 2 batch A -- a leading-letter-only token
    # regex silently exempted "3MF" (and any other digit-leading format name) from verification
    # entirely, neither confirming nor discarding it. An uncorroborated digit-leading claim must
    # now be discarded exactly like any other uncorroborated claim.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["3MF files"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="- Does a thing.",
    )
    findings = checks.check_diagram_verified_format_claims(text, "", None, {"3MF"})
    assert len(findings) == 1
    assert findings[0]["format"] == "3MF"


# --- check_format_name_casing -------------------------------------------------------------------


def test_format_name_casing_flags_inconsistent_bare_casing():
    text = "The XLSX format is supported. This is not a XLSx problem."
    findings = checks.check_format_name_casing(text, {"XLSX": "XLSX"})
    assert any(f["found"] == "XLSx" for f in findings)


def test_format_name_casing_passes_consistent_canonical_casing():
    text = "This library uses .xlsx files consistently. XLSX is the only format."
    assert checks.check_format_name_casing(text, {"XLSX": "XLSX"}) == []


def test_format_name_casing_ignores_dotted_extension_form():
    # ".xlsx" (extension reference) must never be compared against the bare "XLSX" form.
    text = "Save as .xlsx. XLSX is the canonical format name."
    assert checks.check_format_name_casing(text, {"XLSX": "XLSX"}) == []


def test_format_name_casing_ignores_ordinary_prose_words():
    # Sentence-initial capitalization ("The" vs "the") must never be flagged as a
    # casing inconsistency -- the bug this test guards against would fire on every file.
    text = "The library is fast. Read the docs for more. The API is stable."
    assert checks.check_format_name_casing(text, {"XLSX": "XLSX"}) == []


def test_format_name_casing_allows_the_known_gltf_heading_exception():
    # Real, found-live tension (3d/python, 3d/typescript): glTF's genuine official spelling
    # is mixed-case (like "iPhone"), which Rule 6's mechanical title-case-every-heading
    # requirement can't represent -- the resolved portfolio convention is "glTF" in prose
    # and "GLTF" only where it's the first word of a title-cased heading.
    text = "glTF is supported. glTF import and export.\n\n### Assign a PBR Material and Export to GLTF\n"
    assert checks.check_format_name_casing(text, {}) == []


def test_format_name_casing_still_flags_a_genuine_third_gltf_variant():
    text = "GLTF and glTF and Gltf all appear in this file."
    findings = checks.check_format_name_casing(text, {})
    assert any(f["format"] == "GLTF" for f in findings)


def test_format_name_casing_flags_multiple_casings_of_unregistered_word():
    text = "FOO bar. Foo baz. foo qux."
    findings = checks.check_format_name_casing(text, {})
    assert any(f["format"] == "FOO" for f in findings)


def test_format_name_casing_ignores_html_in_a_badge_link_url():
    # Regression test for a real bug found by a sub-agent's own investigation: the shared
    # _MD_LINK_RE used to stop at the FIRST "]" (the inner image alt text's own closing
    # bracket in a "[![alt](img)](target)" badge link), leaving the real OUTER href
    # completely unstripped -- "html" inside a repo-slug URL like
    # ".../aspose-html-foss/..." then leaked into the bare-word prose scan.
    text = (
        "This is HTML.\n\n"
        "[![Contributors](https://img.shields.io/badge/x.svg)]"
        "(https://github.com/aspose-html-foss/Aspose.HTML-FOSS-for-Python/graphs/contributors)\n"
    )
    assert checks.check_format_name_casing(text, {"HTML": "HTML"}) == []


def test_md_link_re_captures_real_outer_href_for_badge_links():
    text = "[![CI](https://img.shields.io/badge/ci.svg)](https://github.com/org/repo/actions)"
    match = checks._MD_LINK_RE.search(text)
    assert match.group(2) == "https://github.com/org/repo/actions"


def test_md_link_re_still_matches_plain_links():
    text = "[Getting started](https://docs.aspose.org/foo/python/)"
    match = checks._MD_LINK_RE.search(text)
    assert match.group(1) == "Getting started"
    assert match.group(2) == "https://docs.aspose.org/foo/python/"


def test_format_name_casing_ignores_generic_project_acronyms():
    # Regression test for a real false positive found via a 30-product portfolio run: FOSS
    # (from repo/CMake-target slugs like aspose-pdf-foss / aspose_pdf_foss) and LICENSE
    # (from plain-prose filename mentions) accounted for the overwhelming majority of
    # findings across the whole corpus, drowning out genuine format-casing defects.
    text = (
        "This is Aspose.PDF FOSS for C++, part of the aspose-pdf-foss organization. "
        "See the LICENSE file. This project is licensed under the MIT License."
    )
    findings = checks.check_format_name_casing(text, {})
    assert not any(f.get("format") in ("FOSS", "LICENSE") for f in findings)


# TC-HARDEN-28 (Twenty-Second incident / MT035, 2026-08-12): a real 12-product, 69-finding
# audit found the no-canonical-entry ("elif") branch produces a 63% false-positive rate from
# two mechanisms, both concentrated inside the `## API Reference` section -- a Title-Case
# module heading colliding with correct all-caps prose elsewhere, and a real, deliberately
# dual-cased technical identifier documented in a table description cell colliding with an
# unrelated ordinary-English use of the same spelling. Every fixture below is captured
# verbatim from the real content that first exposed each mechanism, not synthesized.


def test_format_name_casing_excludes_heading_collision_with_correct_prose():
    # Real shape, html/python: a Title-Case "### Css" module heading (mirroring
    # reference.aspose.org's own real module name) collides with "CSS" used correctly,
    # all-caps, in ordinary body prose -- the heading text was never excluded from the scan.
    text = (
        "It parses and applies CSS to build the render tree.\n\n"
        "## API Reference\n\n"
        "### Css\n\n"
        "| `CSSStyleSheet` | The parsed representation of a CSS stylesheet. |\n\n"
        "## Scope and Limitations\n\n"
        "- Some CSS features are unsupported.\n"
    )
    assert checks.check_format_name_casing(text, {}) == []


def test_format_name_casing_excludes_api_reference_table_field_code_homonym():
    # Real shape, words/net: "DATA" (a Word field-code keyword, `FieldData` implements the
    # DATA field) documented inside an API Reference table row collides with ordinary
    # lowercase "data" used elsewhere in the README with a completely different meaning.
    text = (
        "Clear the default generated series before adding real data.\n\n"
        "## API Reference\n\n"
        "| `FieldData` | Implements the DATA field. |\n"
    )
    assert checks.check_format_name_casing(text, {}) == []


def test_format_name_casing_excludes_api_reference_table_operator_mnemonic_homonym():
    # Real shape, pdf/net: PDF content-stream operator mnemonics `sc`/`SC` are two genuinely
    # different, both-correct ISO 32000 operators (non-stroking vs. stroking color), not a
    # casing defect -- documented side by side inside the same API Reference section.
    text = (
        "## API Reference\n\n"
        "| `SetColor` | sc -- Set color in current color space (non-stroking). |\n"
        "| `SetColorStroke` | SC -- Set color in current color space (stroking). |\n"
    )
    assert checks.check_format_name_casing(text, {}) == []


def test_format_name_casing_excludes_api_reference_emphatic_allcaps_word():
    # Real shape, html/python: "NOT" used for plain English emphasis inside a table
    # description cell ("do NOT match") collides with an unrelated Title-Case heading use of
    # the same word ("### Layout ... Not Visual Rendering") -- neither is a format-name claim.
    text = (
        "## API Reference\n\n"
        "| `ComplexNotPseudoClass` | Matches elements that do NOT match any selector. |\n\n"
        "### Layout (Structural Geometry, Not Visual Rendering)\n\n"
        "Some prose about layout.\n"
    )
    assert checks.check_format_name_casing(text, {}) == []


def test_format_name_casing_still_flags_genuine_drift_inside_api_reference_section():
    # Regression guard: the canonical_casing branch (registry-mismatch) is UNCHANGED and
    # must still catch real drift even when it occurs entirely inside the ## API Reference
    # section -- e.g. commercial-SDK PascalCase spelling ("Pdf") leaking into a table
    # description cell, uncorrected against the canonical all-caps form. Excluding the API
    # Reference section from the no-canonical-entry branch must never suppress this.
    text = (
        "## API Reference\n\n"
        "| `Font` | Lets developers query whether a font is embedded in the PDF. |\n"
        "| `OutlineCollection` | Class in the Pdf CPP API. |\n"
    )
    findings = checks.check_format_name_casing(text, {"PDF": "PDF"})
    assert any(f.get("found") == "Pdf" and f["canonical"] == "PDF" for f in findings)


def test_format_name_casing_heading_only_occurrence_is_vacuous():
    # Regression guard: if a word's ONLY mixed-case occurrence is inside a heading (and every
    # other occurrence in the file is already the correct all-caps form), it must drop to a
    # single variant after heading-stripping, not remain a false "multiple casings" finding.
    text = (
        "This module handles JS execution.\n\n"
        "## API Reference\n\n"
        "### Js\n\n"
        "| `JSRuntime` | The JS execution context. |\n"
    )
    assert checks.check_format_name_casing(text, {}) == []


def test_format_name_casing_api_reference_section_located_before_heading_strip():
    # Regression guard for the real ordering bug found while implementing this fix: locating
    # the ## API Reference section MUST happen before heading lines are stripped -- stripping
    # headings first deletes the "## API Reference" heading itself, leaving nothing for the
    # section matcher to anchor on, so the whole section-exclusion silently no-ops. This
    # fixture reproduces the real words/net shape that exposed the bug: a genuine elif-branch
    # false positive (a field-code keyword vs. ordinary prose) sitting well after several
    # other real ## headings, inside the API Reference section.
    text = (
        "# Product\n\n"
        "## Key Capabilities\n\n"
        "- Does a thing.\n\n"
        "## Installation\n\n"
        "Install it.\n\n"
        "## API Reference\n\n"
        "| `FieldIf` | Implements the IF field. |\n\n"
        "## Scope and Limitations\n\n"
        "- Only if a document is encrypted does this apply.\n"
    )
    assert checks.check_format_name_casing(text, {}) == []


# --- check_no_cross_product_citation -------------------------------------------------------------


def test_no_cross_product_citation_flags_sibling_family_mention():
    text = (
        "## Installation\n\n"
        "(C++ isn't registry-less in general: [Aspose.Cells FOSS for C++]"
        "(https://www.nuget.org/packages/Aspose.Cells.Cpp.FOSS/) does publish there.)\n"
    )
    findings = checks.check_no_cross_product_citation(text, "pdf")
    assert any(f["family"] == "Cells" for f in findings)


def test_no_cross_product_citation_ignores_own_family():
    text = "## Installation\n\nAspose.Pdf for C++ builds as a static library.\n"
    assert checks.check_no_cross_product_citation(text, "pdf") == []


def test_no_cross_product_citation_exempts_documentation_resources_section():
    text = (
        "## Documentation & resources\n\n"
        "See also [Aspose.Cells FOSS for C++](https://github.com/aspose-cells-foss).\n"
    )
    assert checks.check_no_cross_product_citation(text, "pdf") == []


def test_no_cross_product_citation_exempts_title_cased_documentation_resources_section():
    # The exempt-section match must stay case-insensitive on "resources" specifically --
    # once Rule 6 (title-case headings) lands, "## Documentation & Resources" (capital R)
    # must still be recognized as the same exempt section.
    text = (
        "## Documentation & Resources\n\n"
        "See also [Aspose.Cells FOSS for C++](https://github.com/aspose-cells-foss).\n"
    )
    assert checks.check_no_cross_product_citation(text, "pdf") == []


def test_no_cross_product_citation_restricted_to_known_families_ignores_own_namespace_spelling():
    # Regression test for a real false positive found via a 30-product portfolio run:
    # 3d/net's own C# namespace "Aspose.ThreeD" (digit-safe spelling of its own family --
    # data/families.json only ever spells this family "Aspose.3D") and words/net's internal
    # tooling names ("Aspose.EnumExtensionsGenerator", "Aspose.Foundation") were both being
    # flagged as if citing a sibling PRODUCT, once matching is restricted to a real, bounded
    # family allowlist neither is a member of.
    known = {"3D", "PDF", "Cells", "Words"}
    text = "The Aspose.ThreeD namespace contains Scene, Node, and Entity."
    assert checks.check_no_cross_product_citation(text, "3d", known) == []
    text2 = "Comment out the Aspose.EnumExtensionsGenerator PackageReference to build."
    assert checks.check_no_cross_product_citation(text2, "words", known) == []


def test_no_cross_product_citation_still_flags_real_sibling_when_restricted():
    known = {"3D", "PDF", "Cells", "Words"}
    text = "(C++ isn't registry-less: [Aspose.Cells FOSS for C++](https://example.com) does publish.)"
    findings = checks.check_no_cross_product_citation(text, "pdf", known)
    assert any(f["family"] == "Cells" for f in findings)


# --- check_examples_table_collapsed ---------------------------------------------------------------


def test_examples_table_collapsed_flags_always_visible_table():
    text = (
        "## Additional examples\n\n"
        "12 examples demonstrate the core API.\n\n"
        "| Example | Shows |\n|---|---|\n| `01` | opens a file |\n\n"
        "<details><summary>View additional examples</summary>\n\nMore prose.\n</details>\n"
    )
    findings = checks.check_examples_table_collapsed(text)
    assert findings and "not inside a <details> block" in findings[0]["reason"]


def test_examples_table_collapsed_passes_when_table_is_inside_details():
    text = (
        "## Additional examples\n\n"
        "12 examples demonstrate the core API.\n\n"
        "<details><summary>View additional examples</summary>\n\n"
        "| Example | Shows |\n|---|---|\n| `01` | opens a file |\n\n"
        "</details>\n"
    )
    assert checks.check_examples_table_collapsed(text) == []


def test_examples_table_collapsed_noop_when_no_table():
    text = "## Additional examples\n\nOne example, shown directly.\n\n```python\nx = 1\n```\n"
    assert checks.check_examples_table_collapsed(text) == []


def test_examples_table_collapsed_matches_title_cased_heading():
    # Regression test for a real, significant regression found by a sub-agent while
    # title-casing headings portfolio-wide: this section matcher was hardcoded to lowercase
    # "## Additional examples" with no re.IGNORECASE. Once Rule 6 landed and every real
    # file's heading became "## Additional Examples", the match would silently fail on
    # every single file, making this hard gate permanently inert going forward.
    text = (
        "## Additional Examples\n\n"
        "12 examples demonstrate the core API.\n\n"
        "| Example | Shows |\n|---|---|\n| `01` | opens a file |\n\n"
        "<details><summary>View Additional Examples</summary>\n\nMore prose.\n</details>\n"
    )
    findings = checks.check_examples_table_collapsed(text)
    assert findings and "not inside a <details> block" in findings[0]["reason"]


# --- check_heading_title_case ----------------------------------------------------------------------


def test_heading_title_case_flags_sentence_case_headings():
    text = "## At a glance\n\n## Key capabilities\n\n## Documentation & resources\n"
    findings = checks.check_heading_title_case(text)
    headings = {f["heading"] for f in findings}
    assert "At a glance" in headings
    assert "Key capabilities" in headings


def test_heading_title_case_passes_real_title_case():
    text = "## At a Glance\n\n## Key Capabilities\n\n## Documentation & Resources\n"
    assert checks.check_heading_title_case(text) == []


def test_heading_title_case_flags_summary_text_too():
    text = "<details>\n<summary>View additional examples</summary>\n</details>\n"
    findings = checks.check_heading_title_case(text)
    assert any(f["kind"] == "summary" for f in findings)


def test_heading_title_case_allows_minor_words_lowercase():
    text = "## Development and Testing\n"
    assert checks.check_heading_title_case(text) == []


def test_heading_title_case_allows_all_caps_acronyms():
    text = "## API Reference\n"
    assert checks.check_heading_title_case(text) == []


# --- check_section_job_distinctness --------------------------------------------------------------


def test_section_job_distinctness_flags_real_overlap():
    text = (
        "This library provides fast PDF text extraction and page rendering for developers.\n\n"
        "## Key capabilities\n\n"
        "- Fast PDF text extraction and page rendering for developers using this library.\n"
    )
    findings = checks.check_section_job_distinctness(text)
    assert findings and findings[0]["similarity"] > 0.5


def test_section_job_distinctness_clean_when_genuinely_distinct():
    text = (
        "This library is the open-source core of a commercial Aspose product family.\n\n"
        "## Key capabilities\n\n"
        "- Encrypts documents with AES-256.\n"
        "- Renders pages to PNG and JPEG.\n"
    )
    assert checks.check_section_job_distinctness(text) == []


def test_section_job_distinctness_noop_without_key_capabilities_section():
    assert checks.check_section_job_distinctness("Just an intro paragraph.\n") == []


def test_section_job_distinctness_matches_title_cased_heading():
    # Same regression class as check_examples_table_collapsed above: this section matcher
    # was hardcoded to lowercase "## Key capabilities".
    text = (
        "This library provides fast PDF text extraction and page rendering for developers.\n\n"
        "## Key Capabilities\n\n"
        "- Fast PDF text extraction and page rendering for developers using this library.\n"
    )
    findings = checks.check_section_job_distinctness(text)
    assert findings and findings[0]["similarity"] > 0.5


# --- check_only_mermaid_block_changed (unchanged function, new-model fixtures) -----------------


def test_only_mermaid_block_changed_true_for_identical_text():
    assert checks.check_only_mermaid_block_changed(HYBRID_PDF_CPP, HYBRID_PDF_CPP)


def test_only_mermaid_block_changed_true_when_only_diagram_edited():
    new_text = HYBRID_PDF_CPP.replace(
        "StartingPoints --> PRODUCT", "StartingPoints --> PRODUCT\n  %% a comment"
    )
    assert new_text != HYBRID_PDF_CPP
    assert checks.check_only_mermaid_block_changed(HYBRID_PDF_CPP, new_text)


def test_only_mermaid_block_changed_false_when_prose_also_edited():
    new_text = HYBRID_PDF_CPP.replace(
        "StartingPoints --> PRODUCT", "StartingPoints --> PRODUCT\n  %% a comment"
    ).replace("- Does a thing.", "- Does a different thing.")
    assert checks.check_only_mermaid_block_changed(HYBRID_PDF_CPP, new_text) is False


def test_only_mermaid_block_changed_false_when_only_prose_edited():
    new_text = HYBRID_PDF_CPP.replace("- Does a thing.", "- Does a different thing.")
    assert checks.check_only_mermaid_block_changed(HYBRID_PDF_CPP, new_text) is False


def test_only_mermaid_block_changed_false_when_block_disappears():
    new_text = HYBRID_PDF_CPP.split("## At a glance")[0] + "## Key capabilities\n\n- Does a thing.\n"
    assert checks.check_only_mermaid_block_changed(HYBRID_PDF_CPP, new_text) is False


# --- Content checks (whole-README) -- fixtures below intentionally minimal, not full READMEs ---

_ENTERPRISE_LINK_WITH_CONTEXT = (
    "For workflows that require broader format coverage or full feature completeness, "
    "see [Aspose.Foo Enterprise Edition](https://products.aspose.com/foo/python-net/)."
)
_ENTERPRISE_LINK_BAD_ANCHOR_WITH_CONTEXT = (
    "For workflows that require broader format coverage or full feature completeness, "
    "see [Aspose.Foo Enterprise Product](https://products.aspose.com/foo/python-net/)."
)
_ENTERPRISE_LINK_NAKED_CTA = "See [Aspose.Foo Enterprise Edition](https://products.aspose.com/foo/python-net/)."
_ASPOSE_ORG_LINK = "[Getting started](https://docs.aspose.org/foo/python/)"

_ALL_SECTIONS_README = """# Foo

## At a Glance
## Key Capabilities
## Installation
## Quick Start
## Additional Examples
## API Reference
## Documentation & Resources
## Scope and Limitations
## Development and Testing
## License
"""


def test_compute_link_caps_counts_correctly():
    text = f"See {_ENTERPRISE_LINK_WITH_CONTEXT} and {_ASPOSE_ORG_LINK} and [external](https://example.com)."
    result = checks.compute_link_caps(text)
    assert result["total_links"] == 3
    assert result["aspose_org_links"] == 2  # products.aspose.com + docs.aspose.org
    assert result["enterprise_edition_links"] == 1


def test_count_aspose_links():
    text = f"{_ASPOSE_ORG_LINK} and [external](https://example.com)"
    assert checks.count_aspose_links(text) == 1


def test_check_enterprise_edition_naming_passes_correct_anchor_with_context():
    assert checks.check_enterprise_edition_naming(_ENTERPRISE_LINK_WITH_CONTEXT) == []


def test_check_enterprise_edition_naming_flags_wrong_anchor():
    findings = checks.check_enterprise_edition_naming(_ENTERPRISE_LINK_BAD_ANCHOR_WITH_CONTEXT)
    naming_findings = [f for f in findings if f["reason"] == "missing_naming"]
    assert len(naming_findings) == 1
    assert "Enterprise Product" in naming_findings[0]["anchor_text"]


def test_check_enterprise_edition_naming_flags_naked_cta_missing_context():
    # 2026-08-08 (Rule 4): correct naming alone is not enough -- the surrounding text must
    # explain the broader/full functionality gained, not just be a bare "See [...]" CTA.
    findings = checks.check_enterprise_edition_naming(_ENTERPRISE_LINK_NAKED_CTA)
    assert any(f["reason"] == "missing_context" for f in findings)


def test_check_enterprise_edition_naming_context_window_is_paragraph_aware():
    # Regression test for a real false positive found via a 30-product portfolio run: a
    # fixed 60-char-before lookback (centered on the link, not the sentence) cut off the
    # qualifying word in real, already-well-written explanatory sentences.
    text = (
        "Some other paragraph entirely, unrelated content that goes on for a while "
        "so the old 60-character window would never have reached back this far.\n\n"
        "For rendering, the broader exchange-format set (FBX, glTF, USD, PDF, JT, and more), "
        "and advanced mesh operations, see "
        "[Aspose.3D for Java Enterprise Edition](https://products.aspose.com/3d/java/)."
    )
    findings = checks.check_enterprise_edition_naming(text)
    assert not any(f["reason"] == "missing_context" for f in findings)


def test_check_enterprise_edition_naming_context_is_order_agnostic():
    # Regression test for a real false positive: the target-class word ("formats") appears
    # BEFORE the qualifier ("advanced") in this real sentence -- natural English doesn't
    # have a fixed order here.
    text = (
        "For proprietary formats (A3DW, PDF, USD, JT), rendering, and advanced mesh "
        "operations, see [Aspose.3D for .NET — Enterprise Edition](https://products.aspose.com/3d/net/)."
    )
    findings = checks.check_enterprise_edition_naming(text)
    assert not any(f["reason"] == "missing_context" for f in findings)


def test_check_enterprise_edition_link_resolves_passes_matching_link():
    text = "See [Aspose.Foo Enterprise Edition](https://products.aspose.com/foo/net/)."
    enterprise_link = {"url": "https://products.aspose.com/foo/net/"}
    assert checks.check_enterprise_edition_link_resolves(text, enterprise_link) == []


def test_check_enterprise_edition_link_resolves_flags_dead_link_regression():
    # Real, confirmed-live regression from a clean-room regeneration pilot: 3d/typescript's
    # regenerated candidate linked to a real, curl-confirmed 404
    # (https://products.aspose.com/3d/typescript/), while the verified target is
    # https://products.aspose.com/3d/ -- check_enterprise_edition_naming alone (anchor
    # text/context) would have passed this cleanly.
    text = "See [Aspose.3D for TypeScript Enterprise Edition](https://products.aspose.com/3d/typescript/)."
    enterprise_link = {"url": "https://products.aspose.com/3d/"}
    findings = checks.check_enterprise_edition_link_resolves(text, enterprise_link)
    assert findings == [{
        "anchor_text": "Aspose.3D for TypeScript Enterprise Edition",
        "href": "https://products.aspose.com/3d/typescript/",
        "reason": "target_mismatch",
        "detail": "this href does not match the one verified, live-resolving Enterprise target "
                  "'https://products.aspose.com/3d/' for this product",
        "verified_url": "https://products.aspose.com/3d/",
    }]


def test_check_enterprise_edition_link_resolves_flags_no_verified_target():
    text = "See [Aspose.Foo Enterprise Edition](https://products.aspose.com/foo/net/)."
    findings = checks.check_enterprise_edition_link_resolves(text, {"url": None})
    assert findings == [{
        "anchor_text": "Aspose.Foo Enterprise Edition",
        "href": "https://products.aspose.com/foo/net/",
        "reason": "no_verified_target",
        "detail": "this candidate links to products.aspose.com, but no verified Enterprise "
                  "target resolves for this product in data/aspose_com_targets.json -- remove "
                  "the link, never guess a slug",
    }]


def test_check_enterprise_edition_link_resolves_handles_none_enterprise_link():
    text = "See [Aspose.Foo Enterprise Edition](https://products.aspose.com/foo/net/)."
    findings = checks.check_enterprise_edition_link_resolves(text, None)
    assert findings[0]["reason"] == "no_verified_target"


def test_check_enterprise_edition_link_resolves_ignores_non_enterprise_links():
    text = _ASPOSE_ORG_LINK
    assert checks.check_enterprise_edition_link_resolves(text, {"url": None}) == []


def test_check_enterprise_edition_link_resolves_trailing_slash_and_case_normalized():
    text = "See [Aspose.Foo Enterprise Edition](HTTPS://PRODUCTS.ASPOSE.COM/foo/net)."
    enterprise_link = {"url": "https://products.aspose.com/foo/net/"}
    assert checks.check_enterprise_edition_link_resolves(text, enterprise_link) == []


def test_check_required_sections_all_present():
    assert checks.check_required_sections(_ALL_SECTIONS_README) == []


def test_check_required_sections_flags_missing():
    text = _ALL_SECTIONS_README.replace("## License\n", "")
    missing = checks.check_required_sections(text)
    assert missing == ["License"]


def test_surgical_diff_check_no_undeclared_changes():
    assert checks.surgical_diff_check(["README.md"], ["README.md"]) == []


def test_surgical_diff_check_flags_undeclared_file():
    result = checks.surgical_diff_check(["README.md"], ["README.md", "SECURITY.md"])
    assert result == ["SECURITY.md"]


def test_check_license_link_target_no_link_is_fine(tmp_path):
    text = "## License\n\nThis project is licensed under the MIT License.\n"
    assert checks.check_license_link_target(text, str(tmp_path)) == []


def test_check_license_link_target_real_file_passes(tmp_path):
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    text = "## License\n\nThis project is licensed under the [MIT License](LICENSE).\n"
    assert checks.check_license_link_target(text, str(tmp_path)) == []


def test_check_license_link_target_missing_file_fails(tmp_path):
    text = "## License\n\nThis project is licensed under the [MIT License](LICENSE).\n"
    findings = checks.check_license_link_target(text, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["target"] == "LICENSE"


def test_check_license_link_target_ignores_unrelated_second_link_when_license_link_first(tmp_path):
    # TC-HARDEN-25 (MT034 reproof): a real, unrelated cross-reference link legitimately shares
    # the License section with the real license link -- the real license link comes first here.
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    text = (
        "## License\n\n"
        "This project is licensed under the [MIT License](LICENSE). "
        "A known build issue affects a fresh clone -- see "
        "[upstream-issues.md](upstream-issues.md) for details.\n"
    )
    assert checks.check_license_link_target(text, str(tmp_path)) == []


def test_check_license_link_target_ignores_unrelated_second_link_when_license_link_second(tmp_path):
    # Same real shape, reversed order -- the unrelated link comes first, reproducing the exact
    # incident found live on a 3d/typescript clean-room regeneration candidate: a positional
    # "first link in the section" rule wrongly flagged the real, correct license link.
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    text = (
        "## License\n\n"
        "See [upstream-issues.md](upstream-issues.md) for a known build issue. "
        "This project is licensed under the [MIT License](LICENSE).\n"
    )
    assert checks.check_license_link_target(text, str(tmp_path)) == []


def test_check_license_link_target_flags_bad_license_link_even_with_unrelated_second_link(tmp_path):
    # Regression guard: the fix must still catch a genuinely broken license link, not just stop
    # checking once a second link is present.
    text = (
        "## License\n\n"
        "See [upstream-issues.md](upstream-issues.md) for a known build issue. "
        "This project is licensed under the [MIT License](LICENSE).\n"
    )
    findings = checks.check_license_link_target(text, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["target"] == "LICENSE"


# --- check_license_section_matches_template (TC-HARDEN-26, MT034 Twenty-First incident) -------


def test_license_section_matches_template_linked_form_passes():
    text = (
        "## License\n\n"
        "This project is licensed under the [MIT License](LICENSE). The MIT License permits "
        "use, copying, modification, distribution, sublicensing, and commercial use, provided "
        "its copyright and permission notice are retained. The software is provided without "
        "warranty.\n"
    )
    assert checks.check_license_section_matches_template(text, {"relative_path": "LICENSE"}) == []


def test_license_section_matches_template_unlinked_form_passes():
    text = (
        "## License\n\n"
        "This project is licensed under the MIT License. The MIT License permits use, "
        "copying, modification, distribution, sublicensing, and commercial use, provided its "
        "copyright and permission notice are retained. The software is provided without "
        "warranty.\n"
    )
    assert checks.check_license_section_matches_template(text, None) == []


def test_license_section_matches_template_tolerates_real_line_wrap_variance():
    # Real portfolio content wraps the fixed template at different line widths (confirmed live:
    # cells/cpp, barcode/python, pdf/go all wrap differently) -- whitespace normalization must
    # make this a non-issue.
    text = (
        "## License\n\n"
        "This project is licensed under the [MIT License](LICENSE). The MIT License\n"
        "permits use, copying, modification, distribution, sublicensing, and commercial\n"
        "use, provided its copyright and permission notice are retained. The software is\n"
        "provided without warranty.\n"
    )
    assert checks.check_license_section_matches_template(text, {"relative_path": "LICENSE"}) == []


def test_license_section_matches_template_allows_legitimate_extra_content_after():
    # pdf/go's real, already-established third-party font disclosure follows the fixed template
    # -- "starts with", not "equals exactly", must not flag this.
    text = (
        "## License\n\n"
        "This project is licensed under the [MIT License](LICENSE). The MIT License permits "
        "use, copying, modification, distribution, sublicensing, and commercial use, provided "
        "its copyright and permission notice are retained. The software is provided without "
        "warranty.\n\n"
        "The library bundles Latin-subset copies of four metric-compatible fonts, used to "
        "render the Standard-14 fonts.\n"
    )
    assert checks.check_license_section_matches_template(text, {"relative_path": "LICENSE"}) == []


def test_license_section_matches_template_flags_real_narration_incident():
    # Captured verbatim from the real Twenty-First incident: a blind clean-room regeneration of
    # 3d/typescript independently reproduced the identical defect class the 2026-08-04 fix was
    # supposed to have already closed.
    text = (
        "## License\n\n"
        '`package.json` declares `"license": "MIT"`, and the previous version of this README '
        "linked to a `LICENSE` file, but no `LICENSE` file exists anywhere in this repository "
        "snapshot. The MIT License, if formally applied as declared, would permit use, "
        "copying, modification, distribution, sublicensing, and commercial use, provided its "
        "copyright and permission notice are retained, with the software provided without "
        "warranty — but until a real `LICENSE` file is added upstream, treat the license "
        "status as unconfirmed.\n"
    )
    findings = checks.check_license_section_matches_template(text, None)
    assert len(findings) == 1
    assert "does not start with the fixed template" in findings[0]["reason"]


def test_license_section_matches_template_flags_unlinked_form_when_file_exists():
    # A real license file exists, so the LINKED template is required -- the unlinked form must
    # not be silently accepted (proves this check's scope is additive to, not redundant with,
    # check_license_link_target, which only checks the link target when a link is present).
    text = (
        "## License\n\n"
        "This project is licensed under the MIT License. The MIT License permits use, "
        "copying, modification, distribution, sublicensing, and commercial use, provided its "
        "copyright and permission notice are retained. The software is provided without "
        "warranty.\n"
    )
    findings = checks.check_license_section_matches_template(text, {"relative_path": "LICENSE"})
    assert len(findings) == 1


def test_license_section_matches_template_no_section_is_vacuous():
    assert checks.check_license_section_matches_template("# No license section here\n", None) == []


def test_check_process_narration_smells_flags_license_leak_phrases():
    # TC-HARDEN-26: a secondary safety net alongside the primary template check, in case this
    # exact narration recurs in a DIFFERENT section a future run.
    assert checks.check_process_narration_smells(
        "The previous version of this README linked to a LICENSE file."
    )
    assert checks.check_process_narration_smells(
        "No LICENSE file exists anywhere in this repository snapshot."
    )
    assert checks.check_process_narration_smells(
        "The MIT License, if formally applied as declared, would permit use."
    )
    assert checks.check_process_narration_smells(
        "Until a real LICENSE file is added, treat the license status as unconfirmed."
    )


def test_check_process_narration_smells_flags_known_phrases():
    text = "This was verified against the published package, and passes cleanly on Linux."
    findings = checks.check_process_narration_smells(text)
    phrases = {f["phrase"].lower() for f in findings}
    assert "was verified" in phrases
    assert "passes cleanly" in phrases


def test_check_process_narration_smells_flags_broadened_categories():
    # 2026-08-08 (Rule 3): internal receipts, execution notes, provenance, confidence
    # language -- named categories added beyond the original 22 incident-specific phrases.
    assert checks.check_process_narration_smells(
        "According to our audit, this module is stable."
    )
    assert checks.check_process_narration_smells(
        "This session found no issues with the build."
    )
    assert checks.check_process_narration_smells(
        "This file was generated by the pipeline automatically."
    )
    assert checks.check_process_narration_smells("We confirmed that the API works correctly.")
    assert checks.check_process_narration_smells("This behavior has been verified to work.")


def test_check_process_narration_smells_clean_text():
    text = "Convert PostScript files to PDF with a single call."
    assert checks.check_process_narration_smells(text) == []


_UPSTREAM_ISSUES_WITH_BLOCKING = """# Upstream issues

## Broken pip install

- **Severity**: BLOCKING (install/build/import fails for any user)
- **Evidence**: `pip install -e .`
- **Impact**: every user hits this
- **Not fixable here because**: upstream packaging bug
"""


def test_check_no_undisclosed_blocking_commands_flags_real_match():
    readme = "```bash\npip install -e .\n```\n"
    findings = checks.check_no_undisclosed_blocking_commands(readme, _UPSTREAM_ISSUES_WITH_BLOCKING)
    assert len(findings) == 1
    assert findings[0]["command"] == "pip install -e ."


def test_check_no_undisclosed_blocking_commands_clean_when_command_absent():
    readme = "```bash\npip install real-package\n```\n"
    findings = checks.check_no_undisclosed_blocking_commands(readme, _UPSTREAM_ISSUES_WITH_BLOCKING)
    assert findings == []


def test_check_no_undisclosed_blocking_commands_noop_with_no_upstream_issues():
    readme = "```bash\npip install -e .\n```\n"
    assert checks.check_no_undisclosed_blocking_commands(readme, "No upstream issues identified.") == []


def test_check_no_undisclosed_blocking_commands_not_desynced_by_mermaid_block():
    # Regression test for a real, significant production bug found via this module's own
    # test suite once a real diagram was added ahead of an Installation section (now true
    # of every README under the 2026-08-08 simplified model): with the fenced-code regex's
    # language tag optional, an untagged ```mermaid block's own closing fence was mistaken
    # for a fresh opening delimiter, desyncing every match after it -- the real ```bash
    # block was never found, silently disabling this hard gate for the entire portfolio.
    readme = (
        "## At a Glance\n\n```mermaid\nflowchart TD\n  A --> B\n```\n\n"
        "## Installation\n\n```bash\npip install -e .\n```\n"
    )
    findings = checks.check_no_undisclosed_blocking_commands(readme, _UPSTREAM_ISSUES_WITH_BLOCKING)
    assert len(findings) == 1
    assert findings[0]["command"] == "pip install -e ."


def test_check_no_undisclosed_blocking_commands_recognizes_cmake_blocks():
    # A second real gap found alongside the mermaid-desync bug: C++ products' real
    # Installation sections use ```cmake fenced blocks, never previously recognized.
    readme = "```cmake\npip install -e .\n```\n"
    findings = checks.check_no_undisclosed_blocking_commands(readme, _UPSTREAM_ISSUES_WITH_BLOCKING)
    assert len(findings) == 1


def test_check_dropped_content_flags_dropped_link_and_heading():
    old_readme = "See [AGENTS.md](AGENTS.md) for details.\n\n## TypeScript Version Support\n\nSupported.\n"
    new_readme = "## API reference\n\nNothing here.\n"
    result = checks.check_dropped_content(old_readme, new_readme, "irrelevant")
    assert "AGENTS.md" in result["dropped_links"]
    assert "TypeScript Version Support" in result["dropped_headings"]


def test_check_dropped_content_clean_when_carried_forward():
    old_readme = "See [AGENTS.md](AGENTS.md) for details.\n\n## TypeScript Version Support\n\nSupported.\n"
    new_readme = "## Documentation & resources\n\nSee [AGENTS.md](AGENTS.md).\n\n## TypeScript Version Support\n\nStill supported.\n"
    result = checks.check_dropped_content(old_readme, new_readme, "irrelevant")
    assert result == {"dropped_links": [], "dropped_headings": [], "internal_labels": []}


def test_check_dropped_content_flags_internal_label():
    # 2026-08-08 (Rule 7): forbidden internal/process labels, distinct from the
    # meaning-preservation half already covered by dropped_links/dropped_headings above.
    new_readme = "## Preserved repository details\n\nSome content carried forward.\n"
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert any("preserved repository details" in label.lower() for label in result["internal_labels"])


def test_check_dropped_content_heading_rename_not_flagged_after_emoji_titlecase_normalization():
    # Regression test: found live 2026-08-09 (MT030 Phase 1), independently by 3 of 5 pilot
    # agents (words/net, pdf/cpp, note/python) -- a raw literal substring match against the OLD
    # heading text (emoji + original casing intact) can never succeed once check_heading_title_
    # case forces every NEW heading to be emoji-free and title-cased. The real note/python case:
    # "✨ Features" -> "Key Capabilities", underlying content fully preserved, previously flagged
    # as a hard-gate drop forever regardless of any real content work.
    old_readme = "# Product\n\n## ✨ Features\n\nDoes many things.\n"
    new_readme = "## Key Capabilities\n\nFeatures cover the full surface -- does many things.\n"
    result = checks.check_dropped_content(old_readme, new_readme, "irrelevant")
    assert result["dropped_headings"] == []


def test_check_dropped_content_still_flags_a_genuinely_dropped_heading():
    # Regression guard: the emoji/casefold normalization must not become so lenient it stops
    # catching a real drop -- "Roadmap" genuinely appears nowhere in the new candidate.
    old_readme = "# Product\n\n## 🗺️ Roadmap\n\nFuture plans.\n"
    new_readme = "## Key Capabilities\n\nDoes many things.\n"
    result = checks.check_dropped_content(old_readme, new_readme, "irrelevant")
    assert "🗺️ Roadmap" in result["dropped_headings"]


def test_check_no_excluded_domain_links_flags_forum():
    text = "See the [forum](https://forum.aspose.com/c/barcode) for help."
    findings = checks.check_no_excluded_domain_links(text)
    assert len(findings) == 1
    assert "forum.aspose.com" in findings[0]


def test_check_no_excluded_domain_links_flags_aspose_app():
    text = "Try the [free converter](https://products.aspose.app/barcode/generator)."
    findings = checks.check_no_excluded_domain_links(text)
    assert len(findings) == 1


def test_check_no_excluded_domain_links_clean_on_docs_aspose_org():
    text = "See [docs](https://docs.aspose.org/barcode/python/)."
    assert checks.check_no_excluded_domain_links(text) == []


def test_check_named_member_accuracy_ignores_single_line_prose_bullet(tmp_path):
    # Regression test for the real false positive found during development: a flat,
    # single-line "`ClassName` -- prose mentioning `a_term()`" bullet (no indented
    # sub-bullets following it) must NOT be treated as a member-list claim.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "errors.py").write_text("class SymbologyNotFoundError(Exception):\n    pass\n", encoding="utf-8")
    readme = "- `SymbologyNotFoundError` — unknown symbology name passed to `generate()`\n"
    assert checks.check_named_member_accuracy(readme, str(tmp_path)) == []


def test_check_named_member_accuracy_catches_real_fabrication(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "message.py").write_text(
        "class MapiMessage:\n    def create(self):\n        pass\n    def save(self):\n        pass\n",
        encoding="utf-8",
    )
    readme = (
        "- `MapiMessage`\n"
        "  - `create() -> MapiMessage`\n"
        "  - `totally_fabricated_method()`\n"
    )
    findings = checks.check_named_member_accuracy(readme, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["member"] == "totally_fabricated_method()"


def test_check_named_member_accuracy_clean_when_all_members_real(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "message.py").write_text(
        "class MapiMessage:\n    def create(self):\n        pass\n    def save(self):\n        pass\n",
        encoding="utf-8",
    )
    readme = "- `MapiMessage`\n  - `create() -> MapiMessage`\n  - `save()`\n"
    assert checks.check_named_member_accuracy(readme, str(tmp_path)) == []


def test_check_named_member_accuracy_skips_class_with_no_candidate_files(tmp_path):
    readme = "- `NeverDeclaredClass`\n  - `some_method()`\n"
    assert checks.check_named_member_accuracy(readme, str(tmp_path)) == []


# check_api_reference_intro_names_classes was retired 2026-08-09 (MT027), absorbed into
# check_api_reference_classes_exist_in_reference_site -- ported below, same intent, called with
# reference_class_names=None so only the (unchanged-logic) bad-pattern half runs.


def test_check_api_reference_classes_flags_type_count_filler():
    text = '## API reference\n\nThe library ships 193 public types. Selected entry points:\n\n<details>\n'
    findings = checks.check_api_reference_classes_exist_in_reference_site(text, None)
    assert any("bare type-count filler" in f["reason"] for f in findings)


def test_check_api_reference_classes_flags_bare_wildcard():
    text = "## API reference\n\nThe supported public entry point is `aspose.email_foss.msg.*`.\n\n<details>\n"
    findings = checks.check_api_reference_classes_exist_in_reference_site(text, None)
    assert any("bare namespace/package wildcard" in f["reason"] for f in findings)


def test_check_api_reference_classes_passes_real_hub_class():
    text = "## API reference\n\nThe primary entry point is `Workbook`, which owns a `WorksheetCollection`.\n\n<details>\n"
    assert checks.check_api_reference_classes_exist_in_reference_site(text, None) == []


def test_check_api_reference_classes_matches_title_cased_heading():
    # Same regression class as check_examples_table_collapsed/check_section_job_distinctness:
    # this section matcher was hardcoded to lowercase "## API reference".
    text = "## API Reference\n\nThe library ships 193 public types. Selected entry points:\n\n<details>\n"
    findings = checks.check_api_reference_classes_exist_in_reference_site(text, None)
    assert any("bare type-count filler" in f["reason"] for f in findings)


_MECHANISM_DUPLICATE_DIAGRAM = _wrap(
    """flowchart LR
  PRODUCT["P"]
  subgraph Capabilities["Core"]
    C1["Worksheet management"]
    C2["Cell values"]
  end
  subgraph Outputs["Outputs"]
    O1[".xlsx workbook (path)"]
    O2[".xlsx workbook (binary stream)"]
  end
  PRODUCT --- C1
  PRODUCT --- C2
  C1 --- O1
  C1 --- O2
  C2 --- O1"""
)


def test_check_diagram_no_mechanism_duplicate_output_flags_real_incident_shape():
    findings = checks.check_diagram_no_mechanism_duplicate_output(_MECHANISM_DUPLICATE_DIAGRAM)
    assert len(findings) == 1
    assert {findings[0]["node_a"], findings[0]["node_b"]} == {"O1", "O2"}


def test_check_diagram_no_mechanism_duplicate_output_clean_on_simplified_diagram():
    # The simplified model's single Outputs container rarely has mechanism-duplicate
    # pairs left (no per-capability wiring to compare), but the function itself is
    # unchanged and must still run cleanly against a real simplified fixture.
    assert checks.check_diagram_no_mechanism_duplicate_output(TRANSFORM_CELLS_CPP) == []


def test_check_diagram_no_mechanism_duplicate_output_ignores_generic_shared_noun():
    # Regression test for a real false positive found during development: ".msg files" and
    # ".eml files" share only the generic word "files" (and naive substring matching found
    # "file" inside "files", falsely tripping the mechanism-keyword check too) -- these are
    # genuinely different content (different formats), not a delivery-mechanism duplicate.
    text = _wrap(
        """flowchart LR
  PRODUCT["P"]
  subgraph Capabilities["Core"]
    C1["MSG writing"]
    C2["EML writing"]
  end
  subgraph Outputs["Outputs"]
    O1[".msg files"]
    O2[".eml files"]
  end
  PRODUCT --- C1
  PRODUCT --- C2
  C1 --- O1
  C2 --- O2"""
    )
    assert checks.check_diagram_no_mechanism_duplicate_output(text) == []


def test_check_named_member_accuracy_ignores_forward_declarations(tmp_path):
    # Regression test for a real false positive found during development: a C++ forward
    # declaration ("class Worksheet;", common in headers that reference a type by pointer/
    # reference) matched the same naive "class ClassName" search as the real definition, and
    # since forward-declaring files can sort before the real definition file, they starved out
    # the real file within max_files -- producing false "member not found" findings for members
    # that are genuinely declared, just in a file the search never reached.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    # Alphabetically-earlier files that only forward-declare the class (as real C++ headers do).
    for name in ("aaa_cell.h", "bbb_cells.h", "ccc_column.h", "ddd_row.h"):
        (src_dir / name).write_text("class Worksheet;\n", encoding="utf-8")
    # The real definition, alphabetically last, must still be found and searched.
    (src_dir / "zzz_worksheet.h").write_text(
        "class Worksheet final {\npublic:\n    void SetName(std::string_view value);\n};\n",
        encoding="utf-8",
    )
    readme = "- `Worksheet`\n  - `SetName(value)`\n"
    assert checks.check_named_member_accuracy(readme, str(tmp_path)) == []


# --- Eleventh incident / MT025 (2026-08-08): Starting-Points presence + Outputs/Starting
# Points format purity ------------------------------------------------------------------------
#
# Ground-truth violation fixtures below are captured VERBATIM from real candidate READMEs
# read during the forensic investigation (html/python, tex/python, 3d/net, note/python) --
# not synthesized -- so these tests double as proof the new gates fail closed on the exact
# real content that motivated them, per the plan's "prove the check against real content
# before trusting it" discipline.

_KNOWN_FORMATS = {
    "PDF", "XLSX", "DVI", "SVG", "OBJ", "STL", "GLTF", "GLB", "FBX", "COLLADA", "3MF", "HTML",
}

# Real html/python Outputs (2026-08-08 candidate): 4 of 5 nodes are non-format capability-
# return descriptions ("Traversable DOM document tree", "CSS rules and stylesheet objects",
# "Resolved computed style values", "Parsed URLs and decoded text"); only the serialized-HTML
# node is a genuine format claim.
HTML_PYTHON_OUTPUTS_VIOLATION = _wrap(
    """flowchart TD
  PRODUCT["Aspose.HTML FOSS for Python"]
  subgraph Capabilities["Core Capabilities"]
    c1["WHATWG HTML tokenizing and tree construction"]
  end
  subgraph Outputs["Outputs"]
    o1["Traversable DOM document tree"]
    o2["CSS rules and stylesheet objects"]
    o3["Resolved computed style values"]
    o4["Serialized HTML strings"]
    o5["Parsed URLs and decoded text"]
  end
  PRODUCT --> Capabilities --> Outputs"""
)

# Real tex/python Outputs: 3 genuine formats plus one non-format node ("Font and glyph
# metrics") describing structured data, not a deliverable format.
TEX_PYTHON_OUTPUTS_VIOLATION = _wrap(
    """flowchart TD
  PRODUCT["Aspose.TeX FOSS for Python"]
  subgraph Capabilities["Core Capabilities"]
    c1["TeX/LaTeX markup interpretation and typesetting"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF documents"]
    o2["DVI files"]
    o3["SVG 1.1 documents (single- or multi-page)"]
    o4["Font and glyph metrics (widths, kerning, ligatures)"]
  end
  PRODUCT --> Capabilities --> Outputs"""
)

# Real 3d/net Outputs: 2 genuine format-group nodes plus 2 non-format nodes ("Round-tripped
# scene graphs", "Extracted watermark text").
THREE_D_NET_OUTPUTS_VIOLATION = _wrap(
    """flowchart TD
  PRODUCT["Aspose.3D FOSS for .NET"]
  subgraph Capabilities["Core Capabilities"]
    c1["Multi-format load and save"]
  end
  subgraph Outputs["Outputs"]
    o1["OBJ, STL, and glTF/GLB files"]
    o2["FBX, COLLADA, and 3MF files"]
    o3["Round-tripped scene graphs"]
    o4["Extracted watermark text"]
  end
  PRODUCT --> Capabilities --> Outputs"""
)

# Real note/python Outputs: 4 of 5 nodes are "Extracted ..." descriptions of structured data,
# not formats; only the PDF-export node is a genuine format claim.
NOTE_PYTHON_OUTPUTS_VIOLATION = _wrap(
    """flowchart TD
  PRODUCT["Aspose.Note FOSS for Python"]
  subgraph Capabilities["Core Capabilities"]
    c1["Read .one documents"]
  end
  subgraph Outputs["Outputs"]
    o1["Extracted pages, outlines, and metadata"]
    o2["Extracted rich text and formatting"]
    o3["Extracted images and attached files"]
    o4["Extracted tables, tags, and numbered lists"]
    o5["PDF documents"]
  end
  PRODUCT --> Capabilities --> Outputs"""
)

# A corrected, post-fix transform-archetype diagram: real Starting Points container added,
# both containers format-pure. Used as the "target state passes cleanly" regression anchor.
TRANSFORM_CELLS_CPP_WITH_STARTING_POINTS = _wrap(
    """flowchart TD
  subgraph StartingPoints["Starting Points"]
    I1["An existing .xlsx workbook"]
  end
  PRODUCT["Aspose.Cells FOSS for C++"]
  subgraph Capabilities["Core Capabilities"]
    C1["Workbook and worksheet management"]
    C2["Cell values and formulas"]
  end
  subgraph Outputs["Outputs"]
    O1[".xlsx workbook (file path or binary stream)"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs"""
)

# A generative-archetype diagram (barcode/python shape): correctly has NO Starting Points
# container at all.
GENERATIVE_BARCODE_PYTHON = _wrap(
    """flowchart TD
  PRODUCT["Aspose.BarCode FOSS for Python"]
  subgraph Capabilities["Core Capabilities"]
    C1["Generate Code 128 barcodes"]
  end
  subgraph Outputs["Outputs"]
    O1["SVG strings"]
    O2["PNG bytes"]
  end
  PRODUCT --> Capabilities --> Outputs"""
)

# The same generative shape, WRONGLY given a Starting Points container -- regression guard.
GENERATIVE_BARCODE_PYTHON_WITH_WRONG_STARTING_POINTS = _wrap(
    """flowchart TD
  subgraph StartingPoints["Starting Points"]
    I1["An existing barcode image"]
  end
  PRODUCT["Aspose.BarCode FOSS for Python"]
  subgraph Capabilities["Core Capabilities"]
    C1["Generate Code 128 barcodes"]
  end
  subgraph Outputs["Outputs"]
    O1["SVG strings"]
    O2["PNG bytes"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs"""
)


# --- check_diagram_starting_points_presence ----------------------------------------------------


def test_starting_points_presence_flags_missing_container_for_transform():
    # This is literally today's real portfolio state for ~27 of 30 products -- proof the old
    # silently-passing behavior is now correctly rejected.
    findings = checks.check_diagram_starting_points_presence(TRANSFORM_CELLS_CPP, "transform")
    assert findings and "requires a Starting Points container" in findings[0]["reason"]


def test_starting_points_presence_flags_missing_container_for_compile():
    findings = checks.check_diagram_starting_points_presence(TRANSFORM_CELLS_CPP, "compile")
    assert findings and "requires a Starting Points container" in findings[0]["reason"]


def test_starting_points_presence_passes_transform_with_container():
    assert checks.check_diagram_starting_points_presence(
        TRANSFORM_CELLS_CPP_WITH_STARTING_POINTS, "transform"
    ) == []


def test_starting_points_presence_passes_generative_with_no_container():
    assert checks.check_diagram_starting_points_presence(
        GENERATIVE_BARCODE_PYTHON, "generative"
    ) == []


def test_starting_points_presence_flags_generative_with_wrong_container():
    findings = checks.check_diagram_starting_points_presence(
        GENERATIVE_BARCODE_PYTHON_WITH_WRONG_STARTING_POINTS, "generative"
    )
    assert findings and "must have NO Starting Points container" in findings[0]["reason"]


def test_starting_points_presence_passes_hybrid_with_exactly_two_nodes():
    assert checks.check_diagram_starting_points_presence(HYBRID_PDF_CPP, "hybrid") == []


def test_starting_points_presence_flags_hybrid_with_wrong_node_count():
    findings = checks.check_diagram_starting_points_presence(
        TRANSFORM_CELLS_CPP_WITH_STARTING_POINTS, "hybrid"
    )
    assert findings and "exactly 2 Starting Points nodes" in findings[0]["reason"]


# --- check_diagram_container_format_purity -------------------------------------------------


def test_container_format_purity_flags_html_python_real_violations():
    findings = checks.check_diagram_container_format_purity(
        HTML_PYTHON_OUTPUTS_VIOLATION, "outputs", _KNOWN_FORMATS
    )
    flagged_ids = {f["node_id"] for f in findings}
    assert flagged_ids == {"o1", "o2", "o3", "o5"}, flagged_ids
    # The one genuine format node (serialized HTML strings) must NOT be flagged.
    assert "o4" not in flagged_ids


def test_container_format_purity_flags_tex_python_real_violation():
    findings = checks.check_diagram_container_format_purity(
        TEX_PYTHON_OUTPUTS_VIOLATION, "outputs", _KNOWN_FORMATS
    )
    flagged_ids = {f["node_id"] for f in findings}
    assert flagged_ids == {"o4"}, flagged_ids
    assert "metrics" in findings[0]["unrecognized_tokens"]


def test_container_format_purity_flags_3d_net_real_violations():
    findings = checks.check_diagram_container_format_purity(
        THREE_D_NET_OUTPUTS_VIOLATION, "outputs", _KNOWN_FORMATS
    )
    flagged_ids = {f["node_id"] for f in findings}
    assert flagged_ids == {"o3", "o4"}, flagged_ids
    # o1/o2 (real, grouped format lists) must not be flagged.
    assert "o1" not in flagged_ids and "o2" not in flagged_ids


def test_container_format_purity_flags_note_python_real_violations():
    findings = checks.check_diagram_container_format_purity(
        NOTE_PYTHON_OUTPUTS_VIOLATION, "outputs", _KNOWN_FORMATS
    )
    flagged_ids = {f["node_id"] for f in findings}
    assert flagged_ids == {"o1", "o2", "o3", "o4"}, flagged_ids
    assert "o5" not in flagged_ids


def test_container_format_purity_clean_on_fixed_transform_fixture():
    assert checks.check_diagram_container_format_purity(
        TRANSFORM_CELLS_CPP_WITH_STARTING_POINTS, "starting_points", _KNOWN_FORMATS
    ) == []
    assert checks.check_diagram_container_format_purity(
        TRANSFORM_CELLS_CPP_WITH_STARTING_POINTS, "outputs", _KNOWN_FORMATS
    ) == []


def test_container_format_purity_clean_on_existing_hybrid_fixture():
    # Regression guard: the already-correct, already-approved hybrid shape (including its
    # fixed "Nothing -- authored from scratch" literal) must not be disturbed by this new gate.
    assert checks.check_diagram_container_format_purity(
        HYBRID_PDF_CPP, "starting_points", {"PDF"}
    ) == []


def test_container_format_purity_does_not_check_parenthetical_qualifiers():
    # "(save or incremental update)" contains words that are neither formats nor in the
    # connector allowlist -- must not be flagged, since only the core (pre-parenthesis) text
    # is checked.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Save"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF documents (save or incremental update)"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    assert checks.check_diagram_container_format_purity(text, "outputs", {"PDF"}) == []


# --- check_diagram_format_completeness_hint --------------------------------------------------


def test_format_completeness_hint_flags_unmentioned_exported_format():
    formats_md = (
        "# Format Support\n\n"
        "| Format | Import | Export |\n"
        "|--------|--------|--------|\n"
        "| PDF | Yes | Yes |\n"
        "| DOCX | - | Yes |\n"
    )
    text = _wrap(
        """flowchart TD
  subgraph StartingPoints["Starting Points"]
    I1["An existing PDF document"]
  end
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Convert"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF documents"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_format_completeness_hint(text, formats_md, "transform")
    assert any(f["format"] == "DOCX" and f["container"] == "outputs" for f in findings)


def test_format_completeness_hint_clean_when_all_formats_mentioned():
    formats_md = (
        "# Format Support\n\n"
        "| Format | Import | Export |\n"
        "|--------|--------|--------|\n"
        "| PDF | Yes | Yes |\n"
    )
    text = _wrap(
        """flowchart TD
  subgraph StartingPoints["Starting Points"]
    I1["An existing PDF document"]
  end
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Convert"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF documents"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs"""
    )
    assert checks.check_diagram_format_completeness_hint(text, formats_md, "transform") == []


def test_format_completeness_hint_ignores_import_gap_for_generative():
    # A generative product has no format-based Starting Points by design -- an Import=Yes row
    # must never be flagged against it.
    formats_md = (
        "# Format Support\n\n"
        "| Format | Import | Export |\n"
        "|--------|--------|--------|\n"
        "| PDF | Yes | Yes |\n"
    )
    findings = checks.check_diagram_format_completeness_hint(
        GENERATIVE_BARCODE_PYTHON, formats_md, "generative"
    )
    assert not any(f["container"] == "starting_points" for f in findings)


# --- check_banner_present (2026-08-09, MT026) -------------------------------------------------


def _readme_with_badge_and_banner(family, platform, *, badge=True, banner_line=None):
    parts = ["# Test Product", ""]
    if badge:
        parts += ["[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)", ""]
    if banner_line is None:
        banner_line = (
            f"![Test Product](https://products.aspose.org/media/{family}/{platform}/"
            "banner-readme.png)"
        )
    parts += [banner_line, "", "Some intro text."]
    return "\n".join(parts)


def test_banner_present_passes_correct_banner():
    text = _readme_with_badge_and_banner("cells", "cpp")
    assert checks.check_banner_present(text, "cells", "cpp") == []


def test_banner_present_flags_missing_badge_row():
    text = "# Test Product\n\n![Test Product](https://products.aspose.org/media/cells/cpp/banner-readme.png)\n\nIntro."
    findings = checks.check_banner_present(text, "cells", "cpp")
    assert findings and "no badge row" in findings[0]["reason"]


def test_banner_present_flags_missing_banner_line():
    text = "# Test Product\n\n[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n\nIntro text with no banner."
    findings = checks.check_banner_present(text, "cells", "cpp")
    assert findings and "expected a banner image line" in findings[0]["reason"]


def test_banner_present_flags_cross_product_contamination():
    # Regression-shaped test: this repo has already seen real cross-product content
    # contamination twice; a banner copy-pasted from a different product must be caught.
    text = _readme_with_badge_and_banner("email", "net")
    findings = checks.check_banner_present(text, "cells", "cpp")
    assert findings and "does not match this product" in findings[0]["reason"]


def test_banner_present_flags_empty_alt_text():
    text = _readme_with_badge_and_banner(
        "cells", "cpp",
        banner_line="![](https://products.aspose.org/media/cells/cpp/banner-readme.png)",
    )
    findings = checks.check_banner_present(text, "cells", "cpp")
    assert findings and "empty alt text" in findings[0]["reason"]


def test_banner_present_flags_wrong_position():
    # Banner placed after the intro paragraph instead of directly after the badge row.
    text = (
        "# Test Product\n\n"
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n\n"
        "Some intro text.\n\n"
        "![Test Product](https://products.aspose.org/media/cells/cpp/banner-readme.png)\n"
    )
    findings = checks.check_banner_present(text, "cells", "cpp")
    assert findings and "expected a banner image line" in findings[0]["reason"]


def _linked_banner_line(family, platform, homepage="https://products.aspose.org/cells/cpp/"):
    return (
        f"[![Test Product](https://products.aspose.org/media/{family}/{platform}/"
        f"banner-readme.png)]({homepage})"
    )


def test_banner_present_passes_linked_banner():
    # TC-HARDEN-27: check_banner_present must tolerate the click-through-wrapped form -- it only
    # cares about the image itself, not whether/how it's linked (check_banner_links_to_homepage's
    # own job, below).
    text = _readme_with_badge_and_banner("cells", "cpp", banner_line=_linked_banner_line("cells", "cpp"))
    assert checks.check_banner_present(text, "cells", "cpp") == []


def test_banner_present_flags_cross_product_contamination_in_linked_form():
    text = _readme_with_badge_and_banner(
        "cells", "cpp", banner_line=_linked_banner_line("email", "net"),
    )
    findings = checks.check_banner_present(text, "cells", "cpp")
    assert findings and "does not match this product" in findings[0]["reason"]


# --- check_banner_links_to_homepage (TC-HARDEN-27, MT034 Twenty-First incident) ----------------


def test_banner_links_to_homepage_passes_when_verified_and_linked_correctly():
    homepage = {"url": "https://products.aspose.org/cells/cpp/", "verified": True}
    text = _readme_with_badge_and_banner("cells", "cpp", banner_line=_linked_banner_line("cells", "cpp"))
    assert checks.check_banner_links_to_homepage(text, homepage) == []


def test_banner_links_to_homepage_passes_when_unverified_and_unlinked():
    homepage = {"url": "https://products.aspose.org/cells/cpp/", "verified": False}
    text = _readme_with_badge_and_banner("cells", "cpp")  # default banner_line is the bare form
    assert checks.check_banner_links_to_homepage(text, homepage) == []


def test_banner_links_to_homepage_flags_verified_but_unlinked():
    homepage = {"url": "https://products.aspose.org/cells/cpp/", "verified": True}
    text = _readme_with_badge_and_banner("cells", "cpp")  # bare, unlinked form
    findings = checks.check_banner_links_to_homepage(text, homepage)
    assert findings and "not linked to it" in findings[0]["reason"]


def test_banner_links_to_homepage_flags_unverified_but_linked():
    # Must never invent/keep a link to a homepage page that has no confirmed local content --
    # matches this module's "never invent a URL not backed by verified data" rule.
    homepage = {"url": "https://products.aspose.org/cells/cpp/", "verified": False}
    text = _readme_with_badge_and_banner("cells", "cpp", banner_line=_linked_banner_line("cells", "cpp"))
    findings = checks.check_banner_links_to_homepage(text, homepage)
    assert findings and "no verified local" in findings[0]["reason"]


def test_banner_links_to_homepage_flags_wrong_target():
    homepage = {"url": "https://products.aspose.org/cells/cpp/", "verified": True}
    text = _readme_with_badge_and_banner(
        "cells", "cpp",
        banner_line=_linked_banner_line("cells", "cpp", homepage="https://products.aspose.org/cells/net/"),
    )
    findings = checks.check_banner_links_to_homepage(text, homepage)
    assert findings and "does not match the one" in findings[0]["reason"]


def test_banner_links_to_homepage_no_banner_line_is_vacuous():
    # A malformed/missing banner line is check_banner_present's own finding -- this check must
    # not duplicate it.
    text = "# Test Product\n\nNo badge row or banner here.\n"
    assert checks.check_banner_links_to_homepage(text, {"url": "x", "verified": True}) == []


# --- MT027 (2026-08-09): ground API Reference in reference.aspose.org's own graded content ----

# Real content shape, captured from a direct read of content/reference.aspose.org/en/tex/python/
# _index.md and TeXJob.md (frontmatter trimmed to the essentials needed to exercise
# _strip_frontmatter; body content reproduced close to verbatim, including the real confirmed
# leaked-docstring defect in the TeXOptions row).
_REAL_TEX_PYTHON_INDEX_MD = """---
linkTitle: Python
title: Aspose.TeX FOSS for Python
grade: A
evidence:
  claims: []
  apis: []
---

API reference for **Aspose.Tex FOSS for Python** v26.5. 11 public types organized by module.

## Core API

| Class | Description |
|---|---|
| `AsposeTeXError` | Base exception for all aspose_tex errors. |
| `EngineError` | Raised for TeX engine errors. |

---

## Presentation

| Class | Description |
|---|---|
| `DviDevice` | DVI output device -- wraps ``DviWriter``. |
| `TeXJob` | Main entry point for processing TeX input. |
| `TeXOptions` | r\"\"\"Configuration for a TeX processing job. |

### Enumerations

| Enumeration | Description |
|---|---|
| `OutputFormat` | Supported output formats. |

---

## See Also

- [Aspose.Tex -- Enterprise API Reference](https://reference.aspose.com/tex/)
"""

_REAL_TEXJOB_CLASS_PAGE_MD = """---
linkTitle: TeXJob
title: TeXJob
grade: A
evidence:
  apis:
  - TeXJob
  - TeXJob.__init__
  - TeXJob.messages
  - TeXJob.run
---

## Overview

`TeXJob` is a class in Aspose.Tex FOSS for Python.

## Properties

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `messages` | `list[str]` | Read | Gets the messages. |

## Methods

| Signature | Description |
|-----------|-------------|
| `__init__(source: InputSource, device: OutputDevice, options: TeXOptions \\| None)` |  |
| `run()` → `bytes \\| None` |  |

## See Also

- [Aspose.TeX for Python -- Enterprise API Reference](https://reference.aspose.com/tex/python-net/)
"""


def test_parse_reference_api_index_real_tex_python_shape():
    index = checks.parse_reference_api_index(_REAL_TEX_PYTHON_INDEX_MD)
    # "See Also" is a real ## header too (a bullet list, not a class table) -- it correctly ends
    # up as an empty-list module rather than being special-cased out, since it pollutes nothing.
    assert index.get("See Also") == []
    core_classes = {row["class"] for row in index["Core API"]}
    assert core_classes == {"AsposeTeXError", "EngineError"}
    presentation_classes = {row["class"] for row in index["Presentation"]}
    # Enumerations sub-table folds into the same parent module.
    assert presentation_classes == {"DviDevice", "TeXJob", "TeXOptions", "OutputFormat"}
    # Internal-only frontmatter (grade/evidence) must never leak into the parsed result.
    assert "grade" not in str(index) and "evidence" not in str(index)


def test_parse_reference_api_index_empty_on_blank_input():
    assert checks.parse_reference_api_index("") == {}
    assert checks.parse_reference_api_index(None) == {}


# Real, captured-verbatim excerpt from content/reference.aspose.org/en/3d/typescript/_index.md
# (2026-08-11) -- the class-heading-per-entry convention that made this file the one product in
# the whole portfolio whose real modules parsed to zero classes under the table-only parser (a
# full 30-product scan confirmed no other product has this shape). Exercises: a module with real
# intro prose before its first class heading ("OBJ Format"), a plain-text heading, a linked
# heading, a multi-class comma-joined heading followed by a paragraph-then-bullet-list (only the
# first paragraph must be captured), and the vacuous "See Also" bullet-list module.
_REAL_3D_TYPESCRIPT_INDEX_MD = """---
grade: A
evidence: internal-only, never leaked
---

## Core Scene Graph

### Scene

The root container for a 3D scene. Call `scene.open()` or `scene.openFromBuffer()` to load a file, and `scene.save()` to write output. Exposes `scene.rootNode` as the entry point to the node hierarchy.

### [A3DObject](A3DObject/)

Root base class for Aspose.3D objects. Provides the property system (`getProperty`, `setProperty`) and the `name` field shared across the class hierarchy.

---

## Materials

### [Material, LambertMaterial, PhongMaterial, PbrMaterial](/3d/typescript/material/)

Material is the abstract base class for all material types. Three concrete implementations are available:

- **LambertMaterial** -- diffuse-only with ambient, diffuse, and emissive color channels. Suitable for non-specular surfaces.
- **PhongMaterial** -- extends `LambertMaterial` with specular color and shininess properties for Phong shading.
- **PbrMaterial** -- physically-based rendering material with metallic, roughness, base-color, and normal-map channels.

---

## OBJ Format

OBJ supports both import and export. When saving as OBJ, the material library (`.mtl`) is written automatically alongside the `.obj` file.

### ObjImporter

Internal importer that reads Wavefront OBJ files, resolves `.mtl` material libraries, and populates a `Scene`.

---

## See Also

- [Knowledge Base: How-To Guides](https://kb.aspose.org/3d/typescript/)
- [Detailed API Overview](/3d/typescript/)
"""


def test_parse_reference_api_index_class_heading_fallback_real_3d_typescript_shape():
    index = checks.parse_reference_api_index(_REAL_3D_TYPESCRIPT_INDEX_MD)
    # Plain-text and linked headings both resolve to the bare class name.
    core = {row["class"]: row["description"] for row in index["Core Scene Graph"]}
    assert set(core) == {"Scene", "A3DObject"}
    assert core["Scene"].startswith("The root container for a 3D scene.")
    assert core["A3DObject"].startswith("Root base class for Aspose.3D objects.")
    # A multi-class, comma-joined heading yields one entry per class, all sharing the same
    # description -- and only the first paragraph is captured, not the following bullet list.
    materials = {row["class"]: row["description"] for row in index["Materials"]}
    assert set(materials) == {"Material", "LambertMaterial", "PhongMaterial", "PbrMaterial"}
    shared_desc = materials["Material"]
    assert shared_desc == materials["LambertMaterial"] == materials["PhongMaterial"] \
        == materials["PbrMaterial"]
    assert shared_desc == (
        "Material is the abstract base class for all material types. Three concrete "
        "implementations are available:"
    )
    assert "LambertMaterial ---" not in shared_desc and "diffuse-only" not in shared_desc
    # A module's own intro prose before its first class heading is not itself parsed as a class.
    obj_classes = {row["class"] for row in index["OBJ Format"]}
    assert obj_classes == {"ObjImporter"}
    assert "OBJ supports both import and export" not in str(index["OBJ Format"])
    # A real bullet-list-only module (no ### headings at all) stays vacuous, same as a table
    # module with zero rows -- never misread as containing a class named after a bullet link.
    assert index["See Also"] == []


def test_parse_reference_api_index_table_convention_unaffected_by_class_heading_fallback():
    # Regression guard: the fallback must never fire for a module that already has real table
    # rows -- confirmed via the existing tex/python fixture, which is untouched by this change.
    index = checks.parse_reference_api_index(_REAL_TEX_PYTHON_INDEX_MD)
    assert {row["class"] for row in index["Core API"]} == {"AsposeTeXError", "EngineError"}


def test_parse_reference_class_page_real_texjob_shape():
    parsed = checks.parse_reference_class_page(_REAL_TEXJOB_CLASS_PAGE_MD)
    assert parsed["properties"] == ["messages"]
    assert parsed["methods"] == ["__init__", "run"]


def test_parse_reference_class_page_empty_on_blank_input():
    assert checks.parse_reference_class_page("") == {"properties": [], "methods": []}


def test_api_reference_classes_exist_clean_when_all_cited_classes_are_real():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section=(
            "## API Reference\n\n"
            "The primary entry point is `TeXJob`.\n\n"
            "- `TeXJob`\n  - `run()`\n"
        ),
    )
    reference_names = {"TeXJob", "TeXOptions", "AsposeTeXError"}
    assert checks.check_api_reference_classes_exist_in_reference_site(text, reference_names) == []


def test_api_reference_classes_exist_ignores_method_call_in_intro_sentence():
    # Regression test: found live during MT027's own Phase 1 pilot sanity pass -- pdf/cpp's
    # real intro sentence "...and its `Pages()` collection" was false-positived as citing a
    # fabricated class "Pages", because the method-call parens were stripped before the
    # PascalCase check. A backtick token WITH invocation parens is a method reference, not a
    # class-name candidate, even when PascalCase.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section=(
            "## API Reference\n\n"
            "The core API is built around the `Document` class and its `Pages()` collection.\n\n"
            "- `Document`\n  - `Pages() -> PageCollection`\n"
        ),
    )
    reference_names = {"Document"}
    findings = checks.check_api_reference_classes_exist_in_reference_site(text, reference_names)
    assert not any(f.get("class_name") == "Pages" for f in findings)


def test_api_reference_classes_exist_ignores_property_and_exception_mentions_in_prose():
    # Regression test: found live during MT027's full-portfolio sanity pass -- pdf/net's real
    # intro sentence "...exposing `Pages` (a `PageCollection` of `Page` objects)" cites Pages as
    # a PROPERTY, not a class (no invocation parens to distinguish it, unlike a method call);
    # 3d/python's real blockquote "...raise `AttributeError` (for saving)" cites a built-in
    # exception in a caveat, not a product class. Both are prose, not the structured `` -
    # `ClassName` `` bullet convention -- intro/body prose is no longer scanned at all for class
    # citations (root fix, not a narrower exclusion rule).
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section=(
            "## API Reference\n\n"
            "`Document` is the central entry point, exposing `Pages` (a `PageCollection` of "
            "`Page` objects), and raises `AttributeError` in some cases.\n\n"
            "- `Document`\n  - `save()`\n"
        ),
    )
    reference_names = {"Document"}
    findings = checks.check_api_reference_classes_exist_in_reference_site(text, reference_names)
    assert findings == []


def test_api_reference_classes_exist_tolerates_fully_qualified_citation():
    # Regression test: note/python's real bullets cite classes with a fully-qualified module
    # path ("aspose.note.saving.PdfSaveOptions"), but reference.aspose.org's own class index
    # always uses bare names -- the bare last dot-segment must be tried too.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section=(
            "## API Reference\n\n- `aspose.note.saving.PdfSaveOptions`\n  - `format()`\n"
        ),
    )
    reference_names = {"PdfSaveOptions"}
    assert checks.check_api_reference_classes_exist_in_reference_site(text, reference_names) == []


def test_api_reference_classes_exist_skips_package_grouping_bullet():
    # Regression test: pdf/java's real bullet "- `org.aspose.pdf.drawing` -- `Line`,
    # `Rectangle`, ..." groups several real classes under a PACKAGE name, not a single class --
    # the last dot-segment ("drawing") is lowercase, not PascalCase, so this isn't a real
    # single-class citation at all and must not be checked as one.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section=(
            "## API Reference\n\n- `org.aspose.pdf.drawing` -- `Line`, `Rectangle`, `Circle`\n"
        ),
    )
    assert checks.check_api_reference_classes_exist_in_reference_site(text, set()) == []


# --- Thirteenth incident / MT028 (2026-08-09): API Reference PRESENTATION table -----------
# MT027 grounded verification in reference.aspose.org's content but never adapted the section's
# presentation to match it -- direct user review of 3d/java found the section unchanged. Per the
# user's own chosen design (AskUserQuestion, this session): a module-grouped table mirroring
# _index.md's own organization is inserted above a new "#### Detailed Member Reference" marker;
# everything below that marker (today's curated bullet detail) is completely untouched.

_API_TABLE_REFERENCE_INDEX = {
    "Core API": [
        {"class": "Scene", "description": "The root scene graph container."},
        {"class": "Node", "description": "A scene-graph node."},
        {"class": "IExporter", "description": "Returns true when the exporter can export."},
    ],
}


def _api_table_section(*, core_rows=None, interfaces_rows=None, detailed_after=True):
    core_rows = core_rows if core_rows is not None else [
        "| `Scene` | The root scene graph container. |",
        "| `Node` | A scene-graph node. |",
    ]
    interfaces_rows = interfaces_rows if interfaces_rows is not None else [
        "| `IExporter` | Returns true when the exporter can export. |",
    ]
    body = (
        "## API Reference\n\n"
        "The primary entry point is `Scene`, which owns a hierarchy of `Node` objects.\n\n"
        "<details>\n<summary>View the Full API Surface</summary>\n\n"
        "### Core API\n\n"
        "| Class | Description |\n|---|---|\n" + "\n".join(core_rows) + "\n\n"
        "#### Interfaces\n\n"
        "| Interface | Description |\n|---|---|\n" + "\n".join(interfaces_rows) + "\n\n"
        "---\n\n"
    )
    if detailed_after:
        body += (
            "#### Detailed Member Reference\n\n"
            "### Scene Graph\n\n"
            "- `Scene`\n  - `fromFile(path) -> Scene`\n"
            "</details>\n"
        )
    return body


def test_api_reference_table_completeness_clean_when_table_matches_reference_index():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_api_reference_table_completeness(text, _API_TABLE_REFERENCE_INDEX) == []


def test_api_reference_table_completeness_flags_missing_class():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=["| `Scene` | The root scene graph container. |"]),
    )
    findings = checks.check_api_reference_table_completeness(text, _API_TABLE_REFERENCE_INDEX)
    assert {"module": "Core API", "class_name": "Node", "reason": "missing_class",
            "detail": "'Node' is a real class in reference.aspose.org's 'Core API' module "
                      "but is absent from the README's table for that module"} in findings


def test_api_reference_table_completeness_flags_missing_module():
    reference_index = dict(_API_TABLE_REFERENCE_INDEX, Annotations=[
        {"class": "PdfAnnotation", "description": "An annotation on a page."},
    ])
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    findings = checks.check_api_reference_table_completeness(text, reference_index)
    assert any(f["reason"] == "missing_module" and f["module"] == "Annotations" for f in findings)


def test_api_reference_table_completeness_matches_module_names_case_insensitively():
    # 2026-08-11: a real reference.aspose.org module name can need a different heading-safe
    # casing in the README's own ### heading (e.g. "glTF Format" -> "GLTF Format", per
    # check_heading_title_case's own established GLTF exception) without that legitimate
    # re-casing being flagged as a missing/unrecognized module -- found live on 3d/typescript,
    # whose real "glTF Format" module is the first case where this tension actually fired.
    reference_index = {
        "glTF Format": [
            {"class": "GltfImporter", "description": "Reads glTF 2.0 files."},
        ],
    }
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(
            core_rows=["| `GltfImporter` | Reads glTF 2.0 files. |"],
            interfaces_rows=[],
        ).replace("### Core API", "### GLTF Format"),
    )
    assert checks.check_api_reference_table_completeness(text, reference_index) == []


def test_api_reference_table_completeness_flags_unrecognized_class():
    # Fabrication-guard direction: a class in the README's table that isn't real per
    # reference_index -- structurally unlikely (the table is meant to be a direct mirror of
    # already-verified data) but checked rather than assumed.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `Scene` | The root scene graph container. |",
            "| `Node` | A scene-graph node. |",
            "| `FakeClass` | This class does not exist. |",
        ]),
    )
    findings = checks.check_api_reference_table_completeness(text, _API_TABLE_REFERENCE_INDEX)
    assert any(
        f["reason"] == "unrecognized_class" and f["class_name"] == "FakeClass"
        for f in findings
    )


def test_api_reference_table_completeness_ignores_subheader_as_bucket_boundary():
    # #### (Interfaces/Enumerations) must never start its own bucket -- rows still fold into the
    # owning ### module, same keying scheme parse_reference_api_index already uses. Implicitly
    # proven by the "clean" test above (IExporter, under #### Interfaces, must fold into "Core
    # API" or that test would fail on an unexpected "Interfaces" module) -- this test makes the
    # same guarantee explicit and independently checkable.
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    findings = checks.check_api_reference_table_completeness(text, _API_TABLE_REFERENCE_INDEX)
    assert not any(f.get("module") == "Interfaces" for f in findings)


def test_api_reference_table_completeness_flags_unrecognized_module():
    text = (
        _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section(detailed_after=False))
        + "### Bogus Module\n\n| Class | Description |\n|---|---|\n"
          "| `Bogus` | Not real. |\n\n"
          "#### Detailed Member Reference\n\n- `Scene`\n  - `fromFile(path) -> Scene`\n</details>\n"
    )
    findings = checks.check_api_reference_table_completeness(text, _API_TABLE_REFERENCE_INDEX)
    # A whole unrecognized module is flagged once, at the module level -- individual classes
    # inside it are not separately flagged too (redundant with the module-level finding).
    assert findings == [{
        "module": "Bogus Module", "reason": "unrecognized_module",
        "detail": "README table module 'Bogus Module' does not correspond to any real "
                  "reference.aspose.org module for this product",
    }]


def test_api_reference_table_completeness_noop_when_reference_index_empty():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_api_reference_table_completeness(text, {}) == []
    assert checks.check_api_reference_table_completeness(text, None) == []


def test_api_reference_table_completeness_ignores_real_zero_class_module():
    # Regression test: found live during this check's own Phase 1 pilot sanity pass against
    # tex/python's real content (2026-08-09) -- parse_reference_api_index correctly returns a
    # real "See Also" module with an empty class list (a bullet-list cross-reference section, not
    # a class table). Requiring the README to mirror it as an empty table would be nonsensical --
    # a real `##` header with zero rows is not a class-table module at all.
    reference_index = dict(_API_TABLE_REFERENCE_INDEX, **{"See Also": []})
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_api_reference_table_completeness(text, reference_index) == []


def test_api_reference_table_completeness_flags_missing_section_when_reference_data_exists():
    text = _wrap("flowchart TD\n  A --> B")  # no "## API Reference" section at all
    findings = checks.check_api_reference_table_completeness(text, _API_TABLE_REFERENCE_INDEX)
    assert findings == [{
        "reason": "missing_section",
        "detail": "reference.aspose.org has real API index data for this product, but the "
                  "README has no '## API Reference' section to hold its table",
    }]


def test_api_reference_table_completeness_ignores_content_after_detailed_member_reference_marker():
    # A stray, accidentally table-shaped line placed AFTER the marker (inside the untouched
    # curated-detail area) must never be parsed as a table row -- parsing stops at the marker.
    text = (
        _api_table_section(detailed_after=False)
        + "#### Detailed Member Reference\n\n"
          "| `RogueClass` | Looks like a table row but lives in the untouched curated area. |\n"
          "</details>\n"
    )
    text = _wrap("flowchart TD\n  A --> B", extra_section=text)
    findings = checks.check_api_reference_table_completeness(text, _API_TABLE_REFERENCE_INDEX)
    assert not any(f.get("class_name") == "RogueClass" for f in findings)
    assert findings == []


def test_api_reference_table_no_duplicate_rows_clean_table():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_api_reference_table_no_duplicate_rows(text) == []


def test_api_reference_table_no_duplicate_rows_flags_real_cells_cpp_regression():
    # Real, confirmed instance from a clean-room regeneration pilot: cells/cpp's regenerated
    # Enumerations table listed DiagnosticSeverity twice, verbatim, back-to-back -- it passed
    # check_api_reference_table_completeness cleanly (both occurrences are legitimate against
    # the reference index; duplication is a separate, orthogonal defect).
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(interfaces_rows=[
            "| `DiagnosticSeverity` | Indicates the severity of a diagnostic message. |",
            "| `DiagnosticSeverity` | Indicates the severity of a diagnostic message. |",
        ]),
    )
    findings = checks.check_api_reference_table_no_duplicate_rows(text)
    assert findings == [{
        "module": "Core API", "class_name": "DiagnosticSeverity", "count": 2,
        "reason": "'DiagnosticSeverity' appears 2 times in the 'Core API' table -- an exact "
                  "duplicate row, not two different classes",
    }]


def test_api_reference_table_no_duplicate_rows_ignores_different_classes_same_description():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `Scene` | A real class. |",
            "| `Node` | A real class. |",
        ]),
    )
    assert checks.check_api_reference_table_no_duplicate_rows(text) == []


def test_api_reference_table_no_duplicate_rows_noop_without_api_reference_section():
    text = _wrap("flowchart TD\n  A --> B")  # no "## API Reference" section at all
    assert checks.check_api_reference_table_no_duplicate_rows(text) == []


def test_no_generic_class_description_flags_filler_text():
    # Real, confirmed instance: 3d/java's own _index.md, `FileFormat`/`Node` rows.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `Scene` | Class with 20 methods and 61 properties. |",
            "| `Node` | Class with 48 methods and 16 properties. |",
        ]),
    )
    findings = checks.check_no_generic_class_description(text)
    flagged = {f["class_name"] for f in findings}
    assert flagged == {"Scene", "Node"}


def test_no_generic_class_description_flags_variant_without_properties():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=["| `Scene` | Class with 2 methods. |"]),
    )
    findings = checks.check_no_generic_class_description(text)
    assert [f["class_name"] for f in findings] == ["Scene"]


def test_no_generic_class_description_flags_struct_and_in_the_api_variants():
    # Regression test: found live during this check's own Phase 1 pilot sanity pass against
    # cells/cpp's real content (2026-08-09) -- the original regex only matched "Class with N
    # methods...", missing 3 real, confirmed shapes from the same file: "Struct with N
    # properties.", "Class in the Cells CPP API.", "Struct in the Cells CPP API." (the same
    # filler fallback applied to structs and to nested/iterator types with no extractable
    # member count at all).
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `HuffmanTable` | Struct with 2 methods and 4 properties. |",
            "| `ParsedNumericFormat` | Struct with 10 properties. |",
            "| `AutoFilterCustomFilterCollection::Iterator` | Class in the Cells CPP API. |",
            "| `CaseInsensitiveEqual` | Struct in the Cells CPP API. |",
        ]),
    )
    flagged = {f["class_name"] for f in checks.check_no_generic_class_description(text)}
    assert flagged == {
        "HuffmanTable", "ParsedNumericFormat",
        "AutoFilterCustomFilterCollection::Iterator", "CaseInsensitiveEqual",
    }


def test_no_generic_class_description_flags_members_variant():
    # Regression test: found live during the Phase 2 portfolio rollout (2026-08-09) -- two
    # independent agents (pdf/python, email/cpp) each separately found a 4th real filler
    # shape, "Enum with N members."/"Class with N members." (abbreviated "members" wording,
    # 6 confirmed instances in each product), undetected by the prior pattern because it only
    # recognized "Enumeration" (never abbreviated "Enum") and only "methods"/"properties"
    # (never "members").
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `Duplex` | Enum with 4 members. |",
            "| `PrintRange` | Class with 2 members. |",
        ]),
    )
    flagged = {f["class_name"] for f in checks.check_no_generic_class_description(text)}
    assert flagged == {"Duplex", "PrintRange"}


def test_no_generic_class_description_clean_on_real_descriptions():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_no_generic_class_description(text) == []


def test_no_generic_class_description_noop_without_api_reference_section():
    text = _wrap("flowchart TD\n  A --> B")
    assert checks.check_no_generic_class_description(text) == []


def test_no_truncated_class_description_flags_real_confirmed_instances():
    # Regression test: found live during this check's own Phase 1 pilot sanity pass against
    # html/python's real content (2026-08-09) -- 4 real rows truncated mid-sentence at "e.g.",
    # a 5th confirmed instance of the same defect class as cells/cpp's DisplayTextLocaleSupport.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `ProcessingInstruction` | A processing instruction node (e.g. |",
            "| `CommentToken` | A comment token, e.g. |",
            "| `EndTagToken` | An end tag token, e.g. |",
            "| `StartTagToken` | A start tag token, e.g. |",
        ]),
    )
    flagged = {f["class_name"] for f in checks.check_no_truncated_class_description(text)}
    assert flagged == {
        "ProcessingInstruction", "CommentToken", "EndTagToken", "StartTagToken",
    }


def test_no_truncated_class_description_clean_on_real_descriptions():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_no_truncated_class_description(text) == []


def test_no_truncated_class_description_noop_without_api_reference_section():
    text = _wrap("flowchart TD\n  A --> B")
    assert checks.check_no_truncated_class_description(text) == []


def test_no_stripped_example_in_description_flags_real_confirmed_instances():
    # Regression test: found live during this check's own Phase 1 pilot sanity pass against
    # html/python's real content (2026-08-09) -- 81 real rows in that one file had a real
    # HTML-tag example (e.g. `<address>`) stripped out of a double-backtick RST span somewhere
    # in reference.aspose.org's own generation pipeline, leaving a visibly broken empty span.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `HTMLAddressElement` | HTML ```` element. |",
            "| `HTMLOptionsCollection` | Live collection of ```` elements for a ````. |",
        ]),
    )
    flagged = {f["class_name"] for f in checks.check_no_stripped_example_in_description(text)}
    assert flagged == {"HTMLAddressElement", "HTMLOptionsCollection"}


def test_no_stripped_example_in_description_flags_isolated_two_backtick_span():
    # Regression test: found live during the Phase 2 portfolio rollout (2026-08-09,
    # slides/java) -- the same generator defect in its narrower, single-backtick form. A real
    # Javadoc `{@code <tag>}` span collapsed to an isolated, empty 2-backtick pair (not the
    # 4-backtick double-span form the original regex required), e.g. the real `AdjustValue`
    # row's stripped `<a:gd>` tag: "an OOXML `` element."
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `AdjustValue` | Represents an OOXML `` element. |",
        ]),
    )
    flagged = {f["class_name"] for f in checks.check_no_stripped_example_in_description(text)}
    assert flagged == {"AdjustValue"}


def test_no_stripped_example_in_description_does_not_flag_real_double_backtick_span():
    # Regression guard: a legitimate double-backtick span with real content (`` ``real code`` ``)
    # also opens with two adjacent backtick characters -- must not be mistaken for the empty-span
    # defect the broadened 2-backtick alternative was added to catch.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[
            "| `PdfConverter` | Converts using the ``Convert(Stream, SaveFormat)`` overload. |",
        ]),
    )
    assert checks.check_no_stripped_example_in_description(text) == []


def test_no_stripped_example_in_description_clean_on_real_descriptions():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_no_stripped_example_in_description(text) == []


def test_no_stripped_example_in_description_noop_without_api_reference_section():
    text = _wrap("flowchart TD\n  A --> B")
    assert checks.check_no_stripped_example_in_description(text) == []


def test_find_class_source_files_recognizes_typescript_enum(tmp_path):
    # Regression test: 3d/typescript's real ExtrapolationType/StepMode are declared as
    # `export enum ExtrapolationType { ... }` -- the original class|struct|interface|def
    # keyword list had no enum/type keyword at all.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "ExtrapolationType.ts").write_text(
        "export enum ExtrapolationType {\n  CONSTANT,\n  GRADIENT,\n}\n", encoding="utf-8"
    )
    found = checks._find_class_source_files(tmp_path, "ExtrapolationType")
    assert len(found) == 1


# TC-HARDEN-34 (MT035, 2026-08-12): the original 9-extension allowlist permanently excluded any
# new language's real source files from this function -- and therefore from check_named_member_
# accuracy's and check_api_reference_classes_exist_in_reference_site's clone-cache fallback --
# even once a real clone cache existed. Each of these 4 fixtures uses the exact declaration
# shape that language genuinely uses (a real `class`/`interface`/`enum` keyword this function's
# regex already recognizes -- only the extension was ever the blocker).
def test_find_class_source_files_recognizes_php(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "Widget.php").write_text("<?php\nclass Widget {\n    public $name;\n}\n", encoding="utf-8")
    found = checks._find_class_source_files(tmp_path, "Widget")
    assert len(found) == 1


def test_find_class_source_files_recognizes_kotlin(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "Widget.kt").write_text("class Widget(val name: String)\n", encoding="utf-8")
    found = checks._find_class_source_files(tmp_path, "Widget")
    assert len(found) == 1


def test_find_class_source_files_recognizes_kotlin_script_extension(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "build.gradle.kts").write_text("class Widget(val name: String)\n", encoding="utf-8")
    found = checks._find_class_source_files(tmp_path, "Widget")
    assert len(found) == 1


def test_find_class_source_files_recognizes_ruby(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "widget.rb").write_text("class Widget\n  attr_accessor :name\nend\n", encoding="utf-8")
    found = checks._find_class_source_files(tmp_path, "Widget")
    assert len(found) == 1


def test_find_class_source_files_recognizes_swift(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "Widget.swift").write_text("struct Widget {\n    let name: String\n}\n", encoding="utf-8")
    found = checks._find_class_source_files(tmp_path, "Widget")
    assert len(found) == 1


def test_find_class_source_files_still_ignores_unlisted_extensions(tmp_path):
    # Regression guard: the widening is deliberately bounded -- an extension not in the list
    # (e.g. a plain .txt file that happens to contain matching text) must still be ignored.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "Widget.txt").write_text("class Widget {}\n", encoding="utf-8")
    found = checks._find_class_source_files(tmp_path, "Widget")
    assert found == []


# --- check_installation_matches_package_registry (TC-HARDEN-32, MT035) --------------------------
# A heuristic, not a hard gate -- confirmed by direct live evidence the moment this check was
# first run against real content: data/package_registry.json was found independently wrong, in
# BOTH directions, for real products already in this portfolio (words/net's real, live-verified
# NuGet package contradicts its own registry's `published: false`; email/net's real nuspec casing
# contradicts its own registry's `candidate.name` casing). Every fixture below reproduces one of
# the real phrasings/mismatches this investigation actually found.


def test_installation_check_passes_unpublished_with_standard_marker():
    text = "## Installation\n\nA PyPI package has not been published yet. Install from source:\n"
    assert checks.check_installation_matches_package_registry(
        text, {"fallback_text_required": True}
    ) == []


def test_installation_check_recognizes_no_x_has_been_published_for_this_library_yet():
    # Real shape, email/cpp: negation via "No", not "not" -- the original narrower regex missed
    # this real, legitimate phrasing entirely.
    text = (
        "## Installation\n\nNo NuGet package has been published for this library yet — it ships "
        "as CMake source you build and link directly.\n"
    )
    assert checks.check_installation_matches_package_registry(
        text, {"fallback_text_required": True}
    ) == []


def test_installation_check_recognizes_is_not_yet_published():
    # Real shape, slides/cpp.
    text = (
        "## Installation\n\nThis library is not yet published to a package registry. Building it "
        "as a standalone CMake project is straightforward:\n"
    )
    assert checks.check_installation_matches_package_registry(
        text, {"fallback_text_required": True}
    ) == []


def test_installation_check_flags_missing_unpublished_disclosure():
    text = "## Installation\n\n```bash\npip install totally-invented-package\n```\n"
    findings = checks.check_installation_matches_package_registry(
        text, {"fallback_text_required": True}
    )
    assert len(findings) == 1
    assert "does not disclose" in findings[0]["reason"]


def test_installation_check_passes_published_package_naming_real_identity():
    text = "## Installation\n\n```bash\npython -m pip install aspose-email-foss\n```\n"
    install_info = {
        "fallback_text_required": False, "registry_type": "pypi",
        "candidate": {"name": "aspose-email-foss"},
    }
    assert checks.check_installation_matches_package_registry(text, install_info) == []


def test_installation_check_is_case_insensitive_for_published_package_identity():
    # Real shape, email/net: the README's real content ("Aspose.Email.Foss") and the real, live
    # nuspec both use this casing; only data/package_registry.json's own candidate.name
    # ("Aspose.Email.FOSS") differs -- a registry-data bug, not a content defect. NuGet package
    # IDs are conventionally case-insensitive, so this must not be flagged.
    text = "## Installation\n\n```bash\ndotnet add package Aspose.Email.Foss\n```\n"
    install_info = {
        "fallback_text_required": False, "registry_type": "nuget",
        "candidate": {"name": "Aspose.Email.FOSS"},
    }
    assert checks.check_installation_matches_package_registry(text, install_info) == []


def test_installation_check_flags_wrong_published_package_identity():
    text = "## Installation\n\n```bash\npython -m pip install totally-different-package\n```\n"
    install_info = {
        "fallback_text_required": False, "registry_type": "pypi",
        "candidate": {"name": "aspose-email-foss"},
    }
    findings = checks.check_installation_matches_package_registry(text, install_info)
    assert len(findings) == 1
    assert findings[0]["expected"] == "aspose-email-foss"


def test_installation_check_maven_uses_artifact_id_not_group_id():
    text = "## Installation\n\nAdd `org.aspose:aspose-cells-foss:26.5.0` to your build.\n"
    install_info = {
        "fallback_text_required": False, "registry_type": "maven",
        "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss"},
    }
    assert checks.check_installation_matches_package_registry(text, install_info) == []


def test_installation_check_go_modules_uses_module_path():
    text = "## Installation\n\n```bash\ngo get github.com/aspose-pdf-foss/aspose-pdf-foss-for-go\n```\n"
    install_info = {
        "fallback_text_required": False, "registry_type": "go_modules",
        "candidate": {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
    }
    assert checks.check_installation_matches_package_registry(text, install_info) == []


def test_installation_check_noop_when_no_registry_data_at_all():
    text = "## Installation\n\n```bash\npip install anything\n```\n"
    assert checks.check_installation_matches_package_registry(text, {"source": "package_registry_missing"}) == []


def test_installation_check_noop_when_no_installation_section():
    text = "## Key Capabilities\n\n- Does a thing.\n"
    assert checks.check_installation_matches_package_registry(
        text, {"fallback_text_required": True}
    ) == []


def test_installation_check_noop_when_candidate_data_incomplete():
    text = "## Installation\n\n```bash\npip install something\n```\n"
    install_info = {"fallback_text_required": False, "registry_type": "pypi", "candidate": {}}
    assert checks.check_installation_matches_package_registry(text, install_info) == []


def test_api_reference_classes_exist_flags_fabricated_class():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section=(
            "## API Reference\n\n"
            "The primary entry point is `TeXJob`.\n\n"
            "- `FakeClassThatDoesNotExist`\n  - `run()`\n"
        ),
    )
    reference_names = {"TeXJob", "TeXOptions", "AsposeTeXError"}
    findings = checks.check_api_reference_classes_exist_in_reference_site(text, reference_names)
    assert any(f["class_name"] == "FakeClassThatDoesNotExist" for f in findings)


def test_api_reference_classes_exist_confirms_via_clone_cache_when_reference_index_incomplete(tmp_path):
    # Regression test: found live during MT027's own Phase 1 pilot sanity pass -- a class real
    # and already source-verified (tex/python's FontManager) but genuinely absent from
    # reference.aspose.org's own generated index for that product must NOT be flagged, as long
    # as the clone-cache source confirms it's real.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "font_manager.py").write_text("class FontManager:\n    pass\n", encoding="utf-8")
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="## API Reference\n\n- `FontManager`\n  - `load_font()`\n",
    )
    reference_names = {"TeXJob", "TeXOptions"}  # a real, but incomplete, reference index
    findings = checks.check_api_reference_classes_exist_in_reference_site(
        text, reference_names, str(tmp_path)
    )
    assert findings == []


def test_api_reference_classes_exist_flags_fabricated_class_confirmed_by_neither_source(tmp_path):
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="## API Reference\n\n- `TotallyFakeClass`\n  - `run()`\n",
    )
    reference_names = {"TeXJob"}
    findings = checks.check_api_reference_classes_exist_in_reference_site(
        text, reference_names, str(tmp_path)  # empty dir -- clone-cache confirms nothing either
    )
    assert any(f["class_name"] == "TotallyFakeClass" for f in findings)


def test_api_reference_classes_exist_flags_when_no_reference_data_available():
    # TC-HARDEN-31 (Twenty-Second incident / MT035): this used to be a silent no-op --
    # exactly the state a brand-new product starts in (no /repo-scout run, no
    # reference.aspose.org page). A cited class with no corroborating source anywhere must
    # now produce a real, named finding, never zero findings indistinguishable from "clean."
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="## API Reference\n\n- `AnyClassAtAll`\n  - `run()`\n",
    )
    for reference_names in (None, set()):
        findings = checks.check_api_reference_classes_exist_in_reference_site(text, reference_names)
        assert any(f.get("class_name") == "AnyClassAtAll" for f in findings), findings
        assert any("no verification source is available" in f["reason"] for f in findings)


def test_api_reference_classes_exist_still_vacuous_when_no_classes_cited_and_no_sources():
    # Regression guard: the TC-HARDEN-31 fix must not fire when the API Reference section
    # genuinely names no classes at all via the structured bullet convention -- there is
    # nothing to be unverified about.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="## API Reference\n\nThe primary entry point is `Workbook`.\n\n<details>\n",
    )
    assert checks.check_api_reference_classes_exist_in_reference_site(text, None) == []
    assert checks.check_api_reference_classes_exist_in_reference_site(text, set()) == []


def test_api_reference_classes_exist_no_sources_skips_package_grouping_bullet():
    # Regression guard: the existing package-grouping exclusion (a lowercase last dot-segment
    # is not a real class citation) must still apply even when no sources are available --
    # otherwise a real bullet like "- `org.aspose.pdf.drawing` -- `Line`, `Rectangle`" would
    # be wrongly flagged as an unverified class named "org.aspose.pdf.drawing".
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="## API Reference\n\n- `org.aspose.pdf.drawing` -- `Line`, `Rectangle`\n",
    )
    assert checks.check_api_reference_classes_exist_in_reference_site(text, None) == []


def test_api_reference_classes_exist_no_sources_flags_every_distinct_cited_class():
    # Both halves of a combined `` `ClassA` / `ClassB` `` bullet are real, distinct citations
    # -- both must be flagged when no source is available, not just the first.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    o1["Plain text"]
  end
  PRODUCT --> Capabilities --> Outputs""",
        extra_section="## API Reference\n\n- `LoadOptions` / `SaveOptions`\n",
    )
    findings = checks.check_api_reference_classes_exist_in_reference_site(text, None)
    flagged = {f["class_name"] for f in findings}
    assert flagged == {"LoadOptions", "SaveOptions"}


def test_no_leaked_docstring_artifacts_flags_real_texoptions_case():
    # The real, confirmed defect: a raw-string triple-quote prefix leaked into prose.
    text = "Some prose.\n\nr\"\"\"Configuration for a TeX processing job.\n\nMore prose."
    findings = checks.check_no_leaked_docstring_artifacts(text)
    assert findings and "leaked raw Python docstring delimiter" in findings[0]["reason"]


def test_no_leaked_docstring_artifacts_clean_on_ordinary_prose():
    text = "This library parses TeX/LaTeX source and produces PDF, DVI, and SVG output."
    assert checks.check_no_leaked_docstring_artifacts(text) == []


def test_no_leaked_docstring_artifacts_ignores_fenced_code_blocks():
    # A real Python code example legitimately showing a docstring must not be flagged.
    text = '```python\ndef f():\n    r"""A real docstring in a real code example."""\n```\n'
    assert checks.check_no_leaked_docstring_artifacts(text) == []


def test_named_member_accuracy_prefers_reference_page_over_clone_cache(tmp_path):
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    (reference_dir / "TeXJob.md").write_text(_REAL_TEXJOB_CLASS_PAGE_MD, encoding="utf-8")
    # No clone_cache_root needed -- the reference page must take precedence and be sufficient.
    readme = "- `TeXJob`\n  - `run()`\n  - `messages`\n"
    findings = checks.check_named_member_accuracy(
        readme, str(tmp_path / "nonexistent_clone_cache"), reference_dir=str(reference_dir)
    )
    assert findings == []


def test_named_member_accuracy_flags_fabricated_member_via_reference_page(tmp_path):
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    (reference_dir / "TeXJob.md").write_text(_REAL_TEXJOB_CLASS_PAGE_MD, encoding="utf-8")
    readme = "- `TeXJob`\n  - `run()`\n  - `fake_method_not_on_this_class()`\n"
    findings = checks.check_named_member_accuracy(
        readme, str(tmp_path / "nonexistent_clone_cache"), reference_dir=str(reference_dir)
    )
    assert len(findings) == 1
    assert "fake_method_not_on_this_class" in findings[0]["member"]
    assert "reference.aspose.org" in findings[0]["reason"]


def test_named_member_accuracy_falls_back_to_clone_cache_when_reference_page_is_incomplete(tmp_path):
    # Regression test: found live during MT027's full-portfolio sanity pass -- email/cpp's real
    # reference.aspose.org page for mapi_message lists `set_subject` but is genuinely missing
    # the real `subject()` getter (present in real source) from both its Properties and Methods
    # tables. A member missing from the reference page must still be confirmed via clone-cache
    # before being flagged, not flagged on the reference page's incompleteness alone.
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    (reference_dir / "mapi_message.md").write_text(
        "---\ngrade: A\n---\n\n## Methods\n\n"
        "| Signature | Description |\n|---|---|\n"
        "| `set_subject(value: std::string)` | Sets the subject |\n",
        encoding="utf-8",
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "mapi_message.hpp").write_text(
        "class mapi_message {\npublic:\n"
        "    const std::string& subject() const noexcept;\n"
        "    void set_subject(std::string value);\n"
        "};\n",
        encoding="utf-8",
    )
    readme = "- `mapi_message`\n  - `subject()`\n  - `set_subject(value)`\n"
    findings = checks.check_named_member_accuracy(
        readme, str(src_dir), reference_dir=str(reference_dir)
    )
    assert findings == []


def test_named_member_accuracy_falls_back_to_clone_cache_when_no_reference_page(tmp_path):
    # No reference_dir given at all -- must behave exactly as before MT027.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "worksheet.h").write_text(
        "class Worksheet final {\npublic:\n    void SetName(std::string_view value);\n};\n",
        encoding="utf-8",
    )
    readme = "- `Worksheet`\n  - `SetName(value)`\n"
    assert checks.check_named_member_accuracy(readme, str(tmp_path)) == []


# --- Fourteenth incident / MT029 (2026-08-09): five visitor-facing content-quality rules ----

# Real, captured-verbatim upstream-issues.md entry (tex/python, trimmed) -- the confirmed
# motivating instance for check_no_upstream_issue_leaked_into_readme.
_REAL_TEX_PYTHON_UPSTREAM_ISSUES = """# Upstream issues -- Aspose.TeX FOSS for Python

Verified: 2026-08-02 against https://github.com/aspose-tex-foss/Aspose.TeX-FOSS-for-Python

## Package fails to import entirely -- systemic indentation corruption
- **Severity**: BLOCKING
- **Evidence**: `import aspose_tex` raises a real `IndentationError`. Root cause: 35 of the 45
  `.py` files under `src/aspose_tex/` have every block body indented to exactly one space
  regardless of true nesting depth.
- **Impact**: literally none of the documented Python examples in this README can currently
  execute against this source snapshot.
- **Not fixable here because**: reconstructing correct indentation is not recoverable by
  inspection or guesswork.
"""

# Real, captured-verbatim blockquote (tex/python's actual readme.md, trimmed) -- Form A of the
# confirmed defect: duplicates the entry above almost verbatim.
_REAL_TEX_PYTHON_LEAK_BLOCKQUOTE = (
    "> **Known issue:** the current source tree fails to import.\n"
    '> `pip install -e ".[dev]"` completes successfully, but\n'
    "> `import aspose_tex` raises `IndentationError` -- 35 of the 45 modules under\n"
    "> `src/aspose_tex/` have block bodies indented to a single space\n"
    "> regardless of nesting depth, which is not valid Python. `pytest` fails to collect\n"
    "> 67 of 69 test modules for the same reason.\n"
)

# The already-correct, non-leaking pattern (html/python's real shape) -- a plain pointer with
# zero forensic specificity.
_REAL_HTML_PYTHON_CLEAN_POINTER = (
    "`pip install` currently fails for this repository at any source -- "
    "see [upstream-issues.md](upstream-issues.md) for the root cause.\n"
)


def test_no_upstream_issue_leaked_flags_real_blockquote_instance():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- Does a thing.\n\n" + _REAL_TEX_PYTHON_LEAK_BLOCKQUOTE,
    )
    findings = checks.check_no_upstream_issue_leaked_into_readme(
        text, _REAL_TEX_PYTHON_UPSTREAM_ISSUES
    )
    assert findings
    assert len(findings[0]["matched_tokens"]) >= 2


def test_no_upstream_issue_leaked_clean_on_plain_pointer():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- Does a thing.\n\n" + _REAL_HTML_PYTHON_CLEAN_POINTER,
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(
        text, _REAL_TEX_PYTHON_UPSTREAM_ISSUES
    ) == []


def test_no_upstream_issue_leaked_noop_without_upstream_issues_text():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_REAL_TEX_PYTHON_LEAK_BLOCKQUOTE)
    assert checks.check_no_upstream_issue_leaked_into_readme(text, "") == []


def test_no_upstream_issue_leaked_noop_when_no_extractable_fingerprints():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_REAL_TEX_PYTHON_LEAK_BLOCKQUOTE)
    clean_upstream = "# Upstream issues\n\nNo upstream issues identified during verification.\n"
    assert checks.check_no_upstream_issue_leaked_into_readme(text, clean_upstream) == []


def test_no_upstream_issue_leaked_requires_two_concurring_tokens():
    # A single shared token (one class name mentioned legitimately elsewhere) must never
    # trigger a false positive on its own.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- `IndentationError` is a real Python built-in exception type.\n",
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(
        text, _REAL_TEX_PYTHON_UPSTREAM_ISSUES
    ) == []


def test_no_upstream_issue_leaked_allows_legitimate_workaround_pointer():
    # Regression test: found live during this check's own Phase 1 pilot rollout (2026-08-09,
    # cells/go) -- a genuinely legitimate, non-forensic pointer sentence with a real
    # actionable workaround shares the filename and the generic word "version" with the real
    # issue's own title ("...has an invalid version string..."). Title-word fingerprinting
    # was removed specifically because it would have flagged exactly this kind of sentence,
    # which check_no_upstream_issue_leaked_into_readme exists to *allow* (per html/python's
    # already-correct precedent), not block.
    real_cells_go_upstream_issues = (
        "# Upstream issues -- Aspose.Cells FOSS for Go\n\n"
        "## examples/go.mod has an invalid version string, breaking the repo's own "
        "example runner\n"
        "- **Severity**: FUNCTIONAL-DEFECT\n"
        "- **Evidence**: `examples/go.mod` declares `require .../v26 v0.0.0` -- an invalid "
        "version string for a `/v26` major-version module path.\n"
        "- **Impact**: contributors hit an immediate failure.\n"
        "- **Not fixable here because**: it's the upstream repo's own file.\n"
    )
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Does a thing.\n\n## Development and Testing\n\n"
            "If the example-runner loop above fails on a fresh checkout, edit "
            "`examples/go.mod`'s version to a valid pseudo-version before running -- see "
            "[upstream-issues.md](upstream-issues.md) for details.\n"
        ),
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(
        text, real_cells_go_upstream_issues
    ) == []


def test_no_upstream_issue_leaked_scans_bullets_independently():
    # Regression test: found live during this check's own Phase 1 pilot rollout (2026-08-09,
    # cells/go) -- a bulleted list with no blank lines between items was treated as ONE giant
    # paragraph, so an unrelated match in one bullet got misattributed to a completely
    # different bullet's own text. Each bullet in a pure bulleted block must be scanned
    # independently.
    upstream = (
        "# Upstream issues\n\n"
        "## Something breaks\n"
        "- **Severity**: FUNCTIONAL-DEFECT\n"
        "- **Evidence**: the real `go.mod` declares zero `require` entries.\n"
    )
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Create, load, and save `.xlsx` workbooks with `Workbook`/`Worksheet`.\n"
            "- Group formatting into reusable `Style` objects.\n"
            "- Some unrelated bullet mentioning `go.mod` and `require` on its own.\n"
        ),
    )
    findings = checks.check_no_upstream_issue_leaked_into_readme(text, upstream)
    # The real leak (bullet 3) is still caught...
    assert any("go.mod" in f["paragraph"] for f in findings)
    # ...but bullet 1 (Workbook/Worksheet) must never be implicated.
    assert not any("Workbook" in f["paragraph"] for f in findings)


def test_no_upstream_issue_leaked_scans_wrapped_bullets_independently():
    # Regression test: found live 2026-08-13 (3d/net/3d/typescript, during the portfolio-wide
    # upstream-issues.md audit) -- the sibling test above (`..._scans_bullets_independently`)
    # only covers single-PHYSICAL-line bullets. A bullet that WRAPS across multiple lines (a
    # `- ` marker line followed by indented continuation lines with no `- ` prefix of their
    # own -- the normal, near-universal shape for any bullet longer than ~80 chars throughout
    # this portfolio's real Scope and Limitations sections) made `_iter_leak_scan_units`'s own
    # `all(...)` check fail for the WHOLE block (since a continuation line never starts with
    # `- `), silently collapsing the entire bulleted section back into one giant unit --
    # reintroducing the exact cross-bullet misattribution bug the sibling test already proves
    # is fixed for the single-line case. A real, unrelated bullet (about `Rendering`/
    # `Scene.Render`, wrapped across 2 lines) got blamed for a real leak that actually lived in
    # a completely different, later bullet (`Watermark`) purely because the wrapped bullet's
    # own continuation line broke the per-bullet split for the block as a whole.
    upstream = (
        "# Upstream issues\n\n"
        "## Watermark is unimplemented\n"
        "- **Severity**: FUNCTIONAL-DEFECT\n"
        "- **Evidence**: `Watermark.EncodeWatermark`/`DecodeWatermark` both unconditionally "
        "`throw new NotImplementedException(...)`.\n"
    )
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Rendering is not implemented in this FOSS build — `Scene.Render`, "
            "`RenderFactory`, and the\n"
            "  `IRenderTarget`/`IRenderWindow` rendering pipeline all throw "
            "`NotImplementedException`. For\n"
            "  rendering and other advanced functionality, see the Enterprise Edition.\n"
            "- `Watermark.EncodeWatermark`/`DecodeWatermark` — every overload throws "
            "`NotImplementedException`\n"
            "  in this FOSS build; text watermarking is not currently functional.\n"
        ),
    )
    findings = checks.check_no_upstream_issue_leaked_into_readme(text, upstream)
    # The real leak (the Watermark bullet) is still caught...
    assert any("Watermark" in f["paragraph"] for f in findings)
    # ...but the unrelated, wrapped Rendering bullet must never be implicated, even though it
    # physically precedes the real leak in the same blank-line-delimited block.
    assert not any(
        f["paragraph"].startswith("- Rendering is not implemented") for f in findings
    )


def test_no_upstream_issue_leaked_excludes_generic_builtin_exceptions():
    # Regression test: found live during this check's own Phase 1 pilot rollout (2026-08-09,
    # 3d/python) -- a legitimate, accurate Scope and Limitations bullet describing FBX's own
    # real stub methods ("`FbxExporter.save()` ... raise `NotImplementedError`") coincidentally
    # shared `FbxExporter` + `NotImplementedError` with a DIFFERENT real upstream-issues.md
    # entry (about COLLADA-export dispatch order, not FBX) purely because NotImplementedError
    # is the standard, ubiquitous way any Python library signals "not implemented" -- too
    # generic to safely fingerprint on its own.
    upstream = (
        "# Upstream issues\n\n"
        "## Collada export unreachable via the public Scene.save() API\n"
        "- **Severity**: FUNCTIONAL-DEFECT\n"
        "- **Evidence**: `FbxExporter` never overrides `Exporter.supports_format()` and is "
        "registered before `ColladaPlugin`, so `IOService.create_exporter()` raises "
        "`NotImplementedError` before ever reaching the real Collada exporter.\n"
    )
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "## Scope and Limitations\n\n"
            "- FBX support is experimental: `FbxExporter.save()` and "
            "`FbxExporter.save_to_stream()` raise `NotImplementedError`.\n"
        ),
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(text, upstream) == []


def test_no_upstream_issue_leaked_excludes_installation_and_quick_start():
    # Regression test: found live during this check's own Phase 1 pilot rollout (2026-08-09,
    # cells/cpp) -- a C++ product's real, accurate Installation instructions necessarily cite
    # the same real package/file names (`Aspose.Cells.Cpp.FOSS`, `.targets`,
    # `-config.cmake`, `CMakeLists.txt`) that an unrelated INFORMATIONAL upstream-issues.md
    # entry's own evidence also cites (about the package's bundled SAMPLE not building, not
    # about the installation instructions themselves). Installation/Quick Start exist to give
    # real, specific instructions -- overlap there is expected, not suspicious.
    upstream = (
        "# Upstream issues\n\n"
        "## NuGet package's bundled sample doesn't exercise its own packaged CMake config\n"
        "- **Severity**: INFORMATIONAL\n"
        "- **Evidence**: the real `Aspose.Cells.Cpp.FOSS` package ships a working "
        "`aspose.cells.cpp.foss-config.cmake` and `.targets` file, but its own bundled "
        "`build/native/samples/CMakeLists.txt` does `add_subdirectory(\"../Aspose.Cells."
        "Foss.Cpp\")` against a sibling source directory not present in the package.\n"
    )
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Does a thing.\n\n## Installation\n\n"
            "In a CMake project targeting MSVC, point at the package's own bundled CMake "
            "package config instead (`aspose.cells.cpp.foss-config.cmake`, which defines an "
            "`Aspose.Cells.Cpp.FOSS` imported target).\n"
        ),
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(text, upstream) == []


def test_no_upstream_issue_leaked_excludes_badge_row():
    # Regression test: found live during this check's own Phase 1 pilot rollout (2026-08-09,
    # cells/cpp) -- the top-of-file NuGet badge (`[![NuGet version](...Aspose.Cells.Cpp.FOSS...)
    # ]`) coincidentally shared 2 tokens with the same INFORMATIONAL entry as the Installation
    # false positive above. Only the badge line itself is excluded, not the whole preamble --
    # the real, confirmed tex/python leak lived in the preamble (a top-of-file blockquote),
    # so blanket-excluding the preamble would have hidden that real case.
    upstream = (
        "# Upstream issues\n\n"
        "## NuGet package's bundled sample doesn't exercise its own packaged CMake config\n"
        "- **Severity**: INFORMATIONAL\n"
        "- **Evidence**: the real `Aspose.Cells.Cpp.FOSS` package's bundled "
        "`build/native/samples/CMakeLists.txt` doesn't reference its own config.\n"
    )
    text = (
        "# Some Product\n\n"
        "[![NuGet version](https://img.shields.io/nuget/v/Aspose.Cells.Cpp.FOSS.svg)]"
        "(https://www.nuget.org/packages/Aspose.Cells.Cpp.FOSS/) "
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n\n"
        "## Key Capabilities\n\n- Does a thing.\n"
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(text, upstream) == []


def test_no_upstream_issue_leaked_still_catches_preamble_blockquote():
    # Regression guard for the fix above: excluding badge LINES must never accidentally
    # exclude the rest of the preamble too -- the real, confirmed tex/python leak was a
    # blockquote in the preamble (before any ## heading), which must still be caught.
    text = _wrap("flowchart TD\n  A --> B")
    text = text.replace(
        "# Some Product\n\n",
        "# Some Product\n\n" + _REAL_TEX_PYTHON_LEAK_BLOCKQUOTE + "\n",
    )
    findings = checks.check_no_upstream_issue_leaked_into_readme(
        text, _REAL_TEX_PYTHON_UPSTREAM_ISSUES
    )
    assert findings


def test_no_upstream_issue_leaked_excludes_informational_severity():
    # Regression test: found live during this check's own Phase 1 pilot rollout (2026-08-09,
    # html/python) -- a third confirmed false positive against an INFORMATIONAL entry (the
    # `[js]` extra failing to build on Windows), matching legitimate Scope-and-Limitations
    # prose describing the real, unrelated fact that JSContext requires the `[js]` extra.
    # All 7 of this session's confirmed real leak instances trace to BLOCKING/
    # FUNCTIONAL-DEFECT entries, none to INFORMATIONAL ones -- verified directly against
    # every one of the 7 real upstream-issues.md files before adopting this exclusion.
    upstream = (
        "# Upstream issues\n\n"
        "## [js] extra fails to build on Windows\n"
        "- **Severity**: INFORMATIONAL\n"
        "- **Evidence**: the `[js]` extra's `quickjs` dependency fails to build on Windows; "
        "no block uses `JSContext`.\n"
    )
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "## Scope and Limitations\n\n"
            "- JavaScript execution is opt-in through `JSContext` (requires the `[js]` "
            "extra).\n"
        ),
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(text, upstream) == []


def test_no_upstream_issue_leaked_still_catches_functional_defect_severity():
    # Regression guard: excluding INFORMATIONAL severity must never accidentally exclude
    # BLOCKING/FUNCTIONAL-DEFECT entries too.
    upstream = (
        "# Upstream issues\n\n"
        "## Something breaks\n"
        "- **Severity**: FUNCTIONAL-DEFECT\n"
        "- **Evidence**: `import aspose_tex` raises `IndentationError` in 35 of the 45 "
        "modules.\n"
    )
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "> `import aspose_tex` raises `IndentationError` in 35 of the 45 modules.\n"
        ),
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(text, upstream) != []


def test_no_upstream_issue_leaked_ignores_fenced_code_blocks():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Does a thing.\n\n```python\n# import aspose_tex raises IndentationError\n"
            "# 35 of the 45 modules are affected\n```\n"
        ),
    )
    assert checks.check_no_upstream_issue_leaked_into_readme(
        text, _REAL_TEX_PYTHON_UPSTREAM_ISSUES
    ) == []


def test_key_capabilities_quality_flags_too_few_bullets():
    text = _wrap("flowchart TD\n  A --> B", extra_section="- Loads a file.\n- Saves a file.\n")
    findings = checks.check_key_capabilities_quality(text)
    assert any("bullet(s)" in f["reason"] for f in findings)


def test_key_capabilities_quality_flags_fragmented_near_duplicate_openings():
    # Real, confirmed shape: words/python's 3 near-identical "Load X via Y" bullets.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Load DOCX documents with a pure-Python reader.\n"
            "- Load legacy DOC files via `olefile`.\n"
            "- Load RTF files via OLE2 delegation.\n"
            "- Export to Markdown with rich formatting.\n"
        ),
    )
    findings = checks.check_key_capabilities_quality(text)
    assert any("fragmented" in f["reason"] for f in findings)


def test_key_capabilities_quality_flags_thin_bullet():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Reads files.\n- Writes files.\n- Converts files.\n"
            "- Encrypts documents with AES-256 via `PdfFileSecurity`.\n"
        ),
    )
    findings = checks.check_key_capabilities_quality(text)
    assert any(f["reason"].startswith("thin bullet") for f in findings)


def test_key_capabilities_quality_clean_on_well_formed_section():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Open and create PDFs with full round-trip save via `Document` and `Page`.\n"
            "- Extract and search text via `TextAbsorber` and `TextFragmentAbsorber`.\n"
            "- Fill and build AcroForm fields via `Form` and `FormEditor`.\n"
            "- Encrypt with AES-128/256 and sign with PKCS#7 via `PdfFileSignature`.\n"
            "- Render pages to PNG, JPEG, and TIFF via `PngDevice` and `TiffDevice`.\n"
        ),
    )
    assert checks.check_key_capabilities_quality(text) == []


def test_key_capabilities_quality_noop_without_section():
    text = _wrap("flowchart TD\n  A --> B", extra_section="")
    # _wrap always emits a Key capabilities heading with default content -- confirm a real
    # absence (different heading entirely) is a true no-op.
    text_no_section = text.replace("## Key capabilities", "## Something Else")
    assert checks.check_key_capabilities_quality(text_no_section) == []


_3D_NET_WATERMARK_CAPABILITY_BULLET = (
    "- `Watermark` embeds and extracts text watermarks in 3D files.\n"
)
_3D_NET_WATERMARK_SCOPE_BULLET = (
    "- Several members throw `NotImplementedException` in this edition, including Draco "
    "decode/encode, and text-watermark encode/decode.\n"
)


def test_capability_scope_contradiction_flags_real_3d_net_case():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            _3D_NET_WATERMARK_CAPABILITY_BULLET
            + "\n## Scope and Limitations\n\n"
            + _3D_NET_WATERMARK_SCOPE_BULLET
            + "\nFor more, see [Enterprise Edition](https://products.aspose.com/3d/net/).\n"
        ),
    )
    findings = checks.check_capability_scope_contradiction(text)
    assert any(f["matched_keyword"] == "Watermark" for f in findings)


def test_capability_scope_contradiction_clean_when_no_overlap():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- `Cylinder` is a parameterized solid primitive convertible to `Mesh`.\n"
            "\n## Scope and Limitations\n\n"
            "- Rendering (`Scene.Render`) is not implemented in this edition.\n"
            "\nFor more, see [Enterprise Edition](https://products.aspose.com/3d/net/).\n"
        ),
    )
    assert checks.check_capability_scope_contradiction(text) == []


def test_capability_scope_contradiction_flags_partial_stub_overlap_too():
    # Documented, accepted heuristic over-inclusion (see the check's own docstring): a class
    # that's mostly real but has one specific stub method still trips this coarse substring
    # check -- it is a prompt for judgment, not proof of a genuine contradiction, and this
    # test exists to pin that documented behavior, not to treat it as a bug.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- `Scene` builds and traverses a scene graph.\n"
            "\n## Scope and Limitations\n\n"
            "- Rendering (`Scene.Render`) is not implemented in this edition.\n"
            "\nFor more, see [Enterprise Edition](https://products.aspose.com/3d/net/).\n"
        ),
    )
    findings = checks.check_capability_scope_contradiction(text)
    assert any(f["matched_keyword"] == "Scene" for f in findings)


def test_capability_scope_contradiction_noop_without_both_sections():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_3D_NET_WATERMARK_CAPABILITY_BULLET)
    assert checks.check_capability_scope_contradiction(text) == []


def test_capability_scope_contradiction_flags_python_not_implemented_error():
    # Regression test: found live during the Phase 2 portfolio rollout (2026-08-09,
    # words/python) -- the original _STUB_INDICATOR_RE only matched the Java/C# convention
    # (`NotImplementedException`), silently missing Python's idiomatic `NotImplementedError`.
    # Real motivating bullet: "`LdmDocxWriter` has a documented `NotImplementedError`...".
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- `LdmDocxWriter` serializes the light document model to DOCX.\n"
            "\n## Scope and Limitations\n\n"
            "- `LdmDocxWriter` has a documented `NotImplementedError` for footnote export.\n"
            "\nFor more, see [Enterprise Edition](https://products.aspose.com/words/python/).\n"
        ),
    )
    findings = checks.check_capability_scope_contradiction(text)
    assert any(f["matched_keyword"] == "LdmDocxWriter" for f in findings)


_REAL_PDF_NET_SCOPE_LIST = (
    "The following are **not** implemented in this edition.\n\n"
    "- **Out of scope by design** -- AI/LowCode workflows (`Aspose.Pdf.AI.*`); "
    "multithreading APIs (`Aspose.Pdf.Multithreading.*`).\n"
    "- **Partial -- basics work, advanced doesn't** -- digital-signature validation options "
    "are stored but not active.\n"
    "- **Renderer fidelity** -- the FOSS rendering output is pixel-close but not "
    "byte-identical to Aspose.PDF for .NET.\n\n"
    "For AI-assisted workflows, additional format converters, multithreading, and full "
    "validation coverage, see [Aspose.PDF for .NET -- Enterprise Edition]"
    "(https://products.aspose.com/pdf/net/).\n"
)


def test_scope_limitations_format_clean_on_real_pdf_net_shape():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n" + _REAL_PDF_NET_SCOPE_LIST
    ))
    assert checks.check_scope_limitations_format(text) == []


def test_scope_limitations_format_flags_prose_paragraph_shape():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n"
        "This project reads and writes XLSX only. For broader coverage, see "
        "[Enterprise Edition](https://products.aspose.com/cells/cpp/).\n"
    ))
    findings = checks.check_scope_limitations_format(text)
    assert any(f["reason"] == "not_a_list" for f in findings)


def test_scope_limitations_format_flags_bulleted_enterprise_paragraph():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n"
        "- Reads and writes XLSX only.\n"
        "- See [Enterprise Edition](https://products.aspose.com/cells/cpp/) for more.\n"
    ))
    findings = checks.check_scope_limitations_format(text)
    assert any(f["reason"] == "enterprise_paragraph_is_bulleted" for f in findings)


def test_scope_limitations_format_flags_missing_enterprise_paragraph():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n- Reads and writes XLSX only.\n"
    ))
    findings = checks.check_scope_limitations_format(text)
    assert any(f["reason"] == "missing_enterprise_paragraph" for f in findings)


def test_scope_limitations_format_noop_without_section():
    text = _wrap("flowchart TD\n  A --> B", extra_section="- Does a thing.\n")
    assert checks.check_scope_limitations_format(text) == []


def test_dev_test_artifacts_linked_flags_missing_link():
    detected = [{
        "relative_path": "AGENTS.md", "kind": "agents_guide", "section": "Documentation & Resources",
    }]
    text = _wrap("flowchart TD\n  A --> B", extra_section="- Does a thing.\n")
    findings = checks.check_dev_test_artifacts_linked(text, detected)
    assert findings and findings[0]["path"] == "AGENTS.md"


def test_dev_test_artifacts_linked_clean_when_linked():
    detected = [{
        "relative_path": "AGENTS.md", "kind": "agents_guide", "section": "Documentation & Resources",
    }]
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- See [AGENTS.md](AGENTS.md) for contributor guidance.\n",
    )
    assert checks.check_dev_test_artifacts_linked(text, detected) == []


def test_dev_test_artifacts_linked_matches_by_basename():
    detected = [{
        "relative_path": "docs/testing.md", "kind": "docs_guide", "section": "Documentation & Resources",
    }]
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- See [the testing guide](docs/testing.md) for details.\n",
    )
    assert checks.check_dev_test_artifacts_linked(text, detected) == []


def test_dev_test_artifacts_linked_noop_when_none_detected():
    text = _wrap("flowchart TD\n  A --> B", extra_section="- Does a thing.\n")
    assert checks.check_dev_test_artifacts_linked(text, []) == []


def test_development_testing_collapse_flags_uncollapsed_verbose_section():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Development and Testing\n\n"
        "```bash\npip install -e .[dev]\n```\n\n```bash\npytest\n```\n\n```bash\nruff check .\n```\n\n"
        "See [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), and "
        "[the CI workflow](.github/workflows/ci.yml).\n"
    ))
    findings = checks.check_development_testing_collapse(text)
    assert findings and "code block" in findings[0]["reason"]


def test_development_testing_collapse_clean_when_short():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Development and Testing\n\n"
        "Install the dev extras and run the test suite:\n\n```bash\npip install -e .[dev]\n"
        "pytest\n```\n"
    ))
    assert checks.check_development_testing_collapse(text) == []


def test_development_testing_collapse_clean_when_already_collapsed():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Development and Testing\n\n"
        "Install the dev extras and run the test suite.\n\n<details>\n<summary>Full test "
        "matrix</summary>\n\n```bash\npip install -e .[dev]\n```\n\n```bash\npytest\n```\n\n"
        "```bash\nruff check .\n```\n\nSee [AGENTS.md](AGENTS.md) and "
        "[CONTRIBUTING.md](CONTRIBUTING.md).\n\n</details>\n"
    ))
    assert checks.check_development_testing_collapse(text) == []


_SECTION_ISOLATION_BASE = (
    "# Some Product\n\n"
    "## Key Capabilities\n\n- Does a thing.\n\n"
    "## Scope and Limitations\n\n- A limitation.\n\n"
    "## Installation\n\n- Install it.\n"
)


def test_only_sections_changed_clean_when_only_allowed_section_differs():
    old_text = _SECTION_ISOLATION_BASE
    new_text = old_text.replace("- Does a thing.", "- Does a better thing.")
    findings = checks.check_only_sections_changed(old_text, new_text, ["Key Capabilities"])
    assert findings == []


def test_only_sections_changed_flags_unexpected_section_change():
    old_text = _SECTION_ISOLATION_BASE
    new_text = old_text.replace("- Install it.", "- Install it differently.")
    findings = checks.check_only_sections_changed(old_text, new_text, ["Key Capabilities"])
    assert any(f["heading"] == "Installation" for f in findings)


def test_only_sections_changed_allows_preamble_when_declared():
    old_text = _SECTION_ISOLATION_BASE
    new_text = "# Some Product\n\n> A new blockquote.\n\n" + old_text.split("\n\n", 1)[1]
    findings = checks.check_only_sections_changed(old_text, new_text, ["__preamble__"])
    assert findings == []


def test_only_sections_changed_flags_preamble_when_not_declared():
    old_text = _SECTION_ISOLATION_BASE
    new_text = "# Some Product\n\n> A new blockquote.\n\n" + old_text.split("\n\n", 1)[1]
    findings = checks.check_only_sections_changed(old_text, new_text, ["Key Capabilities"])
    assert any(f["heading"] == "__preamble__" for f in findings)


def test_only_sections_changed_flags_section_added_or_removed():
    old_text = _SECTION_ISOLATION_BASE
    new_text = old_text + "\n## Third-Party Notices\n\n- Some notice.\n"
    findings = checks.check_only_sections_changed(old_text, new_text, ["Key Capabilities"])
    assert any(f["heading"] == "Third-Party Notices" for f in findings)


def test_only_sections_changed_clean_when_identical():
    assert checks.check_only_sections_changed(
        _SECTION_ISOLATION_BASE, _SECTION_ISOLATION_BASE, []
    ) == []


# --- Fifteenth incident / MT030: old-README content-unit verify-and-merge ----------------------
# Fixtures built directly from the real survey evidence (words/net's origin story, pdf/cpp's
# font-fallback rationale, note/python's pypdf dependency and "Official Aspose project" claim)
# that motivated this design, not synthetic placeholders.

_PDF_CPP_OLD_README = """# Aspose.PDF FOSS for C++

The official open-source C++ library for PDF processing.

## Standard-14 fonts

References to `/Helvetica`, `/Times-Roman`, `/Courier` without an embedded `/FontFile` paint
correctly via system fonts, falling back to the bundled Liberation substitutes (SIL OFL 1.1) so
glyphs render even in fontless Linux/CI containers.

## Installation

```bash
cmake --preset default
```
"""


def test_extract_old_readme_content_units_real_pdf_cpp_case():
    # Regression fixture: the real pdf/cpp mechanism-level explanation the Fifteenth incident's
    # own survey found compressed to a bare fact with no rationale in the new candidate.
    units = checks.extract_old_readme_content_units(_PDF_CPP_OLD_README)
    excerpts = [u["excerpt"] for u in units]
    assert any("fontless Linux/CI containers" in e for e in excerpts)
    # Heading lines (H1 and H2) must never become content units of their own.
    assert not any(e.startswith("#") for e in excerpts)
    # The fenced cmake block must not leak into a content unit.
    assert not any("cmake --preset" in e for e in excerpts)
    fallback_unit = next(u for u in units if "fontless Linux/CI containers" in u["excerpt"])
    assert "SIL" in fallback_unit["salient_tokens"]  # real ALLCAPS token from "(SIL OFL 1.1)"
    assert fallback_unit["likely_category_1_prefilter"] is False


def test_extract_old_readme_content_units_drops_short_noise():
    text = "# Title\n\n---\n\nOk.\n\nA real sentence long enough to become a content unit.\n"
    units = checks.extract_old_readme_content_units(text)
    excerpts = [u["excerpt"] for u in units]
    assert not any(e in ("---", "Ok.") for e in excerpts)
    assert any("real sentence long enough" in e for e in excerpts)


def test_extract_old_readme_content_units_keeps_short_substantive_bullets():
    # Regression test: found live 2026-08-10 (MT030 Phase 2) -- the original flat
    # len(excerpt) < 25 noise filter silently dropped these exact real, short capability
    # bullets from cells/cpp's and cells/java's old READMEs (confirmed independently on both
    # products -- 9 real bullets lost total). The fix (a 4+-letter-word requirement, replacing
    # the character-count floor) must keep every one of these while the noise test above still
    # correctly drops "---"/"Ok.".
    text = (
        "# Title\n\n"
        "## Supported Features\n\n"
        "- Merged cells\n"
        "- Defined names\n"
        "- Hyperlinks\n"
        "- Data validation\n"
        "- Conditional formatting\n"
        "- Page setup\n"
        "- Worksheet protection\n"
        "- Cells and formulas\n"
        "- Document properties\n"
    )
    units = checks.extract_old_readme_content_units(text)
    excerpts = {u["excerpt"] for u in units}
    for bullet in (
        "- Merged cells", "- Defined names", "- Hyperlinks", "- Data validation",
        "- Conditional formatting", "- Page setup", "- Worksheet protection",
        "- Cells and formulas", "- Document properties",
    ):
        assert bullet in excerpts, f"{bullet!r} (len={len(bullet)}) was incorrectly dropped as noise"


def test_extract_old_readme_content_units_strips_badge_rows():
    text = (
        "# Title\n\n"
        "[![CI](https://img.shields.io/badge/CI-passing-green)](https://example.com/ci)\n\n"
        "A real sentence describing the project in enough detail to count as a unit.\n"
    )
    units = checks.extract_old_readme_content_units(text)
    assert not any("img.shields.io" in u["excerpt"] for u in units)


def test_extract_old_readme_content_units_flags_narrative_cta_prefilter():
    # Real motivating case: words/net's "Star it" call-to-action prose.
    text = (
        "# Title\n\n"
        "This is not the final shape of the project, and the boundary is not set in stone. "
        "Star it ⭐ -- stars are how GitHub decides whether anyone else discovers it!\n"
    )
    units = checks.extract_old_readme_content_units(text)
    assert len(units) == 1
    assert units[0]["likely_category_1_prefilter"] is True


def test_extract_old_readme_content_units_splits_pure_bullet_block():
    text = (
        "# Title\n\n"
        "- Install the `pypdf` package for semantic PDF golden tests to run correctly here.\n"
        "- A second, unrelated bullet with its own distinct real technical claim included.\n"
    )
    units = checks.extract_old_readme_content_units(text)
    assert len(units) == 2
    assert any("pypdf" in u["salient_tokens"] for u in units)


_NOTE_PYTHON_OFFICIAL_CLAIM = (
    "✅ **Official Aspose project** -- 100% free and open-source, with no hidden costs."
)


def _content_unit(unit_id="u0001", excerpt="A real, checkable technical claim about `Widget`.",
                   salient_tokens=("Widget",), classification="2_mechanism_explanation",
                   disposition="merged_reframed", target_section="Scope and Limitations",
                   evidence_status="verified_against_source", evidence_type="clone_cache_path",
                   evidence_ref="src/widget.py", excluded_reason=None):
    return {
        "unit_id": unit_id,
        "source": "clone_cache/README.md",
        "excerpt": excerpt,
        "salient_tokens": list(salient_tokens),
        "classification": classification,
        "classification_basis": "test fixture",
        "verification": {
            "status": evidence_status, "evidence_type": evidence_type, "evidence_ref": evidence_ref,
        },
        "disposition": disposition,
        "target_section": target_section,
        "excluded_reason": excluded_reason,
    }


# --- check_content_unit_disposition_coverage (hard gate) ----------------------------------------


def test_disposition_coverage_clean_when_every_unit_has_a_valid_entry():
    units = [{"unit_id": "u0001"}]
    dispositions = [_content_unit()]
    assert checks.check_content_unit_disposition_coverage(units, dispositions) == []


def test_disposition_coverage_flags_missing_entry():
    units = [{"unit_id": "u0001"}, {"unit_id": "u0002"}]
    dispositions = [_content_unit(unit_id="u0001")]
    findings = checks.check_content_unit_disposition_coverage(units, dispositions)
    assert any(f["unit_id"] == "u0002" for f in findings)


def test_disposition_coverage_flags_dangling_unit_id_reference():
    units = [{"unit_id": "u0001"}]
    dispositions = [_content_unit(unit_id="u0001"), _content_unit(unit_id="u9999")]
    findings = checks.check_content_unit_disposition_coverage(units, dispositions)
    assert any(f["unit_id"] == "u9999" for f in findings)


def test_disposition_coverage_flags_duplicate_entry():
    units = [{"unit_id": "u0001"}]
    dispositions = [_content_unit(unit_id="u0001"), _content_unit(unit_id="u0001")]
    findings = checks.check_content_unit_disposition_coverage(units, dispositions)
    assert any("duplicate" in f["reason"] for f in findings)


def test_disposition_coverage_flags_invalid_classification_and_disposition():
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(unit_id="u0001", classification="not_a_real_category")
    entry["disposition"] = "not_a_real_disposition"
    findings = checks.check_content_unit_disposition_coverage(units, [entry])
    assert any("classification" in f["reason"] for f in findings)
    assert any("disposition" in f["reason"] for f in findings)


def test_disposition_coverage_flags_merged_entry_with_bad_target_section():
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(unit_id="u0001", target_section="Not A Real Section")
    findings = checks.check_content_unit_disposition_coverage(units, [entry])
    assert any("target_section" in f["reason"] for f in findings)


def test_disposition_coverage_flags_excluded_entry_with_thin_reason():
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(
        unit_id="u0001", disposition="excluded", target_section=None, excluded_reason="stale",
        classification="1_narrative_cta", evidence_status="not_applicable_category_1",
        evidence_type=None, evidence_ref=None,
    )
    findings = checks.check_content_unit_disposition_coverage(units, [entry])
    assert any("excluded_reason" in f["reason"] for f in findings)


def test_disposition_coverage_flags_category_1_verification_status_misuse():
    # A non-category-1 classification must never use not_applicable_category_1 -- every real,
    # checkable claim needs real evidence, merged or excluded.
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(
        unit_id="u0001", classification="2_mechanism_explanation",
        evidence_status="not_applicable_category_1", evidence_type=None, evidence_ref=None,
    )
    findings = checks.check_content_unit_disposition_coverage(units, [entry])
    assert any("only category-1" in f["reason"] for f in findings)


def test_disposition_coverage_flags_missing_evidence_ref():
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(unit_id="u0001", evidence_ref=None)
    findings = checks.check_content_unit_disposition_coverage(units, [entry])
    assert any("evidence_ref" in f["reason"] for f in findings)


def test_disposition_coverage_vacuous_pass_when_no_content_units():
    assert checks.check_content_unit_disposition_coverage([], []) == []


# --- check_content_unit_evidence_resolves (hard gate) --------------------------------------------


def test_evidence_resolves_clean_when_clone_cache_path_exists(tmp_path):
    (tmp_path / "widget.py").write_text("class Widget: pass\n", encoding="utf-8")
    dispositions = [_content_unit(evidence_ref="widget.py")]
    assert checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path)) == []


def test_evidence_resolves_flags_dangling_clone_cache_path(tmp_path):
    dispositions = [_content_unit(evidence_ref="does_not_exist.py")]
    findings = checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path))
    assert any(f["unit_id"] == "u0001" for f in findings)


def test_evidence_resolves_clean_for_package_registry_field(tmp_path):
    registry = {"cells": {"python": {"candidate": "aspose-cells-foss"}}}
    dispositions = [_content_unit(
        evidence_type="package_registry_field", evidence_ref="cells.python.candidate",
    )]
    assert checks.check_content_unit_evidence_resolves(
        dispositions, str(tmp_path), package_registry=registry
    ) == []


def test_evidence_resolves_flags_missing_package_registry_field(tmp_path):
    dispositions = [_content_unit(
        evidence_type="package_registry_field", evidence_ref="cells.python.candidate",
    )]
    findings = checks.check_content_unit_evidence_resolves(
        dispositions, str(tmp_path), package_registry={}
    )
    assert findings


def test_evidence_resolves_clean_for_docs_reference(tmp_path):
    dispositions = [_content_unit(evidence_type="docs_reference", evidence_ref="docs/testing.md")]
    findings = checks.check_content_unit_evidence_resolves(
        dispositions, str(tmp_path), docs_texts={"docs/testing.md": "real content"}
    )
    assert findings == []


def test_evidence_resolves_flags_missing_docs_reference(tmp_path):
    dispositions = [_content_unit(evidence_type="docs_reference", evidence_ref="docs/testing.md")]
    findings = checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path), docs_texts={})
    assert findings


def test_evidence_resolves_candidate_section_reference_always_resolves(tmp_path):
    dispositions = [_content_unit(
        evidence_type="candidate_section_reference", evidence_ref="Scope and Limitations",
    )]
    assert checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path)) == []


def test_evidence_resolves_flags_unrecognized_evidence_type(tmp_path):
    dispositions = [_content_unit(evidence_type="something_made_up", evidence_ref="x")]
    findings = checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path))
    assert any("unrecognized" in f["reason"] for f in findings)


def test_evidence_resolves_skips_category_1_entries(tmp_path):
    dispositions = [_content_unit(
        classification="1_narrative_cta", disposition="excluded", target_section=None,
        evidence_status="not_applicable_category_1", evidence_type=None, evidence_ref=None,
        excluded_reason="pure narrative, nothing to verify against source code here",
    )]
    assert checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path)) == []


# --- check_content_unit_merged_into_target_section (hard gate) ----------------------------------

_MERGE_TARGET_README = (
    "# Some Product\n\n"
    "## Scope and Limitations\n\n"
    "- `Widget` has a documented gap in one edge case, see the real source for detail.\n"
    "\n## Installation\n\n- pip install real-package\n"
)


def test_merge_into_target_section_clean_when_token_present():
    dispositions = [_content_unit(salient_tokens=("Widget",), target_section="Scope and Limitations")]
    assert checks.check_content_unit_merged_into_target_section(_MERGE_TARGET_README, dispositions) == []


def test_merge_into_target_section_flags_untouched_section():
    dispositions = [_content_unit(salient_tokens=("Gizmo",), target_section="Scope and Limitations")]
    findings = checks.check_content_unit_merged_into_target_section(_MERGE_TARGET_README, dispositions)
    assert any(f["unit_id"] == "u0001" for f in findings)


def test_merge_into_target_section_falls_back_to_excerpt_when_no_tokens():
    # The fallback compares the excerpt's own leading text, verbatim, against the section body --
    # deliberately chosen here with no backtick-wrapped identifier in between so the plain-text
    # substring genuinely lines up (the token-based path, tested above, is what handles the
    # more common backtick-formatted case).
    dispositions = [_content_unit(
        excerpt="Some legacy edge case is documented in Scope and Limitations already.",
        salient_tokens=(), target_section="Scope and Limitations",
    )]
    text = (
        "# Some Product\n\n## Scope and Limitations\n\n"
        "Some legacy edge case is documented in Scope and Limitations already, see source for detail.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(text, dispositions)
    assert findings == []


def test_merge_into_target_section_ignores_excluded_entries():
    dispositions = [_content_unit(
        disposition="excluded", target_section=None, salient_tokens=("NeverThere",),
        classification="1_narrative_cta", evidence_status="not_applicable_category_1",
        evidence_type=None, evidence_ref=None, excluded_reason="pure narrative, nothing checkable",
    )]
    assert checks.check_content_unit_merged_into_target_section(_MERGE_TARGET_README, dispositions) == []


def test_merge_into_target_section_maps_intro_to_preamble():
    text = "# Some Product\n\nA branding sentence naming `RealBrand` explicitly.\n\n## Installation\n\n- x\n"
    dispositions = [_content_unit(salient_tokens=("RealBrand",), target_section="Intro")]
    assert checks.check_content_unit_merged_into_target_section(text, dispositions) == []


def test_merge_into_target_section_verifies_redundant_excluded_entries_too():
    # Regression test: found live 2026-08-09 (MT030 Phase 1), independently by 2 of 5 pilot
    # agents (words/net, slides/java) -- check_content_unit_evidence_resolves intentionally
    # treats candidate_section_reference as always-resolved, deferring the real check to THIS
    # function -- but this function originally only ever inspected merged_* dispositions, so a
    # redundant_with_existing claim's cited section was never actually checked by either
    # function. A lazy/wrong "already covered in section X" claim would previously pass
    # silently. Verifies the fix looks at verification.evidence_ref (not target_section, which
    # is null for excluded entries) for this specific evidence_type.
    text = "# Some Product\n\n## Scope and Limitations\n\n- `Widget` has one edge case.\n"
    redundant_entry = _content_unit(
        excerpt="Widget's known edge case is already documented.",
        salient_tokens=("Widget",), classification="redundant_with_existing",
        disposition="excluded", target_section=None,
        evidence_status="verified_redundant", evidence_type="candidate_section_reference",
        evidence_ref="Scope and Limitations",
    )
    assert checks.check_content_unit_merged_into_target_section(text, [redundant_entry]) == []


def test_merge_into_target_section_flags_wrong_redundant_claim():
    text = "# Some Product\n\n## Scope and Limitations\n\n- Something unrelated entirely.\n"
    redundant_entry = _content_unit(
        excerpt="Gizmo's known edge case is already documented.",
        salient_tokens=("Gizmo",), classification="redundant_with_existing",
        disposition="excluded", target_section=None,
        evidence_status="verified_redundant", evidence_type="candidate_section_reference",
        evidence_ref="Scope and Limitations",
    )
    findings = checks.check_content_unit_merged_into_target_section(text, [redundant_entry])
    assert any(f["unit_id"] == "u0001" for f in findings)


def test_merge_into_target_section_ignores_category_1_excluded_entries():
    # A category-1 excluded entry has verification.evidence_type=None (not
    # candidate_section_reference) -- must never be mistaken for a redundant claim needing
    # section verification.
    text = "# Some Product\n\n## Scope and Limitations\n\n- Something unrelated entirely.\n"
    narrative_entry = _content_unit(
        classification="1_narrative_cta", disposition="excluded", target_section=None,
        evidence_status="not_applicable_category_1", evidence_type=None, evidence_ref=None,
        excluded_reason="pure narrative content with nothing checkable",
    )
    assert checks.check_content_unit_merged_into_target_section(text, [narrative_entry]) == []


# --- check_content_unit_no_exact_duplicate_merge (hard gate) ------------------------------------


def test_no_exact_duplicate_merge_clean_when_distinct():
    dispositions = [
        _content_unit(unit_id="u0001", excerpt="First real claim."),
        _content_unit(unit_id="u0002", excerpt="Second, different real claim."),
    ]
    assert checks.check_content_unit_no_exact_duplicate_merge(dispositions) == []


def test_no_exact_duplicate_merge_flags_identical_excerpt_same_section():
    dispositions = [
        _content_unit(unit_id="u0001", excerpt="The exact same claim, word for word."),
        _content_unit(unit_id="u0002", excerpt="The exact same claim, word for word."),
    ]
    findings = checks.check_content_unit_no_exact_duplicate_merge(dispositions)
    assert findings and set(findings[0]["unit_ids"]) == {"u0001", "u0002"}


def test_no_exact_duplicate_merge_does_not_flag_different_sections():
    dispositions = [
        _content_unit(unit_id="u0001", excerpt="Same text.", target_section="Scope and Limitations"),
        _content_unit(unit_id="u0002", excerpt="Same text.", target_section="Development and Testing"),
    ]
    assert checks.check_content_unit_no_exact_duplicate_merge(dispositions) == []


# --- check_content_unit_classification_plausibility (heuristic) ---------------------------------


def test_classification_plausibility_flags_narrative_signal_classified_as_checkable():
    units = [{"unit_id": "u0001", "likely_category_1_prefilter": True}]
    dispositions = [_content_unit(unit_id="u0001", classification="2_mechanism_explanation")]
    findings = checks.check_content_unit_classification_plausibility(units, dispositions)
    assert any(f["unit_id"] == "u0001" for f in findings)


def test_classification_plausibility_flags_checkable_signal_classified_as_narrative():
    units = [{"unit_id": "u0001", "likely_category_1_prefilter": False}]
    dispositions = [_content_unit(
        unit_id="u0001", classification="1_narrative_cta", disposition="excluded",
        target_section=None, evidence_status="not_applicable_category_1",
        evidence_type=None, evidence_ref=None, excluded_reason="pure narrative content here",
    )]
    findings = checks.check_content_unit_classification_plausibility(units, dispositions)
    assert any(f["unit_id"] == "u0001" for f in findings)


def test_classification_plausibility_clean_when_aligned():
    units = [{"unit_id": "u0001", "likely_category_1_prefilter": False}]
    dispositions = [_content_unit(unit_id="u0001", classification="2_mechanism_explanation")]
    assert checks.check_content_unit_classification_plausibility(units, dispositions) == []


# --- check_content_unit_probable_duplicate (heuristic) -------------------------------------------


def test_probable_duplicate_flags_shared_tokens_different_excerpt():
    dispositions = [
        _content_unit(unit_id="u0001", excerpt="Widget supports feature A per RealClass.",
                       salient_tokens=("Widget", "RealClass")),
        _content_unit(unit_id="u0002", excerpt="RealClass and Widget also support feature B.",
                       salient_tokens=("Widget", "RealClass")),
    ]
    findings = checks.check_content_unit_probable_duplicate(dispositions)
    assert findings and set(findings[0]["unit_ids"]) == {"u0001", "u0002"}


def test_probable_duplicate_clean_when_only_one_token_shared():
    dispositions = [
        _content_unit(unit_id="u0001", excerpt="Widget claim one.", salient_tokens=("Widget",)),
        _content_unit(unit_id="u0002", excerpt="A different claim two.", salient_tokens=("Widget", "Other")),
    ]
    assert checks.check_content_unit_probable_duplicate(dispositions) == []


def test_probable_duplicate_skips_exact_duplicates():
    # Exact duplicates are check_content_unit_no_exact_duplicate_merge's job, not this heuristic's.
    dispositions = [
        _content_unit(unit_id="u0001", excerpt="Identical.", salient_tokens=("A", "B")),
        _content_unit(unit_id="u0002", excerpt="Identical.", salient_tokens=("A", "B")),
    ]
    assert checks.check_content_unit_probable_duplicate(dispositions) == []


# --- Sixteenth incident / MT031: category-1 was too coarse -- real history and a real embedded
# fact recovered from otherwise-narrative/CTA prose ------------------------------------------------
# Fixtures are the real, verbatim words/net excerpts (u0021/u0025/u0026) this incident's own
# investigation quoted -- not synthetic placeholders, same discipline as every other content-unit
# fixture in this module.

_WORDS_NET_U0021_REAL_TEXT = (
    "One important thing to know: what's included today is the *minimum*... "
    "It is not the final shape of the project, and the boundary is not set in stone. "
    "If a feature you need sits on the wrong side of it, [open an issue](../../issues) "
    "and tell us about your use case. Where there is real demand, we will consider "
    "opening up more of the code."
)
_WORDS_NET_U0025_REAL_TEXT = (
    "The reduction itself was an interesting engineering project. To carry it out, we "
    "built an internal tool, the Full2Foss agent, developed with the help of "
    "[Claude](https://claude.com), Anthropic's AI assistant. Full2Foss traces which "
    "subsystems each piece of code depends on, cuts what has to go, and keeps thousands "
    "of tests honest along the way."
)
_WORDS_NET_U0026_REAL_TEXT = (
    "That is also why the source is worth a read. This is production code, not a "
    "demonstration. If you have ever wondered what it actually takes to handle Word "
    "documents correctly, it is all in here."
)


def test_embedded_actionable_fact_fires_on_real_u0021_pre_fix_text():
    # The real, original defect this incident exists to catch: u0021 was excluded wholesale as
    # pure narrative/CTA, silently losing the genuine "open an issue to request a currently-
    # excluded capability" fact bundled inside the hedge.
    units = [{"unit_id": "u0021"}]
    dispositions = [_content_unit(
        unit_id="u0021", excerpt=_WORDS_NET_U0021_REAL_TEXT, salient_tokens=(),
        classification="1_narrative_cta", disposition="excluded", target_section=None,
        evidence_status="not_applicable_category_1", evidence_type=None, evidence_ref=None,
        excluded_reason="pure narrative hedging about the project's scope boundary",
    )]
    findings = checks.check_content_unit_embedded_actionable_fact(units, dispositions)
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0021"
    assert "open an issue" in findings[0]["signal_phrase"].lower()


def test_embedded_actionable_fact_silent_on_real_negative_fixtures():
    # u0025 (Full2Foss tooling paragraph) and u0026 (pure editorializing) both stay excluded by
    # direct user decision -- neither contains an embedded actionable fact, and the heuristic
    # must not false-positive on either real text.
    units = [{"unit_id": "u0025"}, {"unit_id": "u0026"}]
    dispositions = [
        _content_unit(
            unit_id="u0025", excerpt=_WORDS_NET_U0025_REAL_TEXT, salient_tokens=("Full2Foss", "Claude"),
            classification="1_narrative_cta", disposition="excluded", target_section=None,
            evidence_status="not_applicable_category_1", evidence_type=None, evidence_ref=None,
            excluded_reason="internal tooling/process detail, zero independent corroboration",
        ),
        _content_unit(
            unit_id="u0026", excerpt=_WORDS_NET_U0026_REAL_TEXT, salient_tokens=(),
            classification="1_narrative_cta", disposition="excluded", target_section=None,
            evidence_status="not_applicable_category_1", evidence_type=None, evidence_ref=None,
            excluded_reason="pure editorializing, nothing checkable",
        ),
    ]
    assert checks.check_content_unit_embedded_actionable_fact(units, dispositions) == []


def test_embedded_actionable_fact_ignores_already_recovered_entries():
    # Once u0021 is correctly reclassified/merged (the actual fix), the same real text must
    # never re-trigger the tripwire -- only whole EXCLUDED category-1 entries are examined.
    units = [{"unit_id": "u0021"}]
    dispositions = [_content_unit(
        unit_id="u0021",
        excerpt="If a capability outside this list would be valuable to you, open an issue "
                "describing your use case -- functionality with enough real demand is a "
                "candidate for future inclusion in this edition.",
        salient_tokens=(), classification="2_mechanism_explanation", disposition="merged_reframed",
        target_section="Scope and Limitations",
    )]
    assert checks.check_content_unit_embedded_actionable_fact(units, dispositions) == []


def test_embedded_actionable_fact_zero_findings_across_real_pilot_negative_shapes():
    # Codifies the design-time validation (fires exactly once on u0021, zero elsewhere across
    # all 5 MT030 Phase 1 pilot products' real, current dispositions) as a committed regression
    # test -- a representative sample of real excluded category-1 excerpts from those products,
    # none containing an actionable signal phrase.
    real_excluded_excerpts = [
        _WORDS_NET_U0025_REAL_TEXT,
        _WORDS_NET_U0026_REAL_TEXT,
        "Most open-source Word libraries start from zero and work their way up the OOXML spec. "
        "This one went the other way.",
        "That is also why the source is worth a read.",
    ]
    units = [{"unit_id": f"u{i:04d}"} for i in range(len(real_excluded_excerpts))]
    dispositions = [
        _content_unit(
            unit_id=f"u{i:04d}", excerpt=excerpt, salient_tokens=(),
            classification="1_narrative_cta", disposition="excluded", target_section=None,
            evidence_status="not_applicable_category_1", evidence_type=None, evidence_ref=None,
            excluded_reason="pure narrative/CTA prose with nothing independently checkable",
        )
        for i, excerpt in enumerate(real_excluded_excerpts)
    ]
    assert checks.check_content_unit_embedded_actionable_fact(units, dispositions) == []


# --- disposition_coverage: 4_verifiable_history / verified_by_corroboration pairing (MT031) ------


def test_disposition_coverage_flags_history_without_corroboration_status():
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(
        unit_id="u0001", classification="4_verifiable_history", target_section="Project History",
        evidence_status="verified_against_source",
    )
    findings = checks.check_content_unit_disposition_coverage(units, [entry])
    assert any("verified_by_corroboration" in f["reason"] for f in findings)


def test_disposition_coverage_flags_corroboration_status_on_non_history_unit():
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(
        unit_id="u0001", classification="2_mechanism_explanation",
        evidence_status="verified_by_corroboration",
    )
    findings = checks.check_content_unit_disposition_coverage(units, [entry])
    assert any("reserved for 4_verifiable_history" in f["reason"] for f in findings)


def test_disposition_coverage_clean_for_verifiable_history_with_corroboration():
    units = [{"unit_id": "u0001"}]
    entry = _content_unit(
        unit_id="u0001", classification="4_verifiable_history", target_section="Project History",
        evidence_status="verified_by_corroboration", evidence_type="clone_cache_path",
        evidence_ref="AGENTS.md",
    )
    assert checks.check_content_unit_disposition_coverage(units, [entry]) == []


# --- Project History (H3) section: preamble-boundary regression (MT031) --------------------------


def test_required_sections_unaffected_by_project_history_section():
    # Project History is a new, permanently OPTIONAL H3 section (never added to
    # _REQUIRED_SECTIONS) placed before the first "##" heading -- confirms its presence changes
    # nothing about the existing required-H2-section gate, a pure regression guard for the ~29
    # products that will never emit this section.
    with_history = _ALL_SECTIONS_README.replace(
        "# Foo\n\n## At a Glance",
        "# Foo\n\n### Project History\n\nA real, checkable history sentence naming `RealTool`.\n\n"
        "## At a Glance",
    )
    assert checks.check_required_sections(with_history) == []
    assert checks.check_required_sections(with_history) == checks.check_required_sections(_ALL_SECTIONS_README)


def test_split_into_sections_keeps_project_history_inside_preamble():
    # H3, not H2, is the load-bearing decision -- _split_into_sections only splits on "^##", so
    # an H3 "### Project History" section must stay merged into "__preamble__" alongside the
    # unheaded Intro paragraph, not become its own section key.
    text = (
        "# Some Product\n\n### Project History\n\nA history sentence.\n\n"
        "An intro paragraph.\n\n## Installation\n\n- x\n"
    )
    sections = checks._split_into_sections(text)
    assert "Project History" not in sections
    assert "### Project History" in sections["__preamble__"]
    assert "A history sentence." in sections["__preamble__"]
    assert "An intro paragraph." in sections["__preamble__"]


def test_merge_into_target_section_maps_project_history_to_preamble():
    text = (
        "# Some Product\n\n### Project History\n\n"
        "A history sentence naming `RealTool` explicitly.\n\n"
        "An intro paragraph.\n\n## Installation\n\n- x\n"
    )
    dispositions = [_content_unit(
        salient_tokens=("RealTool",), classification="4_verifiable_history",
        target_section="Project History", evidence_status="verified_by_corroboration",
        evidence_type="clone_cache_path", evidence_ref="AGENTS.md",
    )]
    assert checks.check_content_unit_merged_into_target_section(text, dispositions) == []


def test_merge_into_target_section_intro_unaffected_by_sibling_project_history():
    # An H3 "### Project History" section sitting alongside the unheaded Intro paragraph must
    # not disturb an unrelated, pre-existing Intro-targeted disposition's own resolution against
    # the same "__preamble__" body -- both real content units share one section key by design.
    text = (
        "# Some Product\n\n### Project History\n\n"
        "A history sentence naming `RealTool` explicitly.\n\n"
        "A branding sentence naming `RealBrand` explicitly.\n\n## Installation\n\n- x\n"
    )
    dispositions = [
        _content_unit(
            unit_id="u0001", salient_tokens=("RealTool",), classification="4_verifiable_history",
            target_section="Project History", evidence_status="verified_by_corroboration",
            evidence_type="clone_cache_path", evidence_ref="AGENTS.md",
        ),
        _content_unit(
            unit_id="u0002", salient_tokens=("RealBrand",), classification="3_branding_positioning",
            target_section="Intro",
        ),
    ]
    assert checks.check_content_unit_merged_into_target_section(text, dispositions) == []

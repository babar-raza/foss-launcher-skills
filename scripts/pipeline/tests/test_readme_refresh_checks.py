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


def test_check_api_reference_intro_names_classes_flags_type_count_filler():
    text = '## API reference\n\nThe library ships 193 public types. Selected entry points:\n\n<details>\n'
    assert checks.check_api_reference_intro_names_classes(text) is True


def test_check_api_reference_intro_names_classes_flags_bare_wildcard():
    text = "## API reference\n\nThe supported public entry point is `aspose.email_foss.msg.*`.\n\n<details>\n"
    assert checks.check_api_reference_intro_names_classes(text) is True


def test_check_api_reference_intro_names_classes_passes_real_hub_class():
    text = "## API reference\n\nThe primary entry point is `Workbook`, which owns a `WorksheetCollection`.\n\n<details>\n"
    assert checks.check_api_reference_intro_names_classes(text) is False


def test_check_api_reference_intro_names_classes_matches_title_cased_heading():
    # Same regression class as check_examples_table_collapsed/check_section_job_distinctness:
    # this section matcher was hardcoded to lowercase "## API reference".
    text = "## API Reference\n\nThe library ships 193 public types. Selected entry points:\n\n<details>\n"
    assert checks.check_api_reference_intro_names_classes(text) is True


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

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
import re
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


# --- check_diagram_label_token_length (MT040, Thirtieth incident, 2026-08-14) ----------------


def test_label_token_length_clean_fixtures_all_pass():
    for name, text in CLEAN_FIXTURES.items():
        assert checks.check_diagram_label_token_length(text) == [], name


def test_label_token_length_flags_a_real_overlong_unbroken_token():
    # A synthetic but realistic overlong single token (no spaces) -- the exact shape of the
    # real, open, unfixed upstream mermaid-js#6424 "Long Words are Cut Off" defect class.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["SupercalifragilisticexpialidociousCollectionManager"]
  end
  subgraph Outputs["Outputs"]
    o1["Out"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_label_token_length(text)
    assert findings and findings[0]["token"] == "SupercalifragilisticexpialidociousCollectionManager"
    assert findings[0]["token_length"] > 28


def test_label_token_length_flags_overlong_container_title():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Cap"]
  end
  subgraph Outputs["OutputsAndAccessibleContentForEveryProducedArtifact"]
    o1["Out"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_label_token_length(text)
    assert findings and findings[0]["node_id"] == "Outputs"


def test_label_token_length_does_not_flag_real_corpus_longest_tokens():
    # The two longest real single-token labels found anywhere in the live 30-product corpus
    # during the MT040 investigation -- both independently confirmed to render cleanly (no
    # overflow) against the real Mermaid renderer. Must never be flagged.
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Named range management (DefinedNameCollection)"]
    c2["Text extraction with TextAbsorber and TextFragmentAbsorber"]
  end
  subgraph Outputs["Outputs"]
    o1["Out"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    assert checks.check_diagram_label_token_length(text) == []


def test_label_token_length_no_mermaid_block_is_vacuous():
    assert checks.check_diagram_label_token_length("# No diagram here\n") == []


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


# --- check_additional_example_headings (readme-refresh-seo-deps-headings-hardening, 2026-08-19) ---


def test_additional_example_headings_flags_zero_heading_markup():
    # The real, confirmed 3d/net defect: plain sentence directly followed by a code fence, no
    # heading at all.
    text = (
        "## Additional Examples\n\nOne example, shown directly.\n\n```python\nx = 1\n```\n\n"
        "<details><summary>View Additional Examples</summary>\n\n"
        "Enumerate a loaded scene's node hierarchy:\n\n```csharp\nfoo();\n```\n\n"
        "Assign a PBR material:\n\n```csharp\nbar();\n```\n\n</details>\n"
    )
    findings = checks.check_additional_example_headings(text)
    assert len(findings) == 2
    assert all("no heading" in f["reason"] or "appears before" in f["reason"] for f in findings)


def test_additional_example_headings_flags_generic_label():
    text = (
        "## Additional Examples\n\nFlagship.\n\n```python\nx = 1\n```\n\n"
        "<details><summary>View Additional Examples</summary>\n\n"
        "### Example 1\n\n```csharp\nfoo();\n```\n\n"
        "### Example\n\n```csharp\nbar();\n```\n\n</details>\n"
    )
    findings = checks.check_additional_example_headings(text)
    reasons = [f["reason"] for f in findings]
    assert any("generic label" in r for r in reasons)
    assert sum("generic label" in r for r in reasons) == 2


def test_additional_example_headings_flags_duplicate_heading():
    text = (
        "## Additional Examples\n\nFlagship.\n\n```python\nx = 1\n```\n\n"
        "<details><summary>View Additional Examples</summary>\n\n"
        "### Convert a Scene to OBJ\n\n```csharp\nfoo();\n```\n\n"
        "### Convert a Scene to OBJ\n\n```csharp\nbar();\n```\n\n</details>\n"
    )
    findings = checks.check_additional_example_headings(text)
    assert any("used more than once" in f["reason"] for f in findings)


def test_additional_example_headings_passes_well_formed_distinct_headings():
    text = (
        "## Additional Examples\n\nFlagship.\n\n```python\nx = 1\n```\n\n"
        "<details><summary>View Additional Examples</summary>\n\n"
        "### Enumerate a Scene's Node Hierarchy\n\n"
        "Enumerate a loaded scene's node hierarchy:\n\n```csharp\nfoo();\n```\n\n"
        "### Convert a Lambert Material to PBR\n\n"
        "Assign a PBR material:\n\n```csharp\nbar();\n```\n\n</details>\n"
    )
    assert checks.check_additional_example_headings(text) == []


def test_additional_example_headings_allows_multiple_code_blocks_under_one_heading():
    # A "before" and "after" snippet sharing one real heading must NOT be treated as a second,
    # headingless example -- the exact false-positive trap a naive "look backward from each
    # code block" design would fall into.
    text = (
        "## Additional Examples\n\nFlagship.\n\n```python\nx = 1\n```\n\n"
        "<details><summary>View Additional Examples</summary>\n\n"
        "### Migrate Legacy Load Options\n\n"
        "Before:\n\n```csharp\nold();\n```\n\nAfter:\n\n```csharp\nnew();\n```\n\n</details>\n"
    )
    assert checks.check_additional_example_headings(text) == []


def test_additional_example_headings_noop_when_no_details_block():
    text = "## Additional Examples\n\nFlagship.\n\n```python\nx = 1\n```\n"
    assert checks.check_additional_example_headings(text) == []


def test_additional_example_headings_noop_when_no_examples_section():
    assert checks.check_additional_example_headings("# Product\n") == []


# --- check_navigation_toc_matches_headings (readme-refresh-forensic-trust-audit-2026-08-25) ----


def test_navigation_toc_matches_headings_noop_when_no_navigation_section():
    text = "# Product\n\n## Installation\n\nInstall it.\n"
    assert checks.check_navigation_toc_matches_headings(text) == []


def test_navigation_toc_matches_headings_flags_missing_entry():
    # The real, confirmed defect class: a real "## Dependencies" heading with no matching
    # Navigation bullet (found live on note/python and 8 other products, 9/31).
    text = (
        "## Navigation\n\n- [Installation](#installation)\n\n"
        "## Installation\n\nInstall it.\n\n"
        "## Dependencies\n\n- `requests`\n"
    )
    findings = checks.check_navigation_toc_matches_headings(text)
    assert findings == [{"heading": "Dependencies", "kind": "missing_from_navigation"}]


def test_navigation_toc_matches_headings_flags_orphaned_entry():
    # A Navigation bullet naming a heading that was renamed/removed and never cleaned up.
    text = (
        "## Navigation\n\n- [Installation](#installation)\n- [Old Section](#old-section)\n\n"
        "## Installation\n\nInstall it.\n"
    )
    findings = checks.check_navigation_toc_matches_headings(text)
    assert findings == [{"heading": "Old Section", "kind": "orphaned_navigation_entry"}]


def test_navigation_toc_matches_headings_passes_when_fully_matched():
    text = (
        "## Navigation\n\n- [At a Glance](#at-a-glance)\n- [Installation](#installation)\n\n"
        "## At a Glance\n\nOverview.\n\n"
        "## Installation\n\nInstall it.\n"
    )
    assert checks.check_navigation_toc_matches_headings(text) == []


def test_navigation_toc_matches_headings_ignores_h3_subheadings():
    # Navigation only tracks real ## (H2) sections in this portfolio's convention -- an H3
    # subsection is never expected to have its own Navigation entry.
    text = (
        "## Navigation\n\n- [Installation](#installation)\n\n"
        "## Installation\n\n### Prerequisites\n\nInstall it.\n"
    )
    assert checks.check_navigation_toc_matches_headings(text) == []


def test_navigation_toc_matches_headings_flags_both_missing_and_orphaned_together():
    text = (
        "## Navigation\n\n- [Old Section](#old-section)\n\n"
        "## Installation\n\nInstall it.\n"
    )
    findings = checks.check_navigation_toc_matches_headings(text)
    kinds = {(f["heading"], f["kind"]) for f in findings}
    assert kinds == {
        ("Installation", "missing_from_navigation"),
        ("Old Section", "orphaned_navigation_entry"),
    }


# --- check_api_reference_detail_collapsed (2026-08-15, MT045, TC-HARDEN-67) -----------------------


def test_api_reference_detail_collapsed_flags_real_barcode_python_table_only_shape():
    # Real, captured shape: barcode/python's own defective candidate has NO curated member
    # bullets -- table-only (module table + Enumerations subsection), fully expanded, zero
    # <details> tags anywhere in the section. This is the primary, real proof case, not a
    # hypothetical table+bullets fixture.
    text = (
        "## API Reference\n\n"
        "`Barcode` is the primary entry point: it is returned by `generate()` and every "
        "per-symbology helper.\n\n"
        "### Core API\n\n"
        "| Class | Description |\n|---|---|\n"
        "| `Barcode` | The public barcode object returned by every encoding helper. |\n\n"
        "#### Enumerations\n\n"
        "| Enumeration | Description |\n|---|---|\n"
        "| `Code128EncodeMode` | Code 128 Code Set selection. |\n\n"
        "## Documentation & Resources\n"
    )
    findings = checks.check_api_reference_detail_collapsed(text)
    assert findings and "not inside a <details> block" in findings[0]["reason"]


def test_api_reference_detail_collapsed_flags_table_plus_bullets_general_case():
    text = (
        "## API Reference\n\n"
        "`Workbook` is the primary entry point.\n\n"
        "| Class | Description |\n|---|---|\n| `Workbook` | The workbook object. |\n\n"
        "- `Workbook` -- open, save, and manage worksheets.\n\n"
        "## Documentation & Resources\n"
    )
    findings = checks.check_api_reference_detail_collapsed(text)
    assert findings and "not inside a <details> block" in findings[0]["reason"]

    fixed = (
        "## API Reference\n\n"
        "`Workbook` is the primary entry point.\n\n"
        "<details><summary>View the Full API Surface</summary>\n\n"
        "| Class | Description |\n|---|---|\n| `Workbook` | The workbook object. |\n\n"
        "- `Workbook` -- open, save, and manage worksheets.\n\n"
        "</details>\n\n"
        "## Documentation & Resources\n"
    )
    assert checks.check_api_reference_detail_collapsed(fixed) == []


def test_api_reference_detail_collapsed_passes_smallest_real_surface_size_independence_proof():
    # Size-independence proof: a genuinely small (11-class-shaped, tex/python-style) table
    # still must collapse -- the rule is deterministic and unconditional, never a row-count
    # threshold.
    text = (
        "## API Reference\n\n"
        "`TeXJob` is the primary entry point.\n\n"
        "<details><summary>View the Full API Surface</summary>\n\n"
        "| Class | Description |\n|---|---|\n| `TeXJob` | Compiles a TeX document. |\n\n"
        "</details>\n\n"
        "## Documentation & Resources\n"
    )
    assert checks.check_api_reference_detail_collapsed(text) == []


def test_api_reference_detail_collapsed_noop_when_no_detail_content():
    text = (
        "## API Reference\n\n"
        "`Workbook` is the primary entry point in this library.\n\n"
        "## Documentation & Resources\n"
    )
    assert checks.check_api_reference_detail_collapsed(text) == []


def test_api_reference_detail_collapsed_no_false_positive_on_ordinary_prose():
    # A plain intro sentence naming real classes mid-prose, outside any table/bullet, must
    # never trip the collapse gate.
    text = (
        "## API Reference\n\n"
        "This library exposes `Workbook` and `Worksheet` as its primary entry points, along "
        "with a small set of helper classes for styling and formulas.\n\n"
        "## Documentation & Resources\n"
    )
    assert checks.check_api_reference_detail_collapsed(text) == []


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
## Dependencies
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


# --- check_enterprise_edition_anchor_matches_relationship (TC-HARDEN-62, MT043, Thirty-Third
# incident; CORRECTED 2026-08-14, MT044, Thirty-Fourth incident) -----------------------------------
# Trigger: cells/typescript's real, live candidate linked "Aspose.Cells for .NET -- Enterprise
# Edition" to a family-level URL that has nothing specifically to do with .NET -- both check_
# enterprise_edition_naming (anchor text/context) and check_enterprise_edition_link_resolves
# (href-vs-verified-target) passed this cleanly, since neither ever checked the anchor's own
# PLATFORM CLAIM against what the resolved destination actually represents.
# MT044 correction: MT043's own fix then went too far the other way -- it REQUIRED a "via
# {language}" qualifier plus a disclosure sentence for any compound/bridge URL, exposing exactly
# the implementation-bridge detail the plan now permanently forbids. The "exact"/"bridge" split
# is gone; both collapse into one "platform" relationship using only a normalized, public-facing
# `public_platform` name -- never an implementation qualifier.


def test_enterprise_anchor_relationship_flags_the_real_cells_typescript_defect():
    text = ("This limitation does not apply to [Aspose.Cells for .NET — Enterprise Edition]"
            "(https://products.aspose.com/cells/), which adds full production support.")
    enterprise_link = {
        "url": "https://products.aspose.com/cells/", "relationship": "family",
        "public_platform": None,
    }
    findings = checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link)
    assert len(findings) == 1
    assert findings[0]["reason"] == "platform_claim_on_family_link"


def test_enterprise_anchor_relationship_flags_words_net_family_shape():
    # A second, real, confirmed instance of the same defect class -- different platform name,
    # identical root cause (a family destination, a platform-specific anchor).
    text = "See [Aspose.Words for .NET — Enterprise Edition](https://products.aspose.com/words/)."
    enterprise_link = {
        "url": "https://products.aspose.com/words/", "relationship": "family",
        "public_platform": None,
    }
    findings = checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link)
    assert len(findings) == 1
    assert findings[0]["reason"] == "platform_claim_on_family_link"


def test_enterprise_anchor_relationship_passes_real_family_neutral_anchor():
    text = "See [Aspose.Cells — Enterprise Edition](https://products.aspose.com/cells/)."
    enterprise_link = {
        "url": "https://products.aspose.com/cells/", "relationship": "family",
        "public_platform": None,
    }
    assert checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link) == []


def test_enterprise_anchor_relationship_passes_platform_only_anchor_for_compound_url():
    # Real, confirmed shape: cells/python resolves to a real compound (python-net) URL. Under the
    # CORRECTED contract, the anchor names only "Python" -- no bridge qualifier, no disclosure
    # prose required or permitted. This is the exact real cells/python content this session
    # already published under the corrected wording.
    text = ("See [Aspose.Cells for Python — Enterprise Edition]"
            "(https://products.aspose.com/cells/python-net/), which adds full production support.")
    enterprise_link = {
        "url": "https://products.aspose.com/cells/python-net/", "relationship": "platform",
        "public_platform": "Python",
    }
    assert checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link) == []


def test_enterprise_anchor_relationship_flags_bridge_wording_as_wrong_platform_name():
    # The old, now-forbidden "for Python via .NET" form must fail under the new contract too --
    # ".NET" is a "wrong_platform_name" the anchor must not carry (the bridge-disclosure PROSE
    # half of this defect is caught separately by check_no_implementation_bridge_disclosure).
    text = ("See [Aspose.Cells for Python via .NET — Enterprise Edition]"
            "(https://products.aspose.com/cells/python-net/), which adds full production support.")
    enterprise_link = {
        "url": "https://products.aspose.com/cells/python-net/", "relationship": "platform",
        "public_platform": "Python",
    }
    findings = checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link)
    reasons = {f["reason"] for f in findings}
    assert "wrong_platform_name" in reasons


def test_enterprise_anchor_relationship_passes_real_platform_shape_exact_slug():
    # Real, already-correct, already-shipped shape -- cells/java resolves to the real, exact
    # cells/java/ platform page. Proves the fix doesn't regress the already-clean products.
    text = "See [Aspose.Cells for Java — Enterprise Edition](https://products.aspose.com/cells/java/)."
    enterprise_link = {
        "url": "https://products.aspose.com/cells/java/", "relationship": "platform",
        "public_platform": "Java",
    }
    assert checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link) == []


def test_enterprise_anchor_relationship_flags_wrong_platform_name():
    text = "See [Aspose.Cells for Python — Enterprise Edition](https://products.aspose.com/cells/java/)."
    enterprise_link = {
        "url": "https://products.aspose.com/cells/java/", "relationship": "platform",
        "public_platform": "Java",
    }
    findings = checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link)
    reasons = {f["reason"] for f in findings}
    assert "missing_platform_name" in reasons
    assert "wrong_platform_name" in reasons


def test_enterprise_anchor_relationship_flags_unresolved_relationship():
    text = "See [Aspose.Cells Enterprise Edition](https://products.aspose.com/cells/mystery/)."
    enterprise_link = {
        "url": "https://products.aspose.com/cells/mystery/", "relationship": "unresolved",
        "public_platform": None,
    }
    findings = checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link)
    assert len(findings) == 1
    assert findings[0]["reason"] == "no_classifiable_relationship"


def test_enterprise_anchor_relationship_flags_when_no_relationship_at_all():
    text = "See [Aspose.Cells Enterprise Edition](https://products.aspose.com/cells/whatever/)."
    findings = checks.check_enterprise_edition_anchor_matches_relationship(text, {"relationship": None})
    assert len(findings) == 1
    assert findings[0]["reason"] == "no_classifiable_relationship"


def test_enterprise_anchor_relationship_ignores_non_enterprise_links():
    assert checks.check_enterprise_edition_anchor_matches_relationship(_ASPOSE_ORG_LINK, None) == []


# --- check_no_implementation_bridge_disclosure (MT044 replacement for TC-HARDEN-62's own
# "missing_bridge_disclosure" requirement, Thirty-Fourth incident, 2026-08-14) ----------------------
# Portfolio-wide, document-wide -- not scoped to the Enterprise-link paragraph. Fixtures use real,
# captured-verbatim forbidden phrasings from the mission brief plus the 9 real bridge-wording
# instances found in the two-tree audit.


def test_no_implementation_bridge_disclosure_flags_via_language():
    text = "Aspose.Email for Python via .NET — Enterprise Edition adds full production support."
    findings = checks.check_no_implementation_bridge_disclosure(text)
    assert len(findings) == 1
    assert findings[0]["reason"] == "implementation_bridge_disclosure"


def test_no_implementation_bridge_disclosure_flags_implemented_through():
    text = "This edition is implemented through .NET rather than a pure Python engine."
    findings = checks.check_no_implementation_bridge_disclosure(text)
    assert len(findings) >= 1


def test_no_implementation_bridge_disclosure_flags_backed_by():
    text = "The Go edition is backed by C++ under the hood."
    findings = checks.check_no_implementation_bridge_disclosure(text)
    assert len(findings) == 1


def test_no_implementation_bridge_disclosure_flags_wrapper_around():
    text = "It is essentially a wrapper around the Java implementation."
    findings = checks.check_no_implementation_bridge_disclosure(text)
    assert len(findings) == 1


def test_no_implementation_bridge_disclosure_flags_binding_to():
    text = "The Node.js package is a binding to the underlying C++ engine."
    findings = checks.check_no_implementation_bridge_disclosure(text)
    assert len(findings) == 1


def test_no_implementation_bridge_disclosure_flags_rather_than_native():
    text = "API implemented via .NET rather than as a native Python engine."
    findings = checks.check_no_implementation_bridge_disclosure(text)
    # "via .NET" and "rather than as a native" both match -- at least one finding, both patterns
    # individually confirmed elsewhere; this fixture proves the compound real-world sentence fires.
    assert len(findings) >= 1


def test_no_implementation_bridge_disclosure_silent_on_clean_text():
    text = ("Aspose.Cells for Python — Enterprise Edition adds full production support and "
            "broader format coverage. See the Quick Start example below for usage.")
    assert checks.check_no_implementation_bridge_disclosure(text) == []


def test_no_implementation_bridge_disclosure_ignores_fenced_code():
    # A real code identifier containing "via" phrasing inside a fenced block must never trip this
    # -- fenced content is stripped first, matching this module's own established convention.
    text = "```python\n# implemented via .NET internally, see docs\nprint('hi')\n```"
    assert checks.check_no_implementation_bridge_disclosure(text) == []


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


def test_check_process_narration_smells_flags_internal_comparison_finding():
    # 2026-08-13 (cells/cpp healing pass): defense-in-depth for the exact real incident text --
    # even with the upstream-issues.md filename stripped out, the underlying comparison finding
    # ("this file's own commands don't match the real repo") is still a leak.
    assert checks.check_process_narration_smells(
        "its own build commands reference a `workspace/`-prefixed path layout that does not "
        "match a plain clone of this repository."
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


def test_check_process_narration_smells_flags_generation_mechanism_narration():
    # 2026-08-14 (MT039, Twenty-Ninth incident): "the table/index/section below/above mirrors
    # [source]'s own [structure]" -- describes HOW this document's own section was composed,
    # not a product fact. Real, captured-verbatim shapes across the portfolio.
    assert checks.check_process_narration_smells(
        "The library's reference index lists 80 public types; the table below mirrors its "
        "own module organization for easier lookup."
    )
    assert checks.check_process_narration_smells(
        "The full, generated class index below mirrors `reference.aspose.org`'s own module "
        "grouping."
    )
    assert checks.check_process_narration_smells(
        "The library ships 96 public types, summarized in the module-grouped table below "
        "(mirrors [reference.aspose.org's own class index](https://reference.aspose.org/cells/net/))."
    )
    assert checks.check_process_narration_smells(
        "Every public type is documented across the module-grouped tables below, mirroring "
        "[the full reference](https://reference.aspose.org/pdf/java/)."
    )
    assert checks.check_process_narration_smells(
        "For deeper drill-down, the API Reference section above mirrors the same data."
    )


def test_check_process_narration_smells_flags_grouped_exactly_as():
    assert checks.check_process_narration_smells(
        "Every public class is listed below, grouped exactly as `reference.aspose.org` "
        "organizes them."
    )


def test_check_process_narration_smells_does_not_flag_legitimate_mirror_usage():
    # Negative controls: real, already-shipped uses of "mirror(s)/mirroring" describing a
    # genuine product fact, never this document's own table/index/section structure.
    assert checks.check_process_narration_smells(
        "`MirroredProfile` wraps a color profile with its axes reversed."
    ) == []
    assert checks.check_process_narration_smells(
        "The `HTMLElement` interface mirrors the WHATWG `window.customElements` API."
    ) == []
    assert checks.check_process_narration_smells(
        "`TextPortion` mirrors OperatorCollection but is detached from any page."
    ) == []
    assert checks.check_process_narration_smells(
        "Standard font names use codes mirroring PDF 32000 §12.3.2.2 names."
    ) == []
    assert checks.check_process_narration_smells(
        "The API shape mirrors Aspose.PDF for .NET where natural, and diverges where the "
        "language idiom calls for it."
    ) == []
    assert checks.check_process_narration_smells(
        "(mirrors the project's CI, which runs on Ubuntu and Windows.)"
    ) == []


def test_check_process_narration_smells_widened_upstream_own_pattern():
    # 2026-08-14 (MT039): widened from "repository" alone to also catch "project"/"readme" --
    # a confirmed synonym-evasion instance used the identical shape with a different noun.
    assert checks.check_process_narration_smells(
        "The examples below mirror the upstream project's own usage examples."
    )
    assert checks.check_process_narration_smells(
        "The install steps reproduce the upstream readme's own build instructions."
    )
    # Regression: the original, already-tested "repository" form still fires.
    assert checks.check_process_narration_smells(
        "These are reproduced from its own the upstream repository's own README.md."
    )


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


def test_check_dropped_content_flags_upstream_issues_md_citation():
    # 2026-08-13: real, live defect found on cells/cpp -- a Development and Testing sentence
    # cited upstream-issues.md by name as a pointer for "the corrected commands used above".
    # Neither check_no_upstream_issue_leaked_into_readme (fingerprint-token overlap fell one
    # short of the 2-token threshold, since the cited path was clone-cache-prefixed in
    # upstream-issues.md but bare in the README) nor the pre-existing internal-label patterns
    # caught this -- confirmed live, both returned zero findings against the real defect.
    new_readme = (
        "## Development and Testing\n\n"
        "See [`Nested/README.md`](Nested/README.md) for that option; "
        "see [upstream-issues.md](upstream-issues.md) for the corrected commands used above.\n"
    )
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert any("upstream-issues.md" in label.lower() for label in result["internal_labels"])


def test_check_dropped_content_flags_upstream_issues_md_bare_mention():
    # "cited or summarized" -- a bare, non-linked mention must be caught too, not just a
    # markdown link target.
    new_readme = "## Development and Testing\n\nSee upstream-issues.md for details.\n"
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert any("upstream-issues.md" in label.lower() for label in result["internal_labels"])


def test_check_dropped_content_flags_upstream_issues_md_inside_api_reference_section():
    # MT048 (note/python pilot, 2026-08-15): the real, confirmed shape -- an earlier draft of
    # note/python's real API Reference table cited "upstream-issues.md" by name for the
    # AsposeNoteError re-export gap. check_no_upstream_issue_leaked_into_readme deliberately
    # exempts the whole "## API Reference" section (real class names legitimately recur there),
    # so a bare filename citation placed specifically INSIDE that section is exactly the shape
    # that check cannot catch. This proves the complementary mechanism -- check_dropped_content's
    # internal_labels scan (this function) -- is genuinely unconditional and has NO section
    # exemption, so it still catches this exact shape even where the sibling check would not.
    new_readme = (
        "## API Reference\n\n"
        "| Class | Description |\n|---|---|\n"
        "| `AsposeNoteError` | Not re-exported from the top level; see upstream-issues.md. |\n"
    )
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert any("upstream-issues.md" in label.lower() for label in result["internal_labels"])


def test_check_dropped_content_flags_content_dispositions_json():
    new_readme = "## Scope and Limitations\n\nSee content-dispositions.json for the full record.\n"
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert any("content-dispositions.json" in label.lower() for label in result["internal_labels"])


def test_check_dropped_content_flags_clone_cache_path():
    new_readme = (
        "## Scope and Limitations\n\n"
        "Verified against `runs/.clone_cache/aspose_cells_cpp/README.md`.\n"
    )
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert any(".clone_cache" in label.lower() for label in result["internal_labels"])


def test_check_dropped_content_flags_knowledge_merged_path():
    new_readme = (
        "## Scope and Limitations\n\n"
        "Per `knowledge/cells/cpp/merged/limitations.md`, several classes are unimplemented.\n"
    )
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert any("knowledge/" in label.lower() for label in result["internal_labels"])


def test_check_dropped_content_flags_reports_tree_paths():
    new_readme_a = "## License\n\nSee reports/repo-presenter/cells/cpp/upstream-issues.md.\n"
    result_a = checks.check_dropped_content("Old readme.\n", new_readme_a, "irrelevant")
    assert any("reports/repo-presenter" in label.lower() for label in result_a["internal_labels"])

    new_readme_b = "## License\n\nSee reports/readme_refresh_runs/cells/cpp/manifest.json.\n"
    result_b = checks.check_dropped_content("Old readme.\n", new_readme_b, "irrelevant")
    assert any(
        "reports/readme_refresh_runs" in label.lower() for label in result_b["internal_labels"]
    )


def test_check_dropped_content_internal_artifact_patterns_noop_on_legitimate_content():
    # Regression guard: real, legitimate content (a real target-repo file, a real command)
    # must never trip the new internal-artifact patterns.
    new_readme = (
        "## Development and Testing\n\n"
        "See [`Aspose.Cells.Foss.Cpp.Tests/README.md`](Aspose.Cells.Foss.Cpp.Tests/README.md) "
        "for that option.\n"
    )
    result = checks.check_dropped_content("Old readme.\n", new_readme, "irrelevant")
    assert result["internal_labels"] == []


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


# --- check_banner_asset_exists (readme-refresh-hardening-and-regen-2026-08-30) -----------------


def test_banner_asset_exists_passes_when_file_present(tmp_path):
    (tmp_path / "static" / "media" / "cells" / "cpp").mkdir(parents=True)
    (tmp_path / "static" / "media" / "cells" / "cpp" / "banner-readme.png").write_bytes(b"\x89PNG")
    text = _readme_with_badge_and_banner("cells", "cpp")
    assert checks.check_banner_asset_exists(text, "cells", "cpp", repo_root=tmp_path) == []


def test_banner_asset_exists_flags_missing_file(tmp_path):
    # No static/media directory created at all -- the pdf/typescript reproduction case this
    # check exists for.
    text = _readme_with_badge_and_banner("pdf", "typescript")
    findings = checks.check_banner_asset_exists(text, "pdf", "typescript", repo_root=tmp_path)
    assert findings and "no such file exists on disk" in findings[0]["reason"]
    assert "pdf" in findings[0]["expected_path"] and "typescript" in findings[0]["expected_path"]


def test_banner_asset_exists_checks_the_urls_own_family_platform_not_the_caller_args(tmp_path):
    # Cross-product contamination case: check_banner_present already flags this on its own
    # grounds (URL family/platform != caller's family/platform); this check independently
    # verifies the asset the URL actually names, which is the OTHER product's path, not the
    # caller's -- confirming the two checks are checking genuinely different things, not
    # duplicating each other.
    (tmp_path / "static" / "media" / "email" / "net").mkdir(parents=True)
    (tmp_path / "static" / "media" / "email" / "net" / "banner-readme.png").write_bytes(b"\x89PNG")
    text = _readme_with_badge_and_banner("email", "net")
    assert checks.check_banner_asset_exists(text, "cells", "cpp", repo_root=tmp_path) == []


def test_banner_asset_exists_vacuous_without_a_banner_line():
    text = "# Test Product\n\nNo badge row or banner here.\n"
    assert checks.check_banner_asset_exists(text, "cells", "cpp", repo_root="/nonexistent") == []


def test_banner_asset_exists_vacuous_on_malformed_banner_line():
    text = _readme_with_badge_and_banner(
        "cells", "cpp", banner_line="![Test Product](not-a-real-banner-url.png)",
    )
    # check_banner_present's own job to flag the malformed line -- this check is a no-op here,
    # same convention as check_banner_links_to_homepage above.
    assert checks.check_banner_asset_exists(text, "cells", "cpp", repo_root="/nonexistent") == []


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


def test_api_reference_public_type_count_matches_table_clean_when_counts_agree():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section() + "\nThis package ships 3 public types.\n",
    )
    assert checks.check_api_reference_public_type_count_matches_table(text) == []


def test_api_reference_public_type_count_matches_table_flags_mismatch():
    # Real, confirmed live defect: font/python's Documentation & Resources section states
    # "the complete, browsable reference for all 139 public types" while its own README API
    # Reference table lists a different number of distinct classes -- reproduced here with the
    # default 3-class fixture table standing in for font/python's real (smaller) table.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section() + (
            "\n- **[Full API reference](https://reference.aspose.org/font/python/)** -- the "
            "complete, browsable reference for all 139 public types (the [API reference]"
            "(#api-reference) section above covers the essentials).\n"
        ),
    )
    findings = checks.check_api_reference_public_type_count_matches_table(text)
    assert findings == [{
        "claimed_count": 139, "actual_table_count": 3,
        "reason": "prose claims 139 public types, but the README's own API Reference table "
                  "lists 3 distinct classes -- these two candidate-authored numbers must "
                  "agree with each other",
    }]


def test_api_reference_public_type_count_matches_table_noop_when_no_claim_present():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_api_table_section())
    assert checks.check_api_reference_public_type_count_matches_table(text) == []


def test_api_reference_public_type_count_matches_table_noop_when_no_section():
    text = _wrap("flowchart TD\n  A --> B") + "\nThis package ships 139 public types.\n"
    assert checks.check_api_reference_public_type_count_matches_table(text) == []


def test_api_reference_public_type_count_matches_table_noop_when_table_has_zero_rows():
    # No ground truth to check the prose claim against -- stays a vacuous, non-blocking
    # silence rather than a false positive, matching check_api_reference_table_completeness's
    # own established discipline for the same situation.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section(core_rows=[], interfaces_rows=[]) + (
            "\nThis package ships 139 public types.\n"
        ),
    )
    assert checks.check_api_reference_public_type_count_matches_table(text) == []


def test_api_reference_public_type_count_matches_table_checks_every_restatement_independently():
    # A product may restate the count in more than one place; each restatement is checked on
    # its own, so a correct restatement elsewhere does not mask a wrong one.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=_api_table_section() + (
            "\nThis package ships 3 public types. Elsewhere, docs claim 5 public types.\n"
        ),
    )
    findings = checks.check_api_reference_public_type_count_matches_table(text)
    assert findings == [{
        "claimed_count": 5, "actual_table_count": 3,
        "reason": "prose claims 5 public types, but the README's own API Reference table "
                  "lists 3 distinct classes -- these two candidate-authored numbers must "
                  "agree with each other",
    }]


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


# --- RC-audit-portfolio-runtime-variance-fix: source-file index cache ---------------------------


def test_source_file_index_cache_is_reused_across_calls(tmp_path):
    checks.clear_source_file_index_cache()
    (tmp_path / "widget.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    assert checks._find_class_source_files(tmp_path, "Widget") == [tmp_path / "widget.py"]
    # A file added AFTER the root was first indexed must NOT be picked up -- proves the second
    # call reused the cached index rather than re-walking the filesystem (the whole point of
    # this fix), not merely that both calls happen to return the same answer.
    (tmp_path / "gadget.py").write_text("class Gadget:\n    pass\n", encoding="utf-8")
    assert checks._find_class_source_files(tmp_path, "Gadget") == []
    checks.clear_source_file_index_cache()


def test_clear_source_file_index_cache_forces_a_fresh_scan(tmp_path):
    checks.clear_source_file_index_cache()
    (tmp_path / "widget.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    checks._find_class_source_files(tmp_path, "Widget")  # populate the cache for this root
    (tmp_path / "gadget.py").write_text("class Gadget:\n    pass\n", encoding="utf-8")
    checks.clear_source_file_index_cache()
    assert checks._find_class_source_files(tmp_path, "Gadget") == [tmp_path / "gadget.py"]
    checks.clear_source_file_index_cache()


def test_source_file_index_cache_is_isolated_per_root(tmp_path):
    checks.clear_source_file_index_cache()
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "widget.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    (root_b / "gadget.py").write_text("class Gadget:\n    pass\n", encoding="utf-8")
    assert checks._find_class_source_files(root_a, "Widget") == [root_a / "widget.py"]
    assert checks._find_class_source_files(root_b, "Gadget") == [root_b / "gadget.py"]
    # Cross-root leakage would show up as either finding the other root's class or missing
    # its own -- neither happened, proving the cache key is genuinely per-root.
    assert checks._find_class_source_files(root_a, "Gadget") == []
    assert checks._find_class_source_files(root_b, "Widget") == []
    checks.clear_source_file_index_cache()


def test_module_internal_fan_in_uses_the_same_cached_index_as_find_class_source_files(tmp_path):
    # Regression guard for the defining-file-exclusion logic: _module_internal_fan_in switched
    # from `.resolve()`-based comparison to plain Path equality against the shared cache -- this
    # proves the defining file is still correctly excluded from its own fan-in count.
    checks.clear_source_file_index_cache()
    (tmp_path / "widget.py").write_text(
        "class Widget:\n    pass\n\ndef make() -> Widget:\n    return Widget()\n", encoding="utf-8",
    )
    (tmp_path / "caller.py").write_text("from widget import Widget\nw = Widget()\n", encoding="utf-8")
    fan_in = checks._module_internal_fan_in(str(tmp_path), "Widget")
    # widget.py itself references "Widget" twice more (in make()'s signature/body) but must be
    # excluded as the defining file; only caller.py counts.
    assert fan_in == 1
    checks.clear_source_file_index_cache()


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


# --- check_installation_matches_package_registry: badge-row extension (TC-HARDEN-59, MT042) ------


def test_installation_check_badge_scan_passes_matching_package_version_badge():
    text = (
        "[![PyPI](https://img.shields.io/pypi/v/aspose-email-foss.svg)]"
        "(https://pypi.org/project/aspose-email-foss/) "
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n\n"
        "## Installation\n\n```bash\npython -m pip install aspose-email-foss\n```\n"
    )
    install_info = {
        "fallback_text_required": False, "registry_type": "pypi",
        "candidate": {"name": "aspose-email-foss"},
    }
    assert checks.check_installation_matches_package_registry(text, install_info) == []


def test_installation_check_badge_scan_flags_wrong_package_version_badge():
    text = (
        "[![PyPI](https://img.shields.io/pypi/v/totally-different-package.svg)]"
        "(https://pypi.org/project/totally-different-package/) "
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n\n"
        "## Installation\n\n```bash\npython -m pip install aspose-email-foss\n```\n"
    )
    install_info = {
        "fallback_text_required": False, "registry_type": "pypi",
        "candidate": {"name": "aspose-email-foss"},
    }
    findings = checks.check_installation_matches_package_registry(text, install_info)
    reasons = [f for f in findings if "badge classified" in f["reason"]]
    assert len(reasons) == 1
    assert reasons[0]["expected"] == "aspose-email-foss"


def test_installation_check_badge_scan_ignores_non_package_version_badges():
    text = (
        "[![Contributors](https://img.shields.io/github/contributors/org/repo.svg)]"
        "(https://github.com/org/repo/graphs/contributors) "
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n\n"
        "## Installation\n\n```bash\npython -m pip install aspose-email-foss\n```\n"
    )
    install_info = {
        "fallback_text_required": False, "registry_type": "pypi",
        "candidate": {"name": "aspose-email-foss"},
    }
    assert checks.check_installation_matches_package_registry(text, install_info) == []


def test_installation_check_badge_scan_noop_when_unpublished():
    # fallback_text_required=True -- badge scan must never run (nothing to compare against).
    text = (
        "[![PyPI](https://img.shields.io/pypi/v/totally-wrong.svg)](https://pypi.org/project/totally-wrong/)\n\n"
        "## Installation\n\nA PyPI package has not been published yet. Install from source:\n"
    )
    assert checks.check_installation_matches_package_registry(
        text, {"fallback_text_required": True}
    ) == []


def test_installation_check_badge_scan_noop_when_no_registry_data():
    text = "[![PyPI](https://img.shields.io/pypi/v/whatever.svg)](https://pypi.org/project/whatever/)\n"
    assert checks.check_installation_matches_package_registry(
        text, {"source": "package_registry_missing"}
    ) == []


def test_installation_check_badge_scan_runs_even_with_no_installation_section():
    # A real gap the original Installation-only scan could never catch: a wrong package_version
    # badge with no ## Installation section present at all.
    text = "[![PyPI](https://img.shields.io/pypi/v/totally-wrong.svg)](https://pypi.org/project/totally-wrong/)\n"
    install_info = {
        "fallback_text_required": False, "registry_type": "pypi",
        "candidate": {"name": "aspose-email-foss"},
    }
    findings = checks.check_installation_matches_package_registry(text, install_info)
    assert len(findings) == 1
    assert findings[0]["expected"] == "aspose-email-foss"


# --- check_badge_row_meets_verified_floor / check_badge_available_fact_not_shown (TC-HARDEN-58/
# 59, MT042, Thirty-Second incident) ---------------------------------------------------------------
# Trigger: a real, clean-room `cells/typescript` candidate shipped with a single License badge --
# every other real, currently-shipped candidate in the portfolio has 2-5, zero exceptions. The
# existing badge mechanism is entirely reconciliation-scoped (preserve/dedup an OLD badge) and
# vacuously passes when the old README has zero badges, exactly this case.


def _available(**overrides):
    base = {
        "license": {"available": False, "reason": "n/a"},
        "package_version": {"available": False, "reason": "n/a"},
        "language_version": {"available": False, "reason": "n/a"},
        "ci_build_status": {"available": False, "reason": "n/a"},
        "contributor_count": {"available": False, "reason": "n/a"},
    }
    base.update(overrides)
    return base


def test_badge_floor_flags_the_real_cells_typescript_shape():
    # The real, original defect: License only, while contributor_count is genuinely available
    # (a real, resolvable GitHub repo) and unused.
    text = "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n"
    available = _available(
        license={"available": True},
        contributor_count={"available": True, "alt_text": "Contributors"},
    )
    findings = checks.check_badge_row_meets_verified_floor(text, available)
    assert len(findings) == 1
    assert findings[0]["category"] is None


def test_badge_floor_passes_license_plus_contributors():
    text = (
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) "
        "[![Contributors](https://img.shields.io/github/contributors/org/repo.svg)]"
        "(https://github.com/org/repo/graphs/contributors)\n"
    )
    available = _available(
        license={"available": True}, contributor_count={"available": True},
    )
    assert checks.check_badge_row_meets_verified_floor(text, available) == []


def test_badge_floor_passes_license_plus_ci_instead_of_contributors():
    # Never mandates a SPECIFIC second category -- 6 of 30 real portfolio products use CI/build
    # in this slot instead of Contributors, a legitimate, already-precedented editorial choice.
    text = (
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) "
        "[![Build](https://github.com/org/repo/actions/workflows/ci.yml/badge.svg)]"
        "(https://github.com/org/repo/actions/workflows/ci.yml)\n"
    )
    available = _available(
        license={"available": True}, contributor_count={"available": True},
        ci_build_status={"available": True},
    )
    assert checks.check_badge_row_meets_verified_floor(text, available) == []


def test_badge_floor_flags_missing_license_badge():
    text = "[![Contributors](https://img.shields.io/github/contributors/org/repo.svg)](https://github.com/org/repo/graphs/contributors)\n"
    available = _available(license={"available": True}, contributor_count={"available": True})
    findings = checks.check_badge_row_meets_verified_floor(text, available)
    assert len(findings) == 1
    assert findings[0]["category"] == "license"


def test_badge_floor_vacuous_pass_when_nothing_available():
    # A real, genuinely license-less/repo-unresolvable product -- never fabricate a badge to
    # force a pass, never fail on the absence of a fact this function can't verify either way.
    text = "# Some Product\n"
    assert checks.check_badge_row_meets_verified_floor(text, _available()) == []


def test_badge_available_fact_not_shown_flags_unused_available_category():
    text = "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n"
    available = _available(
        license={"available": True},
        contributor_count={"available": True, "alt_text": "Contributors", "image_url": "x"},
    )
    findings = checks.check_badge_available_fact_not_shown(text, available)
    categories = {f["category"] for f in findings}
    assert "contributor_count" in categories


def test_badge_available_fact_not_shown_silent_when_already_shown():
    text = (
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) "
        "[![Contributors](https://img.shields.io/github/contributors/org/repo.svg)]"
        "(https://github.com/org/repo/graphs/contributors)\n"
    )
    available = _available(license={"available": True}, contributor_count={"available": True})
    assert checks.check_badge_available_fact_not_shown(text, available) == []


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


# --- Thirty-Seventh incident (2026-08-16): Installation/Quick Start leak blind spot ---------

# Real, captured-verbatim upstream-issues.md entry (html/python, trimmed to the BLOCKING entry
# only -- the INFORMATIONAL test-fixture entry is irrelevant to fingerprint extraction since
# only BLOCKING/FUNCTIONAL-DEFECT entries are fingerprinted). This is the exact real entry that
# motivated this incident.
_REAL_HTML_PYTHON_UPSTREAM_ISSUES = """# Upstream issues -- Aspose.HTML FOSS for Python

Verified: 2026-08-13 against `runs/.clone_cache/aspose_html_python/`.

## No `pip install` variant succeeds -- broken build-backend name

- **Severity**: BLOCKING
- **Evidence**: `pyproject.toml`'s `[build-system]` table reads:
  ```toml
  [build-system]
  requires = ["setuptools>=68"]
  build-backend = "setuptools.backends.legacy:build"
  ```
  `setuptools.backends` is not a real module in any released version of setuptools -- the real
  legacy-compatible PEP 517 backend is `setuptools.build_meta:__legacy__` (a `__legacy__` object
  inside the `setuptools.build_meta` module, not a separate `backends` subpackage).
- **Impact**: `pip` resolves and invokes the `[build-system]` table for every install source --
  a local path, an editable local path (`pip install -e .`), or a `git+https` URL -- so every
  one of them fails identically with `ModuleNotFoundError: No module named
  'setuptools.backends'` before any of this package's own code ever runs.
- **Real, working install path**: the repository's own `pyproject.toml` already points pytest at
  `src/` directly (`[tool.pytest.ini_options]` sets `pythonpath = ["src"]`), so the test suite
  never depends on the package being pip-installed. Clone the repository, `pip install` the one
  real runtime dependency (`skia-python>=87.0,<145`), and add `src/` to `PYTHONPATH` instead of
  installing the package itself.
- **Not fixable here**: the broken build-backend string lives in the upstream repository's own
  `pyproject.toml`; a README cannot change another file's contents.
"""

# Reconstructed pre-fix regression shape (this exact wording is not preserved anywhere on disk --
# `reports/` is gitignored and the real orchestrating session's fix landed with no prior commit
# to diff against -- so this rebuilds the incident's own described shape: exact broken
# build-backend string, exact correct value, exact `ModuleNotFoundError` message, and an
# audit-style "every variant fails identically" scope claim) directly from
# `_REAL_HTML_PYTHON_UPSTREAM_ISSUES`'s own Evidence/Impact bullets above, which is how the
# leak is described to have happened -- forensic detail copied out of upstream-issues.md and
# narrated in the README's own Installation section instead of a plain pointer.
_RECONSTRUCTED_HTML_PYTHON_LEAK_INSTALLATION = (
    "## Installation\n\n"
    "A PyPI package has not been published yet. Attempting `pip install` (from a local path, "
    "an editable local path, or a `git+https` URL) fails identically in every case: "
    "`pyproject.toml`'s `[build-system]` table declares "
    '`build-backend = "setuptools.backends.legacy:build"`, but `setuptools.backends` is not a '
    "real module in any released version of setuptools -- the real legacy-compatible backend is "
    "`setuptools.build_meta:__legacy__`, not `setuptools.backends`. As a result, `pip install` "
    "raises `ModuleNotFoundError: No module named 'setuptools.backends'` before any of this "
    "package's own code ever runs. Install by putting the source tree on `PYTHONPATH` directly "
    "instead:\n\n"
    "```bash\n"
    "git clone https://github.com/aspose-html-foss/Aspose.HTML-FOSS-for-Python.git\n"
    "```\n"
)

# The real, current, already-fixed html/python Installation section (verbatim from
# reports/repo-presenter-regen-full/html/python/readme.md, 2026-08-16) -- the orchestrating
# session's own fix, which this new check must NEVER flag.
_REAL_HTML_PYTHON_FIXED_INSTALLATION = (
    "## Installation\n\n"
    "A PyPI package has not been published yet, and `pip install` fails for this repository at "
    "any source (local path, editable local path, or a `git+https` URL) — see "
    "[upstream-issues.md](upstream-issues.md) for the root cause. Until that's fixed upstream, "
    "install by putting the source tree on `PYTHONPATH` directly — the same mechanism the "
    "repository's own test suite already relies on (`pyproject.toml`'s "
    "`[tool.pytest.ini_options]` sets `pythonpath = [\"src\"]`):\n\n"
    "```bash\n"
    "git clone https://github.com/aspose-html-foss/Aspose.HTML-FOSS-for-Python.git\n"
    "cd Aspose.HTML-FOSS-for-Python\n"
    'pip install "skia-python>=87.0,<145"\n'
    "```\n\n"
    "Then add `src/` to `PYTHONPATH` (Linux/macOS: "
    '`export PYTHONPATH="$PWD/src:$PYTHONPATH"`; Windows: '
    "`set PYTHONPATH=%cd%\\src;%PYTHONPATH%`).\n\n"
    "The distribution is named `aspose-html-foss`; the import package is `aspose_html`. The "
    "package requires Python 3.10 or later; `skia-python` (used internally for text-layout "
    "metrics) is its one real runtime dependency. JavaScript execution is optional — "
    "install `quickjs` directly to use it:\n\n"
    "```bash\n"
    'pip install "quickjs>=1.19,<2"\n'
    "```\n"
)

# Real, captured-verbatim words/net BLOCKING entry (trimmed) -- a genuine portfolio example of
# an Installation section that legitimately overlaps 2+ real fingerprint tokens (`dotnet add
# package`, `dotnet build Aspose.Words.sln -c Release`, `Aspose.Words/Aspose.Words.csproj`) with
# zero diagnostic narration -- must never fire.
_REAL_WORDS_NET_UPSTREAM_ISSUES = """# Upstream issues -- Aspose.Words FOSS for .NET

Verified: 2026-08-13 against https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-.NET

## Repo is unbuildable from a clean clone -- missing NuGet package dependency
- **Severity**: BLOCKING
- **Evidence**: `Aspose.Words/Aspose.Words.csproj` carries an unconditional `PackageReference
  Include="Aspose.EnumExtensionsGenerator" Version="1.0.2"`. A live check returns a real HTTP
  404 -- this package has never been published, so `dotnet build Aspose.Words.sln -c Release`
  on a genuinely fresh clone fails at restore with `NU1101`.
- **Impact**: a contributor building from source hits this immediately. Does not affect end
  users -- `Aspose.Words.FOSS` itself is genuinely published on nuget.org, so this candidate's
  Installation section uses `dotnet add package` rather than a from-source build.
- **Not fixable here**: lives entirely in the upstream repository's own project files.
"""

_REAL_WORDS_NET_INSTALLATION = (
    "## Installation\n\n"
    "Install from NuGet:\n\n"
    "```bash\n"
    "dotnet add package Aspose.Words.FOSS\n"
    "```\n\n"
    "Or build from source:\n\n"
    "```bash\n"
    "git clone https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-.NET.git\n"
    "cd Aspose.Words-FOSS-for-.NET\n"
    "dotnet build Aspose.Words.sln -c Release\n"
    "```\n\n"
    "Then reference `Aspose.Words/Aspose.Words.csproj` from your project. The library targets "
    ".NET Standard 2.0, so it runs on .NET Framework 4.6.2+ and .NET 6/8/10, on Windows, Linux, "
    "and macOS.\n"
)

# Real, captured-verbatim slides/cpp Installation section (CMake-based) -- a genuine portfolio
# example with zero fingerprint overlap at all against its own (unrelated, example-code-defect)
# upstream-issues.md entries.
_REAL_SLIDES_CPP_UPSTREAM_ISSUES = """# Upstream issues -- Aspose.Slides FOSS for C++

## README "Notes" example does not compile -- `add_notes_slide()` returns a pointer, not a reference
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: the real README's "Notes" example writes
  `auto& notes = pres.slides()[0].notes_slide_manager().add_notes_slide();`.
  `include/Aspose/Slides/Foss/i_notes_slide_manager.h:19` declares
  `INotesSlide* add_notes_slide()` -- a pointer return, not a reference.
- **Impact**: a developer copy-pasting the README's own Notes example gets a compiler error.
- **Not fixable here**: upstream README example code.
"""

_REAL_SLIDES_CPP_INSTALLATION = (
    "## Installation\n\n"
    "No NuGet package has been published for this library yet — it ships as CMake source "
    "you build and link directly.\n\n"
    "```bash\n"
    "cmake -B build -DCMAKE_BUILD_TYPE=Release\n"
    "cmake --build build\n"
    "```\n\n"
    "Requires a C++20 compiler and CMake 3.20+ (`CMAKE_CXX_STANDARD 20` is set in "
    "`CMakeLists.txt`).\n"
)


def _readme_with_installation(installation_section: str) -> str:
    return (
        "# Some Product\n\n"
        "## At a Glance\n\n"
        "```mermaid\nflowchart TD\n  A --> B\n```\n\n"
        f"{installation_section}\n"
        "## Key Capabilities\n\n- Does a thing.\n"
    )


def test_install_quickstart_leak_flags_reconstructed_regression_shape():
    # (a) the REAL, described pre-fix html/python shape must fire.
    text = _readme_with_installation(_RECONSTRUCTED_HTML_PYTHON_LEAK_INSTALLATION)
    findings = checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, _REAL_HTML_PYTHON_UPSTREAM_ISSUES
    )
    assert findings
    assert findings[0]["heading"] == "Installation"
    assert len(findings[0]["matched_tokens"]) >= 2


def test_install_quickstart_leak_clean_on_real_fixed_html_python_text():
    # (b) the REAL, current, already-fixed html/python text must NOT fire.
    text = _readme_with_installation(_REAL_HTML_PYTHON_FIXED_INSTALLATION)
    assert checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, _REAL_HTML_PYTHON_UPSTREAM_ISSUES
    ) == []


def test_install_quickstart_leak_clean_on_real_words_net_text_despite_token_overlap():
    # (c1) real, legitimate specificity that DOES share 2+ fingerprint tokens with a real
    # BLOCKING entry (`dotnet add package`, `dotnet build Aspose.Words.sln -c Release`,
    # `Aspose.Words/Aspose.Words.csproj`) must still not fire -- no diagnostic narration.
    text = _readme_with_installation(_REAL_WORDS_NET_INSTALLATION)
    findings = checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, _REAL_WORDS_NET_UPSTREAM_ISSUES
    )
    assert findings == []


def test_install_quickstart_leak_clean_on_real_slides_cpp_cmake_text():
    # (c2) real, legitimate CMake specificity with zero fingerprint overlap at all.
    text = _readme_with_installation(_REAL_SLIDES_CPP_INSTALLATION)
    assert checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, _REAL_SLIDES_CPP_UPSTREAM_ISSUES
    ) == []


def test_install_quickstart_leak_clean_on_real_html_python_own_optional_dependency_prose():
    # (c3) real, legitimate specificity for a DIFFERENT part of the same product's own
    # Installation section (the optional `quickjs` extra) -- shares zero fingerprint tokens
    # with the BLOCKING entry, must not fire.
    installation = (
        "## Installation\n\n"
        "JavaScript execution is optional — install `quickjs` directly to use it:\n\n"
        "```bash\n"
        'pip install "quickjs>=1.19,<2"\n'
        "```\n"
    )
    text = _readme_with_installation(installation)
    assert checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, _REAL_HTML_PYTHON_UPSTREAM_ISSUES
    ) == []


def test_install_quickstart_leak_scoped_to_installation_and_quick_start_only():
    # A Scope and Limitations paragraph with the same reconstructed leak text must NOT be
    # caught by this narrow check (that is check_no_upstream_issue_leaked_into_readme's job,
    # for every OTHER section) -- confirms this check really is scoped to just the two named
    # headings, not accidentally scanning the whole document.
    text = (
        "# Some Product\n\n"
        "## At a Glance\n\n"
        "```mermaid\nflowchart TD\n  A --> B\n```\n\n"
        "## Scope and Limitations\n\n"
        + _RECONSTRUCTED_HTML_PYTHON_LEAK_INSTALLATION.replace("## Installation", "").strip()
        + "\n"
    )
    assert checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, _REAL_HTML_PYTHON_UPSTREAM_ISSUES
    ) == []


def test_install_quickstart_leak_noop_without_upstream_issues_text():
    text = _readme_with_installation(_RECONSTRUCTED_HTML_PYTHON_LEAK_INSTALLATION)
    assert checks.check_no_upstream_issue_leaked_into_install_or_quickstart(text, "") == []


def test_install_quickstart_leak_noop_when_no_extractable_fingerprints():
    text = _readme_with_installation(_RECONSTRUCTED_HTML_PYTHON_LEAK_INSTALLATION)
    clean_upstream = "# Upstream issues\n\nNo upstream issues identified during verification.\n"
    assert checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, clean_upstream
    ) == []


def test_install_quickstart_leak_fires_in_quick_start_too():
    # The Quick Start heading gets the same protection as Installation, not just Installation.
    quick_start = (
        "## Quick Start\n\n"
        "Note: `pip install` (from a local path, an editable local path, or a `git+https` URL) "
        "fails identically in every case because `setuptools.backends` is not a real module in "
        "any released version of setuptools -- the real legacy-compatible backend is "
        "`setuptools.build_meta:__legacy__`, not `setuptools.backends`, and `pip install` "
        "raises `ModuleNotFoundError: No module named 'setuptools.backends'` before any of "
        "this package's own code ever runs.\n"
    )
    text = (
        "# Some Product\n\n"
        "## At a Glance\n\n"
        "```mermaid\nflowchart TD\n  A --> B\n```\n\n"
        f"{quick_start}\n"
        "## Key Capabilities\n\n- Does a thing.\n"
    )
    findings = checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
        text, _REAL_HTML_PYTHON_UPSTREAM_ISSUES
    )
    assert findings
    assert findings[0]["heading"] == "Quick Start"


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


# --- check_key_capabilities_structural_variety / check_key_capabilities_formatting -------------
# (TC-HARDEN-40/41, MT037, Twenty-Seventh incident, 2026-08-13)

# Real, captured-shape reproduction of cells/java's own pre-fix Key Capabilities section
# (10 bullets, 8 identifier-first -- the exact ratio that motivated this check).
_CELLS_JAVA_DRY_SHAPE = (
    "- The primary entry point is `Workbook`, which owns a `WorksheetCollection` of "
    "`Worksheet` objects.\n"
    "- `Style` carries a cell's full formatting -- font, borders, fill, alignment, and "
    "number format.\n"
    "- `Row` and `Column` support explicit sizing, hiding, and outline grouping.\n"
    "- Merged cells, defined names, and hyperlinks round-trip through load and save.\n"
    "- `ValidationCollection` applies data validation rules scoped to `CellArea` ranges.\n"
    "- `AutoFilter` supports color filters, dynamic filters, and sort conditions.\n"
    "- `PageSetup` configures page setup and print layout for a worksheet.\n"
    "- `CommentCollection` adds, edits, and removes cell comments with author and text.\n"
    "- `ChartCollection.add()` creates 18 of the 25 real `ChartType` values programmatically.\n"
    "- `CalculationProperties` configures calculation mode and iterative calculation.\n"
)

_VARIED_OPENINGS_SHAPE = (
    "- Open and create Excel workbooks with full round-trip save via `Workbook`.\n"
    "- `Style` carries a cell's full formatting -- font, borders, fill, and alignment.\n"
    "- Merge cells, define names, and add hyperlinks that round-trip through load and save.\n"
    "- `ValidationCollection` applies data validation rules scoped to `CellArea` ranges.\n"
    "- Filter worksheet ranges with color, dynamic, and top-10 filters via `AutoFilter`.\n"
)


def test_key_capabilities_structural_variety_flags_real_cells_java_shape():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_CELLS_JAVA_DRY_SHAPE)
    findings = checks.check_key_capabilities_structural_variety(text)
    assert len(findings) == 1
    assert "8 of 10" in findings[0]["reason"]
    assert len(findings[0]["identifier_first_bullets"]) == 8


def test_key_capabilities_structural_variety_clean_on_varied_openings():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_VARIED_OPENINGS_SHAPE)
    assert checks.check_key_capabilities_structural_variety(text) == []


def test_key_capabilities_structural_variety_boundary_at_70_percent():
    # Exactly 7 of 10 identifier-first -- the ">= 0.7" boundary must fire, not just ">".
    bullets = "".join(f"- `Id{i}` does a real, verified thing with real detail.\n" for i in range(7))
    bullets += "".join(f"- Does a real thing with `Id{i}` involved somewhere in the middle.\n" for i in range(3))
    text = _wrap("flowchart TD\n  A --> B", extra_section=bullets)
    findings = checks.check_key_capabilities_structural_variety(text)
    assert len(findings) == 1
    assert "7 of 10" in findings[0]["reason"]


def test_key_capabilities_structural_variety_noop_without_section():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_CELLS_JAVA_DRY_SHAPE)
    text_no_section = text.replace("## Key capabilities", "## Something Else")
    assert checks.check_key_capabilities_structural_variety(text_no_section) == []


def test_key_capabilities_formatting_flags_unmatched_backtick():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- Loads a file via `Workbook and saves it too.\n",
    )
    findings = checks.check_key_capabilities_formatting(text)
    assert any(f["reason"] == "unmatched backtick in bullet" for f in findings)


def test_key_capabilities_formatting_flags_missing_terminal_punctuation():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- Loads and saves Excel workbooks via `Workbook`\n",
    )
    findings = checks.check_key_capabilities_formatting(text)
    assert any(f["reason"] == "bullet does not end with terminal punctuation" for f in findings)


def test_key_capabilities_formatting_flags_lowercase_bullet_start():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section="- loads and saves Excel workbooks via `Workbook`.\n",
    )
    findings = checks.check_key_capabilities_formatting(text)
    assert any(
        f["reason"] == "bullet starts with a lowercase letter (not a backtick-quoted identifier)"
        for f in findings
    )


def test_key_capabilities_formatting_clean_on_real_well_formed_section():
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- Open and create PDFs with full round-trip save via `Document` and `Page`.\n"
            "- Extract and search text via `TextAbsorber` and `TextFragmentAbsorber`.\n"
            "- Fill and build AcroForm fields via `Form` and `FormEditor`.\n"
        ),
    )
    assert checks.check_key_capabilities_formatting(text) == []


def test_key_capabilities_formatting_handles_wrapped_bullet_without_false_positive():
    # The near-universal real shape: a bullet's closing punctuation lands on a wrapped
    # continuation line, not the opening line -- must not false-positive on either check.
    text = _wrap(
        "flowchart TD\n  A --> B",
        extra_section=(
            "- The primary entry point is `Workbook`, which owns a `WorksheetCollection`\n"
            "  of `Worksheet` objects for reading and writing values.\n"
        ),
    )
    assert checks.check_key_capabilities_formatting(text) == []
    assert checks.check_key_capabilities_structural_variety(text) == []


def test_key_capabilities_formatting_noop_without_section():
    text = _wrap("flowchart TD\n  A --> B", extra_section=_CELLS_JAVA_DRY_SHAPE)
    text_no_section = text.replace("## Key capabilities", "## Something Else")
    assert checks.check_key_capabilities_formatting(text_no_section) == []


# --- check_section_intro_no_meta_narration (MT046, Thirty-Sixth incident, TC-HARDEN-71) ---------

# The real, captured-verbatim font/python sentence that triggered this incident.
_REAL_FONT_PYTHON_META_NARRATION = (
    "Here's what you get — a Capability Snapshot of why teams use it, grouped by real "
    "module rather than by workflow label. Python API Highlights and CLI Highlights are both "
    "covered inline via backtick-quoted class/command names below, and variable-font-first "
    "workflows remain the deepest, most actively developed surface area (`instancing.py` "
    "alone is the largest module in the library)."
)


def test_section_intro_no_meta_narration_flags_real_font_python_sentence():
    text = (
        "## Key Capabilities\n\n"
        f"{_REAL_FONT_PYTHON_META_NARRATION}\n\n"
        "- Loads and edits fonts via `FontLoader.open()`.\n"
    )
    findings = checks.check_section_intro_no_meta_narration(text)
    assert len(findings) == 1
    assert findings[0]["section"] == "Key Capabilities"
    assert findings[0]["matched_phrase"]


def test_section_intro_no_meta_narration_matches_all_three_subpatterns():
    # Direct proof (not merely asserted) that the real sentence trips every one of the three
    # named sub-patterns independently, per this incident's own Validation item 1.
    intro = checks._extract_section_intro_prose(_REAL_FONT_PYTHON_META_NARRATION)
    assert re.search(r"\brather than by\b", intro, re.IGNORECASE)
    assert re.search(r"\bcovered inline\b", intro, re.IGNORECASE)
    assert re.search(
        r"`[\w./-]+\.(?:py)`\s*(?:alone\s+)?is the (?:largest|biggest|smallest)\b",
        intro, re.IGNORECASE,
    )


def test_section_intro_no_meta_narration_clean_on_real_email_cpp_sentence():
    # Real, legitimate, already-shipped portfolio convention: a genuine product-architecture
    # fact ("grouped below by processing layer"), not document-structure commentary. Must
    # never be flagged -- this is the exact negative control that rules out a naive bare
    # "grouped by" pattern.
    text = (
        "## Key Capabilities\n\n"
        "Features are grouped below by processing layer, from low-level CFB container "
        "access up through the high-level `mapi_message` API.\n\n"
        "- Reads and writes CFB storages via `mapi_message`.\n"
    )
    assert checks.check_section_intro_no_meta_narration(text) == []


def test_section_intro_no_meta_narration_clean_on_real_email_python_sentence():
    text = (
        "## Key Capabilities\n\n"
        "The following features are grouped by processing layer, from low-level CFB and "
        "MSG access up through the high-level `MapiMessage` API and its `EmailMessage` "
        "bridge.\n\n"
        "- Reads and writes CFB storages via `MapiMessage`.\n"
    )
    assert checks.check_section_intro_no_meta_narration(text) == []


def test_section_intro_no_meta_narration_clean_on_real_slides_sentence():
    text = (
        "## Key Capabilities\n\n"
        "Features cover the full authoring surface — from presentation I/O and shape "
        "creation to fill, line, and 3D formatting.\n\n"
        "- Opens and saves presentations via `Presentation`.\n"
    )
    assert checks.check_section_intro_no_meta_narration(text) == []


def test_section_intro_no_meta_narration_noop_when_no_intro_sentence():
    # The common, already-correct shape (barcode/python, cells/python): no framing sentence
    # at all, real content starts immediately with the first bullet.
    text = "## Key Capabilities\n\n- Encodes Code 128, Code 39, EAN/UPC, and QR barcodes.\n"
    assert checks.check_section_intro_no_meta_narration(text) == []


def test_section_intro_no_meta_narration_flags_additional_examples_section():
    text = (
        "## Additional Examples\n\n"
        f"{_REAL_FONT_PYTHON_META_NARRATION}\n\n"
        "- A worked example.\n"
    )
    findings = checks.check_section_intro_no_meta_narration(text)
    assert len(findings) == 1
    assert findings[0]["section"] == "Additional Examples"


def test_section_intro_no_meta_narration_clean_on_real_additional_examples_intro():
    text = (
        "## Additional Examples\n\n"
        "More real, runnable snippets are collected below.\n\n"
        "- Loads a scene and converts it to glTF.\n"
    )
    assert checks.check_section_intro_no_meta_narration(text) == []


def test_section_intro_no_meta_narration_noop_when_sections_absent():
    text = "## Installation\n\nRun `pip install aspose-font-foss`.\n"
    assert checks.check_section_intro_no_meta_narration(text) == []


def test_extract_section_intro_prose_stops_at_bullet_fence_and_subheading():
    assert checks._extract_section_intro_prose("Intro line.\n\n- Bullet one.\n") == "Intro line."
    assert checks._extract_section_intro_prose("Intro line.\n\n```python\nx = 1\n```\n") == "Intro line."
    assert checks._extract_section_intro_prose("Intro line.\n\n### Sub Heading\n") == "Intro line."
    assert checks._extract_section_intro_prose("- Bullet one.\n") == ""


# --- filter_relevant_seo_keywords / _seo_keyword_wrong_platform (TC-HARDEN-39, MT037) -----------

# Real, captured-verbatim keyword phrases from keywords/cells.json's own `cells/java`
# products.aspose.org entry -- confirmed live to be 10-of-10 contaminated with .NET/C# terms
# despite the entry being for the Java platform page.
_REAL_CONTAMINATED_JAVA_KEYWORDS = [
    "Aspose.Cells for .NET free open source alternative",
    "Open source Excel library for .NET alternative to Aspose",
    "Free .NET library to read write Excel files",
    "Open source C# Excel API like Aspose",
    "Aspose.Cells alternative open source .NET",
    "Free C# library for Excel manipulation without Aspose",
    "Open source spreadsheet library for .NET Core",
    "C# read write Excel file open source library",
    "Aspose.Cells .NET free alternative",
    "Open source Excel interop alternative for .NET",
]


def test_filter_relevant_seo_keywords_drops_real_contaminated_java_phrases():
    kept = checks.filter_relevant_seo_keywords(_REAL_CONTAMINATED_JAVA_KEYWORDS, "cells", "java")
    assert kept == []


def test_filter_relevant_seo_keywords_keeps_genuinely_relevant_phrase():
    keywords = [
        "Open source Excel library for Java",
        "Free Java library to read write Excel files",
    ]
    kept = checks.filter_relevant_seo_keywords(keywords, "cells", "java")
    assert kept == keywords


def test_filter_relevant_seo_keywords_caps_at_six():
    keywords = [f"Open source Excel library for Java number {i}" for i in range(10)]
    kept = checks.filter_relevant_seo_keywords(keywords, "cells", "java")
    assert len(kept) == 6


def test_filter_relevant_seo_keywords_drops_ungrounded_phrase():
    # No family name, no known relevance term, no known format -- nothing to verify it against.
    kept = checks.filter_relevant_seo_keywords(["Something totally unrelated to anything"], "cells", "java")
    assert kept == []


def test_filter_relevant_seo_keywords_keeps_phrase_naming_a_known_format():
    kept = checks.filter_relevant_seo_keywords(
        ["Java XLSX manipulation toolkit"], "cells", "java", known_format_names={"XLSX"},
    )
    assert kept == ["Java XLSX manipulation toolkit"]


def test_seo_keyword_wrong_platform_true_for_other_platform_token():
    assert checks._seo_keyword_wrong_platform("Open source Excel library for .NET", "java") is True


def test_seo_keyword_wrong_platform_false_for_own_platform_token():
    assert checks._seo_keyword_wrong_platform("Open source Excel library for Java", "java") is False


# --- build_seo_keyword_placement_plan / check_seo_keyword_plan_usage
# (readme-refresh-seo-deps-headings-hardening, 2026-08-19) --------------------------------------


def test_build_seo_keyword_placement_plan_shape():
    plan = checks.build_seo_keyword_placement_plan(
        ["Open source 3D library for .NET", "Free .NET 3D graphics library"], "3d",
    )
    assert len(plan) == 2
    assert plan[0]["phrase"] == "Open source 3D library for .NET"
    assert plan[0]["source_registry"] == "keywords/3d.json"
    assert plan[0]["intended_section"] == "Key Capabilities"
    assert plan[0]["priority"] == "preferred"
    assert plan[0]["max_uses"] == 1


def test_build_seo_keyword_placement_plan_empty_pool():
    assert checks.build_seo_keyword_placement_plan([], "3d") == []


def test_check_seo_keyword_plan_usage_noop_on_empty_plan():
    assert checks.check_seo_keyword_plan_usage("## Key Capabilities\n\n- `Scene` graph.\n", []) == []


def test_check_seo_keyword_plan_usage_flags_zero_lexical_overlap():
    # The real, confirmed 3d/net defect: 10 correct, filtered SEO phrases, and the actual Key
    # Capabilities section is pure identifier-first API-reference prose with no overlap at all.
    plan = checks.build_seo_keyword_placement_plan(
        ["Open source 3D mesh processing .NET", "Free CAD file reader C# library"], "3d",
    )
    text = (
        "## Key Capabilities\n\n"
        "- Build and traverse a scene graph with `Scene` and `Node`.\n"
        "- Assign shading materials through `Material` subclasses.\n"
    )
    findings = checks.check_seo_keyword_plan_usage(text, plan)
    assert len(findings) == 1
    assert findings[0]["plan_size"] == 2


def test_check_seo_keyword_plan_usage_passes_on_any_overlap():
    plan = checks.build_seo_keyword_placement_plan(
        ["Open source 3D mesh processing .NET", "Free CAD file reader C# library"], "3d",
    )
    # Only "processing" (a significant word from the first phrase) needs to appear somewhere.
    text = "## Key Capabilities\n\n- Real-time mesh processing with `Scene` and `Node`.\n"
    assert checks.check_seo_keyword_plan_usage(text, plan) == []


def test_seo_keyword_wrong_platform_false_when_no_platform_token_present():
    assert checks._seo_keyword_wrong_platform("Open source Excel library", "java") is False


def test_seo_keyword_wrong_platform_flags_mixed_platform_phrase_even_when_own_platform_named():
    """Real bug found live on cells/typescript's real keywords/cells.json entry: a phrase
    naming BOTH the correct platform and a contaminating one ("Aspose.Cells for .NET
    TypeScript library") was not flagged, because the original logic excused any other-
    platform mention as long as the correct platform was also present somewhere."""
    assert checks._seo_keyword_wrong_platform(
        "Aspose.Cells for .NET TypeScript library", "typescript"
    ) is True
    assert checks._seo_keyword_wrong_platform(
        "free .NET spreadsheet library for TypeScript", "typescript"
    ) is True


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


# --- check_diagram_from_scratch_capability_labeled (2026-08-17, real words/net incident) --

_WORDS_NET_FROM_SCRATCH_BULLET = (
    "- Create documents from scratch with the full document object model, or through the "
    "cursor-based `DocumentBuilder`, then load and edit existing DOCX, DOCM, DOTX, or DOTM "
    "files with the same `Document` class."
)


def _words_net_diagram(capability_label: str) -> str:
    return (
        "flowchart TD\n"
        "  PRODUCT[\"Aspose.Words FOSS for .NET\"]\n"
        "  subgraph Capabilities[\"Core Capabilities\"]\n"
        f"    C1[\"{capability_label}\"]\n"
        "    C2[\"Field evaluation engine\"]\n"
        "  end\n"
    )


def test_diagram_from_scratch_capability_labeled_flags_real_pre_fix_words_net_shape():
    # Real, captured-verbatim shape: the diagram's own capability label never mentioned
    # "from scratch" even though Key Capabilities' own first bullet explicitly claims it.
    text = _wrap(
        _words_net_diagram("Document creation and editing"),
        extra_section=_WORDS_NET_FROM_SCRATCH_BULLET,
    )
    findings = checks.check_diagram_from_scratch_capability_labeled(text)
    assert len(findings) == 1
    assert "invisible at a glance" in findings[0]["reason"]


def test_diagram_from_scratch_capability_labeled_clean_after_real_fix():
    # The real fix applied to words/net's own candidate.
    text = _wrap(
        _words_net_diagram("Document creation from scratch and editing"),
        extra_section=_WORDS_NET_FROM_SCRATCH_BULLET,
    )
    assert checks.check_diagram_from_scratch_capability_labeled(text) == []


def test_diagram_from_scratch_capability_labeled_clean_for_hybrid_starting_points():
    # Hybrid-archetype products (e.g. pdf/cpp) legitimately carry the phrase in their real
    # StartingPoints container's own literal line rather than in a Capabilities node label --
    # the same real shape as the HYBRID_PDF_CPP fixture above, minus its own default
    # "- Does a thing." Key Capabilities text.
    mermaid_body = (
        "flowchart TD\n"
        "  subgraph StartingPoints[\"Starting Points\"]\n"
        "    I1[\"An existing PDF document\"]\n"
        "    I2[\"Nothing -- authored from scratch\"]\n"
        "  end\n"
        "  PRODUCT[\"Aspose.PDF FOSS for C++\"]\n"
        "  subgraph Capabilities[\"Core Capabilities\"]\n"
        "    C1[\"Text extraction and page rendering\"]\n"
        "    C2[\"Document creation and editing\"]\n"
        "  end\n"
    )
    text = _wrap(mermaid_body, extra_section=_WORDS_NET_FROM_SCRATCH_BULLET)
    assert checks.check_diagram_from_scratch_capability_labeled(text) == []


def test_diagram_from_scratch_capability_labeled_vacuous_without_claim():
    # No "from scratch" claim anywhere in Key Capabilities -- must never fire.
    text = _wrap(
        _words_net_diagram("Document creation and editing"),
        extra_section="- `Cylinder` is a parameterized solid primitive convertible to `Mesh`.\n",
    )
    assert checks.check_diagram_from_scratch_capability_labeled(text) == []


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


def test_scope_limitations_format_allows_zero_bullets_when_only_enterprise_paragraph():
    # 2026-08-13 (cells/cpp healing pass, mission's own item 5): when no limitation traces to
    # an allowed public source, the bulleted list is simply absent -- this must be the VALID
    # shape, not a not_a_list failure, and must not be confused with the prose-limitations
    # shape the check below (unchanged) still correctly rejects.
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n"
        "See [Enterprise Edition](https://products.aspose.com/cells/cpp/) for broader feature "
        "coverage, full production support, and active development.\n"
    ))
    assert checks.check_scope_limitations_format(text) == []


def test_scope_limitations_format_still_flags_mixed_sentence_prose_limitation():
    # Regression guard for the zero-bullet carve-out above: a non-bullet line that mixes a real
    # limitation claim with the Enterprise mention in one paragraph (same physical line, two
    # sentences) must still fail -- this is exactly
    # test_scope_limitations_format_flags_prose_paragraph_shape's own shape, re-asserted
    # explicitly against the new sentence-level logic so the carve-out can never silently widen
    # to swallow it.
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n"
        "This project reads and writes XLSX only. See "
        "[Enterprise Edition](https://products.aspose.com/cells/cpp/) for more.\n"
    ))
    findings = checks.check_scope_limitations_format(text)
    assert any(f["reason"] == "not_a_list" for f in findings)


def test_scope_limitations_format_flags_invented_filler():
    # Mission's own explicit example: "Do not insert filler such as 'no known limitations.'"
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n"
        "This edition has no known limitations. See "
        "[Enterprise Edition](https://products.aspose.com/cells/cpp/) for more.\n"
    ))
    findings = checks.check_scope_limitations_format(text)
    assert any(f["reason"] == "invented_filler" for f in findings)


def test_scope_limitations_format_flags_invented_filler_variants():
    variants = [
        "There are no known limitations for this edition.",
        "No limitations have been identified in this release.",
        "No limitations are currently known.",
    ]
    for sentence in variants:
        text = _wrap("flowchart TD\n  A --> B", extra_section=(
            "- Does a thing.\n\n## Scope and Limitations\n\n"
            f"{sentence} See [Enterprise Edition](https://products.aspose.com/cells/cpp/).\n"
        ))
        findings = checks.check_scope_limitations_format(text)
        assert any(f["reason"] == "invented_filler" for f in findings), sentence


def test_scope_limitations_format_real_bullets_never_flagged_as_filler():
    # Regression guard: the invented-filler regex must never false-positive against a real,
    # legitimate bullet naming an actual constraint.
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n"
        "- Only `.xlsx` (OOXML) is supported for load and save.\n\n"
        "See [Enterprise Edition](https://products.aspose.com/cells/cpp/) for broader coverage.\n"
    ))
    findings = checks.check_scope_limitations_format(text)
    assert not any(f["reason"] == "invented_filler" for f in findings)


def test_scope_limitations_format_flags_missing_enterprise_paragraph():
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n- Reads and writes XLSX only.\n"
    ))
    findings = checks.check_scope_limitations_format(text)
    assert any(f["reason"] == "missing_enterprise_paragraph" for f in findings)


def test_scope_limitations_format_noop_without_section():
    text = _wrap("flowchart TD\n  A --> B", extra_section="- Does a thing.\n")
    assert checks.check_scope_limitations_format(text) == []


# --- check_scope_limitations_format bug fix (2026-08-15, MT045, TC-HARDEN-68) ----------------------
#
# The prior implementation classified raw, blank-line-stripped PHYSICAL lines as
# bullet/non-bullet independently -- so a bullet's own wrapped continuation line (no "- "
# prefix of its own) landed in non_bullet_lines even though it was really the tail of a
# bulleted Limitations item. Fixed by routing through _iter_leak_scan_units (the same,
# already-hardened bullet-with-continuation grouping built for
# check_no_upstream_issue_leaked_into_readme, TC-HARDEN-38).

_REAL_BARCODE_PYTHON_SCOPE_BULLETED_ENTERPRISE = (
    "- This library only generates (encodes) barcodes -- it does not read or decode "
    "existing barcode images for any symbology.\n"
    "- PDF rendering is not implemented -- `Barcode.to_pdf()` and `PdfRenderer.render()` "
    "both raise `NotImplementedError`. SVG and PNG rendering are implemented for every "
    "symbology. For PDF rendering and additional symbologies, see the\n"
    "[Aspose.BarCode for Python -- Enterprise Edition]"
    "(https://products.aspose.com/barcode/python-net/), which adds\n"
    "the full commercial rendering pipeline and broader symbology coverage on top of this "
    "FOSS API surface.\n"
    "- ECI (Extended Channel Interpretation) normalization and validation are not "
    "implemented in this FOSS build.\n"
)


def test_scope_limitations_format_flags_real_barcode_python_bulleted_continuation_enterprise_link():
    # Real, captured-verbatim defect: the Enterprise Edition link sits as a wrapped
    # continuation of the "PDF rendering is not implemented" bullet -- no blank line before
    # it, same physical list item. The prior, buggy implementation missed this entirely
    # (enterprise_in_prose=True/enterprise_in_bullet=False, the exact silently-passing
    # combination this check exists to catch).
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n"
        + _REAL_BARCODE_PYTHON_SCOPE_BULLETED_ENTERPRISE
    ))
    findings = checks.check_scope_limitations_format(text)
    assert any(f["reason"] == "enterprise_paragraph_is_bulleted" for f in findings)


_REAL_EMAIL_PYTHON_SCOPE_LIST = (
    "- Reads and writes `.msg` and `.eml` messages, but does not resolve embedded OLE "
    "compound-document attachments beyond the first nesting level -- a real, disclosed "
    "constraint verified against the current parser.\n"
    "- Calendar (`.ics`) support covers `VEVENT` only; `VTODO` and `VJOURNAL` components "
    "are parsed but not round-tripped on save.\n\n"
    "These limitations apply only to the FOSS edition -- see "
    "[Aspose.Email for Python -- Enterprise Edition]"
    "(https://products.aspose.com/email/python-net/), which adds full MIME/S-MIME support "
    "and broader calendar round-tripping.\n"
)


def test_scope_limitations_format_bug_fix_no_false_positive_on_wrapped_bullet_plus_separate_paragraph():
    # Regression guard for the fix itself: a bullet with its own long, wrapped continuation
    # line (no blank line, the real, near-universal shape for any bullet >~80 chars in this
    # portfolio) sitting above a genuinely separate, blank-line-delimited Enterprise
    # paragraph must still pass. A naive "just group continuation lines" fix (without
    # _iter_leak_scan_units's own blank-line-first paragraph split) was directly simulated
    # to false-positive on exactly this shape.
    text = _wrap("flowchart TD\n  A --> B", extra_section=(
        "- Does a thing.\n\n## Scope and Limitations\n\n" + _REAL_EMAIL_PYTHON_SCOPE_LIST
    ))
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


# --- unit_hash: content-addressed identity (readme-refresh-hardening-and-regen-2026-08-30, TC-19) --


class TestUnitContentHash:
    """RC-disposition-content-addressed-identity: every one of the 4 extractors now emits
    an additive unit_hash alongside its existing positional unit_id. The property that
    matters -- stable identity under reordering -- is what these tests prove, not just
    "the field exists"."""

    def test_direct_hash_helper_is_deterministic_and_content_sensitive(self):
        h1 = checks._unit_content_hash("Some real text.")
        h2 = checks._unit_content_hash("Some real text.")
        h3 = checks._unit_content_hash("Some DIFFERENT text.")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 16  # 64-bit truncated sha256, documented in the helper's own docstring

    def test_content_unit_hash_survives_reordering(self):
        # This is the exact regression class the module's own MT056 comment names: inserting a
        # unit earlier in the document must not change a LATER unit's identity.
        original = "# Title\n\nFirst real technical claim about `Alpha`.\n\nSecond real technical claim about `Beta`.\n"
        reordered = "# Title\n\nA brand new claim inserted first about `Gamma`.\n\nFirst real technical claim about `Alpha`.\n\nSecond real technical claim about `Beta`.\n"
        original_units = checks.extract_old_readme_content_units(original)
        reordered_units = checks.extract_old_readme_content_units(reordered)
        beta_original = next(u for u in original_units if "Beta" in u["excerpt"])
        beta_reordered = next(u for u in reordered_units if "Beta" in u["excerpt"])
        # The positional id DID shift (u0002 -> u0003) -- exactly the confirmed drift bug.
        assert beta_original["unit_id"] != beta_reordered["unit_id"]
        # But the content hash did NOT -- the fix this class of test exists to prove.
        assert beta_original["unit_hash"] == beta_reordered["unit_hash"]

    def test_structural_unit_hash_present_and_content_sensitive(self):
        text_a = "## Project Structure\n\n```\nsrc/\n  a.py\n```\n"
        text_b = "## Project Structure\n\n```\nsrc/\n  b.py\n```\n"
        units_a = checks.extract_old_readme_structural_units(text_a)
        units_b = checks.extract_old_readme_structural_units(text_b)
        assert units_a and units_b
        assert all("unit_hash" in u and len(u["unit_hash"]) == 16 for u in units_a)
        assert units_a[0]["unit_hash"] != units_b[0]["unit_hash"]

    def test_code_unit_hash_present_and_content_sensitive(self):
        text_a = "## Quick Start\n\n```python\nimport widget\nwidget.run()\n```\n"
        text_b = "## Quick Start\n\n```python\nimport gadget\ngadget.run()\n```\n"
        units_a = checks.extract_old_readme_code_units(text_a)
        units_b = checks.extract_old_readme_code_units(text_b)
        assert units_a and units_b
        assert all("unit_hash" in u and len(u["unit_hash"]) == 16 for u in units_a)
        assert units_a[0]["unit_hash"] != units_b[0]["unit_hash"]

    def test_badge_unit_hash_present_and_content_sensitive(self):
        text_a = "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n"
        text_b = "[![Build](https://img.shields.io/badge/Build-passing-green.svg)](CI)\n"
        badges_a = checks.extract_badges(text_a)
        badges_b = checks.extract_badges(text_b)
        assert badges_a and badges_b
        assert all("unit_hash" in b and len(b["unit_hash"]) == 16 for b in badges_a)
        assert badges_a[0]["unit_hash"] != badges_b[0]["unit_hash"]

    def test_badge_hash_survives_reordering(self):
        row_a = "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)"
        row_b = "[![Build](https://img.shields.io/badge/Build-passing-green.svg)](CI)"
        original = row_a + " " + row_b + "\n"
        reordered = row_b + " " + row_a + "\n"
        original_badges = {b["unit_hash"]: b for b in checks.extract_badges(original)}
        reordered_badges = {b["unit_hash"]: b for b in checks.extract_badges(reordered)}
        # Same two hashes present in both, regardless of position -- positional unit_id
        # differs (b0001/b0002 swap), hash-based identity does not.
        assert set(original_badges.keys()) == set(reordered_badges.keys())
        for h in original_badges:
            assert original_badges[h]["unit_id"] != reordered_badges[h]["unit_id"] or len(original_badges) == 1


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


# --- check_content_unit_excerpt_matches_extraction (hard gate, MT048) -----------------------


def test_excerpt_matches_extraction_clean_when_excerpts_agree():
    units = [{"unit_id": "u0001", "excerpt": _NOTE_PYTHON_OFFICIAL_CLAIM}]
    dispositions = [_content_unit(unit_id="u0001", excerpt=_NOTE_PYTHON_OFFICIAL_CLAIM)]
    assert checks.check_content_unit_excerpt_matches_extraction(units, dispositions) == []


def test_excerpt_matches_extraction_flags_real_position_based_drift():
    # The exact MT030 Phase 2 shape (2026-08-10, "recovering a unit earlier in a document shifts
    # every later unit's unit_id"): a disposition entry authored against one excerpt, but the
    # live extractor now reports COMPLETELY DIFFERENT content under the same unit_id (e.g. a unit
    # was inserted earlier in the document, shifting every later id by one). unit_id-presence
    # alone (check_content_unit_disposition_coverage) cannot see this -- u0002 still exists.
    units = [{"unit_id": "u0002", "excerpt": "A newly-inserted, unrelated sentence about `Zeta`."}]
    dispositions = [_content_unit(unit_id="u0002", excerpt=_NOTE_PYTHON_OFFICIAL_CLAIM)]
    findings = checks.check_content_unit_excerpt_matches_extraction(units, dispositions)
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0002"
    assert "drift" in findings[0]["reason"]


def test_excerpt_matches_extraction_tolerates_emoji_and_whitespace_only_differences():
    # A cosmetic re-run difference (emoji rendering, whitespace) must NOT false-positive --
    # reuses _normalize_for_drop_match, the same tolerance check_dropped_content's own heading-
    # rename comparison already relies on.
    units = [{
        "unit_id": "u0001",
        "excerpt": "**Official  Aspose project** -- 100% free and open-source, with no hidden costs.",
    }]
    dispositions = [_content_unit(unit_id="u0001", excerpt=_NOTE_PYTHON_OFFICIAL_CLAIM)]
    assert checks.check_content_unit_excerpt_matches_extraction(units, dispositions) == []


def test_excerpt_matches_extraction_silent_for_dangling_unit_id():
    # A unit_id absent from the live extraction entirely is check_content_unit_disposition_
    # coverage's own job -- this function must not duplicate that finding.
    units = [{"unit_id": "u0001", "excerpt": _NOTE_PYTHON_OFFICIAL_CLAIM}]
    dispositions = [_content_unit(unit_id="u9999", excerpt="something else entirely")]
    assert checks.check_content_unit_excerpt_matches_extraction(units, dispositions) == []


def test_excerpt_matches_extraction_vacuous_when_stored_excerpt_empty():
    units = [{"unit_id": "u0001", "excerpt": _NOTE_PYTHON_OFFICIAL_CLAIM}]
    dispositions = [_content_unit(unit_id="u0001", excerpt="")]
    assert checks.check_content_unit_excerpt_matches_extraction(units, dispositions) == []


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


# MT055/TC-MICRO-04 (2026-08-18): self-citation rejection, RC-C from the MT054 audit -- ~40 of
# pdf/net's own 69 real disposition units cited `evidence_ref: "README.md"` (the old README
# being audited) as their own supporting evidence, which trivially "resolves" (the file exists)
# without being real verification. A 9-unit hand sample found 1 real, confirmed factual failure
# hiding behind exactly this circular citation.

def test_evidence_resolves_flags_self_citation_of_root_readme(tmp_path):
    (tmp_path / "README.md").write_text("# Real old README\n", encoding="utf-8")
    dispositions = [_content_unit(evidence_ref="README.md")]
    findings = checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0001"
    assert "self-citation" in findings[0]["reason"]


def test_evidence_resolves_flags_self_citation_case_insensitive(tmp_path):
    (tmp_path / "README.md").write_text("# Real old README\n", encoding="utf-8")
    dispositions = [_content_unit(evidence_ref="readme.md")]
    findings = checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path))
    assert len(findings) == 1
    assert "self-citation" in findings[0]["reason"]


def test_evidence_resolves_allows_real_subdirectory_readme_not_self_citation(tmp_path):
    # A README belonging to a subdirectory (e.g. a bundled examples/tests project) is a real,
    # genuinely independent file -- never the same document the disposition claim is about.
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "README.md").write_text("# Examples\n", encoding="utf-8")
    dispositions = [_content_unit(evidence_ref="examples/README.md")]
    assert checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path)) == []


def test_evidence_resolves_reject_self_citation_false_allows_verbatim_extraction_provenance(tmp_path):
    # Structural/code-example units cite README.md as the real, literal source of a verbatim
    # extraction (a directory tree, a fenced command) -- legitimate provenance, not a factual
    # claim needing independent verification. reject_self_citation=False must allow this.
    (tmp_path / "README.md").write_text("# Real old README\n\n```bash\npip install -e .\n```\n", encoding="utf-8")
    dispositions = [_content_unit(evidence_ref="README.md")]
    assert checks.check_content_unit_evidence_resolves(
        dispositions, str(tmp_path), reject_self_citation=False
    ) == []


def test_evidence_resolves_real_pdf_net_shaped_self_citation_sample(tmp_path):
    # Real, captured shape from pdf/net's own content-dispositions.json (MT054 audit finding
    # NET-001's own sample): a compound claim self-cited against the very document it describes.
    (tmp_path / "README.md").write_text(
        "# Aspose.PDF FOSS for .NET\n\nSupports rendering to PNG, JPEG, and BMP.\n",
        encoding="utf-8",
    )
    dispositions = [_content_unit(
        unit_id="u0037",
        excerpt="Rendering supports PNG, JPEG, and BMP output at configurable DPI.",
        evidence_type="clone_cache_path", evidence_ref="README.md",
    )]
    findings = checks.check_content_unit_evidence_resolves(dispositions, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0037"


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


def test_no_exact_duplicate_merge_exempts_identical_text_with_different_evidence():
    """Real cells/net false positive (2026-08-19): 6 different classes each genuinely have their
    own `Count: int` property, so their excerpts are byte-identical by API-shape coincidence,
    not lazy duplication -- each independently verified against a different real source file."""
    dispositions = [
        _content_unit(unit_id="u0053", excerpt="- Properties: `Count: int`",
                      target_section="API Reference", evidence_ref="src/ValidationCollection.cs"),
        _content_unit(unit_id="u0059", excerpt="- Properties: `Count: int`",
                      target_section="API Reference", evidence_ref="src/ConditionalFormattingCollection.cs"),
    ]
    assert checks.check_content_unit_no_exact_duplicate_merge(dispositions) == []


def test_no_exact_duplicate_merge_still_flags_identical_text_and_evidence():
    """The exemption is narrow: two entries citing the SAME evidence_ref for the same excerpt
    are still real, lazy duplication, not independently-verified coincidence -- unchanged from
    the check's original behavior."""
    dispositions = [
        _content_unit(unit_id="u0001", excerpt="Same text, same source.",
                      target_section="API Reference", evidence_ref="src/widget.py"),
        _content_unit(unit_id="u0002", excerpt="Same text, same source.",
                      target_section="API Reference", evidence_ref="src/widget.py"),
    ]
    findings = checks.check_content_unit_no_exact_duplicate_merge(dispositions)
    assert findings and set(findings[0]["unit_ids"]) == {"u0001", "u0002"}


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


# --- check_image_content_unit_excluded_reason_verified (MT051, Forty-First incident) ------------
# Real, captured-verbatim shapes from page/python's own two candidate trees.

_PAGE_PYTHON_KEY_CAPABILITIES_TEXT = (
    "## Key Capabilities\n\n"
    "- Convert XPS documents to PDF, then optionally render pages to PNG/JPEG raster images.\n"
    "- Convert PS and EPS files to PDF for downstream viewing and archival.\n"
    "- Render PS/EPS content directly to raster image formats.\n"
)


def test_image_content_unit_excluded_reason_flags_real_page_python_dropped_images():
    # The real, original defect this incident exists to catch: 3 real, on-disk screenshots were
    # excluded via a candidate_section_reference to "Key Capabilities" whose own generic tokens
    # (XPS/PDF/PS) trivially, coincidentally match unrelated Key Capabilities prose -- while the
    # images themselves were never actually re-embedded anywhere in the candidate.
    dispositions = [
        _content_unit(
            unit_id="u0014", excerpt="![mb03 xps2pdf result](readme.resources/mb03.png)",
            salient_tokens=("XPS", "PDF"), classification="redundant_with_existing",
            disposition="excluded", target_section=None,
            evidence_status="verified_redundant", evidence_type="candidate_section_reference",
            evidence_ref="Key Capabilities",
            excluded_reason="the Template's fixed section list has no image-gallery section",
        ),
        _content_unit(
            unit_id="u0015", excerpt="![ps2pdf result](readme.resources/TestImages.png)",
            salient_tokens=("PS", "PDF"), classification="redundant_with_existing",
            disposition="excluded", target_section=None,
            evidence_status="verified_redundant", evidence_type="candidate_section_reference",
            evidence_ref="Key Capabilities",
            excluded_reason="the Template's fixed section list has no image-gallery section",
        ),
        _content_unit(
            unit_id="u0016", excerpt="![PS to image sample](readme.resources/RGB10.png)",
            salient_tokens=("PS", "RGB10"), classification="redundant_with_existing",
            disposition="excluded", target_section=None,
            evidence_status="verified_redundant", evidence_type="candidate_section_reference",
            evidence_ref="Key Capabilities",
            excluded_reason="the Template's fixed section list has no image-gallery section",
        ),
    ]
    units = [{"unit_id": d["unit_id"], "excerpt": d["excerpt"]} for d in dispositions]
    findings = checks.check_image_content_unit_excluded_reason_verified(
        units, dispositions, _PAGE_PYTHON_KEY_CAPABILITIES_TEXT
    )
    assert {f["unit_id"] for f in findings} == {"u0014", "u0015", "u0016"}
    assert "mb03.png" in findings[0]["reason"]


def test_image_content_unit_excluded_reason_silent_when_image_genuinely_reembedded():
    # page/python's OWN repo-presenter tree: the identical raw units, excluded for a genuinely
    # true reason -- the same images really are re-embedded elsewhere in that tree's candidate,
    # under different, clearer captions. Negative control -- must stay silent.
    dispositions = [
        _content_unit(
            unit_id="u0011", excerpt="![mb03 xps2pdf result](readme.resources/mb03.png)",
            salient_tokens=("XPS", "PDF"), classification="redundant_with_existing",
            disposition="excluded", target_section=None,
            evidence_status="verified_redundant", evidence_type="candidate_section_reference",
            evidence_ref="Additional Examples",
            excluded_reason="identical image already embedded, under a clearer caption, in the "
                             "Additional Examples section",
        ),
    ]
    units = [{"unit_id": "u0011", "excerpt": dispositions[0]["excerpt"]}]
    readme_with_reembedded_image = (
        "## Additional Examples\n\n### Example Results\n\n"
        "![XPS to PDF to PNG result](readme.resources/mb03.png)\n"
    )
    assert checks.check_image_content_unit_excluded_reason_verified(
        units, dispositions, readme_with_reembedded_image
    ) == []


def test_image_content_unit_excluded_reason_ignores_non_image_excerpts():
    # The check must scope itself to bare image-markdown excerpts only -- an ordinary text unit
    # excluded via candidate_section_reference is check_content_unit_merged_into_target_section's
    # job, not this one's.
    dispositions = [_content_unit(
        unit_id="u0017", excerpt="MCP tools currently exposed:", salient_tokens=("MCP",),
        classification="redundant_with_existing", disposition="excluded", target_section=None,
        evidence_status="verified_redundant", evidence_type="candidate_section_reference",
        evidence_ref="Key Capabilities",
        excluded_reason="pure section-label text, already captured elsewhere",
    )]
    units = [{"unit_id": "u0017", "excerpt": dispositions[0]["excerpt"]}]
    assert checks.check_image_content_unit_excluded_reason_verified(
        units, dispositions, "## Key Capabilities\n\n- MCP tools: five exposed today.\n"
    ) == []


def test_image_content_unit_excluded_reason_ignores_merged_dispositions():
    # A genuinely restored/merged image (post-fix state) must never be flagged -- only excluded
    # units are in scope.
    dispositions = [_content_unit(
        unit_id="u0014", excerpt="![mb03 xps2pdf result](readme.resources/mb03.png)",
        salient_tokens=("XPS", "PDF"), classification="redundant_with_existing",
        disposition="merged_verbatim", target_section="Additional Examples",
        evidence_status="verified_against_source", evidence_type="clone_cache_path",
        evidence_ref="readme.resources/mb03.png",
    )]
    units = [{"unit_id": "u0014", "excerpt": dispositions[0]["excerpt"]}]
    assert checks.check_image_content_unit_excluded_reason_verified(
        units, dispositions, "no images embedded here at all"
    ) == []


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


# ============================================================================================
# Twenty-Fourth mission (2026-08-13): structural (non-prose) section preservation + badge
# semantic reconciliation -- cells/go's real, live upstream README has a `## Project Structure`
# section that is ENTIRELY a fenced directory-tree code block with no surrounding prose, which
# extract_old_readme_content_units can never see by design (it strips fenced code first).
# ============================================================================================

# Real, captured-verbatim excerpt from cells/go's actual upstream README, used across several
# tests below as ground truth rather than a synthetic approximation.
_REAL_CELLS_GO_README = """# Aspose.Cells for Go

A pure-Go Excel (.xlsx) library.

[![Go Version](https://img.shields.io/badge/Go-%3E%3D1.18-blue)](https://go.dev)
[![Tests](https://img.shields.io/badge/tests-passing-green)](#)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

## Installation

```bash
go get github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26
```

Requires **Go 1.18+**. Only depends on the standard library + `golang.org/x/crypto`.

## Project Structure

```
├── aspose/cells_foss/        # Library source code
│   ├── workbook.go           #   Workbook entry point
│   ├── worksheet.go          #   Worksheet model
│   └── style.go              #   Styles (font, fill, alignment, border)
├── tests/                    # Integration tests (public API)
├── docs/                     # Documentation
│   └── usage.md              #   Detailed usage guide
├── go.mod
└── README.md
```

## Testing

```bash
go test ./...
```

## License

MIT License
"""


def _structural_unit(unit_id="s0001", heading="Project Structure", kind="directory_tree",
                      claimed_paths=("aspose/cells_foss", "aspose/cells_foss/workbook.go")):
    return {
        "unit_id": unit_id, "heading": heading, "heading_level": 2, "kind": kind,
        "fenced_block_text": "```\n" + "\n".join(claimed_paths) + "\n```",
        "dominance_ratio": 1.0, "claimed_paths": list(claimed_paths),
    }


def _structure_disposition(unit_id="s0001", disposition="merged_reframed",
                            target_section="Project Structure", claimed_paths=None,
                            evidence_status="verified_against_source",
                            evidence_type="clone_cache_path", evidence_ref="aspose/cells_foss",
                            excluded_reason=None):
    return {
        "unit_id": unit_id, "disposition": disposition, "target_section": target_section,
        "claimed_paths": claimed_paths, "excluded_reason": excluded_reason,
        "verification": {"status": evidence_status, "evidence_type": evidence_type, "evidence_ref": evidence_ref},
    }


# --- check_structural_unit_disposition_text_diff (RC-disposition-text-diff-verification, TC-21) -


def test_structural_text_diff_reproduces_the_real_font_python_s0002_defect():
    """The exact real defect: a structural disposition claims merged_verbatim for a fenced
    block that lost 5 of 12 print() calls in the candidate -- silent code reduction
    mislabeled as verbatim preservation."""
    old_readme = (
        "## Variable Font Discovery\n\n"
        "```python\n"
        "print(font.smart_instancer.suggest_axis_values(axis))\n"
        "print(font.get_axis(\"wght\").name((\"fr-CA\", \"en\")))\n"
        "print(font.get_axis(\"wght\").localized_labels())\n"
        "print(font.variable_presentation())\n"
        "print(font.variable_presentation())\n"
        "```\n"
    )
    units = checks.extract_old_readme_structural_units(old_readme)
    assert len(units) == 1
    dispositions = [_structure_disposition(unit_id=units[0]["unit_id"], disposition="merged_verbatim")]
    # The candidate dropped the 2 localization calls -- a real, undisclosed reduction.
    candidate = (
        "## Variable Font Discovery\n\n"
        "```python\n"
        "print(font.smart_instancer.suggest_axis_values(axis))\n"
        "print(font.variable_presentation())\n"
        "print(font.variable_presentation())\n"
        "```\n"
    )
    findings = checks.check_structural_unit_disposition_text_diff(units, dispositions, candidate)
    assert len(findings) == 1
    assert findings[0]["unit_id"] == units[0]["unit_id"]
    assert "not present anywhere in the candidate" in findings[0]["reason"]


def test_structural_text_diff_clean_when_verbatim_claim_is_true():
    old_readme = "## Project Structure\n\n```\nsrc/\n  main.py\n```\n"
    units = checks.extract_old_readme_structural_units(old_readme)
    dispositions = [_structure_disposition(unit_id=units[0]["unit_id"], disposition="merged_verbatim")]
    candidate = "## Project Structure\n\nSome intro.\n\n```\nsrc/\n  main.py\n```\n"
    assert checks.check_structural_unit_disposition_text_diff(units, dispositions, candidate) == []


def test_structural_text_diff_ignores_non_verbatim_dispositions():
    old_readme = "## Project Structure\n\n```\nsrc/\n  main.py\n```\n"
    units = checks.extract_old_readme_structural_units(old_readme)
    candidate = "## Project Structure\n\n```\nsrc/\n  other.py\n```\n"
    for disp in ("merged_reframed", "excluded"):
        dispositions = [_structure_disposition(unit_id=units[0]["unit_id"], disposition=disp)]
        assert checks.check_structural_unit_disposition_text_diff(units, dispositions, candidate) == []


# --- extract_old_readme_structural_units -----------------------------------------------------


def test_extract_structural_units_real_cells_go_case():
    units = checks.extract_old_readme_structural_units(_REAL_CELLS_GO_README)
    by_heading = {u["heading"]: u for u in units}
    assert "Project Structure" in by_heading
    assert by_heading["Project Structure"]["kind"] == "directory_tree"
    assert "aspose/cells_foss/workbook.go" in by_heading["Project Structure"]["claimed_paths"]
    # Testing is ALSO a pure fenced-command-list section under the same gating rule -- confirmed
    # real behavior, not just Project Structure gets caught, matching the mission's own "the
    # underlying problem is general" framing.
    assert "Testing" in by_heading
    assert by_heading["Testing"]["kind"] == "generic_structural_block"


def test_extract_structural_units_does_not_flag_installation():
    # The discriminating case: Installation is fenced-code-heavy (dominance would exceed 0.6) but
    # has a real leftover prose sentence once fenced code is stripped -- must NOT be flagged.
    units = checks.extract_old_readme_structural_units(_REAL_CELLS_GO_README)
    headings = {u["heading"] for u in units}
    assert "Installation" not in headings


def test_extract_structural_units_recognizes_differently_named_heading():
    # Semantic matching, not heading-text keyword matching -- the mission's own explicit
    # requirement: "Repository Layout"/"Source Layout"/"Project Structure" must all be
    # recognized identically.
    text = (
        "# Product\n\n## Repository Layout\n\n"
        "```\n├── src/\n│   └── main.go\n└── README.md\n```\n"
    )
    units = checks.extract_old_readme_structural_units(text)
    assert len(units) == 1
    assert units[0]["heading"] == "Repository Layout"
    assert units[0]["kind"] == "directory_tree"


def test_extract_structural_units_generic_block_for_plain_tree_heading_without_box_drawing():
    # A heading that matches no structure-vocabulary AND a fenced block with no box-drawing
    # characters -- correctly falls into the disclosed "no dedicated verifier" bucket rather than
    # being force-classified as a directory tree it can't confidently parse.
    text = "# Product\n\n## Build Artifacts\n\n```\nbin/app.exe\nbin/app.so\n```\n"
    units = checks.extract_old_readme_structural_units(text)
    assert len(units) == 1
    assert units[0]["kind"] == "generic_structural_block"


def test_extract_structural_units_is_deterministic():
    r1 = checks.extract_old_readme_structural_units(_REAL_CELLS_GO_README)
    r2 = checks.extract_old_readme_structural_units(_REAL_CELLS_GO_README)
    assert r1 == r2


# Real, captured-verbatim shape from pdf/cpp's own old upstream README (found live 2026-08-17):
# a genuine directory-tree fenced block (92.3% line dominance in the real file) followed by one
# incidental trailing architectural sentence -- under the pre-fix gate this silently disqualified
# the WHOLE section from structural capture, so the tree was invisible to every extractor.
_REAL_PDF_CPP_PROJECT_STRUCTURE_README = """# Product

## Project structure

```
├── include/
│   ├── aspose/pdf/            # Public-API headers (consumer-facing)
│   └── internal/              # Foundation primitive headers
├── src/
│   ├── public/                # Public-API implementation
│   └── internal/              # Foundation primitives (codecs, renderer, crypto)
├── tests/                     # GoogleTest unit + smoke tests
├── examples/                  # 12 runnable demo programs
├── pdfs/                      # Tiny sample PDFs for the examples
└── CMakeLists.txt
```

Public-API bodies under `src/public/` call directly into foundation primitives under
`src/internal/`. Foundation primitives never reach back into the public API.

## License

MIT License
"""


def test_extract_structural_units_dominant_tree_survives_incidental_caption():
    # The real pdf/cpp fix: a directory tree so fenced-dominant (>= min_fenced_dominance_with_
    # prose) that one trailing caption sentence must not disqualify structural capture.
    units = checks.extract_old_readme_structural_units(_REAL_PDF_CPP_PROJECT_STRUCTURE_README)
    by_heading = {u["heading"]: u for u in units}
    assert "Project structure" in by_heading
    assert by_heading["Project structure"]["kind"] == "directory_tree"
    assert "include" in by_heading["Project structure"]["claimed_paths"]
    # The caption sentence must ALSO still be visible to the prose extractor independently --
    # the two extraction paths are not mutually exclusive.
    prose_units = checks.extract_old_readme_content_units(_REAL_PDF_CPP_PROJECT_STRUCTURE_README)
    assert any("foundation primitives" in u["excerpt"] for u in prose_units)


def test_extract_structural_units_non_tree_with_prose_stays_excluded_even_if_dominant():
    # Regression guard for the narrower, kind-scoped fix: an API-usage code snippet (NOT a
    # directory tree) with a trailing caption must stay excluded even at high fenced dominance --
    # this content class already has real, separate coverage via extract_old_readme_code_units
    # (MT047), and pulling it into structure-dispositions.json too would manufacture a duplicate
    # coverage obligation with no matching disposition mechanism. Confirmed live against pdf/cpp's
    # own real "## Opening documents" API-reference subsection (no box-drawing characters, no
    # structural-vocabulary heading match -- so this stays generic even were it dominant enough).
    text = (
        "# Product\n\n## Opening documents\n\n"
        "```cpp\nDocument doc(\"input.pdf\");\nstd::cout << doc.Pages().Count();\n```\n\n"
        "This reads an existing file and reports its page count.\n"
    )
    units = checks.extract_old_readme_structural_units(text, min_fenced_dominance_with_prose=0.5)
    assert units == []


def test_extract_structural_units_min_fenced_dominance_with_prose_boundary():
    # cells/go's own real Installation dominance (0.667) and pdf/cpp's own real Project Structure
    # dominance (0.923) bracket the default 0.85 threshold -- explicit boundary proof, not just
    # the two real-file integration tests above.
    tree_text = (
        "# Product\n\n## Repository Layout\n\n"
        "```\n├── src/\n│   └── main.go\n└── README.md\n```\n\n"
        "A short caption sentence about the layout above.\n"
    )
    units_default = checks.extract_old_readme_structural_units(tree_text)
    assert units_default == []  # dominance below 0.85 with the default caption -- excluded
    units_lowered = checks.extract_old_readme_structural_units(
        tree_text, min_fenced_dominance_with_prose=0.5
    )
    assert len(units_lowered) == 1
    assert units_lowered[0]["kind"] == "directory_tree"


def test_parse_directory_tree_paths_real_shape():
    fenced = (
        "```\n├── aspose/cells_foss/        # Library source code\n"
        "│   ├── workbook.go           #   Workbook entry point\n"
        "│   └── style.go              #   Styles\n"
        "├── tests/                    # Integration tests\n"
        "└── go.mod\n```"
    )
    paths = checks._parse_directory_tree_paths(fenced)
    assert "aspose/cells_foss" in paths
    assert "aspose/cells_foss/workbook.go" in paths
    assert "aspose/cells_foss/style.go" in paths
    assert "tests" in paths
    assert "go.mod" in paths


# --- check_structural_unit_disposition_coverage (hard gate) --------------------------------


def test_structural_disposition_coverage_noop_when_no_units():
    assert checks.check_structural_unit_disposition_coverage([], []) == []


def test_structural_disposition_coverage_flags_missing_entry():
    # Fail-closed proof: the real cells/go Project Structure unit, with an EMPTY disposition
    # file, must produce a real finding -- this is the exact live gap this whole mission started
    # from (the section was structurally invisible to the pipeline before this mechanism existed).
    units = checks.extract_old_readme_structural_units(_REAL_CELLS_GO_README)
    findings = checks.check_structural_unit_disposition_coverage(units, [])
    project_structure_unit = next(u for u in units if u["heading"] == "Project Structure")
    assert any(f["unit_id"] == project_structure_unit["unit_id"] for f in findings)


def test_structural_disposition_coverage_clean_when_target_is_new_own_heading():
    units = [_structural_unit()]
    dispositions = [_structure_disposition(target_section="Project Structure")]
    assert checks.check_structural_unit_disposition_coverage(units, dispositions) == []


def test_structural_disposition_coverage_allows_merge_into_existing_template_section():
    units = [_structural_unit(unit_id="s0001", heading="Testing", kind="generic_structural_block", claimed_paths=())]
    dispositions = [_structure_disposition(unit_id="s0001", target_section="Development and Testing")]
    assert checks.check_structural_unit_disposition_coverage(units, dispositions) == []


def test_structural_disposition_coverage_allows_merge_into_additional_examples():
    # Real defect found while authoring cells/go's own real structure-dispositions.json (Twenty-
    # Fourth mission): "Additional Examples" is a real, legitimate merge target for reframed
    # worked-example code (the portfolio-wide established home for this content class, per the
    # Template section's own flagship-example rule) but was missing from
    # _CONTENT_UNIT_TARGET_SECTIONS -- a real machinery gap, not a disposition-authoring mistake.
    units = [_structural_unit(unit_id="s0001", heading="Use formulas", kind="generic_structural_block", claimed_paths=())]
    dispositions = [_structure_disposition(unit_id="s0001", target_section="Additional Examples")]
    assert checks.check_structural_unit_disposition_coverage(units, dispositions) == []


def test_structural_disposition_coverage_allows_merge_into_feature_showcase():
    # Real defect found restoring pdf/go's 3 real Example-Results-shaped images
    # (TC-HARDEN-102): "Feature Showcase" is a real, already-shipped, portfolio-precedented
    # optional section (pdf/go's own repo-presenter sibling tree) holding an embedded
    # proof-of-capability screenshot -- the same content class "Additional Examples" and
    # "Project Structure" were already added for -- but was missing from
    # _CONTENT_UNIT_TARGET_SECTIONS, the same class of machinery gap as those two.
    units = [{"unit_id": "u0005"}]
    dispositions = [_content_unit(
        unit_id="u0005",
        excerpt="![Feature showcase preview](docs/feature_showcase-preview.png)",
        target_section="Feature Showcase",
    )]
    assert checks.check_content_unit_disposition_coverage(units, dispositions) == []


def test_structural_disposition_coverage_flags_invalid_target_section():
    units = [_structural_unit()]
    dispositions = [_structure_disposition(target_section="Not A Real Section Anywhere")]
    findings = checks.check_structural_unit_disposition_coverage(units, dispositions)
    assert any("target_section" in f["reason"] for f in findings)


def test_structural_disposition_coverage_flags_missing_excluded_reason():
    units = [_structural_unit()]
    dispositions = [_structure_disposition(disposition="excluded", target_section=None, excluded_reason="too short")]
    findings = checks.check_structural_unit_disposition_coverage(units, dispositions)
    assert any("excluded_reason" in f["reason"] for f in findings)


def test_structural_disposition_coverage_flags_invalid_verification_status():
    units = [_structural_unit()]
    dispositions = [_structure_disposition(evidence_status="not_applicable_category_1")]
    findings = checks.check_structural_unit_disposition_coverage(units, dispositions)
    # not_applicable_category_1 is prose-specific -- has no honest structural-unit analog.
    assert any("verification.status" in f["reason"] for f in findings)


# --- check_structural_unit_merged_into_target_section (hard gate) --------------------------


def test_structural_merged_into_target_section_flags_untouched_target():
    dispositions = [_structure_disposition(
        target_section="Project Structure",
        claimed_paths=["aspose/cells_foss", "aspose/cells_foss/workbook.go"],
    )]
    text = "## Project Structure\n\nCompletely unrelated text with none of the claimed paths.\n"
    findings = checks.check_structural_unit_merged_into_target_section(text, dispositions)
    assert any(f["unit_id"] == "s0001" for f in findings)


def test_structural_merged_into_target_section_passes_with_real_paths_present():
    dispositions = [_structure_disposition(
        target_section="Project Structure",
        claimed_paths=["aspose/cells_foss", "aspose/cells_foss/workbook.go"],
    )]
    text = "## Project Structure\n\n```\naspose/cells_foss/workbook.go\n```\n"
    assert checks.check_structural_unit_merged_into_target_section(text, dispositions) == []


def test_structural_merged_into_target_section_generic_block_requires_fenced_code():
    dispositions = [_structure_disposition(
        unit_id="s0002", target_section="Development and Testing", claimed_paths=[],
    )]
    text_without_code = "## Development and Testing\n\nJust prose, no commands at all.\n"
    findings = checks.check_structural_unit_merged_into_target_section(text_without_code, dispositions)
    assert any(f["unit_id"] == "s0002" for f in findings)

    text_with_code = "## Development and Testing\n\n```bash\ngo test ./...\n```\n"
    assert checks.check_structural_unit_merged_into_target_section(text_with_code, dispositions) == []


# --- check_structural_unit_no_exact_duplicate_merge (hard gate) ----------------------------


def test_structural_no_exact_duplicate_merge_flags_duplicate():
    dispositions = [
        {"unit_id": "s0001", "disposition": "merged_reframed", "heading": "Project Structure", "target_section": "Project Structure"},
        {"unit_id": "s0002", "disposition": "merged_reframed", "heading": "Project Structure", "target_section": "Project Structure"},
    ]
    findings = checks.check_structural_unit_no_exact_duplicate_merge(dispositions)
    assert len(findings) == 1


def test_structural_no_exact_duplicate_merge_clean_on_distinct_headings():
    dispositions = [
        {"unit_id": "s0001", "disposition": "merged_reframed", "heading": "Testing", "target_section": "Development and Testing"},
        {"unit_id": "s0002", "disposition": "merged_reframed", "heading": "Running Examples", "target_section": "Development and Testing"},
    ]
    assert checks.check_structural_unit_no_exact_duplicate_merge(dispositions) == []


# --- check_structural_unit_tree_paths_plausible (heuristic) --------------------------------


def test_structural_tree_paths_plausible_flags_low_resolution_ratio(tmp_path):
    unit = _structural_unit(claimed_paths=("nonexistent/path/one.go", "nonexistent/path/two.go", "nonexistent/three.go"))
    dispositions = [_structure_disposition()]
    findings = checks.check_structural_unit_tree_paths_plausible([unit], dispositions, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["ratio"] == 0.0


def test_structural_tree_paths_plausible_clean_when_resolved(tmp_path):
    (tmp_path / "real.go").write_text("package x", encoding="utf-8")
    unit = _structural_unit(claimed_paths=("real.go",))
    dispositions = [_structure_disposition()]
    assert checks.check_structural_unit_tree_paths_plausible([unit], dispositions, str(tmp_path)) == []


# --- extract_badges / classify_badge --------------------------------------------------------


def test_extract_badges_matches_real_cells_go_badges():
    badges = checks.extract_badges(_REAL_CELLS_GO_README)
    assert [b["alt_text"] for b in badges] == ["Go Version", "Tests", "License"]
    assert badges[2]["link_url"] == "LICENSE"


def test_extract_badges_excludes_banner_line():
    text = (
        "[![Go Reference](https://pkg.go.dev/badge/x.svg)](https://pkg.go.dev/x)\n\n"
        "[![Some Product](https://products.aspose.org/media/cells/go/banner-readme.png)]"
        "(https://products.aspose.org/cells/go/)\n"
    )
    badges = checks.extract_badges(text)
    assert len(badges) == 1
    assert badges[0]["alt_text"] == "Go Reference"


def test_classify_badge_categories_real_cells_go_shapes():
    cases = [
        ({"alt_text": "Go Version", "image_url": "https://img.shields.io/badge/Go-%3E%3D1.18-blue", "link_url": "https://go.dev"}, "language_version"),
        ({"alt_text": "Tests", "image_url": "https://img.shields.io/badge/tests-passing-green", "link_url": "#"}, "ci_build_status"),
        ({"alt_text": "License", "image_url": "https://img.shields.io/badge/license-MIT-blue", "link_url": "LICENSE"}, "license"),
        ({"alt_text": "Go Reference", "image_url": "https://pkg.go.dev/badge/x.svg", "link_url": "https://pkg.go.dev/x"}, "language_package_reference"),
        ({"alt_text": "Contributors", "image_url": "https://img.shields.io/github/contributors/x.svg", "link_url": "https://github.com/x/graphs/contributors"}, "contributor_count"),
    ]
    for badge, expected_category in cases:
        assert checks.classify_badge(badge)["category"] == expected_category, badge


def test_classify_badge_python_pyversions_badge_is_language_version():
    # 2026-08-14 (cells/python regeneration): the portfolio-standard shields.io Python-compat
    # badge -- bare "Python" or "Python versions" alt text, "/pypi/pyversions/" image URL --
    # was falling through to package_version via link_url's bare pypi.org match, causing
    # check_no_duplicate_badges_in_candidate to misfire against the real, distinct PyPI-version
    # badge every Python product pairs it with. Real, captured-verbatim shapes.
    cases = [
        {"alt_text": "Python", "image_url": "https://img.shields.io/pypi/pyversions/aspose-cells-foss.svg",
         "link_url": "https://pypi.org/project/aspose-cells-foss/"},
        {"alt_text": "Python versions", "image_url": "https://img.shields.io/pypi/pyversions/aspose-email-foss.svg",
         "link_url": "https://pypi.org/project/aspose-email-foss/"},
    ]
    for badge in cases:
        assert checks.classify_badge(badge)["category"] == "language_version", badge


def test_classify_badge_cpp_static_version_badge_is_language_version():
    # 2026-08-14 (MT042, TC-HARDEN-58): found live -- 2 real, currently-shipped C++ products
    # (email/cpp, slides/cpp) have a real static "C++ 17"/"C++20" language-version badge that
    # fell through to "unknown" the moment check_badge_row_meets_verified_floor first ran
    # against real content, since "c%2b%2b" was never in the language_version image_url list.
    cases = [
        {"alt_text": "C++", "image_url": "https://img.shields.io/badge/C%2B%2B-17-blue.svg", "link_url": "CMakeLists.txt"},
        {"alt_text": "C++20", "image_url": "https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus", "link_url": "CMakeLists.txt"},
    ]
    for badge in cases:
        assert checks.classify_badge(badge)["category"] == "language_version", badge


def test_check_no_duplicate_badges_in_candidate_does_not_flag_real_python_pypi_pair():
    # Regression proof for the fix above, at the full-check level, not just classify_badge.
    text = (
        "# Aspose.Cells FOSS for Python\n\n"
        "[![PyPI version](https://img.shields.io/pypi/v/aspose-cells-foss.svg)]"
        "(https://pypi.org/project/aspose-cells-foss/) "
        "[![Python](https://img.shields.io/pypi/pyversions/aspose-cells-foss.svg)]"
        "(https://pypi.org/project/aspose-cells-foss/)\n"
    )
    assert checks.check_no_duplicate_badges_in_candidate(text) == []


def test_classify_badge_unknown_for_unrecognized_shape():
    badge = {"alt_text": "Aspose.Cells FOSS for Go", "image_url": "https://products.aspose.org/media/cells/go/banner-readme.png", "link_url": "https://products.aspose.org/cells/go/"}
    assert checks.classify_badge(badge)["category"] == "unknown"


# --- verify_badge_target ---------------------------------------------------------------------


def test_verify_badge_target_flags_placeholder_hash_link():
    badge = {"alt_text": "Tests", "image_url": "https://img.shields.io/badge/tests-passing-green", "link_url": "#"}
    result = checks.verify_badge_target(badge, "ci_build_status", "/irrelevant")
    assert result["target_kind"] == "placeholder"


def test_verify_badge_target_flags_static_badge_claims_dynamic_fact():
    badge = {"alt_text": "Tests", "image_url": "https://img.shields.io/badge/tests-passing-green", "link_url": "https://example.com/ci"}
    result = checks.verify_badge_target(badge, "ci_build_status", "/irrelevant")
    assert result["target_kind"] == "static_badge_claims_dynamic_fact"


def test_verify_badge_target_does_not_flag_legitimately_static_categories():
    # A static shields.io badge is fine for license/language-version -- those ARE legitimately
    # static facts, unlike CI/coverage/downloads/contributors.
    badge = {"alt_text": "License", "image_url": "https://img.shields.io/badge/license-MIT-blue", "link_url": "https://example.com/license"}
    result = checks.verify_badge_target(badge, "license", "/irrelevant")
    assert result["target_kind"] != "static_badge_claims_dynamic_fact"


def test_verify_badge_target_does_not_flag_real_dynamic_badge_shape():
    # A genuinely dynamic, live-queried badge (GitHub Actions workflow badge, the real pdf/go
    # shape) must never be flagged as static.
    badge = {"alt_text": "Build", "image_url": "https://github.com/x/y/actions/workflows/test.yml/badge.svg", "link_url": "https://github.com/x/y/actions"}
    result = checks.verify_badge_target(badge, "ci_build_status", "/irrelevant")
    assert result["target_kind"] != "static_badge_claims_dynamic_fact"


def test_verify_badge_target_resolves_local_file():
    badge = {"alt_text": "License", "image_url": "x", "link_url": "LICENSE"}
    result = checks.verify_badge_target(badge, "license", "runs/.clone_cache/aspose_cells_go")
    assert result["target_kind"] == "local_file_exists"


# --- _same_real_world_target / reconcile_badges --------------------------------------------


def test_same_real_world_target_ignores_label_differences():
    a = {"alt_text": "License", "link_url": "LICENSE"}
    b = {"alt_text": "License: MIT", "link_url": "LICENSE"}
    assert checks._same_real_world_target(a, b) is True


def test_same_real_world_target_rejects_different_targets_despite_same_label():
    a = {"alt_text": "License", "link_url": "LICENSE"}
    b = {"alt_text": "License", "link_url": "https://opensource.org/licenses/Apache-2.0"}
    assert checks._same_real_world_target(a, b) is False


def test_reconcile_badges_pairs_license_across_wording_difference():
    old_badges = checks.extract_badges(_REAL_CELLS_GO_README)
    new_badges = [{"unit_id": "b0001", "alt_text": "License: MIT", "image_url": "x", "link_url": "LICENSE"}]
    result = checks.reconcile_badges(old_badges, new_badges, "runs/.clone_cache/aspose_cells_go")
    assert len(result["duplicate_pairs"]) == 1
    pair = result["duplicate_pairs"][0]
    assert pair["category"] == "license"
    assert pair["keep"] == "b0001"  # candidate's own form wins the tie
    # Go Version and Tests have no candidate equivalent here -- genuine old_only candidates.
    old_only_alts = {b["alt_text"] for b in result["old_only"]}
    assert old_only_alts == {"Go Version", "Tests"}


def test_reconcile_badges_never_pairs_across_different_categories():
    old_badges = [{"unit_id": "o1", "alt_text": "License", "image_url": "x", "link_url": "LICENSE"}]
    new_badges = [{"unit_id": "n1", "alt_text": "Coverage", "image_url": "https://codecov.io/badge.svg", "link_url": "LICENSE"}]
    result = checks.reconcile_badges(old_badges, new_badges, "/irrelevant")
    assert result["duplicate_pairs"] == []
    assert len(result["old_only"]) == 1


# --- check_badge_disposition_coverage (hard gate) -------------------------------------------


def _badge_disposition(unit_id="b0001", action="preserved", new_badge_unit_id="b0001",
                        category="license", evidence_status="verified_against_source",
                        evidence_type="clone_cache_path", evidence_ref="LICENSE",
                        excluded_reason=None):
    return {
        "unit_id": unit_id, "action": action, "new_badge_unit_id": new_badge_unit_id,
        "category": category, "excluded_reason": excluded_reason,
        "verification": {"status": evidence_status, "evidence_type": evidence_type, "evidence_ref": evidence_ref},
    }


def test_badge_disposition_coverage_noop_when_no_old_badges():
    assert checks.check_badge_disposition_coverage([], [], []) == []


def test_badge_disposition_coverage_reproduces_the_real_tex_python_defect(tmp_path):
    """RC-badge-disposition-vacuous-pass (readme-refresh-hardening-and-regen-2026-08-30,
    TC-23): the real, confirmed defect -- tex/python's badge-dispositions.json labels 3
    badges "preserved" from an original upstream README with zero real badge markdown.
    Before this fix, `if not old_badges: return []` never even looked at `dispositions`."""
    dispositions = [
        _badge_disposition(unit_id="b0001", action="preserved", category="license"),
        _badge_disposition(unit_id="b0002", action="preserved", category="language_version"),
        _badge_disposition(unit_id="b0003", action="preserved", category="unknown"),
    ]
    findings = checks.check_badge_disposition_coverage([], [], dispositions)
    assert len(findings) == 3
    assert all("never existed" in f["reason"] for f in findings)


def test_badge_disposition_coverage_still_vacuous_when_dispositions_also_empty():
    # The genuinely-nothing-to-check case must stay a real vacuous pass, not a false alarm.
    assert checks.check_badge_disposition_coverage([], [], []) == []


def test_badge_disposition_coverage_no_old_badges_tolerates_excluded_entries():
    # "excluded"/"new" make no claim about an old badge surviving -- must not be flagged.
    dispositions = [_badge_disposition(unit_id="b0001", action="excluded", excluded_reason="no real old badges to preserve here at all")]
    assert checks.check_badge_disposition_coverage([], [], dispositions) == []


def test_badge_disposition_coverage_flags_missing_entry():
    old_badges = checks.extract_badges(_REAL_CELLS_GO_README)
    findings = checks.check_badge_disposition_coverage(old_badges, [], [])
    assert len(findings) == 3  # Go Version, Tests, License -- all 3 need a real entry


def test_badge_disposition_coverage_flags_missing_excluded_reason():
    old_badges = [{"unit_id": "b0001", "alt_text": "Tests", "image_url": "x", "link_url": "#"}]
    dispositions = [_badge_disposition(action="excluded", new_badge_unit_id=None, excluded_reason="short")]
    findings = checks.check_badge_disposition_coverage(old_badges, [], dispositions)
    assert any("excluded_reason" in f["reason"] for f in findings)


def test_badge_disposition_coverage_flags_bad_credited_reference():
    old_badges = [{"unit_id": "b0001", "alt_text": "License", "image_url": "x", "link_url": "LICENSE"}]
    new_badges = [{"unit_id": "b0001", "alt_text": "License: MIT", "image_url": "x", "link_url": "LICENSE"}]
    dispositions = [_badge_disposition(new_badge_unit_id="b9999")]  # doesn't exist in new_badges
    findings = checks.check_badge_disposition_coverage(old_badges, new_badges, dispositions)
    assert any("new_badge_unit_id" in f["reason"] for f in findings)


def test_badge_disposition_coverage_clean_real_cells_go_full_case():
    old_badges = checks.extract_badges(_REAL_CELLS_GO_README)
    new_badges = [{"unit_id": "b0001", "alt_text": "License: MIT", "image_url": "x", "link_url": "LICENSE"}]
    dispositions = [
        _badge_disposition(unit_id="b0001", action="preserved", new_badge_unit_id="b0001", category="language_version", evidence_ref="go.mod"),
        _badge_disposition(unit_id="b0002", action="excluded", new_badge_unit_id=None, category="ci_build_status",
                            excluded_reason="Static placeholder badge, links to '#', no real CI config in the repo."),
        _badge_disposition(unit_id="b0003", action="superseded_by_duplicate", new_badge_unit_id="b0001", category="license", evidence_ref="LICENSE"),
    ]
    assert checks.check_badge_disposition_coverage(old_badges, new_badges, dispositions) == []


# --- check_badge_preserved_or_credited_in_candidate (hard gate) ----------------------------


def test_badge_preserved_or_credited_flags_wrong_category_claim():
    new_badges = [{"unit_id": "b0001", "alt_text": "Contributors", "image_url": "https://img.shields.io/github/contributors/x.svg", "link_url": "https://github.com/x/graphs/contributors"}]
    dispositions = [_badge_disposition(new_badge_unit_id="b0001", category="license")]  # wrong -- b0001 is really contributor_count
    findings = checks.check_badge_preserved_or_credited_in_candidate(new_badges, dispositions)
    assert len(findings) == 1


def test_badge_preserved_or_credited_clean_on_real_match():
    new_badges = [{"unit_id": "b0001", "alt_text": "License: MIT", "image_url": "x", "link_url": "LICENSE"}]
    dispositions = [_badge_disposition(new_badge_unit_id="b0001", category="license")]
    assert checks.check_badge_preserved_or_credited_in_candidate(new_badges, dispositions) == []


# --- check_badge_probable_duplicate_disposition (heuristic) --------------------------------


def test_badge_probable_duplicate_disposition_flags_double_credit():
    dispositions = [
        _badge_disposition(unit_id="b0001", new_badge_unit_id="b0005"),
        _badge_disposition(unit_id="b0002", new_badge_unit_id="b0005"),
    ]
    findings = checks.check_badge_probable_duplicate_disposition(dispositions)
    assert len(findings) == 1


# --- check_badge_static_claims_dynamic_fact (heuristic, runs on candidate unconditionally) -


def test_badge_static_claims_dynamic_fact_flags_real_tests_badge_in_candidate():
    text = "[![Tests](https://img.shields.io/badge/tests-passing-green)](https://example.com/ci)\n"
    findings = checks.check_badge_static_claims_dynamic_fact(text)
    assert len(findings) == 1


def test_badge_static_claims_dynamic_fact_clean_on_legit_dynamic_badge():
    text = "[![Build](https://github.com/x/y/actions/workflows/test.yml/badge.svg)](https://github.com/x/y/actions)\n"
    assert checks.check_badge_static_claims_dynamic_fact(text) == []


# --- check_no_duplicate_badges_in_candidate (hard gate) -------------------------------------


def test_no_duplicate_badges_in_candidate_flags_real_duplicate():
    text = (
        "[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE) "
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)\n"
    )
    findings = checks.check_no_duplicate_badges_in_candidate(text)
    assert len(findings) == 1
    assert findings[0]["category"] == "license"


def test_no_duplicate_badges_in_candidate_clean_on_distinct_badges():
    text = (
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) "
        "[![Go Reference](https://pkg.go.dev/badge/x.svg)](https://pkg.go.dev/x) "
        "[![Contributors](https://img.shields.io/github/contributors/x.svg)](https://github.com/x/graphs/contributors)\n"
    )
    assert checks.check_no_duplicate_badges_in_candidate(text) == []


def test_no_duplicate_badges_in_candidate_ignores_label_only_similarity():
    # Two badges with similar-sounding labels but genuinely different targets must NOT be
    # flagged -- the mission's own explicit "compare meaning and targets, not labels" rule.
    text = (
        "[![Version](https://img.shields.io/badge/go-1.24-blue)](https://go.dev) "
        "[![Version](https://img.shields.io/nuget/v/SomePackage.svg)](https://nuget.org/packages/SomePackage)\n"
    )
    assert checks.check_no_duplicate_badges_in_candidate(text) == []


# --- leak prevention: the two new sibling disposition filenames ----------------------------


def test_internal_label_patterns_flag_structure_and_badge_dispositions_filenames():
    new_readme_a = "## Project Structure\n\nSee structure-dispositions.json for the full record.\n"
    result_a = checks.check_dropped_content("Old readme.\n", new_readme_a, "irrelevant")
    assert any("structure-dispositions.json" in label.lower() for label in result_a["internal_labels"])

    new_readme_b = "## License\n\nSee badge-dispositions.json for the full record.\n"
    result_b = checks.check_dropped_content("Old readme.\n", new_readme_b, "irrelevant")
    assert any("badge-dispositions.json" in label.lower() for label in result_b["internal_labels"])


# ============================================================================================
# Twenty-Fifth mission (2026-08-13): check_code_example_imports_match_source -- cells/java's
# upstream repo renamed its Java package from `com.aspose.cells_foss` to
# `org.aspose.cells_foss`; every one of the candidate's 20 `import com.aspose.cells_foss.X;`
# statements silently referenced a package that no longer exists. Fixtures below mirror the
# real, post-rename clone-cache shape (`src/main/java/org/aspose/cells_foss/Cell.java`,
# `package org.aspose.cells_foss;`) rather than reading the live clone cache, matching this
# module's own established "captured-verbatim fixture, not a live read" testing convention.
# ============================================================================================


def _write_java_class(root, package, class_name, extra_body=""):
    rel_dir = Path(*package.split("."))
    class_dir = root / "src" / "main" / "java" / rel_dir
    class_dir.mkdir(parents=True, exist_ok=True)
    (class_dir / f"{class_name}.java").write_text(
        f"package {package};\n\n{extra_body}\npublic class {class_name} {{\n}}\n",
        encoding="utf-8",
    )


def test_code_example_imports_match_source_flags_real_cells_java_rename(tmp_path):
    # The exact real defect: Cell.java is real, but declared under org.aspose.cells_foss now,
    # not com.aspose.cells_foss -- the candidate's own stale import claims the old package.
    _write_java_class(tmp_path, "org.aspose.cells_foss", "Cell")
    readme_text = (
        "## Quick Start\n\n```java\n"
        "import com.aspose.cells_foss.Cell;\n"
        "import com.aspose.cells_foss.Workbook;\n"
        "```\n"
    )
    findings = checks.check_code_example_imports_match_source(readme_text, str(tmp_path))
    reasons_by_class = {f["class_name"]: f["reason"] for f in findings}
    assert reasons_by_class.get("Cell") == "wrong_package"
    # Workbook has no real source file in this fixture at all -- a distinct finding reason.
    assert reasons_by_class.get("Workbook") == "class_not_found"


def test_code_example_imports_match_source_clean_when_package_matches(tmp_path):
    _write_java_class(tmp_path, "org.aspose.cells_foss", "Cell")
    readme_text = "## Quick Start\n\n```java\nimport org.aspose.cells_foss.Cell;\n```\n"
    assert checks.check_code_example_imports_match_source(readme_text, str(tmp_path)) == []


def test_code_example_imports_match_source_flags_class_not_found():
    readme_text = "## Quick Start\n\n```java\nimport org.aspose.cells_foss.Nonexistent;\n```\n"
    findings = checks.check_code_example_imports_match_source(readme_text, "/nonexistent/root")
    assert len(findings) == 1
    assert findings[0]["reason"] == "class_not_found"
    assert findings[0]["class_name"] == "Nonexistent"


def test_code_example_imports_match_source_ignores_jdk_stdlib_imports(tmp_path):
    # 2026-08-17 (slides/* portfolio audit): real, captured-verbatim false positive against
    # slides/java's own real candidate -- java.time/java.nio.file/java.io are never declared
    # anywhere in a product's clone cache (they ship with the JDK itself), so all 3 previously
    # fired as class_not_found despite being completely legitimate.
    readme_text = (
        "## Quick Start\n\n```java\n"
        "import java.time.LocalDateTime;\n"
        "import java.nio.file.Path;\n"
        "import java.io.ByteArrayOutputStream;\n"
        "import javax.xml.parsers.DocumentBuilder;\n"
        "```\n"
    )
    assert checks.check_code_example_imports_match_source(readme_text, str(tmp_path)) == []


def test_code_example_imports_match_source_still_flags_real_class_alongside_jdk_import(tmp_path):
    # Regression guard: JDK-stdlib exclusion must not silently swallow a REAL, wrong import in
    # the same code block.
    readme_text = (
        "## Quick Start\n\n```java\n"
        "import java.time.LocalDateTime;\n"
        "import org.aspose.slides_foss.Nonexistent;\n"
        "```\n"
    )
    findings = checks.check_code_example_imports_match_source(readme_text, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["class_name"] == "Nonexistent"


def test_code_example_imports_match_source_ignores_non_java_blocks(tmp_path):
    # A Python import statement inside a ```python block must never be parsed as a Java import,
    # even though "import x.y.Z" superficially resembles Java syntax.
    readme_text = "## Quick Start\n\n```python\nimport com.aspose.cells_foss.Cell\n```\n"
    assert checks.check_code_example_imports_match_source(readme_text, str(tmp_path)) == []


def test_code_example_imports_match_source_deduplicates_repeated_imports(tmp_path):
    _write_java_class(tmp_path, "org.aspose.cells_foss", "Cell")
    readme_text = (
        "## Quick Start\n\n```java\nimport com.aspose.cells_foss.Cell;\n```\n\n"
        "## Additional Examples\n\n```java\nimport com.aspose.cells_foss.Cell;\n```\n"
    )
    findings = checks.check_code_example_imports_match_source(readme_text, str(tmp_path))
    assert len(findings) == 1


def test_code_example_imports_match_source_noop_on_clean_readme(tmp_path):
    readme_text = "## Quick Start\n\n```bash\ngo test ./...\n```\n"
    assert checks.check_code_example_imports_match_source(readme_text, str(tmp_path)) == []


# ============================================================================================
# Twenty-Fifth mission (2026-08-13): check_diagram_container_duplicates_capability +
# check_project_structure_canonical_tree_format -- both real, live defects found while healing
# cells/java's diagram and Project Structure section.
# ============================================================================================

_CELLS_JAVA_DUPLICATE_DIAGRAM = _wrap(
    """flowchart TD
  subgraph StartingPoints["Starting Points"]
    i1["Existing .xlsx workbook (file path or stream)"]
    i2["JPEG, PNG, GIF, or BMP image bytes (for embedded pictures)"]
  end
  PRODUCT["Aspose.Cells FOSS for Java"]
  subgraph Capabilities["Core Capabilities"]
    c11["Embedded pictures"]
    c15["Load diagnostics and repair reporting"]
  end
  subgraph Outputs["Outputs"]
    o1[".xlsx workbook (file path or binary stream)"]
    o2["Load diagnostics and repair report"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs"""
)

# Negative control: a Starting Points node legitimately sharing ONE word with the Capability it
# feeds -- must never be flagged as a duplicate (this is the normal, expected relationship
# between an input and the capability that consumes it, not the same concept modeled twice).
_CSV_LEGITIMATE_OVERLAP_DIAGRAM = _wrap(
    """flowchart TD
  subgraph StartingPoints["Starting Points"]
    i1["CSV files"]
  end
  PRODUCT["Some Product"]
  subgraph Capabilities["Core Capabilities"]
    c1["CSV import and export"]
  end
  subgraph Outputs["Outputs"]
    o1["CSV files"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs"""
)


def test_diagram_container_duplicates_capability_flags_real_cells_java_shape():
    findings = checks.check_diagram_container_duplicates_capability(_CELLS_JAVA_DUPLICATE_DIAGRAM)
    by_node = {f["node_id"]: f for f in findings}
    assert "i2" in by_node
    assert by_node["i2"]["capability_node_id"] == "c11"
    assert "o2" in by_node
    assert by_node["o2"]["capability_node_id"] == "c15"


def test_diagram_container_duplicates_capability_ignores_legitimate_input_capability_overlap():
    # "CSV files" (Starting Points) sharing "csv" with "CSV import and export" (Capabilities) is
    # the ordinary, expected relationship between an input and the capability consuming it --
    # only 1 shared significant word, below the >=2-shared-word floor.
    assert checks.check_diagram_container_duplicates_capability(_CSV_LEGITIMATE_OVERLAP_DIAGRAM) == []


def test_diagram_container_duplicates_capability_clean_on_simplified_diagram():
    assert checks.check_diagram_container_duplicates_capability(TRANSFORM_CELLS_CPP) == []


def test_diagram_container_duplicates_capability_noop_when_no_mermaid_block():
    assert checks.check_diagram_container_duplicates_capability("# No diagram here\n") == []


# --- check_project_structure_canonical_tree_format (hard gate) -----------------------------

_PROJECT_STRUCTURE_BOX_DRAWING = (
    "# Some Product\n\n## Project Structure\n\n"
    "```\n├── src/\n│   └── main.go\n└── README.md\n```\n\n## License\n\nMIT.\n"
)

_PROJECT_STRUCTURE_PLAIN_TEXT = (
    "# Some Product\n\n## Project Structure\n\n"
    "```text\nsrc/main/java/org/aspose/cells_foss/\n"
    "  Public API surface: Workbook, Worksheet, Cell\n```\n\n## License\n\nMIT.\n"
)


def test_project_structure_canonical_tree_format_noop_when_section_absent():
    assert checks.check_project_structure_canonical_tree_format("# Product\n\n## License\n\nMIT.\n") == []


def test_project_structure_canonical_tree_format_clean_on_real_cells_go_shape():
    assert checks.check_project_structure_canonical_tree_format(_PROJECT_STRUCTURE_BOX_DRAWING) == []


def test_project_structure_canonical_tree_format_flags_real_cells_java_plain_text_shape():
    findings = checks.check_project_structure_canonical_tree_format(_PROJECT_STRUCTURE_PLAIN_TEXT)
    assert len(findings) == 1
    assert "box-drawing" in findings[0]["reason"]


def test_project_structure_canonical_tree_format_flags_missing_fenced_block():
    text = "# Some Product\n\n## Project Structure\n\nJust prose, no tree at all.\n\n## License\n\nMIT.\n"
    findings = checks.check_project_structure_canonical_tree_format(text)
    assert len(findings) == 1
    assert "no fenced code block" in findings[0]["reason"]


# ==================================================================================================
# Thirty-First incident / MT041 (2026-08-14): dependency accuracy. The real, captured-verbatim
# defect this whole mission exists to fix: cells/rust's real, live Installation sentence stated
# "Requires a recent stable Rust toolchain (2021 edition) -- no external runtime or Microsoft
# Office installation is needed" while its own Cargo.toml declares 7 real runtime crates (chrono,
# zip, sha2, base64, serde_json, roxmltree, getrandom) -- a same-document contradiction against
# that file's own, correct Intro paragraph, which already, correctly named all 7. (The live file
# has since been independently healed to remove this specific sentence during other work this
# session -- the text below is preserved verbatim from the original, confirmed incident, per this
# project's own "prove it against the real, captured defect" discipline, not a synthetic stand-in.)
# ==================================================================================================

_CELLS_RUST_REAL_INTRO = (
    "Aspose.Cells FOSS for Rust is a free, open-source, pure-Rust library for creating,\n"
    "loading, editing, and saving Excel `.xlsx` (Office Open XML / SpreadsheetML) workbooks.\n"
    "It exposes an API modeled after Aspose.Cells, so\n"
    "the familiar `Workbook` / `Worksheet` / `Cells` object model is available to Rust\n"
    "programs with no proprietary runtime, no Microsoft Office installation, and no external\n"
    "Aspose dependency. The OOXML packaging -- ZIP container, relationships, shared strings,\n"
    "styles, worksheet XML, and charts -- is implemented from scratch on top of a small set of\n"
    "general-purpose crates: `zip` (package container), `roxmltree` (XML parsing), `chrono`\n"
    "(date/time), `sha2` / `base64` / `getrandom` (protection hashing), and `serde_json`.\n"
)
_CELLS_RUST_REAL_BAD_INSTALLATION = (
    "## Installation\n\n"
    "```toml\n[dependencies]\naspose-cells-foss-rust = { git = "
    '"https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Rust" }\n```\n\n'
    "Requires a recent stable Rust toolchain (2021 edition) -- no external runtime or "
    "Microsoft Office installation is needed.\n"
)
_CELLS_RUST_REAL_BAD_README = (
    "# Aspose.Cells FOSS for Rust\n\n" + _CELLS_RUST_REAL_INTRO + "\n"
    + _CELLS_RUST_REAL_BAD_INSTALLATION + "\n## License\n\nMIT.\n"
)

_CELLS_RUST_DEPENDENCY_SNAPSHOT = {
    "family": "cells", "platform": "rust", "ecosystem": "cargo", "applicable": True,
    "not_applicable_reason": None,
    "required": [
        {"name": n, "ecosystem": "cargo", "version_constraint": v, "source_type": "registry",
         "category": "required", "dev_only": False, "activating_feature": None,
         "platform_condition": None, "role": "runtime", "purpose": None, "is_direct": True,
         "extraction_confidence": "structured_parse"}
        for n, v in [
            ("chrono", "0.4"), ("zip", "0.6"), ("sha2", "0.10"), ("base64", "0.22"),
            ("serde_json", "1"), ("roxmltree", "0.20"), ("getrandom", "0.3"),
        ]
    ],
    "optional": [], "native_system": [], "proprietary_runtime": [], "development": [],
    "source_manifest_path": "Cargo.toml", "source_revision": "0339b7e7",
    "extracted_at": "2026-08-14T00:00:00Z", "extractor_schema_version": "dep-snapshot-v1",
    "parse_errors": [],
}


def test_check_unqualified_dependency_claims_fires_on_real_cells_rust_sentence():
    """The mandatory fail-closed fixture (mission regression test #7)."""
    findings = checks.check_unqualified_dependency_claims(_CELLS_RUST_REAL_BAD_README)
    assert findings
    assert any("no external runtime" in f["phrase"] for f in findings)


def test_check_unqualified_dependency_claims_flags_no_external_dependencies():
    assert checks.check_unqualified_dependency_claims(
        "This library has no external dependencies."
    )


def test_check_unqualified_dependency_claims_flags_dependency_free():
    assert checks.check_unqualified_dependency_claims("A fully dependency-free crate.")


def test_check_unqualified_dependency_claims_flags_completely_standalone():
    assert checks.check_unqualified_dependency_claims("This is completely standalone.")


def test_check_unqualified_dependency_claims_passes_scoped_crate_claim():
    assert checks.check_unqualified_dependency_claims(
        "This library has no external runtime crate dependencies beyond the standard build."
    ) == []


def test_check_unqualified_dependency_claims_passes_scoped_native_claim():
    assert checks.check_unqualified_dependency_claims(
        "There are no native system libraries required to build this project."
    ) == []


def test_check_unqualified_dependency_claims_passes_scoped_proprietary_runtime_claim():
    assert checks.check_unqualified_dependency_claims(
        "The library requires no proprietary Aspose runtime to operate."
    ) == []


def test_check_dependency_snapshot_completeness_blocks_on_missing_snapshot():
    findings = checks.check_dependency_snapshot_completeness("# Product\n", None)
    assert len(findings) == 1
    assert "no DependencySnapshot" in findings[0]["reason"]


def test_check_dependency_snapshot_completeness_blocks_on_invariant_violation():
    bad = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, applicable=False, not_applicable_reason=None)
    findings = checks.check_dependency_snapshot_completeness("# Product\n", bad)
    assert len(findings) == 1


def test_check_dependency_snapshot_completeness_passes_ok_snapshot():
    assert checks.check_dependency_snapshot_completeness("# Product\n", _CELLS_RUST_DEPENDENCY_SNAPSHOT) == []


def test_check_dependency_direct_transitive_confusion_flags_unreal_name():
    text = (
        "## Dependencies\n\n### Required Package Dependencies\n\n"
        "- `chrono` 0.4 -- date handling.\n- `some-transitive-crate` 1.0 -- not real.\n"
    )
    findings = checks.check_dependency_direct_transitive_confusion(text, _CELLS_RUST_DEPENDENCY_SNAPSHOT)
    assert len(findings) == 1
    assert findings[0]["name"] == "some-transitive-crate"


def test_check_dependency_direct_transitive_confusion_clean_on_real_manifest_names():
    text = "## Dependencies\n\n### Required Package Dependencies\n\n- `chrono` 0.4 -- date handling.\n"
    assert checks.check_dependency_direct_transitive_confusion(text, _CELLS_RUST_DEPENDENCY_SNAPSHOT) == []


# --- check_dependency_section_subheadings_present (readme-refresh-seo-deps-headings-hardening,
# 2026-08-19) ----------------------------------------------------------------------------------


def test_check_dependency_section_subheadings_present_flags_headingless_flat_prose():
    # The real, confirmed 3d/net defect: a ## Dependencies section with real, accurate content
    # but zero of the four mandated ### subheadings.
    text = (
        "## Dependencies\n\nNo required third-party package dependencies. The published "
        "package builds from Foo.csproj, which declares zero PackageReference entries.\n"
    )
    findings = checks.check_dependency_section_subheadings_present(
        text, dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, required=[]),
    )
    assert any("Required Package Dependencies" in f["reason"] for f in findings)


def test_check_dependency_section_subheadings_present_passes_full_structure():
    text = (
        "## Dependencies\n\n### Required Package Dependencies\n\n"
        "- `chrono` 0.4 -- date handling.\n\n"
        "### Optional Dependencies\n\nNo optional third-party package dependencies.\n"
    )
    assert checks.check_dependency_section_subheadings_present(
        text, _CELLS_RUST_DEPENDENCY_SNAPSHOT,
    ) == []


def test_check_dependency_section_subheadings_present_requires_native_system_when_populated():
    text = "## Dependencies\n\n### Required Package Dependencies\n\n- `chrono` 0.4 -- date handling.\n"
    snapshot = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, native_system=[
        {"name": "edition", "ecosystem": "cargo", "version_constraint": "2021",
         "source_type": "registry", "category": "native-system", "dev_only": False,
         "activating_feature": None, "platform_condition": None, "role": "runtime",
         "purpose": None, "is_direct": True, "extraction_confidence": "structured_parse"},
    ])
    findings = checks.check_dependency_section_subheadings_present(text, snapshot)
    assert any(f["bucket"] == "native_system" for f in findings)


def test_check_dependency_section_subheadings_present_omits_empty_buckets_silently():
    # Optional/Native/Development all genuinely empty -- silent omission is correct, not a
    # finding, when Required Package Dependencies is present.
    text = "## Dependencies\n\n### Required Package Dependencies\n\n- `chrono` 0.4 -- date handling.\n"
    assert checks.check_dependency_section_subheadings_present(
        text, _CELLS_RUST_DEPENDENCY_SNAPSHOT,
    ) == []


def test_check_dependency_section_subheadings_present_no_snapshot_no_missing_section_noop():
    assert checks.check_dependency_section_subheadings_present("# Product\n", None) == []
    assert checks.check_dependency_section_subheadings_present(
        "# Product\n", _CELLS_RUST_DEPENDENCY_SNAPSHOT,
    ) == []


def test_bulleted_dependency_names_does_not_truncate_dotted_npm_scoped_name():
    # Real bug found live 2026-08-14 against cells/typescript: splitting on "." truncated the
    # real npm-scoped dependency "@zip.js/zip.js" to "@zip", producing a false
    # check_dependency_direct_transitive_confusion finding against a real manifest entry.
    text = (
        "## Dependencies\n\n### Required Package Dependencies\n\n"
        "- `@zip.js/zip.js` ^2.8.21 -- reads and writes the ZIP container.\n"
        "- `@xmldom/xmldom` ^0.8.10 -- parses XML.\n"
    )
    snapshot = dict(
        _CELLS_RUST_DEPENDENCY_SNAPSHOT,
        required=[
            {"name": "@zip.js/zip.js", "ecosystem": "npm", "version_constraint": "^2.8.21",
             "source_type": "registry", "category": "required", "dev_only": False,
             "activating_feature": None, "platform_condition": None, "role": "runtime",
             "purpose": None, "is_direct": True, "extraction_confidence": "structured_parse"},
            {"name": "@xmldom/xmldom", "ecosystem": "npm", "version_constraint": "^0.8.10",
             "source_type": "registry", "category": "required", "dev_only": False,
             "activating_feature": None, "platform_condition": None, "role": "runtime",
             "purpose": None, "is_direct": True, "extraction_confidence": "structured_parse"},
        ],
    )
    assert checks.check_dependency_direct_transitive_confusion(text, snapshot) == []


def test_check_dependency_optional_presented_as_required_flags_misplacement():
    snapshot = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, optional=[
        {"name": "rayon", "ecosystem": "cargo", "version_constraint": "1", "source_type": "registry",
         "category": "optional", "dev_only": False, "activating_feature": "parallel",
         "platform_condition": None, "role": "runtime", "purpose": None, "is_direct": True,
         "extraction_confidence": "structured_parse"},
    ])
    text = "## Dependencies\n\n### Required Package Dependencies\n\n- `rayon` 1 -- parallel save.\n"
    findings = checks.check_dependency_optional_presented_as_required(text, snapshot)
    assert len(findings) == 1
    assert findings[0]["name"] == "rayon"


def test_check_dependency_dev_only_presented_as_runtime_flags_misplacement():
    snapshot = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, development=[
        {"name": "criterion", "ecosystem": "cargo", "version_constraint": "0.5", "source_type": "registry",
         "category": "required", "dev_only": True, "activating_feature": None,
         "platform_condition": None, "role": "runtime", "purpose": None, "is_direct": True,
         "extraction_confidence": "structured_parse"},
    ])
    text = "## Dependencies\n\n### Required Package Dependencies\n\n- `criterion` 0.5 -- benchmarks.\n"
    findings = checks.check_dependency_dev_only_presented_as_runtime(text, snapshot)
    assert len(findings) == 1
    assert findings[0]["name"] == "criterion"


def test_check_dependency_development_claim_not_in_manifest_flags_real_slides_python_fabrication():
    # 2026-08-17 (slides/* portfolio audit): real, captured-verbatim fabrication -- slides/
    # python's own candidate claims `pytest` and `python-pptx` as development dependencies;
    # neither is declared anywhere in the real pyproject.toml (no [project.optional-
    # dependencies] table exists at all) nor imported anywhere in the real test suite. Every
    # OTHER dependency check in this module passed this content cleanly.
    snapshot = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, development=[])
    text = (
        "## Dependencies\n\n### Development Dependencies\n\n"
        "- `pytest` >= 7 -- the test runner.\n"
        "- `python-pptx` >= 1.0 -- an independent reader used by this project's own "
        "conformance tests.\n"
    )
    findings = checks.check_dependency_development_claim_not_in_manifest(text, snapshot)
    assert {f["name"] for f in findings} == {"pytest", "python-pptx"}


def test_check_dependency_development_claim_not_in_manifest_clean_on_real_manifest_names():
    snapshot = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, development=[
        {"name": "criterion", "ecosystem": "cargo", "version_constraint": "0.5", "source_type": "registry",
         "category": "required", "dev_only": True, "activating_feature": None,
         "platform_condition": None, "role": "runtime", "purpose": None, "is_direct": True,
         "extraction_confidence": "structured_parse"},
    ])
    text = "## Dependencies\n\n### Development Dependencies\n\n- `criterion` 0.5 -- benchmarks.\n"
    assert checks.check_dependency_development_claim_not_in_manifest(text, snapshot) == []


def test_check_dependency_development_claim_not_in_manifest_noop_without_snapshot():
    text = "## Dependencies\n\n### Development Dependencies\n\n- `pytest` >= 7 -- fabricated.\n"
    assert checks.check_dependency_development_claim_not_in_manifest(text, None) == []


def test_bulleted_dependency_names_ignores_backtick_wrapped_version_constraint():
    # Real, live-confirmed bug (2026-08-17): font/python's real, verified bullet backtick-wraps
    # its version constraint (the established `` - `name` `constraint` -- description `` shape),
    # and slides/java backtick-wraps a bare version like `5.11.4` with no constraint operator at
    # all -- both were extracted as if they were separate, unrecognized dependency NAMES,
    # producing false "possibly a fabricated dependency claim" findings on already-shipped,
    # already-verified content. No real package name in any ecosystem this module handles starts
    # with a comparison operator or is purely digits and dots.
    text = (
        "## Dependencies\n\n### Development Dependencies\n\n"
        '- `pytest` `>=7.4` — test suite runner (`pip install -e ".[dev]"`).\n'
        "- [`org.junit.jupiter:junit-jupiter-api`](https://example.test) `5.11.4`\n"
    )
    names = checks._bulleted_dependency_names(checks._extract_h3_subsection(
        checks._split_into_sections(text)["Dependencies"], "Development Dependencies",
    ))
    assert names == ["pytest", "org.junit.jupiter:junit-jupiter-api"]


def test_bulleted_dependency_names_ignores_backtick_tokens_after_em_dash():
    # Real, live-confirmed bug (2026-08-17, pdf/java): a real, legitimate backtick code span
    # inside the DESCRIPTION half of a bullet ("the Maven `test` phase") was extracted as if it
    # were a second dependency name, "test" -- a fabricated-looking finding for a real, accurate
    # candidate. Only the name+constraint prefix before the em-dash is a dependency-name claim.
    text = (
        "## Dependencies\n\n### Development Dependencies\n\n"
        "- `org.junit.jupiter:junit-jupiter` 5.10.2 — test runner used by the Maven `test` phase; "
        "not needed to use the published library.\n"
    )
    names = checks._bulleted_dependency_names(checks._extract_h3_subsection(
        checks._split_into_sections(text)["Dependencies"], "Development Dependencies",
    ))
    assert names == ["org.junit.jupiter:junit-jupiter"]


def test_check_dependency_development_claim_not_in_manifest_clean_on_real_font_python_text():
    # Full-battery regression proof for the two fixes above, using the real, captured-verbatim
    # font/python Development Dependencies text this bug was originally found against.
    snapshot = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, development=[
        {"name": "pytest", "ecosystem": "pypi", "version_constraint": ">=7.4", "source_type": "registry",
         "category": "required", "dev_only": True, "activating_feature": None,
         "platform_condition": None, "role": "runtime", "purpose": None, "is_direct": True,
         "extraction_confidence": "structured_parse"},
        {"name": "ruff", "ecosystem": "pypi", "version_constraint": ">=0.4", "source_type": "registry",
         "category": "required", "dev_only": True, "activating_feature": None,
         "platform_condition": None, "role": "runtime", "purpose": None, "is_direct": True,
         "extraction_confidence": "structured_parse"},
        {"name": "build", "ecosystem": "pypi", "version_constraint": ">=1.2", "source_type": "registry",
         "category": "required", "dev_only": True, "activating_feature": None,
         "platform_condition": None, "role": "runtime", "purpose": None, "is_direct": True,
         "extraction_confidence": "structured_parse"},
    ])
    text = (
        "## Dependencies\n\n### Development Dependencies\n\n"
        '- `pytest` `>=7.4` — test suite runner (`pip install -e ".[dev]"`; `uv`\'s own\n'
        "  `dependency-groups.dev` pins `pytest>=9.0.2` for `uv run`/`uv sync` workflows).\n"
        "- `ruff` `>=0.4` — linter.\n"
        "- `build` `>=1.2` — builds the wheel/sdist for release.\n"
    )
    assert checks.check_dependency_development_claim_not_in_manifest(text, snapshot) == []


def test_check_dependency_scope_claim_matches_evidence_flags_unproven_proprietary_claim():
    text = "This crate requires no proprietary Aspose runtime to operate."
    findings = checks.check_dependency_scope_claim_matches_evidence(text, _CELLS_RUST_DEPENDENCY_SNAPSHOT)
    assert len(findings) == 1


def test_check_dependencies_intro_contradiction_fires_on_real_cells_rust_shape():
    """The same-file-contradiction fixture (mission regression test #15): the real Intro
    paragraph correctly names real crates while a later section states an unqualified claim."""
    findings = checks.check_dependencies_intro_contradiction(
        _CELLS_RUST_REAL_BAD_README, _CELLS_RUST_DEPENDENCY_SNAPSHOT,
    )
    assert findings


def test_check_dependencies_intro_contradiction_clean_when_both_sections_agree():
    good_installation = (
        "## Installation\n\n```toml\n[dependencies]\naspose-cells-foss-rust = "
        '{ git = "https://..." }\n```\n\nRequires a recent stable Rust toolchain '
        "(2021 edition or later). No proprietary Aspose runtime and no Microsoft Office "
        "installation is required.\n\n## Dependencies\n\n### Required Package Dependencies\n\n"
        "- `chrono` 0.4 -- date/time handling.\n"
    )
    good_readme = (
        "# Aspose.Cells FOSS for Rust\n\n" + _CELLS_RUST_REAL_INTRO + "\n"
        + good_installation + "\n## License\n\nMIT.\n"
    )
    assert checks.check_dependencies_intro_contradiction(good_readme, _CELLS_RUST_DEPENDENCY_SNAPSHOT) == []


def test_check_dependency_native_system_scope_limitations_placement_flags_duplicate():
    text = (
        "## Dependencies\n\n### Native and System Requirements\n\n"
        "- Requires a recent stable Rust toolchain (2021 edition or later).\n\n"
        "## Scope and Limitations\n\n"
        "- Requires a recent stable Rust toolchain (2021 edition or later).\n\n"
        "This project is licensed under the [MIT License](LICENSE), which permits broader "
        "commercial use via [Aspose.Cells for Rust -- Enterprise Edition](https://products.aspose.com/cells/rust/).\n"
    )
    findings = checks.check_dependency_native_system_scope_limitations_placement(text)
    assert len(findings) == 1


def test_check_dependency_native_system_scope_limitations_placement_clean_no_duplicate():
    text = (
        "## Dependencies\n\n### Native and System Requirements\n\n"
        "- Requires a recent stable Rust toolchain (2021 edition or later).\n\n"
        "## Scope and Limitations\n\n- Some unrelated limitation entirely.\n"
    )
    assert checks.check_dependency_native_system_scope_limitations_placement(text) == []


def test_check_dependency_disposition_reconciliation_flags_narrative_only_evidence():
    dispositions = [{
        "unit_id": "u0001", "classification": "5_dependency_claim", "disposition": "merged_verbatim",
        "target_section": "Dependencies",
        "verification": {"status": "verified_against_manifest", "evidence_ref": "trust me, it's fine"},
    }]
    findings = checks.check_dependency_disposition_reconciliation([], dispositions, _CELLS_RUST_DEPENDENCY_SNAPSHOT)
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0001"


def test_check_dependency_disposition_reconciliation_passes_real_manifest_evidence():
    dispositions = [{
        "unit_id": "u0001", "classification": "5_dependency_claim", "disposition": "merged_verbatim",
        "target_section": "Dependencies",
        "verification": {"status": "verified_against_manifest", "evidence_ref": "Cargo.toml (chrono)"},
    }]
    findings = checks.check_dependency_disposition_reconciliation([], dispositions, _CELLS_RUST_DEPENDENCY_SNAPSHOT)
    assert findings == []


def test_check_required_sections_requires_dependencies_heading():
    """Mission regression test #17."""
    missing = checks.check_required_sections(_ALL_SECTIONS_README.replace("## Dependencies\n", ""))
    assert "Dependencies" in missing
    assert checks.check_required_sections(_ALL_SECTIONS_README) == []


def test_5_dependency_claim_disposition_round_trips_through_unmodified_coverage_check():
    """Proves TC-HARDEN-54's own central claim: extending the enum sets alone is sufficient --
    zero new hard-gate code needed in check_content_unit_disposition_coverage itself."""
    content_units = [{"unit_id": "u0001", "excerpt": "Depends on chrono, zip, and sha2."}]
    dispositions = [{
        "unit_id": "u0001", "classification": "5_dependency_claim", "disposition": "merged_verbatim",
        "target_section": "Dependencies",
        "verification": {"status": "verified_against_manifest", "evidence_ref": "Cargo.toml [dependencies]"},
    }]
    assert checks.check_content_unit_disposition_coverage(content_units, dispositions) == []


def test_check_dependency_section_manifest_corroboration_handles_multi_crate_bullet():
    """Real bug found running against the real, corrected cells/rust candidate: a single,
    natural bullet naming 3 related crates together must not silently drop 2 of them."""
    text = (
        "## Dependencies\n\n### Required Package Dependencies\n\n"
        "- `sha2` 0.10, `base64` 0.22, `getrandom` 0.3 -- hashing and encoding.\n"
    )
    snapshot = dict(_CELLS_RUST_DEPENDENCY_SNAPSHOT, required=[
        e for e in _CELLS_RUST_DEPENDENCY_SNAPSHOT["required"]
        if e["name"] in ("sha2", "base64", "getrandom")
    ])
    assert checks.check_dependency_section_manifest_corroboration(text, snapshot, None) == []


def test_check_dependency_version_pin_freshness_does_not_confuse_crate_name_digit_with_version():
    """Real bug found the same way: `sha2` itself contains a digit, so a whole-bullet version
    scan matched "2" (from the crate name) before ever reaching the real "0.10" that follows
    it. Each name must be paired only with the version immediately following its own token."""
    text = (
        "## Dependencies\n\n### Required Package Dependencies\n\n"
        "- `sha2` 0.10, `base64` 0.22, `getrandom` 0.3 -- hashing and encoding.\n"
    )
    findings = checks.check_dependency_version_pin_freshness(text, _CELLS_RUST_DEPENDENCY_SNAPSHOT)
    assert findings == []


def test_check_dependency_version_pin_freshness_still_fires_on_real_mismatch():
    text = "## Dependencies\n\n### Required Package Dependencies\n\n- `chrono` 0.9 -- date handling.\n"
    findings = checks.check_dependency_version_pin_freshness(text, _CELLS_RUST_DEPENDENCY_SNAPSHOT)
    assert len(findings) == 1
    assert findings[0]["name"] == "chrono"
    assert findings[0]["readme_version"] == "0.9"


def test_build_dependency_verification_matrix_scores_real_cells_rust_snapshot():
    readme = (
        "# Aspose.Cells FOSS for Rust\n\n" + _CELLS_RUST_REAL_INTRO + "\n"
        + "## Dependencies\n\n### Required Package Dependencies\n\n"
        "- `chrono` 0.4 -- date/time handling.\n"
        "- `zip` 0.6 -- ZIP container.\n"
    )
    matrix = checks.build_dependency_verification_matrix(_CELLS_RUST_DEPENDENCY_SNAPSHOT, readme)
    rows_by_name = {r["name"]: r for r in matrix["rows"]}
    assert rows_by_name["chrono"]["in_readme_dependencies_section"] is True
    assert rows_by_name["chrono"]["in_readme_prose_elsewhere"] is True  # named in the real Intro
    assert rows_by_name["chrono"]["status"] == "VERIFIED"
    # roxmltree is a real required dep, mentioned in the Intro, but never listed in the
    # Dependencies section in this deliberately-incomplete test README -- still corroborated
    # via prose alone (1 signal), correctly flagged NEEDS_REVIEW, not silently dropped.
    assert rows_by_name["roxmltree"]["in_readme_dependencies_section"] is False
    assert rows_by_name["roxmltree"]["status"] == "NEEDS_REVIEW"


# =================================================================================================
# Thirty-Seventh incident / MT047 (2026-08-15): TC-HARDEN-74/75/76/78 -- font/python preservation
# audit hardening. Every fixture below is a small, real, captured-verbatim excerpt of font/python's
# own actual old README / source (or, where a control-pair contrast is needed, a hermetic tmp_path
# clone cache populated with real, captured file content) -- per the mission's own explicit
# instruction NOT to turn font/python's full README into a universal golden template.
# =================================================================================================

# Real, captured-verbatim excerpt of font/python's actual old README (runs/.clone_cache/
# aspose_font_python/README.md) -- the exact section (## Python API Highlights) whose ~120-line
# code block plus one real trailing prose sentence fell through BOTH extract_old_readme_content_
# units and extract_old_readme_structural_units simultaneously (Stage 1's own sharper root-cause
# finding). Trimmed to the real opening imports/calls plus the real trailing sentence -- not the
# whole 130-line block -- while still exceeding _CODE_UNIT_SPLIT_THRESHOLD (15 non-blank lines)
# so the compound-block-splitting behavior is genuinely exercised, not just asserted.
_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT = """## Python API Highlights

```python
from aspose_font import FontLoader, FontPreviewBuilder, FontQaReporter, WebFontBuilder
from aspose_font import FontCleaner
from aspose_font.subsetter import FontSubsetter

font = FontLoader.open("Roboto-VariableFont_wdth,wght.ttf")

subset_result = FontSubsetter.subset_for_web_with_coverage(
    font,
    presets=("latin", "arabic"),
    text="Aspose مرحبا",
)
print(subset_result.font.num_glyphs)
print(subset_result.coverage.covered_count, subset_result.coverage.missing_codepoints)

preview = FontPreviewBuilder.build(font, instance_name="Bold", text="Preview")
preview.write_to("preview.png")

menu_named = font.instantiate(
    {"wght": 700, "wdth": 75},
    naming_strategy="ribbi-safe",
    legacy_family_name="Acme Sans Menu",
    typographic_family_name="Acme Sans Pro",
    stat_policy="static",
)
print(menu_named.ttf_tables.name.get(1), menu_named.ttf_tables.name.get(16))

preview = font.preview_naming_policy(
    {"wght": 700, "wdth": 75},
    naming_strategy="ribbi-safe",
    stat_policy="static",
)
print(preview.stat_diagnostics.generated_stat_axis_value_flags)

live_bundle = WebFontBuilder.build(
    font,
    include_woff=False,
    variable_mode="live",
)
print(live_bundle.manifest["requested_variable_mode"], live_bundle.manifest["export_mode"])

static_stat_bundle = WebFontBuilder.build(
    font,
    include_woff=False,
    variable_mode="static",
    instance_name="Bold",
    stat_policy="static",
)
print(static_stat_bundle.manifest["requested_stat_policy"])

grid_package = font.smart_instancer.build_axis_grid_web_family_package(
    "wght",
    [400.0, 700.0],
    family_name="Roboto Grid",
    include_woff=False,
    preview_text="Grid Family",
    naming_strategy="preserve-family",
)
grid_package.write_to("web-grid-family")
print(grid_package.manifest["bundles"][1]["review_label"])
```

The generated grid-family package links back to the demo-site direction: `family.html` shows
coordinate labels like `wdth=100 wght=700`, while `family-manifest.json` exposes the same
`review_label` and `instance_coordinates` fields for automation.
"""

# Real, captured-verbatim excerpt of font/python's actual old README's own "## CLI Highlights"
# section -- the real 4-category structure (general inspection/conversion, variable-font previews,
# QA tooling, web packaging), each category separated by a real blank line in the source.
_REAL_FONT_PYTHON_CLI_HIGHLIGHTS_EXCERPT = """## CLI Highlights

```bash
# General inspection and conversion
aspose-font info Roboto.ttf
aspose-font convert Roboto.ttf Roboto.woff2 --to woff2
aspose-font meta-clean Roboto.ttf Roboto-clean.ttf

# Variable-font previews and review boards
aspose-font preview Roboto-VariableFont_wdth,wght.ttf preview.svg --instance-name Bold --format svg
aspose-font var-instance Roboto-VariableFont_wdth,wght.ttf bold-condensed.ttf --instance wght=Bold --instance wdth=Condensed
aspose-font var-info Roboto-VariableFont_wdth,wght.ttf
aspose-font preview-grid-sheet Roboto-VariableFont_wdth,wght.ttf grid-sheet.png --axis wght --use-presets

# QA tooling
aspose-font qa-report Roboto-VariableFont_wdth,wght.ttf --preset latin --text "Aspose QA" --json-output qa-report.json --html-output qa-report.html
aspose-font var-compat Roboto-VariableFont_wdth,wght.ttf --before-instance-name Regular --after-instance-name "Condensed Bold" --text Aspose
aspose-font var-delta Roboto-VariableFont_wdth,wght.ttf --instance-name Bold --char A

# Web packaging
aspose-font web-build Roboto-VariableFont_wdth,wght.ttf web-out --instance-name Bold --template editorial --no-woff
aspose-font web-family Roboto-VariableFont_wdth,wght.ttf family-out --instance-name Bold --naming-strategy preserve-family --no-woff
aspose-font web-grid Roboto-VariableFont_wdth,wght.ttf grid-web --axis wght --use-presets --no-woff
```
"""


# --- extract_old_readme_code_units (TC-HARDEN-74) -------------------------------------------


def test_extract_code_units_unconditional_real_python_api_highlights():
    # Stage 8 test 1: the exact bug this incident found -- a section combining a large code block
    # with real trailing prose must produce BOTH a real prose unit (via extract_old_readme_content_
    # units, already correctly capturing the trailing sentence today) AND real code units (via the
    # new, unconditional extractor) -- never neither, never the code silently swallowed.
    prose_units = checks.extract_old_readme_content_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    code_units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    assert any("grid-family package" in u["excerpt"] for u in prose_units)
    assert len(code_units) > 1
    assert all(u["heading_context"] == "Python API Highlights" for u in code_units)
    all_fingerprints = {call for u in code_units for call in u["api_call_fingerprint"]}
    assert "FontSubsetter.subset_for_web_with_coverage" in all_fingerprints
    assert "font.preview_naming_policy" in all_fingerprints


def test_extract_code_units_compound_block_splits_on_real_blank_line_boundaries():
    # Stage 8 test 2: the real Python API Highlights excerpt exceeds _CODE_UNIT_SPLIT_THRESHOLD
    # non-blank lines and has real blank-line boundaries -- must split into multiple c%04d{letter}
    # sub-units, not stay one monolithic unit.
    code_units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    unit_ids = [u["unit_id"] for u in code_units]
    assert len(unit_ids) > 1
    assert all(uid.startswith("c0001") for uid in unit_ids)
    assert unit_ids == sorted(unit_ids)
    assert unit_ids[0] == "c0001a"


def test_extract_code_units_single_block_no_letter_suffix():
    text = "## Installation\n\n```bash\npip install aspose-font\n```\n"
    units = checks.extract_old_readme_code_units(text)
    assert len(units) == 1
    assert units[0]["unit_id"] == "c0001"


def test_extract_code_units_is_deterministic():
    # Stage 8 test 9 / TC-HARDEN-80's own machinery-layer idempotency proof, at unit-test scope:
    # running the extractor twice against identical input must produce byte-identical (here,
    # value-identical) structured output.
    r1 = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    r2 = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    assert r1 == r2
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_extract_code_units_cli_highlights_four_real_categories():
    units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_CLI_HIGHLIGHTS_EXCERPT)
    categories = [checks._cli_unit_category(u["code_text"]) for u in units]
    categories = [c for c in categories if c]
    assert categories == [
        "General inspection and conversion",
        "Variable-font previews and review boards",
        "QA tooling",
        "Web packaging",
    ]


# --- check_code_example_disposition_coverage / no_exact_duplicate_merge (TC-HARDEN-74) ------


def _code_disposition(unit_id="c0001a", disposition="merged_reframed",
                       target_section="Additional Examples", api_call_fingerprint=("FontSubsetter.subset_for_web_with_coverage",),
                       excluded_reason=None, evidence_status="verified_against_source",
                       evidence_type="clone_cache_path", evidence_ref="src/aspose_font/subsetter.py"):
    return {
        "unit_id": unit_id, "heading_context": "Python API Highlights", "language": "python",
        "api_call_fingerprint": list(api_call_fingerprint), "disposition": disposition,
        "target_section": target_section, "excluded_reason": excluded_reason,
        "verification": {"status": evidence_status, "evidence_type": evidence_type, "evidence_ref": evidence_ref},
    }


def test_check_code_example_disposition_coverage_vacuous_on_empty():
    assert checks.check_code_example_disposition_coverage([], []) == []


def test_check_code_example_disposition_coverage_flags_missing_entry():
    units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    findings = checks.check_code_example_disposition_coverage(units, [])
    assert len(findings) == len(units)
    assert all("no disposition entry" in f["reason"] for f in findings)


def test_check_code_example_disposition_coverage_clean_on_well_formed_entries():
    units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    dispositions = [
        _code_disposition(unit_id=u["unit_id"], api_call_fingerprint=tuple(u["api_call_fingerprint"]) or ("placeholder",))
        for u in units
    ]
    assert checks.check_code_example_disposition_coverage(units, dispositions) == []


def test_check_code_example_disposition_coverage_rejects_invalid_target_section():
    units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_API_HIGHLIGHTS_EXCERPT)
    dispositions = [_code_disposition(unit_id=u["unit_id"], target_section="Not A Real Section") for u in units]
    findings = checks.check_code_example_disposition_coverage(units, dispositions)
    assert any("real target_section" in f["reason"] for f in findings)


def test_check_code_example_no_exact_duplicate_merge_flags_identical_fingerprint():
    dispositions = [
        _code_disposition(unit_id="c0001a"),
        _code_disposition(unit_id="c0002a"),  # same fingerprint, same target_section -- duplicate
    ]
    findings = checks.check_code_example_no_exact_duplicate_merge(dispositions)
    assert len(findings) == 1
    assert set(findings[0]["unit_ids"]) == {"c0001a", "c0002a"}


def test_check_code_example_no_exact_duplicate_merge_clean_on_distinct_fingerprints():
    dispositions = [
        _code_disposition(unit_id="c0001a", api_call_fingerprint=("FontSubsetter.subset_for_web_with_coverage",)),
        _code_disposition(unit_id="c0002a", api_call_fingerprint=("font.preview_naming_policy",)),
    ]
    assert checks.check_code_example_no_exact_duplicate_merge(dispositions) == []


def test_check_code_example_no_exact_duplicate_merge_exempts_identical_fingerprint_with_different_evidence():
    """Real font/python false positive (2026-08-20, TC-PC-FONT-PYTHON): two code units under
    "Export Live and Static Variable Web Bundles" both call `WebFontBuilder.build(...)` -- the
    mechanical dotted-call fingerprint scan produces the identical single-item fingerprint for
    both even though they demonstrate genuinely different, independently-verified behavior
    (`variable_mode="live"` vs. `variable_mode="static", stat_policy="static"`, the latter backed
    by a real, distinct source dependency the former never touches). Mirrors the exemption
    `check_content_unit_no_exact_duplicate_merge` already has for the same false-positive shape."""
    dispositions = [
        _code_disposition(unit_id="c0021c", api_call_fingerprint=("WebFontBuilder.build",),
                           evidence_ref="src/aspose_font/web.py"),
        _code_disposition(unit_id="c0021d", api_call_fingerprint=("WebFontBuilder.build",),
                           evidence_ref="src/aspose_font/ttf/tables/stat.py"),
    ]
    assert checks.check_code_example_no_exact_duplicate_merge(dispositions) == []


def test_check_code_example_no_exact_duplicate_merge_still_flags_identical_fingerprint_and_evidence():
    """The exemption is narrow: two entries citing the SAME evidence_ref for the same fingerprint
    are still real, lazy duplication, not independently-verified coincidence."""
    dispositions = [
        _code_disposition(unit_id="c0021c", api_call_fingerprint=("WebFontBuilder.build",),
                           evidence_ref="src/aspose_font/web.py"),
        _code_disposition(unit_id="c0021d", api_call_fingerprint=("WebFontBuilder.build",),
                           evidence_ref="src/aspose_font/web.py"),
    ]
    findings = checks.check_code_example_no_exact_duplicate_merge(dispositions)
    assert findings and set(findings[0]["unit_ids"]) == {"c0021c", "c0021d"}


# --- check_code_example_disposition_text_diff (RC-disposition-text-diff-verification, TC-21) ---


def test_code_example_text_diff_reproduces_the_real_tex_python_c0001_defect():
    """The exact real defect this check was built to catch: a disposition claims
    merged_verbatim for a code unit whose real old text is `pip install aspose-tex`, but
    the candidate replaced it with a from-source install -- the disposition is wrong,
    even though the editorial decision (replace the broken command) was correct."""
    old_readme = "## Installation\n\n```bash\npip install aspose-tex\n```\n"
    units = checks.extract_old_readme_code_units(old_readme)
    assert len(units) == 1
    dispositions = [_code_disposition(unit_id=units[0]["unit_id"], disposition="merged_verbatim")]
    candidate = "## Installation\n\n```bash\ngit clone https://github.com/example/repo\npip install -e .\n```\n"
    findings = checks.check_code_example_disposition_text_diff(units, dispositions, candidate)
    assert len(findings) == 1
    assert findings[0]["unit_id"] == units[0]["unit_id"]
    assert "not present anywhere in the candidate" in findings[0]["reason"]


def test_code_example_text_diff_clean_when_verbatim_claim_is_true():
    old_readme = "## Installation\n\n```bash\npip install aspose-font\n```\n"
    units = checks.extract_old_readme_code_units(old_readme)
    dispositions = [_code_disposition(unit_id=units[0]["unit_id"], disposition="merged_verbatim")]
    candidate = "## Installation\n\nSome intro text.\n\n```bash\npip install aspose-font\n```\n"
    assert checks.check_code_example_disposition_text_diff(units, dispositions, candidate) == []


def test_code_example_text_diff_tolerates_whitespace_only_reflow():
    old_readme = "## Installation\n\n```bash\npip install aspose-font\n```\n"
    units = checks.extract_old_readme_code_units(old_readme)
    dispositions = [_code_disposition(unit_id=units[0]["unit_id"], disposition="merged_verbatim")]
    # Different indentation/line-wrapping, same tokens -- must NOT be flagged as a content change.
    candidate = "## Installation\n\n```bash\n  pip   install   aspose-font  \n```\n"
    assert checks.check_code_example_disposition_text_diff(units, dispositions, candidate) == []


def test_code_example_text_diff_ignores_non_verbatim_dispositions():
    """merged_reframed/corrected/relocated already disclose the text changed -- this check
    must never fire against them, even when the old text is genuinely absent."""
    old_readme = "## Installation\n\n```bash\npip install aspose-tex\n```\n"
    units = checks.extract_old_readme_code_units(old_readme)
    candidate = "## Installation\n\n```bash\npip install -e .\n```\n"
    for disp in ("merged_reframed", "corrected", "relocated", "excluded"):
        dispositions = [_code_disposition(unit_id=units[0]["unit_id"], disposition=disp)]
        assert checks.check_code_example_disposition_text_diff(units, dispositions, candidate) == []


def test_code_example_text_diff_skips_dangling_unit_id():
    # A disposition referencing a unit_id absent from the current extraction is
    # check_code_example_disposition_coverage's own finding to raise -- this check must not
    # also fire (and must not crash) on it.
    dispositions = [_code_disposition(unit_id="c9999", disposition="merged_verbatim")]
    assert checks.check_code_example_disposition_text_diff([], dispositions, "anything") == []


def test_code_example_evidence_resolves_reuses_content_unit_evidence_resolves(tmp_path):
    # TC-HARDEN-74's own explicit reuse requirement: check_content_unit_evidence_resolves is
    # reused VERBATIM as the code-example evidence-resolution gate -- no new implementation.
    (tmp_path / "subsetter.py").write_text("class FontSubsetter:\n    pass\n", encoding="utf-8")
    good = [_code_disposition(evidence_ref="subsetter.py")]
    bad = [_code_disposition(evidence_ref="does_not_exist.py")]
    assert checks.check_content_unit_evidence_resolves(good, str(tmp_path)) == []
    findings = checks.check_content_unit_evidence_resolves(bad, str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["reason"].startswith("cited evidence does not resolve")


# --- check_code_example_api_coverage_survives (TC-HARDEN-75) --------------------------------


def test_check_code_example_api_coverage_survives_fails_closed_on_real_fontsubsetter_gap():
    # Stage 8 test 3: the real, confirmed defect this check exists to catch -- a disposition
    # claiming FontSubsetter.subset_for_web_with_coverage survives, against a candidate with zero
    # matching code anywhere (the real font/python shape before this incident's own fix).
    candidate_without_subsetting = (
        "## Quick Start\n\n```python\nfrom aspose_font import FontLoader\n"
        'font = FontLoader.open("Roboto.ttf")\nprint(font.font_name)\n```\n'
    )
    dispositions = [_code_disposition(
        unit_id="c0001a", disposition="merged_reframed",
        api_call_fingerprint=("FontSubsetter.subset_for_web_with_coverage", "subset_result.font.num_glyphs"),
    )]
    findings = checks.check_code_example_api_coverage_survives(candidate_without_subsetting, dispositions)
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "c0001a"


def test_check_code_example_api_coverage_survives_passes_on_real_matching_code():
    candidate_with_subsetting = (
        "## Additional Examples\n\n```python\nfrom aspose_font.subsetter import FontSubsetter\n"
        "subset_result = FontSubsetter.subset_for_web_with_coverage(font, presets=(\"latin\",))\n```\n"
    )
    dispositions = [_code_disposition(
        unit_id="c0001a", disposition="merged_reframed",
        api_call_fingerprint=("FontSubsetter.subset_for_web_with_coverage",),
    )]
    assert checks.check_code_example_api_coverage_survives(candidate_with_subsetting, dispositions) == []


def test_check_code_example_api_coverage_survives_skips_excluded_entries():
    candidate = "## Quick Start\n\n```python\nprint(1)\n```\n"
    dispositions = [_code_disposition(unit_id="c0001a", disposition="excluded", excluded_reason="not preserved, low value, no real user demand confirmed")]
    assert checks.check_code_example_api_coverage_survives(candidate, dispositions) == []


# --- check_cli_category_representation (TC-HARDEN-75) ---------------------------------------


def test_check_cli_category_representation_flags_real_missing_categories():
    # Stage 8 test 4: the real, captured 4-category CLI Highlights structure, against a candidate
    # that only demonstrates 2 of the 4 categories (the real, confirmed font/python shape before
    # this incident's own fix: only "Variable-font previews" and "Web packaging" survived).
    code_units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_CLI_HIGHLIGHTS_EXCERPT)
    candidate = (
        "## Additional Examples\n\n```bash\n"
        "aspose-font preview Roboto.ttf preview.svg --instance-name Bold --format svg\n"
        "aspose-font web-build Roboto.ttf web-out --instance-name Bold --template editorial --no-woff\n"
        "```\n"
    )
    findings = checks.check_cli_category_representation(candidate, code_units)
    flagged = {f["category"] for f in findings}
    assert flagged == {"General inspection and conversion", "QA tooling"}


def test_check_cli_category_representation_clean_when_all_categories_survive():
    code_units = checks.extract_old_readme_code_units(_REAL_FONT_PYTHON_CLI_HIGHLIGHTS_EXCERPT)
    assert checks.check_cli_category_representation(_REAL_FONT_PYTHON_CLI_HIGHLIGHTS_EXCERPT, code_units) == []


# --- _module_internal_fan_in / check_api_reference_class_internal_only (TC-HARDEN-76) --------


# Real, captured-verbatim excerpts standing in for font/python's own real source shape, in a
# hermetic tmp_path clone cache (real class definitions, real import-graph shape -- not
# fabricated): reporting.py's 3 real classes (TaskTokenEstimate/TaskCompletionReceipt/
# CompletedTaskRecord) are never imported anywhere else under src/aspose_font/ (confirmed live,
# this incident, via grep -rl); converter.py's real FontConverter has real internal fan-in
# (cli.py's real `from aspose_font.converter import FontConverter`).
_REAL_REPORTING_PY_EXCERPT = (
    '"""Task token estimate storage and Google Sheets reporting helpers."""\n\n'
    "from dataclasses import dataclass\n\n"
    "@dataclass(slots=True)\n"
    "class TaskTokenEstimate:\n"
    "    task_id: str\n\n"
    "@dataclass(slots=True)\n"
    "class TaskCompletionReceipt:\n"
    "    task_id: str\n\n"
    "@dataclass(slots=True)\n"
    "class CompletedTaskRecord:\n"
    "    task_id: str\n"
)
_REAL_CONVERTER_PY_EXCERPT = (
    "class FontConverter:\n"
    "    @staticmethod\n"
    "    def convert(font, target):\n"
    "        raise NotImplementedError\n"
)
_REAL_CLI_PY_IMPORT_EXCERPT = (
    "from aspose_font.converter import FontConverter\n\n"
    "def main():\n"
    "    FontConverter.convert(None, None)\n"
)


def _real_font_python_control_clone_cache(tmp_path):
    src = tmp_path / "src" / "aspose_font"
    src.mkdir(parents=True)
    (src / "reporting.py").write_text(_REAL_REPORTING_PY_EXCERPT, encoding="utf-8")
    (src / "converter.py").write_text(_REAL_CONVERTER_PY_EXCERPT, encoding="utf-8")
    (src / "cli.py").write_text(_REAL_CLI_PY_IMPORT_EXCERPT, encoding="utf-8")
    (src / "__init__.py").write_text("# no top-level re-export of either class\n", encoding="utf-8")
    return tmp_path


def test_module_internal_fan_in_zero_for_real_reporting_classes(tmp_path):
    root = _real_font_python_control_clone_cache(tmp_path)
    for cls in ("TaskTokenEstimate", "TaskCompletionReceipt", "CompletedTaskRecord"):
        assert checks._module_internal_fan_in(str(root), cls) == 0


def test_module_internal_fan_in_nonzero_for_real_converter_control(tmp_path):
    root = _real_font_python_control_clone_cache(tmp_path)
    assert checks._module_internal_fan_in(str(root), "FontConverter") == 1  # cli.py's real import


def test_module_internal_fan_in_none_when_class_not_found(tmp_path):
    root = _real_font_python_control_clone_cache(tmp_path)
    assert checks._module_internal_fan_in(str(root), "NoSuchClass") is None


def test_check_api_reference_class_internal_only_flags_real_leaked_classes_not_real_converter(tmp_path):
    # Stage 8 test 5: reporting.py's real shape (0 fan-in, no top-level export) must flag;
    # converter.py's real shape (real fan-in) must not -- via the actual function, not the ad hoc
    # investigation script used during Stage 1.
    root = _real_font_python_control_clone_cache(tmp_path)
    readme_text = (
        "## API Reference\n\n<details>\n<summary>View the Supported Public API Surface</summary>\n\n"
        "### Core API\n\n| Class | Description |\n|---|---|\n"
        "| `FontConverter` | Converts between font formats. |\n"
        "| `TaskTokenEstimate` | TaskTokenEstimate.task_id is the unique identifier of the task. |\n"
        "| `TaskCompletionReceipt` | TaskCompletionReceipt.task_id identifies the task uniquely. |\n"
        "| `CompletedTaskRecord` | CompletedTaskRecord.task_id uniquely identifies the completed task. |\n"
        "\n</details>\n"
    )
    reference_index = {
        "Core API": [
            {"class": "FontConverter", "description": "x"},
            {"class": "TaskTokenEstimate", "description": "x"},
            {"class": "TaskCompletionReceipt", "description": "x"},
            {"class": "CompletedTaskRecord", "description": "x"},
        ]
    }
    findings = checks.check_api_reference_class_internal_only(readme_text, reference_index, str(root))
    flagged = {f["class_name"] for f in findings}
    assert flagged == {"TaskTokenEstimate", "TaskCompletionReceipt", "CompletedTaskRecord"}
    assert "FontConverter" not in flagged


def test_check_api_reference_class_internal_only_vacuous_without_clone_cache():
    findings = checks.check_api_reference_class_internal_only("## API Reference\n\n", {}, None)
    assert findings == []


# --- exported-base-exception false-positive fix (MT048, note/python pilot, 2026-08-15) ------

_REAL_NOTE_PYTHON_EXCEPTIONS_PY_EXCERPT = (
    "class AsposeNoteError(Exception):\n"
    "    \"\"\"Base exception for the library.\"\"\"\n\n"
    "class FileCorruptedException(AsposeNoteError):\n"
    "    pass\n\n"
    "class IncorrectPasswordException(AsposeNoteError):\n"
    "    pass\n"
)


def _real_note_python_control_clone_cache(tmp_path):
    # The real, confirmed-live shape: AsposeNoteError has zero cross-file fan-in (nothing
    # references it by name outside exceptions.py) and is absent from __init__.py's __all__/
    # imports -- but its 2 real subclasses ARE both exported at the top level, exactly like
    # note/python's real 5-subclass shape.
    src = tmp_path / "src" / "aspose" / "note"
    src.mkdir(parents=True)
    (src / "exceptions.py").write_text(_REAL_NOTE_PYTHON_EXCEPTIONS_PY_EXCERPT, encoding="utf-8")
    (src / "__init__.py").write_text(
        "from .exceptions import FileCorruptedException, IncorrectPasswordException\n\n"
        "__all__ = [\"FileCorruptedException\", \"IncorrectPasswordException\"]\n",
        encoding="utf-8",
    )
    return tmp_path


def test_find_top_level_init_exports_finds_real_two_level_namespace_package_init(tmp_path):
    # MT048's own real, confirmed bug: a one-level-only glob matches note/python's thin
    # `src/aspose/__init__.py` namespace stub (`__all__ = ["note"]`) and never reaches the real
    # export list one level deeper, at `src/aspose/note/__init__.py`.
    root = _real_note_python_control_clone_cache(tmp_path)
    exports = checks._find_top_level_init_exports(str(root))
    assert exports is not None
    assert {"FileCorruptedException", "IncorrectPasswordException"} <= exports


def test_find_top_level_init_exports_still_finds_real_one_level_flat_package_init(tmp_path):
    # Regression guard: font/python's real flat `src/aspose_font/__init__.py` layout (one level,
    # no namespace stub) must keep resolving exactly as before the two-level glob was added -- its
    # own __init__.py fixture is a comment-only file with no real exports, so the file must still
    # be FOUND (not None) even though it legitimately yields an empty set.
    root = _real_font_python_control_clone_cache(tmp_path)
    exports = checks._find_top_level_init_exports(str(root))
    assert exports is not None
    assert exports == set()


def test_class_has_exported_subclass_in_same_file_true_for_real_asposenoteerror(tmp_path):
    root = _real_note_python_control_clone_cache(tmp_path)
    root_exports = checks._find_top_level_init_exports(str(root))
    assert checks._class_has_exported_subclass_in_same_file(str(root), "AsposeNoteError", root_exports)


def test_class_has_exported_subclass_in_same_file_false_for_real_reporting_leak(tmp_path):
    # The real font/python positive control must NOT be cleared by this new exemption -- none of
    # reporting.py's 3 leaked classes has any subclass at all, exported or otherwise.
    root = _real_font_python_control_clone_cache(tmp_path)
    root_exports = checks._find_top_level_init_exports(str(root))
    assert not checks._class_has_exported_subclass_in_same_file(str(root), "TaskTokenEstimate", root_exports)


def test_check_api_reference_class_internal_only_does_not_flag_real_public_base_exception(tmp_path):
    # MT048's own real, confirmed false-positive: AsposeNoteError is a genuinely public base
    # exception (zero fan-in, absent from __all__, but base of 2 real exported subclasses in the
    # same file) -- must NOT be flagged as a possible internal-only leak.
    root = _real_note_python_control_clone_cache(tmp_path)
    readme_text = (
        "## API Reference\n\n<details>\n<summary>View the Supported Public API Surface</summary>\n\n"
        "### Core API\n\n| Class | Description |\n|---|---|\n"
        "| `AsposeNoteError` | Base exception for the library; all other library exceptions "
        "inherit from it. |\n"
        "| `FileCorruptedException` | Raised when the source file's container is malformed. |\n"
        "\n</details>\n"
    )
    reference_index = {
        "Core API": [
            {"class": "AsposeNoteError", "description": "x"},
            {"class": "FileCorruptedException", "description": "x"},
        ]
    }
    findings = checks.check_api_reference_class_internal_only(readme_text, reference_index, str(root))
    assert findings == []


def test_check_api_reference_class_internal_only_exclusions_param_actually_suppresses(tmp_path):
    # MT048: the finding's own `reason` text has always told the reader that recording a class in
    # data/api_reference_class_exclusions.json "suppresses this prompt permanently" -- but the
    # function never accepted or consulted that data at all until this fix. Proves the promise is
    # now real: the same real reporting.py positive control, once passed via `exclusions`, is no
    # longer flagged.
    root = _real_font_python_control_clone_cache(tmp_path)
    readme_text = (
        "## API Reference\n\n<details>\n<summary>View the Supported Public API Surface</summary>\n\n"
        "### Core API\n\n| Class | Description |\n|---|---|\n"
        "| `TaskTokenEstimate` | TaskTokenEstimate.task_id is the unique identifier of the task. |\n"
        "\n</details>\n"
    )
    reference_index = {"Core API": [{"class": "TaskTokenEstimate", "description": "x"}]}
    without = checks.check_api_reference_class_internal_only(readme_text, reference_index, str(root))
    assert {f["class_name"] for f in without} == {"TaskTokenEstimate"}
    with_exclusion = checks.check_api_reference_class_internal_only(
        readme_text, reference_index, str(root), exclusions={"TaskTokenEstimate"},
    )
    assert with_exclusion == []


def test_check_api_reference_class_internal_only_scoped_to_python_only(tmp_path):
    # 2026-08-17 (slides/* portfolio audit): run for real against 3 non-Python products for the
    # first time, this heuristic flagged 161/238/260+ classes respectively (C++/Java/.NET) --
    # effectively every class in each table, since __init__.py-export detection has no meaning
    # outside Python. Reuses the exact real font/python positive control (which WOULD trip the
    # fan-in-only signal) to prove: platform=None (legacy callers) still runs the real check;
    # platform="python" still runs it; any other platform is a real no-op regardless of content.
    root = _real_font_python_control_clone_cache(tmp_path)
    readme_text = (
        "## API Reference\n\n<details>\n<summary>View the Supported Public API Surface</summary>\n\n"
        "### Core API\n\n| Class | Description |\n|---|---|\n"
        "| `TaskTokenEstimate` | TaskTokenEstimate.task_id is the unique identifier of the task. |\n"
        "\n</details>\n"
    )
    reference_index = {"Core API": [{"class": "TaskTokenEstimate", "description": "x"}]}
    unscoped = checks.check_api_reference_class_internal_only(readme_text, reference_index, str(root))
    assert {f["class_name"] for f in unscoped} == {"TaskTokenEstimate"}
    python_scoped = checks.check_api_reference_class_internal_only(
        readme_text, reference_index, str(root), platform="python",
    )
    assert {f["class_name"] for f in python_scoped} == {"TaskTokenEstimate"}
    for other_platform in ("cpp", "java", "net", "go", "rust", "typescript"):
        assert checks.check_api_reference_class_internal_only(
            readme_text, reference_index, str(root), platform=other_platform,
        ) == []


def test_check_api_reference_class_internal_only_real_reporting_leak_still_flags_with_new_exemption(tmp_path):
    # Regression guard: the new same-file-exported-subclass exemption must not accidentally
    # clear the real font/python positive control (no subclasses of any kind).
    root = _real_font_python_control_clone_cache(tmp_path)
    readme_text = (
        "## API Reference\n\n<details>\n<summary>View the Supported Public API Surface</summary>\n\n"
        "### Core API\n\n| Class | Description |\n|---|---|\n"
        "| `TaskTokenEstimate` | TaskTokenEstimate.task_id is the unique identifier of the task. |\n"
        "\n</details>\n"
    )
    reference_index = {"Core API": [{"class": "TaskTokenEstimate", "description": "x"}]}
    findings = checks.check_api_reference_class_internal_only(readme_text, reference_index, str(root))
    assert {f["class_name"] for f in findings} == {"TaskTokenEstimate"}


# --- data/api_reference_class_exclusions.json suppression (TC-HARDEN-77) --------------------


def test_check_api_reference_table_completeness_exclusion_suppresses_missing_class():
    # Stage 8 test 6: a class present in the exclusions set must never be required in the table,
    # even though it's still present in a real reference-site index fixture.
    readme_text = (
        "## API Reference\n\n<details>\n<summary>View the Supported Public API Surface</summary>\n\n"
        "### Core API\n\n| Class | Description |\n|---|---|\n"
        "| `FontConverter` | Converts between font formats. |\n"
        "\n</details>\n"
    )
    reference_index = {
        "Core API": [
            {"class": "FontConverter", "description": "x"},
            {"class": "TaskTokenEstimate", "description": "x"},
        ]
    }
    # Without exclusions: TaskTokenEstimate is missing from the table -- a real finding.
    findings_without = checks.check_api_reference_table_completeness(readme_text, reference_index)
    assert any(f.get("class_name") == "TaskTokenEstimate" and f["reason"] == "missing_class" for f in findings_without)
    # With the override: TaskTokenEstimate is never required -- no finding for it.
    findings_with = checks.check_api_reference_table_completeness(
        readme_text, reference_index, exclusions={"TaskTokenEstimate"},
    )
    assert not any(f.get("class_name") == "TaskTokenEstimate" for f in findings_with)


def test_check_api_reference_table_completeness_exclusion_still_flags_if_reintroduced():
    # An excluded class present in the table anyway now surfaces as unrecognized_class -- a real,
    # mechanical deterrent against reintroducing a confirmed-internal class.
    readme_text = (
        "## API Reference\n\n<details>\n<summary>View the Supported Public API Surface</summary>\n\n"
        "### Core API\n\n| Class | Description |\n|---|---|\n"
        "| `TaskTokenEstimate` | TaskTokenEstimate.task_id is the unique identifier of the task. |\n"
        "\n</details>\n"
    )
    reference_index = {"Core API": [{"class": "TaskTokenEstimate", "description": "x"}]}
    findings = checks.check_api_reference_table_completeness(
        readme_text, reference_index, exclusions={"TaskTokenEstimate"},
    )
    assert any(f.get("class_name") == "TaskTokenEstimate" and f["reason"] == "unrecognized_class" for f in findings)


# --- check_content_unit_merged_into_target_section free-text extension (TC-HARDEN-78) -------


def test_check_content_unit_merged_into_target_section_catches_real_stale_u0028_shape():
    # Stage 8 test 7: the real, captured u0028 shape from font/python's own current
    # content-dispositions.json -- an excluded disposition whose excluded_reason names "the
    # candidate's own Key Capabilities intro paragraph independently states..." a claim that, in
    # the real candidate (post-MT046), no longer exists at all (the Key Capabilities section now
    # opens directly with bullets, no intro paragraph). Must fail.
    candidate_without_intro_paragraph = (
        "## Key Capabilities\n\n- Load, auto-detect, and inspect TrueType (TTF) fonts.\n"
    )
    entry = {
        "unit_id": "u0028",
        "salient_tokens": [],
        "disposition": "excluded",
        "target_section": None,
        "excluded_reason": (
            "Roadmap/focus positioning. The candidate's own Key Capabilities intro paragraph "
            "independently states the same 'variable-font-first' framing in different wording."
        ),
    }
    findings = checks.check_content_unit_merged_into_target_section(candidate_without_intro_paragraph, [entry])
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0028"


def test_check_content_unit_merged_into_target_section_clean_before_real_deletion():
    # Same u0028 shape, but against candidate text that still genuinely carries the claim (the
    # real pre-MT046 state) -- must pass.
    candidate_with_intro_paragraph = (
        "## Key Capabilities\n\n"
        "These capabilities are variable-font-first: instancing, previews, and web packaging all "
        "build on the same variable-font-first foundation.\n\n"
        "- Load, auto-detect, and inspect TrueType (TTF) fonts.\n"
    )
    entry = {
        "unit_id": "u0028",
        "salient_tokens": [],
        "disposition": "excluded",
        "target_section": None,
        "excluded_reason": (
            "Roadmap/focus positioning. The candidate's own Key Capabilities intro paragraph "
            "independently states the same 'variable-font-first' framing in different wording."
        ),
    }
    assert checks.check_content_unit_merged_into_target_section(candidate_with_intro_paragraph, [entry]) == []


def test_check_content_unit_merged_into_target_section_real_u0001_and_u0049_stay_clean():
    # The other 2 real font/python entries the audit confirmed still accurate (u0001/u0049) must
    # NOT be flagged by this extension -- proving it doesn't over-fire on genuinely-still-valid
    # free-text claims.
    candidate = (
        "Aspose.Font FOSS for Python is a free, open-source, pure-Python library with zero "
        "required third-party runtime dependencies.\n\n"
        "## Development and Testing\n\n"
        "The test suite also regenerates the demo-site preview assets referenced under "
        "Additional Examples.\n"
    )
    entries = [
        {
            "unit_id": "u0001", "salient_tokens": [], "disposition": "excluded", "target_section": None,
            "excluded_reason": (
                "Positions the library as pure-Python workflow automation with no native runtime "
                "dependency. The candidate's own Intro independently states the same underlying "
                "fact ('zero required third-party runtime dependencies') in different wording."
            ),
        },
        {
            "unit_id": "u0049", "salient_tokens": [], "disposition": "excluded", "target_section": None,
            "excluded_reason": (
                "Real build/test-tooling detail. The candidate's own Development and Testing "
                "section independently states the same fact ('the test suite also regenerates "
                "the demo-site preview assets') in different wording."
            ),
        },
    ]
    assert checks.check_content_unit_merged_into_target_section(candidate, entries) == []


def test_normalize_independent_statement_target_real_captured_shapes():
    assert checks._normalize_independent_statement_target("Intro") == "Intro"
    assert checks._normalize_independent_statement_target("Key Capabilities bullets") == "Key Capabilities"
    assert checks._normalize_independent_statement_target("Key Capabilities intro paragraph") == "Key Capabilities"
    assert checks._normalize_independent_statement_target("Development and Testing section") == "Development and Testing"


def test_check_content_unit_merged_into_target_section_ignores_unrelated_excluded_reason():
    # Regression guard: an ordinary excluded entry with no "independently states" phrase at all
    # must be completely unaffected by this extension (the pre-existing "continue" path).
    entry = {
        "unit_id": "u0099", "salient_tokens": [], "disposition": "excluded", "target_section": None,
        "excluded_reason": "Pure narrative/CTA prose with no checkable claim -- out of scope per policy.",
    }
    assert checks.check_content_unit_merged_into_target_section("## Intro\n\nSome text.\n", [entry]) == []


# --- _extract_salient_tokens markdown-link coverage (2026-08-16) -------------------------------
# Real, captured html/python u0032 excerpt (content-dispositions.json, reports/repo-presenter-
# regen-full/html/python/) -- before this fix, neither `[PUBLIC_API.md](PUBLIC_API.md)` nor
# `[examples](examples)` produced any real token (only a stray ALLCAPS "API" fragment), so
# `check_content_unit_merged_into_target_section`'s otherwise-correct per-sentence-group logic
# (MT049) had nothing to check the second sentence against -- a disposition claiming BOTH facts
# landed in "Documentation & Resources" passed even though "examples" actually landed in a
# different section (Additional Examples) in the real candidate.
_U0032_EXCERPT = (
    "For the stable API summary, see [PUBLIC_API.md](PUBLIC_API.md). For runnable scenarios, "
    "see [examples](examples)."
)


def test_extract_salient_tokens_captures_markdown_link_text_and_target():
    tokens = checks._extract_salient_tokens(_U0032_EXCERPT)
    assert "PUBLIC_API.md" in tokens
    assert "examples" in tokens


def test_extract_salient_tokens_excludes_image_link_target():
    # Real, captured page/python u0015 excerpt -- an image reference, not a prose link. Its
    # filename/path must never be extracted as a "checkable identifier" the way a real link
    # target is: an asset path never gets restated verbatim as prose elsewhere (an earlier,
    # independent fix pass had already hand-removed this exact filename from u0015's own
    # salient_tokens for this reason -- the new link-target pattern must not reintroduce it).
    tokens = checks._extract_salient_tokens(
        "![ps2pdf result](readme.resources/TestImages.png)"
    )
    assert "readme.resources/TestImages.png" not in tokens
    assert "ps2pdf result" not in tokens


def test_merged_into_target_section_catches_real_u0032_shape_once_tokens_fixed():
    # With the fixed tokens, a target_section that only genuinely carries the FIRST sentence's
    # fact must now be flagged for the second (real, pre-fix-disposition html/python shape).
    entry = {
        "unit_id": "u0032",
        "excerpt": _U0032_EXCERPT,
        "salient_tokens": checks._extract_salient_tokens(_U0032_EXCERPT),
        "disposition": "merged_verbatim",
        "target_section": "Documentation & Resources",
    }
    candidate = (
        "## Documentation & Resources\n\n"
        "- **[Public API surface](PUBLIC_API.md)** -- the stable top-level entry points this "
        "library's compatibility guarantees cover.\n\n"
        "## Additional Examples\n\n"
        "Runnable scripts are available in the [`examples`](examples/) directory.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(candidate, [entry])
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0032"


def test_merged_into_target_section_u0032_clean_once_both_facts_present_in_target():
    # Regression guard, opposite direction: once the target section genuinely carries both
    # facts (the corrected state), the same entry must pass clean.
    entry = {
        "unit_id": "u0032",
        "excerpt": _U0032_EXCERPT,
        "salient_tokens": checks._extract_salient_tokens(_U0032_EXCERPT),
        "disposition": "merged_verbatim",
        "target_section": "Documentation & Resources",
    }
    candidate = (
        "## Documentation & Resources\n\n"
        "- **[Public API surface](PUBLIC_API.md)** -- the stable top-level entry points this "
        "library's compatibility guarantees cover.\n"
        "- **[Runnable examples](examples/)** -- scenario-focused scripts.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(candidate, [entry]) == []


# --- check_content_unit_merged_into_target_section compound-excerpt extension (MT049, ----------
# Thirty-Ninth incident) ---------------------------------------------------------------------

# Real, captured note/python u0020 shape (content-dispositions.json, reports/repo-presenter-
# regen-full/note/python/) -- 3 genuinely distinct sentences bundled into one merged_reframed
# excerpt under 6 shared salient_tokens.
_U0020_TOKENS = [
    "tests/goldens/pdf/",
    "ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1",
    "PDFs",
    "JSON",
    "PDF",
    "ReportLab",
]
_U0020_EXCERPT = (
    "Golden PDFs are stored under `tests/goldens/pdf/` together with JSON manifests extracted "
    "from the generated PDF.\n"
    "The test suite compares manifests, not raw PDF bytes, so it stays stable across platforms "
    "and ReportLab internals.\n"
    "The PDF writer now uses deterministic Base-14 fonts by default. If you explicitly want to "
    "try Windows system fonts for local inspection, set `ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1` "
    "before export."
)


def test_merge_into_target_section_catches_real_u0020_compound_excerpt_partial_drop():
    # Real, captured MT049/Thirty-Ninth-incident defect: note/python's own u0020 bundles 3
    # genuinely distinct facts (golden-PDF storage/manifest comparison; cross-platform stability
    # via ReportLab; deterministic Base-14 default font + the ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1
    # override) under one merged_reframed disposition. The real pre-fix candidate only ever
    # carried the FIRST fact forward -- the third fact's own distinctive token (the env-var name)
    # never appeared anywhere in the section -- yet the OLD whole-excerpt "any one token,
    # anywhere" check still passed, because `tests/goldens/pdf/` (the first fact's own token)
    # legitimately matched. The corrected, per-sentence-group check must fail this shape.
    entry = {
        "unit_id": "u0020", "excerpt": _U0020_EXCERPT, "salient_tokens": list(_U0020_TOKENS),
        "disposition": "merged_reframed", "target_section": "Development and Testing",
    }
    text = (
        "## Development and Testing\n\n"
        "### PDF Golden Tests and Example Scripts\n\n"
        "The PDF golden-output tests compare generated PDFs against JSON manifests in "
        "`tests/goldens/pdf/`, not raw bytes, so they stay stable across platforms.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(text, [entry])
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0020"


def test_merge_into_target_section_passes_real_u0020_after_all_facts_restored():
    # Same real u0020 unit, against the actual post-fix merged text now live in note/python's own
    # candidate (reports/repo-presenter-regen-full/note/python/readme.md, lines ~484-490) -- all
    # 3 bundled facts are genuinely present, so the corrected check must pass cleanly.
    entry = {
        "unit_id": "u0020", "excerpt": _U0020_EXCERPT, "salient_tokens": list(_U0020_TOKENS),
        "disposition": "merged_reframed", "target_section": "Development and Testing",
    }
    text = (
        "## Development and Testing\n\n"
        "### PDF Golden Tests and Example Scripts\n\n"
        "The PDF golden-output tests (`tests.test_aspose_note_pdf_goldens`) compare generated "
        "PDFs against manifests in `tests/goldens/pdf/`, not raw bytes, so they stay stable "
        "across platforms and ReportLab internals. The PDF writer uses deterministic Base-14 "
        "fonts by default; set `ASPOSE_NOTE_PDF_USE_SYSTEM_FONTS=1` before export to use Windows "
        "system fonts for local inspection instead.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_merge_into_target_section_real_u0003_single_sentence_still_passes_unchanged():
    # Regression guard against reintroducing the historical over-strictness mistake this
    # function's own docstring already documents (the retired leading-20-char-literal-substring
    # fallback that false-positived on dozens of real, correctly-reframed single-fact
    # dispositions): a REAL, currently-passing, single-sentence entry from note/python's own live
    # content-dispositions.json (u0003, target_section "Intro") must still pass unchanged under
    # the new per-sentence-group logic -- a single-sentence excerpt has exactly one group, so this
    # is provably identical to the old "any one token, anywhere" behavior.
    entry = {
        "unit_id": "u0003",
        "excerpt": (
            "This repository provides a Python library with a **subset-compatible Aspose.Note "
            "for .NET-shaped public API** for reading Microsoft OneNote files (`.one`)."
        ),
        "salient_tokens": [".one", "NET", "API", "OneNote"],
        "disposition": "merged_reframed", "target_section": "Intro",
    }
    text = (
        "Aspose.Note FOSS for Python reads Microsoft OneNote `.one` files through a "
        "subset-compatible, Aspose.Note for .NET-shaped API.\n\n## Installation\n\n- pip install x\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_merge_into_target_section_compound_excerpt_also_applies_to_redundant_evidence_ref_path():
    # Same compound-drop defect class, via the sibling excluded/candidate_section_reference path
    # that shares this exact code block (see docstring's own "ALSO verifies..." paragraph) --
    # must be caught there too, not just for merged_* dispositions.
    entry = {
        "unit_id": "u0020", "excerpt": _U0020_EXCERPT, "salient_tokens": list(_U0020_TOKENS),
        "disposition": "excluded", "target_section": None,
        "verification": {
            "evidence_type": "candidate_section_reference",
            "evidence_ref": "Development and Testing",
        },
    }
    text = (
        "## Development and Testing\n\n"
        "The PDF golden-output tests compare generated PDFs against JSON manifests in "
        "`tests/goldens/pdf/`, not raw bytes, so they stay stable across platforms.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(text, [entry])
    assert len(findings) == 1 and findings[0]["unit_id"] == "u0020"


# 2026-08-17 -- real, captured verbatim from words/python's own live content-dispositions.json
# (reports/repo-presenter-regen-full/words/python/content-dispositions.json, unit u0020): the
# exact `### Files` table MT049's own docstring cited as the unresolved "known tension" (a
# genuine markdown table, deliberately NOT split into per-row facts by MT049's own terminal-
# punctuation rule, since table rows end in `|`, not `.`/`!`/`?`).
_WORDS_PYTHON_FILES_TABLE_EXCERPT = (
    "| File | What it shows |\n"
    "|------|---------------|\n"
    "| `convert_document.py` | Every input format (DOCX, DOC, RTF, TXT, MD) to every output "
    "format (Markdown, PDF, TXT) |\n"
    "| `loading_document.py` | Loading documents from a file path and from a binary stream, "
    "with `LoadOptions` |\n"
    "| `loading_markdown.py` | Reading Markdown from in-memory content |\n"
    "| `working_with_markdown_save_options.py` | `MarkdownSaveOptions` — "
    "`export_underline_formatting`, `encoding`, `paragraph_break` |\n"
    "| `working_with_ooxml_save_options.py` | `OoxmlSaveOptions` for DOCX export — "
    "`pretty_format`, `compression_level`, `zip_64_mode` |\n"
    "| `working_with_pdf_save_options.py` | PDF export from all input formats |\n"
    "| `working_with_txt_save_options.py` | Plain-text export and `get_text()` |\n"
    "| `working_with_images.py` | Image-containing documents to all output formats |"
)
_WORDS_PYTHON_FILES_TABLE_TOKENS = [
    "convert_document.py", "loading_document.py", "loading_markdown.py",
    "working_with_markdown_save_options.py", "working_with_ooxml_save_options.py",
    "working_with_pdf_save_options.py", "working_with_txt_save_options.py", "working_with_images.py",
]


def test_split_excerpt_into_sentence_groups_splits_real_words_python_files_table_into_rows():
    # Direct proof of the table-aware split itself: the real 8-row Files table produces exactly
    # 8 groups (header + separator rows carry no distinct fact and are dropped), each containing
    # its own row's real filename -- the precise fix MT049's own docstring deferred.
    groups = checks._split_excerpt_into_sentence_groups(_WORDS_PYTHON_FILES_TABLE_EXCERPT)
    assert len(groups) == 8
    for token, group in zip(_WORDS_PYTHON_FILES_TABLE_TOKENS, groups):
        assert token in group
    assert "File" not in groups[0] or "What it shows" not in groups[0]  # header row excluded


def test_merge_into_target_section_catches_real_words_python_table_row_entirely_dropped():
    # The real, meaningful defect this fix closes: BEFORE this fix, the whole 8-filename excerpt
    # was one ungrouped blob (table rows end in `|`, not `.`/`!`/`?`, so MT049's own terminal-
    # punctuation rule never split it) -- so a target section naming even ONE of the 8 filenames
    # satisfied "any token, anywhere," passing cleanly even if the other 7 rows were entirely
    # absent. Here only 1 of 8 real filenames survives into the target section; the corrected,
    # per-row-group check must now catch the other 7 as missing.
    entry = {
        "unit_id": "u0020", "excerpt": _WORDS_PYTHON_FILES_TABLE_EXCERPT,
        "salient_tokens": list(_WORDS_PYTHON_FILES_TABLE_TOKENS),
        "disposition": "merged_reframed", "target_section": "Additional Examples",
    }
    text = (
        "## Additional Examples\n\n"
        "Runnable scripts are collected under `ApiExamples/`, including `convert_document.py`.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(text, [entry])
    assert len(findings) == 1
    assert findings[0]["unit_id"] == "u0020"
    # names the 7 genuinely-missing rows, not a bare "not traceable to real text" message
    assert "working_with_images.py" in findings[0]["reason"]
    assert "loading_markdown.py" in findings[0]["reason"]


def test_merge_into_target_section_passes_real_words_python_table_when_every_row_filename_present():
    # The disclosed, unchanged remaining limitation: this check verifies presence, not
    # description-level faithfulness (Evidence Contract rule 4) -- when every row's own filename
    # genuinely survives (matching the real, current regen-full candidate's own bare-list shape),
    # the check correctly passes even though the per-row DESCRIPTIONS aren't independently
    # checked here. That gap is closed by restoring real prose in the candidate itself, not by
    # this mechanical check.
    entry = {
        "unit_id": "u0020", "excerpt": _WORDS_PYTHON_FILES_TABLE_EXCERPT,
        "salient_tokens": list(_WORDS_PYTHON_FILES_TABLE_TOKENS),
        "disposition": "merged_reframed", "target_section": "Additional Examples",
    }
    text = (
        "## Additional Examples\n\n"
        "Runnable scripts under `ApiExamples/` -- `convert_document.py`, `loading_document.py`, "
        "`loading_markdown.py`, `working_with_markdown_save_options.py`, "
        "`working_with_ooxml_save_options.py`, `working_with_pdf_save_options.py`, "
        "`working_with_txt_save_options.py`, and `working_with_images.py`.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_split_excerpt_into_sentence_groups_unaffected_by_non_table_line_wrap():
    # Negative control, representative of barcode/python's own documented real shape (a single
    # sentence wrapping mid-clause across a `\n`, no separator row anywhere) -- must stay exactly
    # one group; the table-aware split must never trigger on a bare, non-table `\n`.
    excerpt = "The verification script must be run from\nthe repository root, not a subdirectory."
    assert checks._split_excerpt_into_sentence_groups(excerpt) == [excerpt]


def test_split_excerpt_into_sentence_groups_unaffected_by_heading_to_bullet_wrap():
    # Negative control, representative of 3d/java's own documented real shape (a bold heading
    # fragment separated from markdown bullet items by `\n-`, no separator row) -- a table-aware
    # split must not mistake ordinary bullet-list `\n` structure for a table.
    excerpt = "**Excluded APIs:**\n- `LegacyImporter`\n- `LegacyExporter`"
    groups = checks._split_excerpt_into_sentence_groups(excerpt)
    assert groups == [excerpt]


def test_split_excerpt_into_table_aware_groups_returns_none_for_non_table_excerpt():
    # Direct proof the helper itself is a real, conditional no-op -- confirms the caller's
    # fall-through to the unchanged sentence-based split is reached, not silently bypassed.
    assert checks._split_excerpt_into_table_aware_groups("Just an ordinary single sentence.") is None


# ---------------------------------------------------------------------------------------------
# MT052 (Forty-Third incident, 2026-08-18): pdf/go's content-dispositions.json claimed real
# capability coverage never actually written into the candidate -- two distinct blind spots in
# check_content_unit_merged_into_target_section (semicolon-joined compound excerpts never
# splitting; a compound group's match accepting a weak bare token) let 6 real capabilities
# silently pass a hard gate that should have caught them. Fixtures below are captured verbatim
# from pdf/go's own real content-dispositions.json (u0093, u0042, u0048, u0041).
# ---------------------------------------------------------------------------------------------

_PDF_GO_U0048_EXCERPT = (
    "- **Document JavaScript & open action** — `Document.JavaScript()` is the "
    "document-level named-script collection (`/Catalog/Names/JavaScript`); "
    "`Document.SetOpenAction` sets the action run when the document opens (GoTo, "
    "JavaScript, …)"
)
_PDF_GO_U0048_TOKENS = [
    "Document.JavaScript()", "/Catalog/Names/JavaScript", "Document.SetOpenAction",
    "JavaScript", "SetOpenAction", "GoTo",
]

_PDF_GO_U0093_EXCERPT = (
    "`Document.JavaScript()` is a named-script collection (`Add`/`Get`/`Has`/`Remove`/`Names`/"
    "`Count`/`Clear`)\nbacked by the `/Catalog/Names/JavaScript` name tree — distinct from "
    "the action-level\n`JavaScriptAction` that fires on an annotation click. "
    "`Document.SetOpenAction` /\n`OpenAction` / `RemoveOpenAction` manage the "
    "`/Catalog/OpenAction` run on open (GoTo,\nJavaScript, Named, …); a GoTo open-action "
    "resolves its destination to a 1-based page\nnumber on read. Both round-trip through Save "
    "and coexist with named destinations.\nDocument-level JavaScript executes in the "
    "recipient's viewer when the file is opened —\nembed only scripts you authored or "
    "audited."
)
_PDF_GO_U0093_TOKENS = [
    "Document.JavaScript()", "Add", "Get", "Has", "Remove", "Names", "Count", "Clear",
    "/Catalog/Names/JavaScript", "JavaScriptAction", "Document.SetOpenAction", "OpenAction",
    "RemoveOpenAction", "/Catalog/OpenAction", "JavaScript", "SetOpenAction", "GoTo",
]

_PDF_GO_U0042_EXCERPT = (
    "- **Add text** — draw text on pages with font selection, alignment, word wrap, "
    "color, background, underline, strikethrough, rotation, and behind-content mode. "
    "**Right-to-left / bidirectional** text (Hebrew and Arabic) is laid out via a pure-Go "
    "Unicode Bidi Algorithm (UAX #9): set `TextStyle.RTL` or just include RTL characters, and "
    "each line is reordered into visual order with embedded numbers/Latin kept left-to-right; "
    "RTL paragraphs right-align by default. **Arabic contextual shaping** (connected "
    "letterforms + lam-alef ligatures via Presentation Forms-B) renders proper Arabic with any "
    "font that covers the block (e.g. the bundled DejaVu Sans)"
)
_PDF_GO_U0042_TOKENS = ["TextStyle.RTL", "UAX", "TextStyle", "RTL", "DejaVu"]

_PDF_GO_U0041_EXCERPT = (
    "- **Add blank pages** — append or insert blank pages into existing documents at any "
    "position"
)


def test_split_excerpt_into_sentence_groups_splits_real_pdf_go_u0048_on_semicolon():
    # Fix item 1 (TC-HARDEN-105): a `;` immediately followed by a backtick-quoted identifier is
    # now a real split point -- MT049's own terminal-punctuation-only rule never split this real,
    # captured semicolon-joined bullet, letting the SetOpenAction half silently vanish.
    groups = checks._split_excerpt_into_sentence_groups(_PDF_GO_U0048_EXCERPT)
    assert len(groups) == 2
    assert "Document.JavaScript()" in groups[0]
    assert "Document.SetOpenAction" in groups[1]


def test_split_excerpt_into_sentence_groups_semicolon_split_requires_backtick_identifier():
    # Negative control: a bare `;` with no backtick-quoted identifier immediately after must NOT
    # split -- the rule is deliberately narrow, not a blanket semicolon-as-boundary rule.
    excerpt = "This does one thing; and also another thing in plain prose."
    assert checks._split_excerpt_into_sentence_groups(excerpt) == [excerpt]


def test_merge_into_target_section_catches_real_pdf_go_u0093_setopenaction_gap():
    # Fix item 2 (TC-HARDEN-106): u0093's real Group 2 previously passed via the bare, reused
    # word "JavaScript" (present elsewhere for unrelated reasons -- JavaScriptCollection, a
    # DateField JS-format action) while its own distinctive dotted identifiers
    # (Document.SetOpenAction, /Catalog/OpenAction) never appeared anywhere. The corrected,
    # compound-token-preferring check must now catch this real, confirmed gap.
    entry = {
        "unit_id": "u0093", "excerpt": _PDF_GO_U0093_EXCERPT, "salient_tokens": list(_PDF_GO_U0093_TOKENS),
        "disposition": "merged_reframed", "target_section": "API Reference",
    }
    text = (
        "## API Reference\n\n"
        "`Document.JavaScript()` is the document-level named-script collection backed by the "
        "`/Catalog/Names/JavaScript` name tree (ISO 32000-1 §7.7.4 / §8.5.1).\n\n"
        "Annotations support GoTo, JavaScript, Named, and other action types.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(text, [entry])
    assert len(findings) == 1 and findings[0]["unit_id"] == "u0093"
    assert "Document.SetOpenAction" in findings[0]["reason"]


def test_merge_into_target_section_u0093_group1_still_passes_via_compound_token():
    # Regression guard: u0093's own Group 1 (the genuine JS-collection-storage fact) must
    # continue to pass unchanged -- it already correctly matches via its own compound token
    # `/Catalog/Names/JavaScript`, not a bare word.
    entry = {
        "unit_id": "u0093", "excerpt": _PDF_GO_U0093_EXCERPT, "salient_tokens": list(_PDF_GO_U0093_TOKENS),
        "disposition": "merged_reframed", "target_section": "API Reference",
    }
    text = (
        "## API Reference\n\n"
        "`Document.JavaScript()` is the document-level named-script collection backed by the "
        "`/Catalog/Names/JavaScript` name tree.\n\n"
        "`Document.SetOpenAction` / `OpenAction` / `RemoveOpenAction` manage the "
        "`/Catalog/OpenAction` run on open.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_merge_into_target_section_catches_real_pdf_go_u0042_rtl_gap():
    # Same real defect shape as u0093, second confirmed instance: the whole excerpt (a single,
    # unsplit group -- its own bold-markdown "**Right-to-left" boundary never triggers MT049's
    # capital-letter lookahead) previously passed via the bare, reused class name "TextStyle"
    # instead of its own distinctive dotted token "TextStyle.RTL", the group's only compound
    # token. The corrected, compound-token-preferring check must now catch this real gap even
    # with no group split at all -- proof item 2 (TC-HARDEN-106) closes real cases item 1
    # (TC-HARDEN-105) does not reach.
    entry = {
        "unit_id": "u0042", "excerpt": _PDF_GO_U0042_EXCERPT, "salient_tokens": list(_PDF_GO_U0042_TOKENS),
        "disposition": "merged_reframed", "target_section": "API Reference",
    }
    text = (
        "## API Reference\n\n"
        "`TextStyle` configures font selection, alignment, word wrap, color, background, "
        "underline, strikethrough, and rotation for drawn text.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(text, [entry])
    assert len(findings) == 1 and findings[0]["unit_id"] == "u0042"


def test_merge_into_target_section_passes_real_bare_token_case_unchanged():
    # Regression guard (item 2's own "must not regress" requirement): a real, sampled,
    # currently-passing single-bare-token merge (words/net's own real shape) must continue to
    # pass unchanged -- its one group has no compound token at all, so it correctly falls back
    # to the original "any token" behavior.
    entry = {
        "unit_id": "wn0001",
        "excerpt": "The library ships a real Document Object Model, not a thin XML wrapper.",
        "salient_tokens": ["Document", "XML"],
        "disposition": "merged_reframed", "target_section": "API Reference",
    }
    text = "## API Reference\n\nThe `Document` object model exposes the full DOCX structure.\n"
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_merge_into_target_section_trailing_segment_promotes_real_short_names():
    # Real, confirmed false positive found via a live portfolio sweep, fixed the same day
    # (_compound_token_trailing_segment): pdf/go's own real u0010 merges cleanly using the
    # product's own already-established bare short names "NUp"/"Booklet" -- both must be
    # promoted to "strong" because they exactly equal the TRAILING segment of their own group's
    # compound tokens (Document.NUp -> NUp, Document.Booklet -> Booklet), not rejected merely for
    # being bare.
    entry = {
        "unit_id": "u0010",
        "excerpt": (
            "- **Imposition** — `Document.NUp` lays multiple source pages onto larger sheets in "
            "a Rows×Cols grid; `Document.Booklet` reorders pages two-up for saddle-stitch "
            "binding. Both return a new document (source untouched), built from Form XObjects"
        ),
        "salient_tokens": ["Document.NUp", "Document.Booklet", "NUp", "Booklet", "XObjects"],
        "disposition": "merged_reframed", "target_section": "Key Capabilities",
    }
    text = (
        "## Key Capabilities\n\n"
        "`Rotate`/`SetRotation` turn pages; `NUp` and `Booklet` support N-up printing or "
        "saddle-stitch binding, each returning a new document built from Form XObjects.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_merge_into_target_section_trailing_segment_does_not_promote_leading_segment():
    # Regression guard: a blind substring match would also wrongly promote "TextStyle" (the
    # LEADING segment of TextStyle.RTL, not the trailing one) -- must stay weak, since promoting
    # it would silently reintroduce the real u0042 false negative this whole rule exists to close.
    entry = {
        "unit_id": "u0042", "excerpt": _PDF_GO_U0042_EXCERPT, "salient_tokens": list(_PDF_GO_U0042_TOKENS),
        "disposition": "merged_reframed", "target_section": "API Reference",
    }
    text = (
        "## API Reference\n\n"
        "`TextStyle` configures font selection, alignment, word wrap, color, background, "
        "underline, strikethrough, and rotation for drawn text.\n"
    )
    findings = checks.check_content_unit_merged_into_target_section(text, [entry])
    assert len(findings) == 1 and findings[0]["unit_id"] == "u0042"


def test_content_unit_redundant_claim_verifiable_flags_real_pdf_go_u0041():
    # Fix item 3 (TC-HARDEN-107): u0041's real disposition has empty salient_tokens and no
    # backtick-quoted identifier at all -- even after the extended stoplist, only "append"/
    # "insert" remain, both too generic to mechanically verify. Must fire.
    entry = {
        "unit_id": "u0041", "excerpt": _PDF_GO_U0041_EXCERPT, "salient_tokens": [],
        "disposition": "excluded", "classification": "redundant_with_existing",
        "target_section": None,
    }
    findings = checks.check_content_unit_redundant_claim_verifiable([entry], "")
    assert len(findings) == 1 and findings[0]["unit_id"] == "u0041"


def test_content_unit_redundant_claim_verifiable_silent_on_verifiable_short_claim():
    # Negative control: a short, identifier-free claim that still carries 3+ genuinely
    # distinctive words (not stripped by the stoplist) is NOT flagged -- the heuristic targets
    # only the specific "nothing left to verify" shape, not every short excluded claim.
    entry = {
        "unit_id": "u9999",
        "excerpt": "- **Barcode symbology autodetection** — scans QR, DataMatrix, and Aztec",
        "salient_tokens": [],
        "disposition": "excluded", "classification": "redundant_with_existing",
        "target_section": None,
    }
    assert checks.check_content_unit_redundant_claim_verifiable([entry], "") == []


def test_content_unit_redundant_claim_verifiable_ignores_non_redundant_dispositions():
    # Scope guard: only excluded/redundant_with_existing entries with empty salient_tokens are
    # considered -- a merged entry, or an excluded entry with real tokens, is never flagged.
    entries = [
        {
            "unit_id": "m1", "excerpt": "Append or insert blank pages.", "salient_tokens": [],
            "disposition": "merged_reframed", "classification": "2_mechanism_explanation",
            "target_section": "API Reference",
        },
        {
            "unit_id": "e1", "excerpt": "Append or insert blank pages.",
            "salient_tokens": ["AddBlankPage"],
            "disposition": "excluded", "classification": "redundant_with_existing",
            "target_section": None,
        },
    ]
    assert checks.check_content_unit_redundant_claim_verifiable(entries, "") == []


# MT052 (Forty-Third incident): the mirrors-clause exemption (`_mirrors_clause_only_tokens`) and
# the trailing-segment paren/slash fix (`_compound_token_trailing_segment`), both real code
# landed this session -- fixtures built from the exact real `pdf/go` excerpts/tokens this
# incident's own investigation captured, proving both fixes against real content, not synthetic
# stand-ins.

def test_mirrors_clause_sentence_initial_form_excluded_from_required_tokens():
    # Real, captured u0033 shape: "Mirrors Aspose.PDF for .NET's `Document.OptimizeResources`."
    # -- the .NET-only identifier must never be required to match the Go candidate's own text.
    entry = {
        "unit_id": "u0033",
        "excerpt": (
            "- **Optimize (unified)** — `Document.Optimize(OptimizationOptions)` runs a "
            "size-reduction pass in one call: remove unused objects, subset fonts, "
            "Flate-compress uncompressed streams, dedupe byte-identical streams, and "
            "optionally recompress images; returns an `OptimizationResult` of per-op counts. "
            "`DefaultOptimizationOptions()` is the safe lossless preset. Mirrors Aspose.PDF "
            "for .NET's `Document.OptimizeResources`"
        ),
        "salient_tokens": [
            "Document.Optimize(OptimizationOptions)", "OptimizationResult",
            "DefaultOptimizationOptions()", "Document.OptimizeResources", "OptimizeResources",
        ],
        "disposition": "merged_reframed", "target_section": "Key Capabilities",
    }
    text = (
        "## Key Capabilities\n\n"
        "`Document.Optimize(OptimizationOptions)` runs a size-reduction pass; "
        "`DefaultOptimizationOptions()` is the safe lossless preset, returning an "
        "`OptimizationResult` of per-op counts.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_mirrors_clause_mid_sentence_form_excluded_from_required_tokens():
    # Real, captured u0065 shape: "...mirroring the intent of Aspose.PDF for .NET's
    # `PdfFileEditor.MakeNUp` / `MakeBooklet`, adapted to..." -- the mid-sentence "mirroring"
    # form (not sentence-initial "Mirrors") must be recognized too.
    entry = {
        "unit_id": "u0065",
        "excerpt": (
            "`NUp` arranges pages in a `Rows`×`Cols` grid, scaling each to fit its cell "
            "(aspect preserved, centered) and filling sheet after sheet. `Booklet` imposes "
            "pages two-up in saddle-stitch order. Both return a new `*Document` (the receiver "
            "is untouched) built from Form XObjects, so the output is an ordinary PDF. This is "
            "a production helper (not a PDF-spec feature) mirroring the intent of Aspose.PDF "
            "for .NET's `PdfFileEditor.MakeNUp` / `MakeBooklet`, adapted to the "
            "`Document`-method API."
        ),
        "salient_tokens": ["NUp", "Booklet", "*Document", "PdfFileEditor.MakeNUp", "MakeNUp"],
        "disposition": "excluded",
        "verification": {"evidence_type": "candidate_section_reference", "evidence_ref": "Key Capabilities"},
        "target_section": None,
    }
    text = (
        "## Key Capabilities\n\n"
        "`NUp` and `Booklet` impose pages onto larger sheets, returning a new `*Document` "
        "built from Form XObjects.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_mirrors_clause_whole_excerpt_pure_mirrors_skips_verification_entirely():
    # Real, captured u0128 shape: the ENTIRE excerpt is a mirrors clause with no independent
    # Go-side claim of its own -- after filtering, zero tokens remain, and the unit must be
    # skipped entirely (never fall through to the word-overlap fallback, which would test the
    # mirrors clause's own generic words against an unrelated body for a meaningless result).
    entry = {
        "unit_id": "u0128",
        "excerpt": (
            "Mirrors the intent of Aspose.PDF for .NET's generator / `Page.Paragraphs` / "
            "`FloatingBox` / columns / floats."
        ),
        "salient_tokens": ["Page.Paragraphs", "FloatingBox", "PDF", "NET"],
        "disposition": "excluded",
        "verification": {"evidence_type": "candidate_section_reference", "evidence_ref": "API Reference"},
        "target_section": None,
    }
    text = "## API Reference\n\nNothing about generators or paragraphs is mentioned here at all.\n"
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_mirrors_clause_does_not_exclude_tokens_with_a_real_independent_occurrence():
    # Negative control: a token that ALSO occurs outside the mirrors clause (a real, independent
    # Go-side use) must still be required and must still be checked against the body normally --
    # the exemption only ever applies to tokens whose EVERY occurrence is inside the clause.
    entry = {
        "unit_id": "uXXXX",
        "excerpt": (
            "`Document.Stamp` places overlay content on a page. Mirrors Aspose.PDF for .NET's "
            "`Document.Stamp` family."
        ),
        "salient_tokens": ["Document.Stamp"],
        "disposition": "merged_reframed", "target_section": "API Reference",
    }
    text_missing = "## API Reference\n\nNo stamp API is mentioned anywhere here.\n"
    findings = checks.check_content_unit_merged_into_target_section(text_missing, [entry])
    assert len(findings) == 1 and findings[0]["unit_id"] == "uXXXX"
    text_present = "## API Reference\n\n`Document.Stamp` overlays a stamp onto a page.\n"
    assert checks.check_content_unit_merged_into_target_section(text_present, [entry]) == []


def test_trailing_segment_strips_slash_containing_parenthesized_args():
    # Real, captured u0023 shape: `Document.ValidatePDFA(PDFA1B/2B/3B/1A/2A/3A)`'s own
    # parenthesized argument list contains literal "/" characters -- naively splitting on "./"
    # BEFORE stripping the parens computes a garbage trailing segment ("3A)" instead of the real
    # "ValidatePDFA"), which would wrongly refuse to promote the bare "ValidatePDFA" sibling
    # token even though it's the product's own real, already-used short name.
    assert checks._compound_token_trailing_segment(
        "Document.ValidatePDFA(PDFA1B/2B/3B/1A/2A/3A)"
    ) == "ValidatePDFA"
    entry = {
        "unit_id": "u0023",
        "excerpt": (
            "- **PDF/A validate + convert** — `Document.ValidatePDFA(PDFA1B/2B/3B/1A/2A/3A)` "
            "reports archival-conformance violations for the basic levels, and "
            "`Document.ConvertToPDFA(...)` adjusts the document toward conformance."
        ),
        "salient_tokens": [
            "Document.ValidatePDFA(PDFA1B/2B/3B/1A/2A/3A)", "Document.ConvertToPDFA(...)",
            "ValidatePDFA", "ConvertToPDFA",
        ],
        "disposition": "merged_reframed", "target_section": "Key Capabilities",
    }
    text = (
        "## Key Capabilities\n\n"
        "`ValidatePDFA` reports archival-conformance violations; `ConvertToPDFA` adjusts the "
        "document toward conformance in one call.\n"
    )
    assert checks.check_content_unit_merged_into_target_section(text, [entry]) == []


def test_trailing_segment_empty_parens_unaffected_by_paren_stripping():
    # Regression guard: the already-proven `pdf.NewTable()` -> "NewTable" trailing-segment case
    # (empty, non-slash-containing parens) must be completely unaffected by the new paren-first
    # stripping order.
    assert checks._compound_token_trailing_segment("pdf.NewTable()") == "NewTable"


# --- MT057 (Fifty-Seventh incident, TC-UIW-06/07): upstream-issue GitHub Issue draft checks ---


def test_issue_draft_leak_check_fires_on_process_narration_reused_from_readme_check():
    # The shared _PROCESS_NARRATION_RE mechanism (already proven against real README content)
    # must be equally active for an issue draft -- reused, not reimplemented.
    text = "This session confirmed that the install command fails identically on a clean clone."
    findings = checks.check_no_internal_details_leaked_into_issue_draft(text)
    categories = {f["category"] for f in findings}
    assert "process_narration" in categories


def test_issue_draft_leak_check_fires_on_real_internal_artifact_references():
    # Real, captured-shape leak: a draft that cites this project's own internal tracking
    # artifacts and plan machinery by name -- exactly what TC-UIW-06 exists to catch.
    text = (
        "Per TC-HARDEN-105 in MT052, this finding was recorded in "
        "reports/repo-presenter/pdf/go/upstream-issues.md (finding_id UF-pdf-go-0003, "
        "bundle_id UB-pdf-go-0001) after a candidate-generation pass; see "
        "content-dispositions.json for the disposition trail."
    )
    findings = checks.check_no_internal_details_leaked_into_issue_draft(text)
    categories = {f["category"] for f in findings}
    assert "internal_reference" in categories
    phrases = {f["phrase"].lower() for f in findings}
    assert any("mt0" in p or "tc-harden" in p for p in phrases)
    assert any("upstream-issues.md" in p for p in phrases)
    assert any("finding_id" in p for p in phrases)
    assert any("bundle_id" in p for p in phrases)


def test_issue_draft_leak_check_does_not_flag_upstream_issues_md_convention_because_it_never_appears():
    # Sanity/documentation check, not a real assertion gap: the README-context convention of
    # citing upstream-issues.md as a plain, non-forensic pointer is legitimate INSIDE a README,
    # but this check operates on ISSUE DRAFTS, where that same citation is a real leak (the
    # target repo has no such file) -- confirmed by the test above that it DOES fire there.
    # This test documents the deliberate asymmetry: check_process_narration_smells (README-
    # scoped) does not include "upstream-issues.md" in its own shared pattern list, so a real
    # README's own legitimate pointer sentence stays unaffected by this addition.
    readme_text = (
        "`pip install` fails for this repository at any source -- see "
        "[upstream-issues.md](upstream-issues.md) for the root cause and a verified workaround."
    )
    assert checks.check_process_narration_smells(readme_text) == []


def test_issue_draft_leak_check_clean_on_a_real_professional_draft():
    # A real, professional, sanitized draft body (matching the mission's own Stage 7 shape) must
    # produce zero findings.
    text = (
        "## Summary\n\n"
        "`pip install aspose-pdf-foss` fails on a clean Python 3.12 virtual environment with a "
        "build-backend error.\n\n"
        "## Environment\n\nPython 3.12.4, pip 24.0, Ubuntu 22.04.\n\n"
        "## Minimal reproduction\n\n```bash\npython -m venv .venv\n.venv/bin/pip install "
        "aspose-pdf-foss\n```\n\n"
        "## Expected behavior\n\nThe package installs successfully.\n\n"
        "## Actual behavior\n\nThe build backend raises ModuleNotFoundError for setuptools."
    )
    assert checks.check_no_internal_details_leaked_into_issue_draft(text) == []


def test_issue_draft_rejection_hard_gate_fires_on_credential_patterns():
    cases = {
        "ghp_" + "a" * 36: "github_personal_access_token",
        "AKIAABCDEFGHIJKLMNOP": "aws_access_key_id",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END RSA PRIVATE KEY-----": "private_key_block",
        "GH_TOKEN=ghp_abcdef1234567890": "token_assignment",
        "https://user:secretpass@example.com/repo.git": "credential_in_url",
    }
    for text, expected_reason in cases.items():
        result = checks.check_issue_draft_rejection_list(text)
        reasons = {f["reason"] for f in result["hard_gate_findings"]}
        assert expected_reason in reasons, f"expected {expected_reason} for {text!r}, got {reasons}"


def test_issue_draft_rejection_hard_gate_fires_on_local_absolute_paths():
    for text in (
        r"See C:\Users\prora\AppData\Local\Temp\evidence.txt for the raw output.",
        "See /home/prora/evidence.txt for the raw output.",
        "See /Users/prora/evidence.txt for the raw output.",
    ):
        result = checks.check_issue_draft_rejection_list(text)
        reasons = {f["reason"] for f in result["hard_gate_findings"]}
        assert reasons & {"windows_absolute_user_path", "unix_absolute_home_path", "macos_absolute_home_path"}


def test_issue_draft_rejection_hard_gate_clean_on_professional_draft():
    text = (
        "## Summary\n\n`pip install` fails on a clean Python 3.12 virtualenv.\n\n"
        "## Minimal reproduction\n\n```bash\npython -m venv .venv && .venv/bin/pip install "
        "aspose-pdf-foss\n```\n"
    )
    result = checks.check_issue_draft_rejection_list(text)
    assert result["hard_gate_findings"] == []
    assert result["advisory_findings"] == []


def test_issue_draft_rejection_advisory_tier_never_blocks():
    # The accusatory-language tier is advisory-only by design -- it must be surfaced but must
    # NEVER appear in hard_gate_findings, since it is an unproven-at-scale heuristic.
    text = "This is sloppy work and you broke the build."
    result = checks.check_issue_draft_rejection_list(text)
    assert result["hard_gate_findings"] == []
    assert len(result["advisory_findings"]) >= 2
    reasons = {f["reason"] for f in result["advisory_findings"]}
    assert reasons == {"accusatory_language"}

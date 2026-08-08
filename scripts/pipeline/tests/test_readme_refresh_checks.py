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


def test_hybrid_reverification_flags_missing_archetype_entry():
    findings = checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, None, "2026-08-08")
    assert findings and "no archetype override entry" in findings[0]["reason"]


def test_hybrid_reverification_flags_wrong_archetype():
    entry = {"archetype": "transform", "evidence": "x", "decided_at": "2026-08-08"}
    findings = checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, entry, "2026-08-08")
    assert findings and "not 'hybrid'" in findings[0]["reason"]


def test_hybrid_reverification_flags_stale_decided_at():
    entry = {"archetype": "hybrid", "evidence": "real evidence", "decided_at": "2026-08-06"}
    findings = checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, entry, "2026-08-08")
    assert findings and "was not refreshed" in findings[0]["reason"]


def test_hybrid_reverification_passes_fresh_entry():
    entry = {"archetype": "hybrid", "evidence": "real evidence", "decided_at": "2026-08-08"}
    assert checks.check_diagram_hybrid_reverification(HYBRID_PDF_CPP, entry, "2026-08-08") == []


# --- check_diagram_format_support_claims -------------------------------------------------------


def test_format_support_claims_flags_unsupported_format():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Convert PDF to XLSX"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF output"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_format_support_claims(
        text, "Supported formats: PDF only.", {"PDF", "XLSX"}
    )
    assert any(f["format"] == "XLSX" for f in findings)


def test_format_support_claims_clean_when_all_formats_verified():
    text = _wrap(
        """flowchart TD
  PRODUCT["P"]
  subgraph Capabilities["Core Capabilities"]
    c1["Convert PDF to XLSX"]
  end
  subgraph Outputs["Outputs"]
    o1["PDF and XLSX output"]
  end
  PRODUCT --> Capabilities --> Outputs"""
    )
    findings = checks.check_diagram_format_support_claims(
        text, "Supported formats: PDF, XLSX.", {"PDF", "XLSX"}
    )
    assert findings == []


def test_format_support_claims_ignores_unrecognized_words():
    # "Workbook" is not a known format name -- must never be treated as a format claim.
    assert checks.check_diagram_format_support_claims(
        TRANSFORM_CELLS_CPP, "Supported formats: XLSX.", {"XLSX"}
    ) == []


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


def test_format_name_casing_flags_multiple_casings_of_unregistered_word():
    text = "FOO bar. Foo baz. foo qux."
    findings = checks.check_format_name_casing(text, {})
    assert any(f["format"] == "FOO" for f in findings)


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

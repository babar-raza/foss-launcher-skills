"""
Tests for scripts/pipeline/commands/content/body_impact.py.

Min required: 8 tests. This file has 9.
"""

import json
import pytest
from pathlib import Path

import commands.content.body_impact as bi


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    yield
    bi.configure(reports_root="reports/refresh_review")


def _setup_reports(
    tmp_path: Path,
    family: str,
    platform: str,
    changes: list[dict] | None = None,
    claim_maps: list[dict] | None = None,
) -> Path:
    """Write semantic_changes.json and claim_maps/ to tmp_path/reports."""
    reports = tmp_path / "reports" / family / platform
    reports.mkdir(parents=True)
    bi.configure(reports_root=str(tmp_path / "reports"))

    if changes is not None:
        (reports / "semantic_changes.json").write_text(
            json.dumps(changes), encoding="utf-8"
        )

    if claim_maps is not None:
        cm_dir = reports / "claim_maps"
        cm_dir.mkdir()
        for cm in claim_maps:
            slug = cm["page_path"].replace("/", "_")
            (cm_dir / f"{slug}.claim_map.json").write_text(
                json.dumps(cm), encoding="utf-8"
            )

    return reports


def _make_change(
    symbol: str,
    change_type: str = "API_REMOVED",
    public_impact: str = "USER_VISIBLE",
    content_impact: str = "BODY_UPDATE",
    change_id: str = "CHG-pdf-net-0001",
) -> dict:
    return {
        "change_id": change_id,
        "change_type": change_type,
        "symbol": symbol,
        "symbol_kind": "class",
        "public_impact": public_impact,
        "content_impact": content_impact,
        "confidence": 0.95,
        "family": "pdf",
        "platform": "net",
        "base_sha": "abc",
        "current_sha": "def",
        "evidence_paths": [],
    }


def _make_claim_map(page_path: str, symbols: list[str], section_id: str = "installation") -> dict:
    return {
        "page_path": page_path,
        "sections": [
            {
                "section_id": section_id,
                "heading": f"## {section_id.capitalize()}",
                "start_line": 10,
                "end_line": 30,
                "claims": [
                    {
                        "sentence": f"Use `{sym}` to perform the operation.",
                        "line_number": 12,
                        "detected_symbols": [sym],
                        "detected_formats": [],
                        "detected_features": [],
                        "detected_versions": [],
                        "claim_type": "API_REFERENCE",
                    }
                    for sym in symbols
                ],
            }
        ],
    }


# ── Tests ─────────────────────────────────────────────────────────────────

def test_definite_match_on_exact_symbol(tmp_path):
    """Exact symbol match in section claims produces DEFINITE impact."""
    changes = [_make_change("Document")]
    claim_maps = [_make_claim_map("content/docs.aspose.org/en/pdf/net/page.md", ["Document"])]
    _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)

    impacts = bi.run("pdf", "net")
    assert len(impacts) == 1
    sections = impacts[0]["affected_sections"]
    assert any(s["impact_level"] == bi.IL_DEFINITE for s in sections)


def test_highly_likely_on_keyword_match(tmp_path):
    """Partial keyword match (no exact symbol) produces HIGHLY_LIKELY impact."""
    # "DocumentSomething" should not exactly match "Document" but keyword "docum" will
    changes = [_make_change("DocumentConverter")]
    # claim_map uses "document" in a sentence but not as an exact symbol
    cm = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "sections": [
            {
                "section_id": "overview",
                "heading": "## Overview",
                "start_line": 0,
                "end_line": 10,
                "claims": [
                    {
                        "sentence": "The document converter tool processes files.",
                        "line_number": 5,
                        "detected_symbols": [],
                        "detected_formats": [],
                        "detected_features": ["convert"],
                        "detected_versions": [],
                        "claim_type": "FEATURE_CLAIM",
                    }
                ],
            }
        ],
    }
    _setup_reports(tmp_path, "pdf", "net", changes, [cm])
    impacts = bi.run("pdf", "net")
    # Should have HIGHLY_LIKELY from keyword "document" appearing in sentence
    all_levels = [
        s["impact_level"]
        for imp in impacts
        for s in imp["affected_sections"]
    ]
    assert bi.IL_HIGHLY_LIKELY in all_levels or bi.IL_DEFINITE in all_levels


def test_verified_unaffected_on_no_match(tmp_path):
    """No symbol or keyword match → page not included in impacts."""
    changes = [_make_change("AnnotationCollection")]
    claim_maps = [_make_claim_map("content/docs.aspose.org/en/pdf/net/page.md", ["TextFragment"])]
    _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)

    impacts = bi.run("pdf", "net")
    assert impacts == []


def test_section_line_range_captured(tmp_path):
    """Affected section records correct start_line and end_line."""
    changes = [_make_change("TextFragment")]
    claim_maps = [_make_claim_map("content/docs.aspose.org/en/pdf/net/page.md", ["TextFragment"])]
    _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)

    impacts = bi.run("pdf", "net")
    assert len(impacts) == 1
    section = impacts[0]["affected_sections"][0]
    assert section["lines"] == [10, 30]


def test_internal_change_produces_no_impacts(tmp_path):
    """INTERNAL_ONLY change does not produce any impact entries."""
    changes = [_make_change("InternalHelper", public_impact="INTERNAL_ONLY", content_impact="NO_ACTION")]
    claim_maps = [_make_claim_map("content/docs.aspose.org/en/pdf/net/page.md", ["InternalHelper"])]
    _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)

    impacts = bi.run("pdf", "net")
    assert impacts == []


def test_multi_page_discovery(tmp_path):
    """Multiple claim_map files produce separate impact entries per page."""
    changes = [_make_change("PdfDocument")]
    claim_maps = [
        _make_claim_map("content/docs.aspose.org/en/pdf/net/page1.md", ["PdfDocument"]),
        _make_claim_map("content/docs.aspose.org/en/pdf/net/page2.md", ["PdfDocument"]),
        _make_claim_map("content/kb.aspose.org/en/pdf/net/faq.md", ["PdfDocument"]),
    ]
    _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)

    impacts = bi.run("pdf", "net")
    assert len(impacts) == 3


def test_planner_output_used_as_signal_when_present(tmp_path):
    """If planner_output.json exists, planner-flagged pages appear as POSSIBLE."""
    changes = []  # no semantic changes
    claim_maps = []  # no claim maps

    reports = _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)
    # Write a fake planner output referencing a page
    planner_data = [{"page_path": "content/docs.aspose.org/en/pdf/net/flagged.md"}]
    (reports / "planner_output.json").write_text(json.dumps(planner_data), encoding="utf-8")

    impacts = bi.run("pdf", "net")
    assert any(imp["page_path"] == "content/docs.aspose.org/en/pdf/net/flagged.md" for imp in impacts)
    flagged = next(imp for imp in impacts if "flagged.md" in imp["page_path"])
    assert any(s["impact_level"] == bi.IL_POSSIBLE for s in flagged["affected_sections"])


def test_idempotency(tmp_path):
    """Running twice with same inputs produces identical output."""
    changes = [_make_change("Document")]
    claim_maps = [_make_claim_map("content/docs.aspose.org/en/pdf/net/page.md", ["Document"])]
    _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)

    result1 = bi.run("pdf", "net")
    result2 = bi.run("pdf", "net")
    assert result1 == result2


def test_output_written_to_body_impact_json(tmp_path):
    """body_impact.json is written to expected location."""
    changes = [_make_change("PdfConverter")]
    claim_maps = [_make_claim_map("content/docs.aspose.org/en/pdf/net/page.md", ["PdfConverter"])]
    _setup_reports(tmp_path, "pdf", "net", changes, claim_maps)

    bi.run("pdf", "net")
    out_path = tmp_path / "reports" / "pdf" / "net" / "body_impact.json"
    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    assert len(loaded) == 1


def test_api_added_uses_rewrite_strategy_for_keyword_match(tmp_path):
    """API additions need rewrite, not surgical replacement with no old symbol."""
    changes = [_make_change("NewAnnotationApi", change_type="API_ADDED")]
    cm = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "sections": [
            {
                "section_id": "annotations",
                "heading": "## Annotations",
                "start_line": 0,
                "end_line": 10,
                "claims": [
                    {
                        "sentence": "Annotation workflows support document markup.",
                        "line_number": 5,
                        "detected_symbols": [],
                        "detected_formats": [],
                        "detected_features": ["annotation"],
                        "detected_versions": [],
                        "claim_type": "FEATURE_CLAIM",
                    }
                ],
            }
        ],
    }
    _setup_reports(tmp_path, "pdf", "net", changes, [cm])

    impacts = bi.run("pdf", "net")
    section = impacts[0]["affected_sections"][0]
    assert section["impact_level"] == bi.IL_HIGHLY_LIKELY
    assert section["update_type"] == bi.UT_REWRITE
    assert section["change_id"] == "CHG-pdf-net-0001"


def test_duplicate_section_matches_deduped_to_one_entry(tmp_path):
    """Multiple changes keyword-matching the SAME section collapse to one
    affected_sections entry.

    Regression test for the body_refresh repeated-rewrite bug found during
    FONT-PYTHON-REFRESH-002: before this fix, N changes matching a shared
    boilerplate section produced N near-duplicate affected_sections entries
    for that section_id, and body_refresh.py's consumer loop rewrote the
    same section once per duplicate within a single pass — compounding
    near-duplicate prose and malformed markdown at each successive rewrite.
    """
    changes = [
        _make_change("DocumentConverter", change_id="CHG-pdf-net-0001"),
        _make_change("DocumentBuilder", change_id="CHG-pdf-net-0002"),
        _make_change("DocumentLoader", change_id="CHG-pdf-net-0003"),
    ]
    cm = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "sections": [
            {
                "section_id": "overview",
                "heading": "## Overview",
                "start_line": 0,
                "end_line": 10,
                "claims": [
                    {
                        "sentence": "The document conversion tools build and load documents.",
                        "line_number": 5,
                        "detected_symbols": [],
                        "detected_formats": [],
                        "detected_features": ["convert"],
                        "detected_versions": [],
                        "claim_type": "FEATURE_CLAIM",
                    }
                ],
            }
        ],
    }
    _setup_reports(tmp_path, "pdf", "net", changes, [cm])

    impacts = bi.run("pdf", "net")
    assert len(impacts) == 1
    overview_entries = [
        s for s in impacts[0]["affected_sections"] if s["section_id"] == "overview"
    ]
    assert len(overview_entries) == 1
    # All 3 changes are still recorded at the page level, even though only
    # one drives the section-level rewrite.
    assert len(impacts[0]["semantic_change_ids"]) == 3


def test_definite_match_wins_over_highly_likely_for_same_section(tmp_path):
    """When one change is an exact symbol match (DEFINITE) and another only
    keyword-matches (HIGHLY_LIKELY) the same section, dedup keeps the
    higher-confidence DEFINITE entry rather than an arbitrary one."""
    changes = [
        _make_change("DocumentConverter", change_id="CHG-pdf-net-0001"),  # keyword-only
        _make_change("Document", change_id="CHG-pdf-net-0002"),  # exact symbol match
    ]
    cm = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "sections": [
            {
                "section_id": "overview",
                "heading": "## Overview",
                "start_line": 0,
                "end_line": 10,
                "claims": [
                    {
                        "sentence": "Use `Document` with the document conversion workflow.",
                        "line_number": 5,
                        "detected_symbols": ["Document"],
                        "detected_formats": [],
                        "detected_features": [],
                        "detected_versions": [],
                        "claim_type": "API_REFERENCE",
                    }
                ],
            }
        ],
    }
    _setup_reports(tmp_path, "pdf", "net", changes, [cm])

    impacts = bi.run("pdf", "net")
    overview_entries = [
        s for s in impacts[0]["affected_sections"] if s["section_id"] == "overview"
    ]
    assert len(overview_entries) == 1
    assert overview_entries[0]["impact_level"] == bi.IL_DEFINITE
    assert overview_entries[0]["change_id"] == "CHG-pdf-net-0002"


# ── Task 17 (§9.12, closes the other half of G10): claim-text-based keyword
# matching, replacing the opaque-claim_id tokenizer for symbol_kind="claim" ──


def _make_claim_change(claim_id: str, new_text: str | None = None, old_text: str | None = None,
                        change_type: str = "CLAIM_MODIFIED", change_id: str = "CHG-pdf-net-0001") -> dict:
    change = _make_change(claim_id, change_type=change_type,
                           content_impact="BODY_UPDATE", change_id=change_id)
    change["symbol_kind"] = "claim"
    if new_text is not None:
        change["new_text"] = new_text
    if old_text is not None:
        change["old_text"] = old_text
    return change


def test_claim_kind_keyword_match_uses_real_text_not_opaque_id(tmp_path):
    """Before Task 17, symbol="CLM-pdf-abc123" tokenized to fragments that
    could never match real page prose -- a claim-kind change could only ever
    reach DEFINITE (exact detected_symbols citation) or nothing at all. With
    real claim text available, a genuine prose mention is now caught too."""
    changes = [_make_claim_change(
        "CLM-pdf-abc123",
        new_text="PdfConverter now supports exporting to Markdown.",
    )]
    cm = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "sections": [{
            "section_id": "overview", "heading": "## Overview",
            "start_line": 0, "end_line": 10,
            "claims": [{
                "sentence": "The PdfConverter class handles format conversion.",
                "line_number": 5, "detected_symbols": [], "detected_formats": [],
                "detected_features": [], "detected_versions": [], "claim_type": "FEATURE_CLAIM",
            }],
        }],
    }
    _setup_reports(tmp_path, "pdf", "net", changes, [cm])
    impacts = bi.run("pdf", "net")
    levels = [s["impact_level"] for imp in impacts for s in imp["affected_sections"]]
    assert bi.IL_HIGHLY_LIKELY in levels or bi.IL_DEFINITE in levels


def test_claim_kind_without_text_falls_back_to_symbol_and_never_matches_generic_prose(tmp_path):
    """A claim-kind change with no old_text/new_text at all (older, pre-
    Task-17 knowledge_delta.json) falls back to tokenizing the opaque
    claim_id -- exactly the pre-Task-17 behavior, never crashing."""
    changes = [_make_claim_change("CLM-pdf-abc123")]  # no text at all
    cm = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "sections": [{
            "section_id": "overview", "heading": "## Overview",
            "start_line": 0, "end_line": 10,
            "claims": [{
                "sentence": "This section discusses general conversion topics.",
                "line_number": 5, "detected_symbols": [], "detected_formats": [],
                "detected_features": [], "detected_versions": [], "claim_type": "FEATURE_CLAIM",
            }],
        }],
    }
    _setup_reports(tmp_path, "pdf", "net", changes, [cm])
    impacts = bi.run("pdf", "net")
    # No exact symbol, no keyword derivable from an opaque hash ID -> unaffected.
    assert impacts == [] or all(
        s["impact_level"] not in (bi.IL_DEFINITE, bi.IL_HIGHLY_LIKELY)
        for imp in impacts for s in imp["affected_sections"]
    )


class TestClaimTextTokensPrecision:
    """Direct unit tests for _claim_text_tokens' precision profile: it must
    extract distinctive identifier-like fragments (CamelCase/capitalized
    mentions), never generic lowercase English prose words -- otherwise
    _keyword_in_section would over-match almost any section's prose, turning
    a HIGHLY_LIKELY signal into an almost-always-true one."""

    def test_generic_prose_words_are_not_extracted(self):
        tokens = bi._claim_text_tokens(
            "this method will return the result when called with a valid path"
        )
        assert tokens == []

    def test_camelcase_identifier_is_extracted(self):
        tokens = bi._claim_text_tokens("PdfConverter now supports Markdown export.")
        # "Pdf" itself is only 3 chars -- correctly excluded by the same >=4
        # length floor the symbol tokenizer already applies; "Converter" (9
        # chars) survives the CamelCase split.
        assert "converter" in tokens
        assert "markdown" in tokens

    def test_short_words_excluded_even_if_capitalized(self):
        tokens = bi._claim_text_tokens("Db is a short class name.")
        assert "db" not in tokens  # below the 4-char floor, same as symbol tokenizer

    def test_keyword_in_section_does_not_match_unrelated_generic_sentence(self):
        """A claim about one topic must not spuriously match a section whose
        only overlap is common English words."""
        change = _make_claim_change(
            "CLM-pdf-x", new_text="the library will now return a better result for this case"
        )
        section = {
            "claims": [{"sentence": "This document explains how to install the library."}]
        }
        assert bi._keyword_in_section(change, section) is False

    def test_keyword_in_section_matches_real_identifier_mention(self):
        change = _make_claim_change("CLM-pdf-x", new_text="PdfConverter supports Markdown export.")
        section = {"claims": [{"sentence": "Use the PdfConverter class to transform documents."}]}
        assert bi._keyword_in_section(change, section) is True


# ── Task 19 (§9.14, closes G12): format changes reach general body-prose
# review, not only format_table_handler.py's narrow table path ──────────────


def test_format_change_produces_impact_via_general_review_pipeline(tmp_path):
    """End-to-end: a semantic_changes.json entry with symbol_kind="format"
    (as semantic_diff.py's Task 19 fix now produces) is picked up by
    body_impact.py's existing DEFINITE/HIGHLY_LIKELY matching -- exactly
    like an API or claim change already was, closing G12's "format changes
    reach only one narrow consumer" gap."""
    changes = [{
        "change_id": "CHG-pdf-net-0001", "change_type": "FORMAT_ADDED",
        "symbol": "DOCX", "symbol_kind": "format",
        "public_impact": "USER_VISIBLE", "content_impact": "BODY_UPDATE",
        "confidence": 0.90, "family": "pdf", "platform": "net",
        "base_sha": "abc", "current_sha": "def", "evidence_paths": [],
        "format_ext": "docx",
    }]
    cm = {
        "page_path": "content/docs.aspose.org/en/pdf/net/page.md",
        "sections": [{
            "section_id": "supported-formats", "heading": "## Supported Formats",
            "start_line": 0, "end_line": 10,
            "claims": [{
                "sentence": "This library exports files in DOCX and other formats.",
                "line_number": 5, "detected_symbols": ["DOCX"], "detected_formats": ["DOCX"],
                "detected_features": [], "detected_versions": [], "claim_type": "FORMAT_CLAIM",
            }],
        }],
    }
    _setup_reports(tmp_path, "pdf", "net", changes, [cm])
    impacts = bi.run("pdf", "net")
    assert len(impacts) == 1
    sections = impacts[0]["affected_sections"]
    assert any(s["impact_level"] == bi.IL_DEFINITE for s in sections)

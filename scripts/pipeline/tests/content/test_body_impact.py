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

"""Tests for page_impact_assess.py — Page Impact Assessment.

Coverage:
- HIGH_IMPACT: page body contains a class name from modified_apis
- MEDIUM_IMPACT: page body contains ≥2 claim keywords from modified/removed claims
- LOW_IMPACT: delta has signals but page body has no matches
- NOT_AFFECTED: page body contains no delta signals (empty delta)
- PIA covers all 5 subdomain patterns
- Empty delta → all pages NOT_AFFECTED
- api_names and claim_keywords extraction functions
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import page_impact_assess


@pytest.fixture(autouse=True)
def _reset_pia():
    yield
    page_impact_assess.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_page(dir_: Path, name: str, body: str = "body content here") -> Path:
    """Write a minimal markdown page to dir_/name."""
    dir_.mkdir(parents=True, exist_ok=True)
    p = dir_ / name
    p.write_text(f"---\ntitle: {name}\n---\n{body}\n", encoding="utf-8")
    return p


def _write_delta(knowledge_dir: Path, delta: dict) -> None:
    """Write knowledge_delta.json to the merged/ dir."""
    merged = knowledge_dir / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "knowledge_delta.json").write_text(
        json.dumps(delta), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Unit: _extract_api_names
# ---------------------------------------------------------------------------

class TestExtractApiNames:
    def test_extracts_class_name_strings(self):
        delta = {"modified_apis": ["Workbook", "Cells"]}
        names = page_impact_assess._extract_api_names(delta)
        assert "workbook" in names
        assert "cells" in names

    def test_extracts_class_name_dicts(self):
        delta = {"removed_apis": [{"name": "ChartCollection", "methods": []}]}
        names = page_impact_assess._extract_api_names(delta)
        assert "chartcollection" in names

    def test_extracts_method_names_from_dict(self):
        delta = {"modified_apis": [{"name": "Workbook", "methods": ["Save", "Open"]}]}
        names = page_impact_assess._extract_api_names(delta)
        assert "workbook" in names
        assert "save" in names
        assert "open" in names

    def test_empty_delta_returns_empty_set(self):
        assert page_impact_assess._extract_api_names({}) == set()


# ---------------------------------------------------------------------------
# Unit: _score_page — HIGH_IMPACT detection
# ---------------------------------------------------------------------------

class TestHighImpactDetection:
    def test_page_with_modified_api_class_scores_high(self, tmp_path):
        """Fixture page containing a class name from modified_apis → HIGH_IMPACT."""
        page = _write_page(
            tmp_path,
            "guide.md",
            "This guide explains how to use the Workbook class to open spreadsheets.",
        )
        api_names = {"workbook", "save"}
        claim_keywords = set()

        score, signals = page_impact_assess._score_page(page, api_names, claim_keywords)

        assert score == "HIGH_IMPACT"
        assert any("api:workbook" == s for s in signals)

    def test_case_insensitive_matching(self, tmp_path):
        """Matching is case-insensitive: body 'WORKBOOK' matches api_name 'workbook'."""
        page = _write_page(
            tmp_path, "guide.md",
            "Use the WORKBOOK object to access spreadsheets.",
        )
        score, _ = page_impact_assess._score_page(page, {"workbook"}, set())
        assert score == "HIGH_IMPACT"


# ---------------------------------------------------------------------------
# Unit: _score_page — NOT_AFFECTED detection
# ---------------------------------------------------------------------------

class TestNotAffectedDetection:
    def test_unrelated_page_scores_low_impact(self, tmp_path):
        """Page with no body matches when delta has signals → LOW_IMPACT.
        NOT_AFFECTED is reserved for the empty-delta shortcut in assess_product."""
        page = _write_page(
            tmp_path, "unrelated.md",
            "This is a general overview page about installation requirements.",
        )
        api_names = {"specificclassname", "anotherclass"}
        claim_keywords = {"uniquekeyword1", "uniquekeyword2", "uniquekeyword3"}

        score, signals = page_impact_assess._score_page(page, api_names, claim_keywords)

        assert score == "LOW_IMPACT"
        assert signals == []

    def test_empty_delta_signals_returns_low_impact(self, tmp_path):
        """_score_page with empty signal sets → LOW_IMPACT.
        The NOT_AFFECTED label is assigned by assess_product when delta is absent/empty,
        before _score_page is ever called."""
        page = _write_page(tmp_path, "page.md", "Any body text here.")
        score, signals = page_impact_assess._score_page(page, set(), set())
        assert score == "LOW_IMPACT"

    def test_assess_product_assigns_not_affected_for_empty_delta(self, tmp_path, monkeypatch):
        """assess_product shortcut: when delta has no signals, all pages → NOT_AFFECTED."""
        page_impact_assess.configure(repo_root=tmp_path)
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        _write_page(d, "page.md", "Any body text here.")
        # No knowledge dir → _load_delta returns {} → empty signal sets → shortcut fires
        result = page_impact_assess.assess_product(
            "cells", "net",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )
        assert result["pages"][0]["pia_score"] == "NOT_AFFECTED"
        assert result["summary"]["NOT_AFFECTED"] == 1
        assert result["summary"]["LOW_IMPACT"] == 0


# ---------------------------------------------------------------------------
# Integration: assess_product covers all 5 subdomain patterns
# ---------------------------------------------------------------------------

class TestSubdomainCoverage:
    def test_discovers_files_in_all_five_subdomains(self, tmp_path, monkeypatch):
        """Script discovers fixture files planted in all 5 subdomain directories."""
        page_impact_assess.configure(repo_root=tmp_path)

        # Create pages in each subdomain
        subdomain_paths = [
            tmp_path / "content" / "docs.aspose.org" / "en" / "test" / "py",
            tmp_path / "content" / "kb.aspose.org" / "en" / "test" / "py",
            tmp_path / "content" / "products.aspose.org" / "en" / "test" / "py",
            tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "py",
            tmp_path / "content" / "blog.aspose.org" / "test" / "py",
        ]
        created_files = []
        for d in subdomain_paths:
            created_files.append(_write_page(d, "page.md", "body text for testing"))

        # Empty delta — no signals
        knowledge_dir = tmp_path / "knowledge" / "test" / "py"
        _write_delta(knowledge_dir, {})

        result = page_impact_assess.assess_product(
            "test", "py",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )

        discovered_paths = {p["path"] for p in result["pages"]}
        assert result["summary"]["total"] >= 5, f"Expected ≥5 pages, got {result['summary']['total']}"
        # Verify each subdomain is represented
        subdomains_found = {p["subdomain"] for p in result["pages"]}
        assert "docs" in subdomains_found
        assert "kb" in subdomains_found
        assert "products" in subdomains_found
        assert "reference" in subdomains_found
        assert "blog" in subdomains_found

    def test_locale_files_excluded(self, tmp_path, monkeypatch):
        """Translation files (.fr.md, .de.md) are excluded from assessment."""
        page_impact_assess.configure(repo_root=tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "test" / "py"
        _write_page(d, "page.md", "English page")
        _write_page(d, "page.fr.md", "French translation")

        knowledge_dir = tmp_path / "knowledge" / "test" / "py"
        _write_delta(knowledge_dir, {})

        result = page_impact_assess.assess_product(
            "test", "py",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )

        paths = [p["path"] for p in result["pages"]]
        assert not any("fr.md" in p for p in paths)
        assert any("page.md" in p for p in paths)


# ---------------------------------------------------------------------------
# Integration: empty delta → all NOT_AFFECTED
# ---------------------------------------------------------------------------

class TestEmptyDelta:
    def test_truly_empty_delta_all_not_affected(self, tmp_path, monkeypatch):
        """When delta has no signals at all (no new/modified/removed), all pages are NOT_AFFECTED."""
        page_impact_assess.configure(repo_root=tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "fam" / "plat"
        _write_page(d, "page1.md", "Uses Workbook class extensively")
        _write_page(d, "page2.md", "About spreadsheet operations")

        knowledge_dir = tmp_path / "knowledge" / "fam" / "plat"
        _write_delta(knowledge_dir, {})

        result = page_impact_assess.assess_product(
            "fam", "plat",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )

        for p in result["pages"]:
            assert p["pia_score"] == "NOT_AFFECTED"

    def test_new_apis_generate_signals_not_not_affected(self, tmp_path, monkeypatch):
        """new_apis now generate api_name signals — pages are scored, not NOT_AFFECTED."""
        page_impact_assess.configure(repo_root=tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "fam" / "plat"
        _write_page(d, "page1.md", "Uses Workbook class extensively")

        knowledge_dir = tmp_path / "knowledge" / "fam" / "plat"
        _write_delta(knowledge_dir, {"new_apis": ["NewClass"]})

        result = page_impact_assess.assess_product(
            "fam", "plat",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )

        # new_apis generate api_names → _score_page is called → LOW_IMPACT (no match)
        assert result["pages"][0]["pia_score"] == "LOW_IMPACT"


# ---------------------------------------------------------------------------
# Integration: assess_product HIGH_IMPACT end-to-end
# ---------------------------------------------------------------------------

class TestAssessProductHighImpact:
    def test_page_with_modified_api_class_is_high_impact(self, tmp_path, monkeypatch):
        """End-to-end: page mentioning modified_api class → HIGH_IMPACT in results."""
        page_impact_assess.configure(repo_root=tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        _write_page(
            d, "workbook-guide.md",
            "The Workbook class is central to Aspose.Cells for .NET operations.",
        )

        knowledge_dir = tmp_path / "knowledge" / "cells" / "net"
        _write_delta(knowledge_dir, {
            "modified_apis": [{"name": "Workbook", "methods": ["Save"]}],
        })

        result = page_impact_assess.assess_product(
            "cells", "net",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )

        high_pages = [p for p in result["pages"] if p["pia_score"] == "HIGH_IMPACT"]
        assert len(high_pages) >= 1
        assert any("workbook-guide.md" in p["path"] for p in high_pages)
        assert result["summary"]["HIGH_IMPACT"] >= 1


# ---------------------------------------------------------------------------
# MEDIUM_IMPACT detection
# ---------------------------------------------------------------------------

class TestMediumImpactDetection:
    def test_medium_impact_two_keyword_matches(self, tmp_path):
        """Page body with ≥2 claim keywords → MEDIUM_IMPACT."""
        delta = {
            "modified_claims": [
                {"claim_id": "CLM-001", "text": "spreadsheet processing performance"},
                {"claim_id": "CLM-002", "text": "workbook rendering accuracy"},
            ]
        }
        page = tmp_path / "guide.md"
        page.write_text(
            "---\ntitle: Guide\n---\n"
            "This guide covers spreadsheet performance and workbook rendering.\n",
            encoding="utf-8",
        )
        keywords = page_impact_assess._extract_claim_keywords(delta)
        assert "spreadsheet" in keywords
        assert "workbook" in keywords

        score, signals = page_impact_assess._score_page(page, set(), keywords)
        assert score == "MEDIUM_IMPACT"
        assert any(s.startswith("kw:") for s in signals)

    def test_single_keyword_not_medium(self, tmp_path):
        """Only 1 keyword match falls below threshold → LOW_IMPACT (not MEDIUM)."""
        delta = {"modified_claims": [{"claim_id": "CLM-001", "text": "spreadsheet processing"}]}
        page = tmp_path / "page.md"
        page.write_text(
            "---\ntitle: Page\n---\nOnly spreadsheet is mentioned here.\n",
            encoding="utf-8",
        )
        keywords = page_impact_assess._extract_claim_keywords(delta)
        score, _ = page_impact_assess._score_page(page, set(), keywords)
        # 1 match is below the 2-keyword threshold
        assert score == "LOW_IMPACT"


# ---------------------------------------------------------------------------
# LOW_IMPACT detection
# ---------------------------------------------------------------------------

class TestLowImpactDetection:
    def test_low_impact_when_delta_has_api_signals_but_page_has_none(self, tmp_path):
        """Delta has api_names; page body has no matches → LOW_IMPACT, not NOT_AFFECTED."""
        page = tmp_path / "unrelated.md"
        page.write_text(
            "---\ntitle: Unrelated\n---\n"
            "This page discusses completely different topics with no relevant terms.\n",
            encoding="utf-8",
        )
        api_names = {"workbook", "worksheet"}
        score, signals = page_impact_assess._score_page(page, api_names, set())
        assert score == "LOW_IMPACT"
        assert signals == []

    def test_low_impact_when_delta_has_keywords_but_page_has_none(self, tmp_path):
        """Delta has claim keywords; page body has no matches → LOW_IMPACT."""
        page = tmp_path / "page.md"
        page.write_text(
            "---\ntitle: Page\n---\n"
            "Introduction to the product with no specific technical terms.\n",
            encoding="utf-8",
        )
        claim_keywords = {"rendering", "compression", "encryption"}
        score, _ = page_impact_assess._score_page(page, set(), claim_keywords)
        assert score == "LOW_IMPACT"

    def test_score_page_never_returns_not_affected(self, tmp_path):
        """_score_page with non-empty delta signals always returns LOW_IMPACT or higher."""
        page = tmp_path / "page.md"
        page.write_text("---\ntitle: Page\n---\nsome generic content here\n", encoding="utf-8")
        score, _ = page_impact_assess._score_page(page, {"workbook"}, {"spreadsheet"})
        assert score != "NOT_AFFECTED"
        assert score == "LOW_IMPACT"

    def test_not_affected_path_owned_by_assess_product(self, tmp_path, monkeypatch):
        """assess_product uses NOT_AFFECTED for empty-delta shortcut, not via _score_page."""
        page_impact_assess.configure(repo_root=tmp_path)
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        _write_page(d, "page.md", "generic content")
        # No delta — _load_delta returns {} → api_names/claim_keywords empty
        result = page_impact_assess.assess_product(
            "cells", "net",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )
        assert result["summary"]["NOT_AFFECTED"] == 1
        assert result["summary"]["LOW_IMPACT"] == 0
        assert result["pages"][0]["pia_score"] == "NOT_AFFECTED"


# ---------------------------------------------------------------------------
# PAGE-MAP-001: new_claims and new_apis now generate PIA signals
# ---------------------------------------------------------------------------

class TestNewClaimsNewApisScoring:
    """Verify that new_claims and new_apis from knowledge delta are included
    in PIA scoring (PAGE-MAP-001 fix)."""

    def test_new_apis_extracted_by_extract_api_names(self):
        """_extract_api_names includes new_apis entries."""
        delta = {"new_apis": ["AsyncConverter", {"name": "StreamProcessor", "methods": ["Process"]}]}
        names = page_impact_assess._extract_api_names(delta)
        assert "asyncconverter" in names
        assert "streamprocessor" in names
        assert "process" in names

    def test_new_claims_extracted_by_extract_claim_keywords(self):
        """_extract_claim_keywords includes new_claims entries."""
        delta = {"new_claims": [
            {"claim_id": "CLM-test-001", "text": "supports asynchronous conversion for large documents"},
        ]}
        keywords = page_impact_assess._extract_claim_keywords(delta)
        assert "asynchronous" in keywords
        assert "conversion" in keywords
        assert "documents" in keywords
        assert "large" in keywords

    def test_new_apis_match_produces_high_impact(self, tmp_path):
        """Page body mentioning a new_apis class name → HIGH_IMPACT."""
        page = _write_page(
            tmp_path, "convert-guide.md",
            "Use the AsyncConverter class to process documents asynchronously.",
        )
        api_names = page_impact_assess._extract_api_names({"new_apis": ["AsyncConverter"]})
        score, signals = page_impact_assess._score_page(page, api_names, set())
        assert score == "HIGH_IMPACT"
        assert any("api:asyncconverter" == s for s in signals)

    def test_new_claims_keywords_produce_medium_impact(self, tmp_path):
        """Page body with ≥2 keywords from new_claims → MEDIUM_IMPACT."""
        delta = {"new_claims": [
            {"claim_id": "CLM-test-001", "text": "supports brotli compression for font subsetting"},
        ]}
        page = _write_page(
            tmp_path, "font-guide.md",
            "This guide covers brotli compression and font subsetting techniques.",
        )
        keywords = page_impact_assess._extract_claim_keywords(delta)
        score, signals = page_impact_assess._score_page(page, set(), keywords)
        assert score == "MEDIUM_IMPACT"
        assert any(s.startswith("kw:") for s in signals)

    def test_single_new_claim_keyword_stays_low_impact(self, tmp_path):
        """Single keyword match from new_claims is below threshold → LOW_IMPACT."""
        delta = {"new_claims": [
            {"claim_id": "CLM-test-002", "text": "supports brotli compression"},
        ]}
        page = _write_page(
            tmp_path, "overview.md",
            "General overview with only brotli mentioned once.",
        )
        keywords = page_impact_assess._extract_claim_keywords(delta)
        score, _ = page_impact_assess._score_page(page, set(), keywords)
        assert score == "LOW_IMPACT"

    def test_assess_product_new_apis_high_impact_end_to_end(self, tmp_path):
        """End-to-end: assess_product with new_apis in delta → matching page is HIGH_IMPACT."""
        page_impact_assess.configure(repo_root=tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "test" / "py"
        _write_page(d, "converter.md", "The AsyncConverter handles batch processing efficiently.")
        _write_page(d, "unrelated.md", "This page has nothing to do with conversion.")

        knowledge_dir = tmp_path / "knowledge" / "test" / "py"
        _write_delta(knowledge_dir, {"new_apis": ["AsyncConverter"]})

        result = page_impact_assess.assess_product(
            "test", "py",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )

        scores = {p["path"].split("/")[-1]: p["pia_score"] for p in result["pages"]}
        assert scores["converter.md"] == "HIGH_IMPACT"
        assert scores["unrelated.md"] == "LOW_IMPACT"
        assert result["summary"]["HIGH_IMPACT"] == 1

    def test_modified_claims_still_work_regression(self, tmp_path):
        """Regression: modified_claims keyword extraction unchanged after adding new_claims."""
        delta = {
            "modified_claims": [
                {"claim_id": "CLM-001", "text": "spreadsheet rendering performance improved"},
            ]
        }
        page = _write_page(
            tmp_path, "perf.md",
            "Spreadsheet rendering and performance benchmarks are discussed here.",
        )
        keywords = page_impact_assess._extract_claim_keywords(delta)
        assert "spreadsheet" in keywords
        assert "rendering" in keywords
        assert "performance" in keywords
        score, _ = page_impact_assess._score_page(page, set(), keywords)
        assert score == "MEDIUM_IMPACT"

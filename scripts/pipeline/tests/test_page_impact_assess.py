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

import builtins
import json
import sys
import types
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

    def test_score_page_fallback_path_never_returns_not_affected(self, tmp_path):
        """FALLBACK path (evidence-less page, legacy 3-arg call) never returns
        NOT_AFFECTED. (The citation path CAN return NOT_AFFECTED per RPR-D-02 —
        see TestCitationBasedScoring — but only for pages that carry evidence.)"""
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


# ---------------------------------------------------------------------------
# RPR-D-01 / RPR-D-02: citation-based scoring + per-page NOT_AFFECTED
# ---------------------------------------------------------------------------

def _write_page_with_evidence(
    dir_: Path,
    name: str,
    *,
    claims: "list[str] | None" = None,
    apis: "list[str] | None" = None,
    body: str = "generic body content with no special tokens",
) -> Path:
    """Write a page carrying an evidence: frontmatter block."""
    import yaml as _yaml
    dir_.mkdir(parents=True, exist_ok=True)
    fm: dict = {"title": name, "evidence": {}}
    if claims is not None:
        fm["evidence"]["claims"] = claims
    if apis is not None:
        fm["evidence"]["apis"] = apis
    p = dir_ / name
    p.write_text("---\n" + _yaml.dump(fm, sort_keys=False) + "---\n" + body + "\n", encoding="utf-8")
    return p


class TestCitationBasedScoring:
    """RPR-D-01: scoring driven by the page's own evidence.claims/apis, not body tokens."""

    def test_high_on_cited_api_change(self, tmp_path):
        page = _write_page_with_evidence(tmp_path, "p.md", apis=["Document", "Permissions"])
        score, signals = page_impact_assess._score_page(
            page, set(), set(),
            changed_api_ids={"Document"}, changed_claim_ids=set(),
        )
        assert score == "HIGH_IMPACT"
        assert any(s.startswith("cite-api:Document") for s in signals)

    def test_high_on_cited_method_when_owning_class_changed(self, tmp_path):
        """A page citing Document.Create is HIGH when the class Document changed,
        even though the delta tracks the change at class granularity."""
        page = _write_page_with_evidence(tmp_path, "p.md", apis=["Document.Create"])
        score, signals = page_impact_assess._score_page(
            page, set(), set(),
            changed_api_ids={"Document"}, changed_claim_ids=set(),
        )
        assert score == "HIGH_IMPACT"
        assert any("Document.Create" in s for s in signals)

    def test_medium_on_cited_claim_change(self, tmp_path):
        page = _write_page_with_evidence(tmp_path, "p.md", claims=["CLM-pdf-073e10"])
        score, signals = page_impact_assess._score_page(
            page, set(), set(),
            changed_api_ids=set(), changed_claim_ids={"CLM-pdf-073e10"},
        )
        assert score == "MEDIUM_IMPACT"
        assert any("CLM-pdf-073e10" in s for s in signals)

    def test_api_citation_beats_claim_citation(self, tmp_path):
        """When both a cited API and a cited claim changed, HIGH (api) wins over MEDIUM (claim)."""
        page = _write_page_with_evidence(
            tmp_path, "p.md", apis=["Document"], claims=["CLM-x"],
        )
        score, _ = page_impact_assess._score_page(
            page, set(), set(),
            changed_api_ids={"Document"}, changed_claim_ids={"CLM-x"},
        )
        assert score == "HIGH_IMPACT"

    def test_not_affected_when_page_cites_unrelated_apis_only(self, tmp_path):
        """RPR-D-02: a page whose cited APIs/claims are NONE of them in the delta
        scores NOT_AFFECTED even though the product delta is non-empty."""
        page = _write_page_with_evidence(tmp_path, "p.md", apis=["SomethingElse"], claims=["CLM-unrelated"])
        score, signals = page_impact_assess._score_page(
            page, set(), set(),
            changed_api_ids={"Document"}, changed_claim_ids={"CLM-pdf-073e10"},
        )
        assert score == "NOT_AFFECTED"
        assert signals == ["cite-clean"]

    def test_citation_path_ignores_body_tokens(self, tmp_path):
        """Even if the body text mentions a changed API by name, an evidence-bearing
        page that does NOT cite it scores NOT_AFFECTED — citation is authoritative,
        body-token coincidence is not (the exact false-positive class RPR-D-01 fixes)."""
        page = _write_page_with_evidence(
            tmp_path, "p.md", apis=["UnrelatedClass"],
            body="This prose happens to mention Document in passing.",
        )
        score, _ = page_impact_assess._score_page(
            page, {"document"}, set(),
            changed_api_ids={"Document"}, changed_claim_ids=set(),
        )
        assert score == "NOT_AFFECTED"


class TestEvidencelessFallback:
    """RPR-D-01: pages with no evidence fall back to the token heuristic, visibly marked."""

    def test_fallback_warns_on_missing_evidence(self, tmp_path):
        """An evidence-less page scored during a real run (changed_ids supplied)
        gets a 'fallback-no-evidence' marker so the token-guess is never mistaken
        for a confident citation verdict."""
        page = tmp_path / "p.md"
        page.write_text("---\ntitle: P\n---\nUse the Workbook class heavily here.\n", encoding="utf-8")
        score, signals = page_impact_assess._score_page(
            page, {"workbook"}, set(),
            changed_api_ids={"Workbook"}, changed_claim_ids=set(),
        )
        assert score == "HIGH_IMPACT"
        assert "fallback-no-evidence" in signals

    def test_evidenceless_page_never_defaults_to_not_affected(self, tmp_path):
        """RPR-D-02 guard: a page with empty/missing evidence must NOT silently
        become NOT_AFFECTED — it routes to the fallback path (LOW_IMPACT here),
        never the citation-clean NOT_AFFECTED branch."""
        page = tmp_path / "p.md"
        page.write_text("---\ntitle: P\n---\ncompletely unrelated prose\n", encoding="utf-8")
        score, _ = page_impact_assess._score_page(
            page, {"workbook"}, {"spreadsheet"},
            changed_api_ids={"Workbook"}, changed_claim_ids={"CLM-x"},
        )
        assert score == "LOW_IMPACT"  # fallback path, not NOT_AFFECTED

    def test_malformed_frontmatter_falls_back_not_crashes(self, tmp_path):
        page = tmp_path / "p.md"
        page.write_text("---\ntitle: [unclosed\n---\nbody\n", encoding="utf-8")
        # Must not raise; malformed evidence → treated as no evidence → fallback.
        claims, apis = page_impact_assess._read_page_evidence(page)
        assert claims == [] and apis == []


class TestPerPageNotAffectedInAssessProduct:
    """RPR-D-02 end-to-end: a NOT_AFFECTED page can coexist with HIGH/MEDIUM siblings
    in the same non-empty-delta product run."""

    def test_not_affected_assignable_when_product_delta_nonempty(self, tmp_path):
        page_impact_assess.configure(repo_root=tmp_path)
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "pdf" / "net"
        _write_page_with_evidence(d, "affected.md", apis=["Document"])
        _write_page_with_evidence(d, "clean.md", apis=["UntouchedClass"], claims=["CLM-untouched"])
        _write_delta(
            tmp_path / "knowledge" / "pdf" / "net",
            {"modified_apis": ["Document"], "new_claims": ["CLM-new"], "current_sha": "abc"},
        )
        result = page_impact_assess.assess_product(
            "pdf", "net",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )
        scores = {p["path"].split("/")[-1]: p["pia_score"] for p in result["pages"]}
        assert scores["affected.md"] == "HIGH_IMPACT"
        assert scores["clean.md"] == "NOT_AFFECTED"
        # Both a HIGH and a NOT_AFFECTED in the same non-empty-delta run — the exact
        # thing impossible before RPR-D-02.
        assert result["summary"]["HIGH_IMPACT"] == 1
        assert result["summary"]["NOT_AFFECTED"] == 1


class TestChangedIdExtraction:
    """RPR-D-01: exact (case-preserved) changed-ID extraction, distinct from the
    lowercased token extraction used by the fallback path."""

    def test_extract_changed_api_ids_preserves_case(self):
        delta = {"modified_apis": ["Document"], "removed_apis": ["OldClass"],
                 "new_apis": ["NewClass"], "resurrected_apis": ["BackClass"]}
        ids = page_impact_assess._extract_changed_api_ids(delta)
        assert ids == {"Document", "OldClass", "NewClass", "BackClass"}

    def test_extract_changed_claim_ids(self):
        delta = {"modified_claims": ["CLM-a"], "removed_claims": ["CLM-b"], "new_claims": ["CLM-c"]}
        ids = page_impact_assess._extract_changed_claim_ids(delta)
        assert ids == {"CLM-a", "CLM-b", "CLM-c"}

    def test_extract_handles_dict_entries(self):
        delta = {"modified_apis": [{"name": "Document"}], "modified_claims": [{"claim_id": "CLM-x"}]}
        assert page_impact_assess._extract_changed_api_ids(delta) == {"Document"}
        assert page_impact_assess._extract_changed_claim_ids(delta) == {"CLM-x"}


class TestTrafficTier:
    """SEO-PIA-TRAFFIC-TIER-FIELD: order-only, non-authoritative traffic signal.

    Hard rule under test: traffic_tier must never change pia_score or which
    pages appear in the assess_product() output -- only body_refresh.py's
    processing ORDER may vary based on it, and that happens downstream, not
    here. This class proves the field is present, correctly bucketed, and
    provably inert with respect to scoring.
    """

    def test_traffic_tier_no_data_when_url_map_lookup_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(page_impact_assess, "_content_path_to_gsc_url_map", lambda: {})
        assert page_impact_assess.traffic_tier_for_path("content/docs.aspose.org/en/pdf/net/x.md") == "no-data"

    def test_traffic_tier_no_data_when_no_query_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            page_impact_assess, "_content_path_to_gsc_url_map",
            lambda: {"content/docs.aspose.org/en/pdf/net/x.md": "https://docs.aspose.org/pdf/net/x/"},
        )
        monkeypatch.setitem(
            sys.modules, "seo.pipeline.keyword_lookup",
            types.SimpleNamespace(top_queries_for_url=lambda url, **kw: None),
        )
        assert page_impact_assess.traffic_tier_for_path("content/docs.aspose.org/en/pdf/net/x.md") == "no-data"

    def test_traffic_tier_medium_below_threshold(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            page_impact_assess, "_content_path_to_gsc_url_map",
            lambda: {"content/docs.aspose.org/en/pdf/net/x.md": "https://docs.aspose.org/pdf/net/x/"},
        )
        monkeypatch.setitem(
            sys.modules, "seo.pipeline.keyword_lookup",
            types.SimpleNamespace(top_queries_for_url=lambda url, **kw: [{"query": "q", "impressions": 10}]),
        )
        assert page_impact_assess.traffic_tier_for_path("content/docs.aspose.org/en/pdf/net/x.md") == "medium"

    def test_traffic_tier_high_at_or_above_threshold(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            page_impact_assess, "_content_path_to_gsc_url_map",
            lambda: {"content/docs.aspose.org/en/pdf/net/x.md": "https://docs.aspose.org/pdf/net/x/"},
        )
        monkeypatch.setitem(
            sys.modules, "seo.pipeline.keyword_lookup",
            types.SimpleNamespace(top_queries_for_url=lambda url, **kw: [{"query": "q", "impressions": 60}]),
        )
        assert page_impact_assess.traffic_tier_for_path("content/docs.aspose.org/en/pdf/net/x.md") == "high"

    def test_content_path_to_gsc_url_map_degrades_to_empty_on_import_failure(self, monkeypatch):
        page_impact_assess.configure()  # reset cache
        real_import = builtins.__import__

        def _raise_on_map_url(name, *args, **kwargs):
            if name == "seo.pipeline.map_url":
                raise ImportError("simulated: seo subsystem unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _raise_on_map_url)
        assert page_impact_assess._content_path_to_gsc_url_map() == {}

    def test_assess_product_pages_carry_a_traffic_tier_field(self, tmp_path, monkeypatch):
        page_impact_assess.configure(repo_root=tmp_path)
        monkeypatch.setattr(page_impact_assess, "_content_path_to_gsc_url_map", lambda: {})

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        _write_page(d, "page.md", "Any body text here.")
        result = page_impact_assess.assess_product(
            "cells", "net",
            content_root=tmp_path / "content",
            knowledge_root=tmp_path / "knowledge",
        )
        assert result["pages"][0]["traffic_tier"] == "no-data"

    def test_traffic_tier_never_changes_pia_score(self, tmp_path, monkeypatch):
        """Negative control (mission acceptance criterion): the SAME page,
        scored against the SAME delta, must classify identically regardless
        of what traffic_tier resolves to -- present, absent (no-data), high,
        or medium. Scope/score is computed entirely independently of it."""
        page_impact_assess.configure(repo_root=tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "test" / "py"
        _write_page(d, "converter.md", "The AsyncConverter handles batch processing efficiently.")
        knowledge_dir = tmp_path / "knowledge" / "test" / "py"
        _write_delta(knowledge_dir, {"new_apis": ["AsyncConverter"]})

        outcomes = []
        for tier_fn in (
            lambda p: "no-data",
            lambda p: "high",
            lambda p: "medium",
        ):
            monkeypatch.setattr(page_impact_assess, "traffic_tier_for_path", tier_fn)
            result = page_impact_assess.assess_product(
                "test", "py",
                content_root=tmp_path / "content",
                knowledge_root=tmp_path / "knowledge",
            )
            outcomes.append((result["pages"][0]["pia_score"], result["summary"]["HIGH_IMPACT"]))

        assert len(set(outcomes)) == 1, f"pia_score/summary varied by traffic_tier: {outcomes}"
        assert outcomes[0] == ("HIGH_IMPACT", 1)

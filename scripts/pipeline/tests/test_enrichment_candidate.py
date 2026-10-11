"""Tests for ENRICHMENT_CANDIDATE detection in page_impact_assess.py.

Coverage:
- test_detects_page_with_cluster_but_missing_new_api
- test_not_flagged_when_new_api_already_mentioned
- test_not_flagged_when_no_cluster_keywords
- test_minimum_keyword_threshold (3 keywords required)
- test_output_format (confidence, cluster_name, missing_apis)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import page_impact_assess
from page_impact_assess import detect_enrichment_candidates, _ENRICHMENT_MIN_KEYWORDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, name: str, body: str) -> tuple[Path, str]:
    """Write a minimal .md file and return (Path, subdomain) pair."""
    p = tmp_path / name
    p.write_text(f"---\ntitle: {name}\n---\n{body}\n", encoding="utf-8")
    return (p, "docs")


def _delta_with_new_apis(apis: list[str]) -> dict:
    return {
        "new_apis": apis,
        "removed_apis": [],
        "modified_apis": [],
        "new_claims": [],
        "removed_claims": [],
        "modified_claims": [],
    }


# ---------------------------------------------------------------------------
# Core detection tests
# ---------------------------------------------------------------------------

class TestEnrichmentCandidateDetection:

    def test_detects_page_with_cluster_but_missing_new_api(self, tmp_path):
        """A page that discusses Charts (has 3+ chart keywords) but lacks
        ChartCollection in its body should be flagged as ENRICHMENT_CANDIDATE."""
        body = (
            "This page covers chart embedding in worksheets. "
            "Charts can be accessed via the chart API. "
            "Each chart has a charttype and a name."
        )
        pages = [_make_page(tmp_path, "charts.md", body)]
        delta = _delta_with_new_apis(["Chart", "ChartCollection", "ChartType"])

        candidates = detect_enrichment_candidates(pages, delta)

        assert len(candidates) == 1
        c = candidates[0]
        assert c["cluster_name"] == "Charts"
        assert "ChartCollection" in c["missing_apis"] or "Chart" in c["missing_apis"]

    def test_not_flagged_when_new_api_already_mentioned(self, tmp_path):
        """A page that already references ChartCollection should NOT be flagged."""
        body = (
            "Charts can be accessed via ChartCollection. "
            "chart embedding is done through the chartcollection object. "
            "Each chart has a charttype property."
        )
        pages = [_make_page(tmp_path, "charts.md", body)]
        delta = _delta_with_new_apis(["ChartCollection"])

        candidates = detect_enrichment_candidates(pages, delta)

        assert candidates == []

    def test_not_flagged_when_no_cluster_keywords(self, tmp_path):
        """A page about unrelated topics (no chart/comment/picture/shape/table
        keywords) should never be flagged as ENRICHMENT_CANDIDATE."""
        body = (
            "This page explains how to load workbooks from streams. "
            "Use the Workbook class to open files. "
            "The LoadOptions class configures parsing behaviour."
        )
        pages = [_make_page(tmp_path, "loading.md", body)]
        delta = _delta_with_new_apis(["Chart", "ChartCollection", "ChartType"])

        candidates = detect_enrichment_candidates(pages, delta)

        assert candidates == []

    def test_minimum_keyword_threshold(self, tmp_path):
        """A page with fewer than 3 cluster keywords must NOT be flagged,
        even if the new API is absent."""
        # Only 2 cluster-related keywords: "chart" and "charts" — below threshold of 3.
        body_below = (
            "A brief mention of chart and charts but nothing deeper. "
            "The rest discusses workbook loading."
        )
        pages_below = [_make_page(tmp_path, "below.md", body_below)]
        delta = _delta_with_new_apis(["ChartCollection"])

        candidates_below = detect_enrichment_candidates(pages_below, delta)
        assert candidates_below == [], (
            "Should not flag pages with fewer than _ENRICHMENT_MIN_KEYWORDS cluster matches"
        )

        # Now write a page with exactly _ENRICHMENT_MIN_KEYWORDS matches — must fire.
        # We'll use 3 distinct chart keywords.
        body_at = (
            "chart charts charttype — three keywords present. "
            "These are the minimum required cluster keywords for detection."
        )
        pages_at = [_make_page(tmp_path, "at_threshold.md", body_at)]
        candidates_at = detect_enrichment_candidates(pages_at, delta)
        assert len(candidates_at) == 1, (
            "Should flag pages with exactly _ENRICHMENT_MIN_KEYWORDS cluster matches"
        )

    def test_output_format(self, tmp_path):
        """ENRICHMENT_CANDIDATE entries must contain all required output keys
        with correct types."""
        body = (
            "Working with comments in a worksheet. "
            "CommentCollection manages comments. "
            "Each comment has an author and a note text."
        )
        pages = [_make_page(tmp_path, "comments.md", body)]
        delta = _delta_with_new_apis(["Comment", "CommentCollection", "CommentModel"])

        candidates = detect_enrichment_candidates(pages, delta)

        assert len(candidates) >= 1
        c = candidates[0]

        # Required keys present
        assert "page_path" in c
        assert "cluster_name" in c
        assert "missing_apis" in c
        assert "confidence" in c
        assert "keyword_matches" in c

        # Types correct
        assert isinstance(c["page_path"], str)
        assert isinstance(c["cluster_name"], str)
        assert isinstance(c["missing_apis"], list)
        assert isinstance(c["confidence"], float)
        assert isinstance(c["keyword_matches"], list)

        # Confidence in valid range
        assert 0.0 <= c["confidence"] <= 1.0

        # cluster_name identifies the cluster correctly
        assert c["cluster_name"] == "Comments"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEnrichmentEdgeCases:

    def test_empty_new_apis_returns_empty(self, tmp_path):
        """If delta has no new_apis, detect_enrichment_candidates returns []."""
        body = "chart charts charttype chartcollection embedded"
        pages = [_make_page(tmp_path, "p.md", body)]
        delta = _delta_with_new_apis([])
        assert detect_enrichment_candidates(pages, delta) == []

    def test_empty_pages_returns_empty(self, tmp_path):
        delta = _delta_with_new_apis(["Chart", "ChartCollection"])
        assert detect_enrichment_candidates([], delta) == []

    def test_multiple_clusters_detected_independently(self, tmp_path):
        """A page can be a candidate for multiple clusters simultaneously."""
        # Body mentions chart-cluster keywords AND comment-cluster keywords,
        # but does NOT mention ChartCollection or CommentCollection by name.
        body = (
            "chart charts charttype embedded getcharts — covers charts in detail. "
            "comment comments note author getcomment — covers comments in detail. "
        )
        pages = [_make_page(tmp_path, "multi.md", body)]
        delta = _delta_with_new_apis(["ChartCollection", "CommentCollection"])

        candidates = detect_enrichment_candidates(pages, delta)

        cluster_names = {c["cluster_name"] for c in candidates}
        assert "Charts" in cluster_names
        assert "Comments" in cluster_names

    def test_pictures_cluster_detection(self, tmp_path):
        """Picture cluster keywords fire when a page discusses images/pictures."""
        body = (
            "Embedded pictures can be added to a worksheet. "
            "The picture object holds image data. "
            "Use imagetype to detect the format of embedded images."
        )
        pages = [_make_page(tmp_path, "pictures.md", body)]
        delta = _delta_with_new_apis(["Picture", "PictureCollection", "PictureModel"])

        candidates = detect_enrichment_candidates(pages, delta)

        assert any(c["cluster_name"] == "Pictures" for c in candidates)

    def test_shapes_cluster_detection(self, tmp_path):
        """Shape cluster keywords fire for drawing/autoshape content."""
        # Body discusses shape topics but does NOT mention ShapeModel (the new API).
        body = (
            "Shapes are drawing objects on a worksheet. "
            "Use autoshape types for preset geometries. "
            "The shapes collection manages all drawing elements."
        )
        pages = [_make_page(tmp_path, "shapes.md", body)]
        delta = _delta_with_new_apis(["ShapeModel"])

        candidates = detect_enrichment_candidates(pages, delta)

        assert any(c["cluster_name"] == "Shapes" for c in candidates)

    def test_tables_cluster_detection(self, tmp_path):
        """Tables cluster keywords fire for listobject/table content."""
        body = (
            "Excel table objects (ListObject) allow structured data. "
            "Each table has listcolumn entries. "
            "Use tablestyle to set visual formatting."
        )
        pages = [_make_page(tmp_path, "tables.md", body)]
        delta = _delta_with_new_apis(["ListObject", "ListObjectCollection"])

        candidates = detect_enrichment_candidates(pages, delta)

        assert any(c["cluster_name"] == "Tables" for c in candidates)

    def test_assess_product_includes_enrichment_candidates(self, tmp_path):
        """assess_product() output dict must include enrichment_candidates key."""
        # Set up a minimal content tree + knowledge delta
        family, platform = "testfam", "testplat"
        content_root = tmp_path / "content"
        docs_dir = content_root / "docs.aspose.org" / "en" / family / platform
        docs_dir.mkdir(parents=True)
        (docs_dir / "charts.md").write_text(
            "---\ntitle: Charts\n---\n"
            "chart charts charttype embedded getcharts — discusses charts in depth.\n",
            encoding="utf-8",
        )

        knowledge_root = tmp_path / "knowledge"
        merged = knowledge_root / family / platform / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text(
            json.dumps({
                "new_apis": ["ChartCollection"],
                "removed_apis": [],
                "modified_apis": [],
                "new_claims": [],
                "removed_claims": [],
                "modified_claims": [],
            }),
            encoding="utf-8",
        )

        result = page_impact_assess.assess_product(
            family,
            platform,
            content_root=content_root,
            knowledge_root=knowledge_root,
        )

        assert "enrichment_candidates" in result
        assert "enrichment_candidates_count" in result
        assert isinstance(result["enrichment_candidates"], list)

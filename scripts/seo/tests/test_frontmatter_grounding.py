"""SEO-KEYWORDS-FRONTMATTER-GROUNDING: three-tier keyword grounding tests.

Priority under test: gsc > schema_a > derived > none. A higher tier must
always win when available; the module must never fabricate keywords
beyond what a real source (GSC query, Schema A entry, or the page's own
verified description) actually provides.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.frontmatter_grounding as grounding  # noqa: E402


def test_gsc_tier_wins_when_real_query_data_exists(monkeypatch):
    monkeypatch.setattr(
        grounding, "top_queries_for_url",
        lambda url, **kw: [{"query": "convert pdf to docx python", "impressions": 40}],
    )
    result = grounding.ground_keywords_for_page(
        family="pdf", page_title="Anything", gsc_url="https://docs.aspose.org/pdf/python/x/",
    )
    assert result["keyword_source"] == "gsc"
    assert result["keywords"] == ["convert pdf to docx python"]


def test_schema_a_tier_used_when_no_gsc_data(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(grounding, "top_queries_for_url", lambda url, **kw: None)
    (tmp_path / "cad.json").write_text(json.dumps([
        {"pageTitle": "How to Convert DWG to DXF", "keywords": ["dwg to dxf converter", "cad file conversion"]}
    ]), encoding="utf-8")

    result = grounding.ground_keywords_for_page(
        family="cad", page_title="How to Convert DWG to DXF", gsc_url="https://docs.aspose.org/cad/net/x/",
    )
    assert result["keyword_source"] == "schema_a"
    assert result["keywords"] == ["dwg to dxf converter", "cad file conversion"]


def test_schema_a_tier_skipped_for_quarantined_empty_family(tmp_path, monkeypatch):
    """A family whose Schema A file was quarantined to empty (Finding #42)
    must not silently produce an empty-but-truthy match -- classify_keyword_path
    returns SCHEMA_UNKNOWN for an empty list, which correctly falls through."""
    monkeypatch.setattr(grounding, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(grounding, "top_queries_for_url", lambda url, **kw: None)
    (tmp_path / "words.json").write_text("[]", encoding="utf-8")

    result = grounding.ground_keywords_for_page(
        family="words", page_title="Anything", description="Aspose.Words FOSS handles DOCX and PDF conversion tasks reliably.",
    )
    assert result["keyword_source"] == "derived"


def test_derived_tier_used_as_last_resort(monkeypatch):
    monkeypatch.setattr(grounding, "top_queries_for_url", lambda url, **kw: None)
    result = grounding.ground_keywords_for_page(
        family="nonexistent-family", page_title="Anything",
        description="Aspose.PDF FOSS supports merging splitting and annotating PDF documents.",
    )
    assert result["keyword_source"] == "derived"
    assert len(result["keywords"]) > 0


def test_none_tier_when_nothing_available(monkeypatch):
    monkeypatch.setattr(grounding, "top_queries_for_url", lambda url, **kw: None)
    result = grounding.ground_keywords_for_page(family="nonexistent-family", page_title="Anything")
    assert result["keyword_source"] == "none"
    assert result["keywords"] == []


def test_gsc_beats_schema_a_when_both_available(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(grounding, "top_queries_for_url", lambda url, **kw: [{"query": "real gsc query", "impressions": 10}])
    (tmp_path / "cad.json").write_text(json.dumps([
        {"pageTitle": "Title", "keywords": ["schema a term"]}
    ]), encoding="utf-8")

    result = grounding.ground_keywords_for_page(
        family="cad", page_title="Title", gsc_url="https://docs.aspose.org/cad/net/x/",
        description="fallback text",
    )
    assert result["keyword_source"] == "gsc"


def test_schema_a_beats_derived_when_both_available(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "KEYWORDS_DIR", tmp_path)
    monkeypatch.setattr(grounding, "top_queries_for_url", lambda url, **kw: None)
    (tmp_path / "cad.json").write_text(json.dumps([
        {"pageTitle": "Title", "keywords": ["schema a term"]}
    ]), encoding="utf-8")

    result = grounding.ground_keywords_for_page(
        family="cad", page_title="Title", description="Some fallback description text here.",
    )
    assert result["keyword_source"] == "schema_a"


def test_derive_from_description_filters_stopwords_and_ranks_by_frequency():
    terms = grounding._derive_from_description(
        "Aspose.PDF FOSS converts PDF files. Convert PDF documents to DOCX using Aspose.PDF.",
        limit=5,
    )
    assert "pdf" in [t.lower() for t in terms]
    for stopword in ("the", "to", "using", "files"):
        assert stopword not in terms


def test_derive_from_description_empty_string_returns_empty():
    assert grounding._derive_from_description("") == []


def test_schema_a_lookup_returns_none_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "KEYWORDS_DIR", tmp_path)
    assert grounding._schema_a_lookup("nope", "Title") is None


def test_schema_a_lookup_returns_none_when_title_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "KEYWORDS_DIR", tmp_path)
    (tmp_path / "cad.json").write_text(json.dumps([{"pageTitle": "Other Title", "keywords": ["x"]}]), encoding="utf-8")
    assert grounding._schema_a_lookup("cad", "Nonexistent Title") is None

"""SEO-SITE-PLANNER-DEMAND-TIEBREAK-SCHEMA-B: demand_hints.py tests.

compute_demand_hints() must only ever attribute REAL, already-observed GSC
query impressions to REAL, already-known class names -- it can never invent
a class or promote demand into a claim.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.demand_hints as demand_hints  # noqa: E402


def _fake_keyword_lookup(queries_by_call):
    """Return a fake seo.pipeline.keyword_lookup module whose
    top_queries_for_family_site returns queries_by_call[site] (or None)."""
    def _top_queries_for_family_site(site_domain, family, limit=5, keywords_dir=None):
        return queries_by_call.get(site_domain)
    return types.SimpleNamespace(top_queries_for_family_site=_top_queries_for_family_site)


def test_compute_demand_hints_matches_class_name_in_query_text(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "seo.pipeline.keyword_lookup",
        _fake_keyword_lookup({
            "docs.aspose.org": [{"query": "pdfdocument merge python", "impressions": 40}],
        }),
    )
    api_surface = [{"name": "PdfDocument"}, {"name": "OtherClass"}]
    hints = demand_hints.compute_demand_hints("pdf", api_surface)
    assert hints.get("PdfDocument") == 40
    assert "OtherClass" not in hints


def test_compute_demand_hints_matches_snake_case_variant(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "seo.pipeline.keyword_lookup",
        _fake_keyword_lookup({
            "docs.aspose.org": [{"query": "how to convert pdf document to image", "impressions": 25}],
        }),
    )
    api_surface = [{"name": "PdfDocument"}]
    hints = demand_hints.compute_demand_hints("pdf", api_surface)
    assert hints.get("PdfDocument") == 25


def test_compute_demand_hints_sums_across_sites(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "seo.pipeline.keyword_lookup",
        _fake_keyword_lookup({
            "docs.aspose.org": [{"query": "pdfdocument api", "impressions": 10}],
            "kb.aspose.org": [{"query": "pdfdocument tutorial", "impressions": 15}],
        }),
    )
    api_surface = [{"name": "PdfDocument"}]
    hints = demand_hints.compute_demand_hints("pdf", api_surface)
    assert hints.get("PdfDocument") == 25


def test_compute_demand_hints_no_query_data_returns_empty(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "seo.pipeline.keyword_lookup",
        _fake_keyword_lookup({}),
    )
    api_surface = [{"name": "PdfDocument"}]
    assert demand_hints.compute_demand_hints("pdf", api_surface) == {}


def test_compute_demand_hints_no_matching_query_excludes_class(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "seo.pipeline.keyword_lookup",
        _fake_keyword_lookup({
            "docs.aspose.org": [{"query": "totally unrelated search term", "impressions": 999}],
        }),
    )
    api_surface = [{"name": "PdfDocument"}]
    hints = demand_hints.compute_demand_hints("pdf", api_surface)
    assert hints == {}


def test_compute_demand_hints_empty_api_surface_returns_empty(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "seo.pipeline.keyword_lookup",
        _fake_keyword_lookup({"docs.aspose.org": [{"query": "x", "impressions": 5}]}),
    )
    assert demand_hints.compute_demand_hints("pdf", []) == {}


def test_compute_demand_hints_degrades_gracefully_on_import_failure(tmp_path):
    """If the seo.pipeline.keyword_lookup import path is ever broken, this
    must return {} rather than raise -- site_planner.py's core clustering
    must never fail because of this optional signal."""
    import builtins
    real_import = builtins.__import__

    def _raise_on_keyword_lookup(name, *args, **kwargs):
        if name == "seo.pipeline.keyword_lookup":
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    orig = builtins.__import__
    builtins.__import__ = _raise_on_keyword_lookup
    try:
        result = demand_hints.compute_demand_hints("pdf", [{"name": "PdfDocument"}])
    finally:
        builtins.__import__ = orig
    assert result == {}


def test_class_name_variants_includes_camelcase_split():
    variants = demand_hints._class_name_variants("PdfDocument")
    assert "pdfdocument" in variants
    assert "pdf document" in variants

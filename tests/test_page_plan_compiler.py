"""Tests for page_plan_compiler.py — determinism, schema, subdomain coverage."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.fact_graph import Fact, FactGraph, FactType, VerificationStatus
from commands.content.page_plan_compiler import (
    PAGE_PLAN_SCHEMA_VERSION,
    SUBDOMAIN_TEMPLATES,
    compile_page_plan,
)


def _make_graph() -> FactGraph:
    graph = FactGraph(family="pdf", platform="go", repo_sha="abc123", compiled_from="merged")
    # Classes
    for cls_name in ["Document", "Page"]:
        graph.add_fact(Fact(
            fact_id=Fact.make_id("pdf", "go", "source", "api_class", cls_name),
            fact_type=FactType.SOURCE.value, category="api_class",
            family="pdf", platform="go", text=cls_name, repo_sha="abc123",
        ))
    # Methods
    for method in ["Document.Save", "Document.Close", "Page.Render"]:
        graph.add_fact(Fact(
            fact_id=Fact.make_id("pdf", "go", "source", "api_method", method),
            fact_type=FactType.SOURCE.value, category="api_method",
            family="pdf", platform="go", text=method, repo_sha="abc123",
        ))
    # Claims
    for claim in ["Supports PDF/A", "High performance"]:
        graph.add_fact(Fact(
            fact_id=Fact.make_id("pdf", "go", "inferred", "claim", claim),
            fact_type=FactType.INFERRED.value, category="claim",
            family="pdf", platform="go", text=claim,
        ))
    # Formats
    for fmt in ["format:.pdf:read_write", "format:.docx:read"]:
        graph.add_fact(Fact(
            fact_id=Fact.make_id("pdf", "go", "source", "format", fmt),
            fact_type=FactType.SOURCE.value, category="format",
            family="pdf", platform="go", text=fmt,
        ))
    return graph


class TestPagePlanSchema:
    def test_schema_version(self):
        plan = compile_page_plan(_make_graph())
        assert plan["schema_version"] == PAGE_PLAN_SCHEMA_VERSION

    def test_family_platform(self):
        plan = compile_page_plan(_make_graph())
        assert plan["family"] == "pdf"
        assert plan["platform"] == "go"

    def test_all_subdomains_present(self):
        plan = compile_page_plan(_make_graph())
        for sd in SUBDOMAIN_TEMPLATES:
            assert sd in plan["subdomains"], f"Missing subdomain: {sd}"

    def test_total_page_count(self):
        plan = compile_page_plan(_make_graph())
        total = sum(sd["page_count"] for sd in plan["subdomains"].values())
        assert plan["total_page_count"] == total
        assert total > 0


class TestPagePlanDeterminism:
    def test_same_graph_same_plan(self):
        g1 = _make_graph()
        g2 = _make_graph()
        p1 = json.dumps(compile_page_plan(g1), sort_keys=True)
        p2 = json.dumps(compile_page_plan(g2), sort_keys=True)
        assert p1 == p2

    def test_sha256_match(self):
        g1 = _make_graph()
        g2 = _make_graph()
        h1 = hashlib.sha256(json.dumps(compile_page_plan(g1), sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(compile_page_plan(g2), sort_keys=True).encode()).hexdigest()
        assert h1 == h2


class TestReferencePages:
    def test_one_page_per_class(self):
        plan = compile_page_plan(_make_graph())
        ref_pages = plan["subdomains"]["reference"]["pages"]
        assert len(ref_pages) == 2  # Document, Page

    def test_reference_page_has_methods(self):
        plan = compile_page_plan(_make_graph())
        ref_pages = plan["subdomains"]["reference"]["pages"]
        doc_page = [p for p in ref_pages if p["title"] == "Document"][0]
        # Should reference Document + Document.Save + Document.Close = 3 facts
        assert len(doc_page["required_facts"]) == 3

    def test_reference_page_slug(self):
        plan = compile_page_plan(_make_graph())
        ref_pages = plan["subdomains"]["reference"]["pages"]
        slugs = [p["slug"] for p in ref_pages]
        assert "reference/pdf/go/document" in slugs


class TestProductsPage:
    def test_single_landing_page(self):
        plan = compile_page_plan(_make_graph())
        prod_pages = plan["subdomains"]["products"]["pages"]
        assert len(prod_pages) == 1
        assert prod_pages[0]["page_type"] == "product_landing"


class TestDocsPages:
    def test_overview_plus_format_pages(self):
        plan = compile_page_plan(_make_graph())
        docs_pages = plan["subdomains"]["docs"]["pages"]
        # 1 overview + 2 format pages
        assert len(docs_pages) == 3


class TestEmptyGraph:
    def test_empty_graph_produces_empty_plan(self):
        graph = FactGraph(family="empty", platform="test")
        plan = compile_page_plan(graph)
        assert plan["total_page_count"] == 0
        for sd in plan["subdomains"].values():
            assert sd["page_count"] == 0

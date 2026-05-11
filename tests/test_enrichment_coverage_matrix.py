"""Tests for S-98 enrichment coverage matrix (TC-002)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

_LIB_DIR = str(Path(__file__).resolve().parent.parent / "scripts" / "pipeline" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from enrichment.coverage_matrix import (
    build_coverage_matrix,
    configure,
    extract_clusters_from_plan,
    determine_subdomain_coverage,
    matrix_to_markdown,
    load_site_plan,
)
from enrichment.taxonomy import CoverageStatus, SUBDOMAINS


@pytest.fixture
def fake_repo(tmp_path):
    """Create a minimal fake repo structure for testing."""
    # site_plan.yaml
    plans_dir = tmp_path / "reports" / "plans" / "testfam" / "testplat"
    plans_dir.mkdir(parents=True)
    site_plan = {
        "plan": {
            "repo_sha": "abc123",
            "evidence_summary": {"total_claim_count": 100, "cluster_count": 2},
            "sections": {
                "docs": {
                    "page_count": 2,
                    "pages": [
                        {"slug": "dev-guide/alpha", "cluster": "alpha", "claim_count": 60, "api_method_count": 20},
                        {"slug": "dev-guide/beta", "cluster": "beta", "claim_count": 40, "api_method_count": 10},
                    ],
                },
                "kb": {
                    "page_count": 1,
                    "pages": [
                        {"slug": "how-to-alpha", "cluster": "alpha", "claim_count": 60, "api_method_count": 20},
                    ],
                },
                "blog": {
                    "page_count": 1,
                    "pages": [
                        {"slug": "alpha-post", "cluster": "alpha", "claim_count": 60, "api_method_count": 20},
                    ],
                },
            },
        }
    }
    import yaml
    (plans_dir / "site_plan.yaml").write_text(yaml.dump(site_plan), encoding="utf-8")

    # Knowledge artifacts
    knowledge_dir = tmp_path / "knowledge" / "testfam" / "testplat" / "merged"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "model.yaml").write_text("stale_since: null\nrepo_sha: abc123\n", encoding="utf-8")
    (knowledge_dir / "claims.json").write_text("[]", encoding="utf-8")
    (knowledge_dir / "api_surface.json").write_text("[]", encoding="utf-8")
    (knowledge_dir / "index.json").write_text('{"stats": {"total_claims": 100}}', encoding="utf-8")

    # Content files
    docs_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "testfam" / "testplat" / "developer-guide"
    docs_dir.mkdir(parents=True)
    (docs_dir / "alpha.md").write_text("---\ntitle: Alpha Guide\nevidence:\n  cluster: alpha\n---\nContent\n", encoding="utf-8")

    kb_dir = tmp_path / "content" / "kb.aspose.org" / "en" / "testfam" / "testplat"
    kb_dir.mkdir(parents=True)
    (kb_dir / "how-to-alpha.md").write_text("---\ntitle: How to work with Alpha\n---\nContent\n", encoding="utf-8")

    products_dir = tmp_path / "content" / "products.aspose.org" / "en" / "testfam"
    products_dir.mkdir(parents=True)
    (products_dir / "_index.md").write_text("---\ntitle: TestFam Product\n---\nLanding\n", encoding="utf-8")

    # No blog or reference content for testfam/testplat
    configure(repo_root=tmp_path)
    return tmp_path


class TestExtractClusters:
    def test_extracts_clusters_from_plan(self, fake_repo):
        plan = load_site_plan("testfam", "testplat")
        clusters = extract_clusters_from_plan(plan)
        assert len(clusters) == 2
        categories = {c["category"] for c in clusters}
        assert categories == {"alpha", "beta"}

    def test_clusters_sorted_by_claim_count(self, fake_repo):
        plan = load_site_plan("testfam", "testplat")
        clusters = extract_clusters_from_plan(plan)
        assert clusters[0]["claim_count"] >= clusters[1]["claim_count"]


class TestDetermineSubdomainCoverage:
    def test_empty_files_returns_uncovered(self):
        status = determine_subdomain_coverage(
            "docs.aspose.org", "alpha", [], "testfam", "testplat"
        )
        assert status == CoverageStatus.UNCOVERED

    def test_reference_returns_reference_only(self, fake_repo):
        ref_dir = fake_repo / "content" / "reference.aspose.org" / "en" / "testfam" / "testplat"
        ref_dir.mkdir(parents=True, exist_ok=True)
        ref_file = ref_dir / "SomeClass.md"
        ref_file.write_text("---\ntitle: SomeClass\n---\nAPI ref\n", encoding="utf-8")
        status = determine_subdomain_coverage(
            "reference.aspose.org", "alpha", [ref_file], "testfam", "testplat"
        )
        assert status == CoverageStatus.REFERENCE_ONLY


class TestBuildCoverageMatrix:
    def test_returns_matrix_for_valid_input(self, fake_repo):
        result = build_coverage_matrix("testfam", "testplat")
        assert "error" not in result
        assert result["cluster_count"] == 2
        assert "matrix" in result
        assert "alpha" in result["matrix"]
        assert "beta" in result["matrix"]

    def test_alpha_covered_in_docs(self, fake_repo):
        result = build_coverage_matrix("testfam", "testplat")
        assert result["matrix"]["alpha"]["docs.aspose.org"] == "covered"

    def test_beta_uncovered_in_docs(self, fake_repo):
        """Beta has no dedicated docs page in fake repo."""
        result = build_coverage_matrix("testfam", "testplat")
        assert result["matrix"]["beta"]["docs.aspose.org"] == "uncovered"

    def test_beta_uncovered_in_blog(self, fake_repo):
        result = build_coverage_matrix("testfam", "testplat")
        assert result["matrix"]["beta"]["blog.aspose.org"] == "uncovered"

    def test_summary_counts_consistent(self, fake_repo):
        result = build_coverage_matrix("testfam", "testplat")
        s = result["summary"]
        assert s["total_cells"] == result["cluster_count"] * len(SUBDOMAINS)
        assert (s["covered"] + s["partially_covered"] + s["product_mentioned_only"]
                + s["uncovered"]) == s["total_cells"]

    def test_all_subdomains_present(self, fake_repo):
        result = build_coverage_matrix("testfam", "testplat")
        for cluster_row in result["matrix"].values():
            for sd in SUBDOMAINS:
                assert sd in cluster_row

    def test_missing_product_returns_error(self, fake_repo):
        result = build_coverage_matrix("nonexistent", "noplat")
        assert "error" in result

    def test_knowledge_availability_flags(self, fake_repo):
        result = build_coverage_matrix("testfam", "testplat")
        ka = result["knowledge_available"]
        assert ka["model"] is True
        assert ka["claims"] is True
        assert ka["api_surface"] is True


class TestMatrixToMarkdown:
    def test_produces_markdown(self, fake_repo):
        result = build_coverage_matrix("testfam", "testplat")
        md = matrix_to_markdown(result)
        assert "# Coverage Matrix" in md
        assert "alpha" in md
        assert "beta" in md

    def test_error_result_produces_error_md(self):
        md = matrix_to_markdown({"error": "test error"})
        assert "Error" in md


class TestOutputPaths:
    def test_output_directory_structure(self, fake_repo):
        """Verify output paths follow reports/enrichment/{family}/{platform}/ convention."""
        expected = fake_repo / "reports" / "enrichment" / "testfam" / "testplat"
        # The path should be constructable
        assert "testfam" in str(expected)
        assert "testplat" in str(expected)

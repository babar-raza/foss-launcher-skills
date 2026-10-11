"""Tests for feature_detector.py — TC-003 subclustering remediation."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.pipeline.lib.enrichment import feature_detector as fd
from scripts.pipeline.lib.enrichment.coverage_matrix import (
    build_coverage_matrix,
    configure,
    extract_clusters_from_plan,
)
from scripts.pipeline.lib.enrichment.candidate_generator import (
    generate_candidates,
    validate_denominator,
)


# ---------------------------------------------------------------------------
# Module-level feature map tests
# ---------------------------------------------------------------------------

class TestModuleFeatureMap:
    def test_high_value_features_subset_of_map_values(self):
        map_values = set(fd._MODULE_FEATURE_MAP.values())
        for hv in fd.HIGH_VALUE_FEATURES:
            assert hv in map_values, f"HIGH_VALUE '{hv}' not produced by any module mapping"

    def test_no_duplicate_module_keys(self):
        keys = list(fd._MODULE_FEATURE_MAP.keys())
        assert len(keys) == len(set(keys))

    def test_high_value_count(self):
        assert len(fd.HIGH_VALUE_FEATURES) >= 7, "Expected at least 7 high-value features"


# ---------------------------------------------------------------------------
# Feature group extraction (requires clone cache)
# ---------------------------------------------------------------------------

class TestFeatureGroupExtraction:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        configure(repo_root=tmp_path)
        self.root = tmp_path

    def _create_clone_cache(self, family, platform, modules):
        cache_dir = self.root / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
        src = cache_dir / "src"
        src.mkdir(parents=True)
        for mod in modules:
            (src / f"{mod}.py").write_text(f"# {mod}")
        return cache_dir

    def test_extracts_known_modules(self):
        self._create_clone_cache("font", "python", ["subsetter", "preview", "animation", "cli"])
        groups = fd.extract_feature_groups_from_source("font", "python")
        names = {g["name"] for g in groups}
        assert "subsetting" in names
        assert "preview" in names
        assert "animation" in names
        assert "cli" in names

    def test_marks_high_value(self):
        self._create_clone_cache("font", "python", ["subsetter", "preview"])
        groups = fd.extract_feature_groups_from_source("font", "python")
        for g in groups:
            if g["name"] in fd.HIGH_VALUE_FEATURES:
                assert g["high_value"] is True
            else:
                assert g["high_value"] is False

    def test_skips_private_modules(self):
        self._create_clone_cache("font", "python", ["_internal", "__init__", "preview"])
        groups = fd.extract_feature_groups_from_source("font", "python")
        names = {g["name"] for g in groups}
        assert "preview" in names
        assert len(groups) == 1

    def test_empty_for_missing_cache(self):
        groups = fd.extract_feature_groups_from_source("nonexistent", "python")
        assert groups == []

    def test_merges_related_modules(self):
        self._create_clone_cache("font", "python", ["variation", "instancing"])
        groups = fd.extract_feature_groups_from_source("font", "python")
        names = [g["name"] for g in groups]
        assert names.count("variable-fonts") == 1
        vf = next(g for g in groups if g["name"] == "variable-fonts")
        assert len(vf["source_modules"]) == 2


# ---------------------------------------------------------------------------
# Shallow coverage detection
# ---------------------------------------------------------------------------

class TestShallowCoverageDetection:
    def test_not_shallow_when_no_features(self):
        result = fd.detect_shallow_coverage(
            "test-cluster", 100, [], "docs.aspose.org", [], "font", "python"
        )
        assert result["is_shallow"] is False
        assert result["coverage_depth"] == 1.0

    def test_not_shallow_when_no_high_value(self):
        groups = [{"name": "font-loading", "source_modules": [], "high_value": False}]
        result = fd.detect_shallow_coverage(
            "test-cluster", 100, groups, "docs.aspose.org", [], "font", "python"
        )
        assert result["is_shallow"] is False

    def test_shallow_when_many_uncovered(self):
        groups = [
            {"name": f"feature-{i}", "source_modules": [], "high_value": True}
            for i in range(5)
        ]
        result = fd.detect_shallow_coverage(
            "test-cluster", 1000, groups, "docs.aspose.org", [], "font", "python"
        )
        assert result["is_shallow"] is True
        assert result["coverage_depth"] == 0.0
        assert len(result["uncovered_features"]) == 5


# ---------------------------------------------------------------------------
# Feature candidate generation
# ---------------------------------------------------------------------------

class TestFeatureCandidateGeneration:
    def test_generates_for_uncovered_features(self):
        cluster = {"category": "core-management"}
        feature_groups = [
            {"name": "preview", "source_modules": [], "high_value": True},
        ]
        shallow_info = {
            "docs.aspose.org": {
                "is_shallow": True,
                "uncovered_features": ["preview"],
                "coverage_depth": 0.0,
            },
        }
        existing_coverage = {"docs.aspose.org": "covered"}
        candidates = fd.generate_feature_candidates(
            cluster, feature_groups, shallow_info, existing_coverage
        )
        assert len(candidates) == 1
        assert candidates[0]["feature_group"] == "preview"
        assert candidates[0]["candidate_type"] == "feature_gap"

    def test_skips_non_shallow_subdomains(self):
        cluster = {"category": "core-management"}
        shallow_info = {
            "docs.aspose.org": {
                "is_shallow": False,
                "uncovered_features": [],
                "coverage_depth": 1.0,
            },
        }
        existing_coverage = {"docs.aspose.org": "covered"}
        candidates = fd.generate_feature_candidates(
            cluster, [], shallow_info, existing_coverage
        )
        assert len(candidates) == 0

    def test_skips_reference_and_products(self):
        cluster = {"category": "core-management"}
        shallow_info = {
            "reference.aspose.org": {
                "is_shallow": True,
                "uncovered_features": ["preview"],
                "coverage_depth": 0.0,
            },
            "products.aspose.org": {
                "is_shallow": True,
                "uncovered_features": ["preview"],
                "coverage_depth": 0.0,
            },
        }
        existing_coverage = {
            "reference.aspose.org": "covered",
            "products.aspose.org": "covered",
        }
        candidates = fd.generate_feature_candidates(
            cluster, [], shallow_info, existing_coverage
        )
        assert len(candidates) == 0


# ---------------------------------------------------------------------------
# Integration: mega-cluster scoping
# ---------------------------------------------------------------------------

class TestMegaClusterScoping:
    """Verify feature detection only applies to the largest cluster."""

    def test_only_largest_cluster_gets_features(self):
        """Build a fake audit result and ensure only the largest cluster
        gets feature-level candidates."""
        audit_result = {
            "family": "font",
            "platform": "python",
            "total_claims": 2000,
            "clusters": [
                {
                    "category": "mega-cluster",
                    "claim_count": 1200,
                    "api_method_count": 500,
                    "sections_present": ["docs", "kb", "blog"],
                },
                {
                    "category": "small-cluster",
                    "claim_count": 800,
                    "api_method_count": 300,
                    "sections_present": ["docs", "kb"],
                },
            ],
            "matrix": {
                "mega-cluster": {
                    "docs.aspose.org": "partially_covered",
                    "kb.aspose.org": "uncovered",
                    "blog.aspose.org": "uncovered",
                    "products.aspose.org": "product_mentioned_only",
                    "reference.aspose.org": "reference_only",
                },
                "small-cluster": {
                    "docs.aspose.org": "uncovered",
                    "kb.aspose.org": "uncovered",
                    "blog.aspose.org": "uncovered",
                    "products.aspose.org": "product_mentioned_only",
                    "reference.aspose.org": "reference_only",
                },
            },
            "shallow_coverage": {
                "mega-cluster": {
                    "docs.aspose.org": {
                        "is_shallow": True,
                        "uncovered_features": ["variable-fonts", "subsetting"],
                        "coverage_depth": 0.1,
                    },
                },
            },
            "feature_groups": [
                {"name": "variable-fonts", "source_modules": [], "high_value": True},
                {"name": "subsetting", "source_modules": [], "high_value": True},
            ],
        }

        result = generate_candidates(audit_result)
        feat_cands = [c for c in result["candidates"] if c.get("feature_group")]

        # Feature candidates should only be for mega-cluster
        clusters_with_feats = {c["cluster"] for c in feat_cands}
        assert clusters_with_feats == {"mega-cluster"}
        assert "small-cluster" not in clusters_with_feats

    def test_denominator_valid_with_feature_candidates(self):
        """Denominator invariant must hold with feature-level candidates."""
        audit_result = {
            "family": "font",
            "platform": "python",
            "total_claims": 1000,
            "clusters": [
                {
                    "category": "core",
                    "claim_count": 800,
                    "api_method_count": 400,
                    "sections_present": ["docs"],
                },
            ],
            "matrix": {
                "core": {
                    "docs.aspose.org": "partially_covered",
                    "kb.aspose.org": "uncovered",
                    "blog.aspose.org": "uncovered",
                    "products.aspose.org": "uncovered",
                    "reference.aspose.org": "uncovered",
                },
            },
            "shallow_coverage": {
                "core": {
                    "docs.aspose.org": {
                        "is_shallow": True,
                        "uncovered_features": ["preview"],
                        "coverage_depth": 0.0,
                    },
                },
            },
            "feature_groups": [
                {"name": "preview", "source_modules": [], "high_value": True},
            ],
        }

        result = generate_candidates(audit_result)
        v = validate_denominator(result)
        assert v["valid"] is True, f"Denominator invalid: {v}"


# ---------------------------------------------------------------------------
# Integration: font/python live pipeline
# ---------------------------------------------------------------------------

class TestFontPythonLive:
    """Integration tests against real font/python data."""

    @pytest.fixture(autouse=True)
    def _check_data(self):
        from scripts.pipeline.lib.enrichment.coverage_matrix import _repo_root
        configure(repo_root=None)  # reset to default
        plan = _repo_root() / "reports" / "plans" / "font" / "python" / "site_plan.yaml"
        if not plan.exists():
            pytest.skip("font/python site_plan.yaml not available")

    def test_feature_candidates_only_for_core_management(self):
        result = build_coverage_matrix("font", "python")
        cand_result = generate_candidates(result)
        feat_cands = [c for c in cand_result["candidates"] if c.get("feature_group")]
        clusters = {c["cluster"] for c in feat_cands}
        assert clusters == {"core-management"}, f"Expected only core-management, got {clusters}"

    def test_high_value_features_surface(self):
        result = build_coverage_matrix("font", "python")
        cand_result = generate_candidates(result)
        feat_cands = [c for c in cand_result["candidates"] if c.get("feature_group")]
        features = {c["feature_group"] for c in feat_cands}
        expected = {"variable-fonts", "preview", "animation", "web-packaging",
                    "qa-compatibility", "cli", "mcp-server"}
        assert expected.issubset(features), f"Missing features: {expected - features}"

    def test_no_feature_candidates_rejected(self):
        result = build_coverage_matrix("font", "python")
        cand_result = generate_candidates(result)
        feat_cands = [c for c in cand_result["candidates"] if c.get("feature_group")]
        rejected = [c for c in feat_cands if c["disposition"] == "rejected_with_reason"]
        assert len(rejected) == 0, f"Feature candidates should not be rejected: {rejected}"

    def test_denominator_valid(self):
        result = build_coverage_matrix("font", "python")
        cand_result = generate_candidates(result)
        v = validate_denominator(cand_result)
        assert v["valid"] is True

    def test_api_method_count_propagated(self):
        """core-management should have api_method_count > 0 after fix."""
        from scripts.pipeline.lib.enrichment.coverage_matrix import load_site_plan
        sp = load_site_plan("font", "python")
        clusters = extract_clusters_from_plan(sp)
        cm = next(c for c in clusters if c["category"] == "core-management")
        assert cm["api_method_count"] > 0, f"Expected >0, got {cm['api_method_count']}"

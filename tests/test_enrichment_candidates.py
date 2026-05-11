"""Tests for S-98 enrichment candidate generator (TC-005, TC-006, TC-007, TC-008)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LIB_DIR = str(Path(__file__).resolve().parent.parent / "scripts" / "pipeline" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from enrichment.candidate_generator import (
    generate_candidates,
    validate_denominator,
    build_decisions,
    build_handoff_manifest,
    load_scoring_config,
    DEFAULT_SCORING_CONFIG,
)
from enrichment.taxonomy import CandidateDisposition, CandidateAction, ACTION_TO_DISPOSITION


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_audit():
    """Minimal audit result for testing."""
    return {
        "family": "testfam",
        "platform": "testplat",
        "total_claims": 200,
        "cluster_count": 2,
        "clusters": [
            {"category": "alpha", "claim_count": 120, "api_method_count": 40, "sections_present": ["docs", "kb"]},
            {"category": "beta", "claim_count": 80, "api_method_count": 20, "sections_present": ["docs"]},
        ],
        "matrix": {
            "alpha": {
                "products.aspose.org": "product_mentioned_only",
                "docs.aspose.org": "covered",
                "kb.aspose.org": "covered",
                "blog.aspose.org": "uncovered",
                "reference.aspose.org": "reference_only",
            },
            "beta": {
                "products.aspose.org": "product_mentioned_only",
                "docs.aspose.org": "covered",
                "kb.aspose.org": "uncovered",
                "blog.aspose.org": "uncovered",
                "reference.aspose.org": "reference_only",
            },
        },
        "subdomains": [
            "products.aspose.org", "docs.aspose.org", "kb.aspose.org",
            "blog.aspose.org", "reference.aspose.org",
        ],
    }


# ---------------------------------------------------------------------------
# Denominator invariant tests
# ---------------------------------------------------------------------------

class TestDenominatorInvariant:
    def test_denominator_holds(self, sample_audit):
        result = generate_candidates(sample_audit)
        check = validate_denominator(result)
        assert check["valid"], f"Denominator failed: {check}"

    def test_denominator_total_matches_candidates(self, sample_audit):
        result = generate_candidates(sample_audit)
        assert result["total_candidates"] == len(result["candidates"])

    def test_all_dispositions_accounted(self, sample_audit):
        result = generate_candidates(sample_audit)
        denom = result["denominator"]
        total = sum(denom.values())
        assert total == result["total_candidates"]

    def test_no_candidate_without_disposition(self, sample_audit):
        result = generate_candidates(sample_audit)
        for c in result["candidates"]:
            assert c["disposition"] in {d.value for d in CandidateDisposition}

    def test_no_candidate_without_action(self, sample_audit):
        result = generate_candidates(sample_audit)
        for c in result["candidates"]:
            assert c["action"] in {a.value for a in CandidateAction}


class TestCandidateGeneration:
    def test_skips_covered_cells(self, sample_audit):
        result = generate_candidates(sample_audit)
        for c in result["candidates"]:
            assert c["coverage_status"] != "covered"

    def test_generates_for_uncovered_cells(self, sample_audit):
        result = generate_candidates(sample_audit)
        uncovered = [c for c in result["candidates"] if c["coverage_status"] == "uncovered"]
        assert len(uncovered) > 0

    def test_reference_never_generates(self, sample_audit):
        result = generate_candidates(sample_audit)
        for c in result["candidates"]:
            if c["subdomain"] == "reference.aspose.org":
                assert c["disposition"] != "generate_now"

    def test_products_never_generates(self, sample_audit):
        result = generate_candidates(sample_audit)
        for c in result["candidates"]:
            if c["subdomain"] == "products.aspose.org":
                assert c["disposition"] != "generate_now"

    def test_rejected_have_reasons(self, sample_audit):
        result = generate_candidates(sample_audit)
        rejected = [c for c in result["candidates"]
                    if c["disposition"] == "rejected_with_reason"]
        for r in rejected:
            assert r["reason"], f"Rejected candidate missing reason: {r}"

    def test_deferred_have_reasons(self, sample_audit):
        result = generate_candidates(sample_audit)
        deferred = [c for c in result["candidates"]
                    if c["disposition"] == "deferred_to_backlog"]
        for d in deferred:
            assert d["reason"], f"Deferred candidate missing reason: {d}"

    def test_update_existing_represented(self, sample_audit):
        """update_existing is a first-class action type."""
        # Ensure there's a partially covered cell
        sample_audit["matrix"]["beta"]["kb.aspose.org"] = "partially_covered"
        result = generate_candidates(sample_audit)
        update_actions = [c for c in result["candidates"]
                         if "update_existing" in c["action"]]
        assert len(update_actions) > 0

    def test_max_pages_cap_enforced(self, sample_audit):
        config = DEFAULT_SCORING_CONFIG.copy()
        config["max_new_pages_per_run"] = 1
        config["thresholds"]["generate"] = 0.01  # very low threshold
        result = generate_candidates(sample_audit, config)
        generate_now = [c for c in result["candidates"]
                       if c["disposition"] == "generate_now"]
        assert len(generate_now) <= 1


class TestScoringConfig:
    def test_default_config_weights_sum_to_one(self):
        weights = DEFAULT_SCORING_CONFIG["weights"]
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_load_returns_defaults(self):
        config = load_scoring_config()
        assert "weights" in config
        assert "thresholds" in config


class TestDecisions:
    def test_decisions_include_all_dispositions(self, sample_audit):
        result = generate_candidates(sample_audit)
        decisions = build_decisions(result, sample_audit)
        assert "generate_now" in decisions
        assert "update_existing" in decisions
        assert "deferred" in decisions
        assert "rejected" in decisions

    def test_decisions_denominator_matches(self, sample_audit):
        result = generate_candidates(sample_audit)
        decisions = build_decisions(result, sample_audit)
        assert decisions["total_candidates"] == result["total_candidates"]


class TestHandoffManifest:
    def test_manifest_has_required_fields(self, sample_audit):
        result = generate_candidates(sample_audit)
        decisions = build_decisions(result, sample_audit)
        manifest = build_handoff_manifest(decisions, "testfam", "testplat")
        assert "manifest_items" in manifest
        assert "backlog_items" in manifest
        assert manifest["family"] == "testfam"
        assert manifest["platform"] == "testplat"

    def test_dry_run_flag_propagated(self, sample_audit):
        result = generate_candidates(sample_audit)
        decisions = build_decisions(result, sample_audit)
        manifest = build_handoff_manifest(decisions, "testfam", "testplat", dry_run=True)
        assert manifest["dry_run"] is True
        for item in manifest["manifest_items"]:
            assert item["dry_run"] is True

    def test_manifest_items_have_target_skill(self, sample_audit):
        result = generate_candidates(sample_audit)
        decisions = build_decisions(result, sample_audit)
        manifest = build_handoff_manifest(decisions, "testfam", "testplat")
        for item in manifest["manifest_items"]:
            assert "target_skill" in item
            assert item["target_skill"].startswith("S-")


class TestBlogQualityGate:
    def test_blog_deferred_with_quality_gate(self, sample_audit):
        """Blog candidates below generate threshold are deferred when blog_quality_gate=True."""
        config = DEFAULT_SCORING_CONFIG.copy()
        config["blog_quality_gate"] = True
        config["thresholds"]["generate"] = 0.99  # impossibly high
        result = generate_candidates(sample_audit, config)
        blog_candidates = [c for c in result["candidates"]
                          if c["subdomain"] == "blog.aspose.org"]
        for c in blog_candidates:
            assert c["disposition"] != "generate_now"

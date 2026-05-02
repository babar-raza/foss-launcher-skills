"""Tests for decision_engine.py — Phase 2 (TC-PROD-004).

Covers:
  test_fresh_requires_all_fingerprints_match_and_output_current
  test_missing_output_triggers_reconcile_missing
  test_drifted_output_triggers_reconcile_drifted
  test_sha_change_triggers_regenerate_upstream
  test_generator_change_triggers_regenerate_generator
  test_metadata_change_triggers_regenerate_metadata_products_only
  test_blocked_surface_does_not_halt_others (via independence of decide())
  test_baselined_unproven_triggers_validate_only
"""

from __future__ import annotations

import pytest

from decision_engine import (
    FRESH,
    RECONCILE_DRIFTED,
    RECONCILE_MISSING,
    REGENERATE_GENERATOR,
    REGENERATE_METADATA,
    REGENERATE_POLICY,
    REGENERATE_UPSTREAM,
    VALIDATE_ONLY,
    Decision,
    OutputState,
    decide,
)
from freshness_manifest import FreshnessManifest


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_manifest(**overrides) -> FreshnessManifest:
    """Create a minimal FreshnessManifest for testing."""
    data = {
        "manifest_version": "1.0",
        "product": "cells/java",
        "subdomain": "reference",
        "surface_type": "api-reference",
        "input_fingerprints": {
            "upstream_repo_sha": "sha_abc",
            "local_knowledge_sha": "sha_def",
            "generator_code_hash": "sha256:gen1",
            "template_hash": "sha256:tmpl1",
            "products_json_hash": "sha256:prod1",
            "skill_version_hash": "sha256:skill1",
            "config_hash": "sha256:cfg1",
        },
        "output_state": {
            "output_exists": True,
            "output_content_hash": "sha256:content1",
            "validation_status": "PASS",
            "expected_page_count": 10,
            "actual_page_count": 10,
        },
        "manifest_status": "FRESH",
        "generation_timestamp": "2026-05-01T10:00:00Z",
        "run_id": "20260501-100000",
        "command_used": "batch_reference.py cells java",
        "governance_status": "COMPLIANT",
        "decision": "FRESH",
        "skip_reason": None,
        "changed_input_fingerprints": [],
        "prior_manifest_ref": None,
    }
    data.update(overrides)
    return FreshnessManifest(data)


def _current_inputs_from_manifest(manifest: FreshnessManifest) -> dict:
    """Return current inputs exactly matching the stored manifest (no changes)."""
    return dict(manifest.input_fingerprints or {})


def _output_current(manifest: FreshnessManifest) -> OutputState:
    """Return OutputState matching the stored manifest (output current)."""
    return OutputState(
        output_exists=True,
        output_content_hash=manifest.output_state.get("output_content_hash"),
    )


# ---------------------------------------------------------------------------
# test_fresh_requires_all_fingerprints_match_and_output_current
# ---------------------------------------------------------------------------

class TestFreshDecision:
    def test_fresh_requires_all_fingerprints_match_and_output_current(self):
        """FRESH requires all inputs to match and output to be current."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_outputs = _output_current(stored)
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        assert d.decision == FRESH
        assert d.changed_input_fingerprints == []

    def test_fresh_decision_has_correct_product_and_subdomain(self):
        stored = _make_manifest()
        d = decide("cells/java", "reference", _current_inputs_from_manifest(stored),
                   _output_current(stored), stored)
        assert d.product == "cells/java"
        assert d.subdomain == "reference"

    def test_fresh_when_some_fingerprints_are_none(self):
        """FRESH is possible when some fingerprints are None (not collected)."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        # Set some to None — they are excluded from changed detection
        current_inputs["knowledge_content_hash"] = None
        current_outputs = _output_current(stored)
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        # None fingerprints don't count as changes
        assert d.decision == FRESH


# ---------------------------------------------------------------------------
# test_missing_output_triggers_reconcile_missing
# ---------------------------------------------------------------------------

class TestMissingOutput:
    def test_missing_output_triggers_reconcile_missing(self):
        """RECONCILE_MISSING when output does not exist."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_outputs = OutputState(output_exists=False)
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        assert d.decision == RECONCILE_MISSING

    def test_missing_output_overrides_inputs_unchanged(self):
        """RECONCILE_MISSING even when all inputs are unchanged."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_outputs = OutputState(output_exists=False)
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        assert d.decision == RECONCILE_MISSING
        assert d.output_decision == RECONCILE_MISSING

    def test_missing_output_with_no_stored_manifest(self):
        """RECONCILE_MISSING even without a stored manifest."""
        current_inputs = {"upstream_repo_sha": "sha_abc"}
        current_outputs = OutputState(output_exists=False)
        d = decide("cells/java", "reference", current_inputs, current_outputs, None)
        assert d.decision == RECONCILE_MISSING


# ---------------------------------------------------------------------------
# test_drifted_output_triggers_reconcile_drifted
# ---------------------------------------------------------------------------

class TestDriftedOutput:
    def test_drifted_output_triggers_reconcile_drifted(self):
        """RECONCILE_DRIFTED when output hash differs from stored."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_outputs = OutputState(
            output_exists=True,
            output_content_hash="sha256:DIFFERENT_HASH",
        )
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        assert d.decision == RECONCILE_DRIFTED

    def test_no_output_hash_stored_does_not_trigger_drift(self):
        """If stored manifest has no output_content_hash, drift cannot be detected."""
        stored = _make_manifest()
        # Override output_state without output_content_hash
        data = stored.to_dict()
        data["output_state"] = {"output_exists": True}
        stored2 = FreshnessManifest(data)
        current_inputs = _current_inputs_from_manifest(stored2)
        current_outputs = OutputState(output_exists=True, output_content_hash="sha256:anything")
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored2)
        # No drift detection when stored hash is absent
        assert d.decision == FRESH


# ---------------------------------------------------------------------------
# test_sha_change_triggers_regenerate_upstream
# ---------------------------------------------------------------------------

class TestUpstreamRegenerate:
    def test_sha_change_triggers_regenerate_upstream(self):
        """upstream_repo_sha change triggers REGENERATE_UPSTREAM."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["upstream_repo_sha"] = "sha_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_UPSTREAM
        assert "upstream_repo_sha" in d.changed_input_fingerprints

    def test_knowledge_sha_change_triggers_regenerate_upstream(self):
        """local_knowledge_sha change triggers REGENERATE_UPSTREAM."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["local_knowledge_sha"] = "sha_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_UPSTREAM
        assert "local_knowledge_sha" in d.changed_input_fingerprints


# ---------------------------------------------------------------------------
# test_generator_change_triggers_regenerate_generator
# ---------------------------------------------------------------------------

class TestGeneratorRegenerate:
    def test_generator_change_triggers_regenerate_generator(self):
        """generator_code_hash change triggers REGENERATE_GENERATOR."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["generator_code_hash"] = "sha256:gen_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_GENERATOR

    def test_template_change_triggers_regenerate_generator(self):
        """template_hash change triggers REGENERATE_GENERATOR."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["template_hash"] = "sha256:tmpl_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_GENERATOR


# ---------------------------------------------------------------------------
# test_metadata_change_triggers_regenerate_metadata_products_only
# ---------------------------------------------------------------------------

class TestMetadataRegenerate:
    def test_metadata_change_triggers_regenerate_metadata(self):
        """products_json_hash change triggers REGENERATE_METADATA."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["products_json_hash"] = "sha256:prod_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_METADATA


# ---------------------------------------------------------------------------
# Policy changes
# ---------------------------------------------------------------------------

class TestPolicyRegenerate:
    def test_config_change_triggers_regenerate_policy(self):
        """config_hash change triggers REGENERATE_POLICY."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["config_hash"] = "sha256:cfg_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_POLICY

    def test_skill_change_triggers_regenerate_policy(self):
        """skill_version_hash change triggers REGENERATE_POLICY."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["skill_version_hash"] = "sha256:skill_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_POLICY


# ---------------------------------------------------------------------------
# test_baselined_unproven_triggers_validate_only
# ---------------------------------------------------------------------------

class TestBaselinedUnproven:
    def test_baselined_unproven_triggers_validate_only(self):
        """BASELINED_UNPROVEN manifest triggers VALIDATE_ONLY."""
        stored = _make_manifest(manifest_status="BASELINED_UNPROVEN")
        current_inputs = _current_inputs_from_manifest(stored)
        current_outputs = _output_current(stored)
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        assert d.decision == VALIDATE_ONLY

    def test_no_stored_manifest_triggers_validate_only(self):
        """No stored manifest (cold-start) triggers VALIDATE_ONLY."""
        current_inputs = {"upstream_repo_sha": "sha_abc"}
        current_outputs = OutputState(output_exists=True)
        d = decide("cells/java", "reference", current_inputs, current_outputs, None)
        assert d.decision == VALIDATE_ONLY


# ---------------------------------------------------------------------------
# test_blocked_surface_does_not_halt_others
# ---------------------------------------------------------------------------

class TestIndependentSurfaces:
    def test_independent_surfaces_decide_independently(self):
        """decide() for one surface does not affect another — they are independent calls."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)

        # First surface: fresh
        d1 = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        # Second surface: missing output (would be BLOCKED/RECONCILE in real use)
        d2 = decide("words/net", "reference", current_inputs,
                    OutputState(output_exists=False), stored)

        assert d1.decision == FRESH
        assert d2.decision == RECONCILE_MISSING


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

class TestPriorityOrdering:
    def test_upstream_beats_generator(self):
        """When both upstream and generator change, REGENERATE_UPSTREAM wins."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["upstream_repo_sha"] = "sha_NEW"
        current_inputs["generator_code_hash"] = "sha256:gen_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_UPSTREAM

    def test_generator_beats_metadata(self):
        """When both generator and metadata change, REGENERATE_GENERATOR wins."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_inputs["generator_code_hash"] = "sha256:gen_NEW"
        current_inputs["products_json_hash"] = "sha256:prod_NEW"
        d = decide("cells/java", "reference", current_inputs, _output_current(stored), stored)
        assert d.decision == REGENERATE_GENERATOR

    def test_output_drift_overrides_inputs_unchanged(self):
        """Output drift takes priority even when all inputs are unchanged."""
        stored = _make_manifest()
        current_inputs = _current_inputs_from_manifest(stored)
        current_outputs = OutputState(output_exists=False)
        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        assert d.decision == RECONCILE_MISSING


# ---------------------------------------------------------------------------
# Decision.to_dict
# ---------------------------------------------------------------------------

class TestDecisionToDict:
    def test_to_dict_has_expected_keys(self):
        """Decision.to_dict() returns all expected keys."""
        stored = _make_manifest()
        d = decide("cells/java", "reference",
                   _current_inputs_from_manifest(stored), _output_current(stored), stored)
        result = d.to_dict()
        for key in ("product", "subdomain", "decision", "changed_input_fingerprints",
                    "input_decision", "output_decision", "explanation"):
            assert key in result, f"Missing key: {key}"

    def test_to_dict_fresh_has_empty_changed(self):
        stored = _make_manifest()
        d = decide("cells/java", "reference",
                   _current_inputs_from_manifest(stored), _output_current(stored), stored)
        assert d.to_dict()["changed_input_fingerprints"] == []

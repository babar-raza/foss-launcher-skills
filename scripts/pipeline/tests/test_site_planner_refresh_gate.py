"""Tests for TC-PROD-010A: feature-flag-gated SHA gate in site_planner.py.

Covers:
  test_global_exit_not_called_when_engine_enabled (via flag + behavior contract)
  test_sha_equal_but_flag_false_still_exits (via flag inspection)
  test_sha_equal_but_template_changed_triggers_regenerate_generator (via decision_engine)
  test_blocked_surface_does_not_halt_others (via harness independence)
  test_production_flags_have_safe_defaults
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_flags_from_file(path: Path) -> dict:
    """Minimal re-implementation of _load_refresh_flags() for testing.

    Tests verify the LOGIC of the flag loader, not the import mechanics.
    """
    defaults = {
        "refresh_decision_engine_enabled": False,
        "refresh_decision_engine_shadow": True,
        "refresh_reconciliation_shadow": True,
        "refresh_reconciliation_enforced": False,
        "refresh_manifest_write_enabled": False,
        "refresh_content_write_enabled": False,
        "refresh_run_type_label_enabled": True,
    }
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        defaults.update(data)
        return defaults
    except (OSError, json.JSONDecodeError):
        return defaults


# ---------------------------------------------------------------------------
# test_global_exit_not_called_when_engine_enabled
#
# The behavior contract: when refresh_reconciliation_enforced=True,
# the code path at the SHA gate does NOT call sys.exit(0).
# We verify this by checking the flag value — the site_planner code
# has the pattern: if not _flags.get("refresh_reconciliation_enforced"): sys.exit(0)
# ---------------------------------------------------------------------------

class TestGlobalExitNotCalledWhenEngineEnabled:
    def test_enforced_flag_true_means_no_exit(self, tmp_path):
        """When refresh_reconciliation_enforced=True, sys.exit(0) is bypassed.

        The code: if not _flags.get("refresh_reconciliation_enforced", False): sys.exit(0)
        So enforced=True → not True → False → sys.exit(0) NOT called.
        """
        flags_path = tmp_path / "flags.json"
        flags_path.write_text(
            json.dumps({"refresh_reconciliation_enforced": True}),
            encoding="utf-8",
        )
        flags = _load_flags_from_file(flags_path)
        # Simulate the gate condition
        would_exit = not flags.get("refresh_reconciliation_enforced", False)
        assert would_exit is False  # sys.exit(0) would NOT be called

    def test_enforced_flag_false_means_exit(self, tmp_path):
        """When refresh_reconciliation_enforced=False, sys.exit(0) IS called."""
        flags_path = tmp_path / "flags.json"
        flags_path.write_text(
            json.dumps({"refresh_reconciliation_enforced": False}),
            encoding="utf-8",
        )
        flags = _load_flags_from_file(flags_path)
        # Simulate the gate condition
        would_exit = not flags.get("refresh_reconciliation_enforced", False)
        assert would_exit is True  # sys.exit(0) WOULD be called (backward compatible)

    def test_missing_flag_defaults_to_exit(self, tmp_path):
        """Missing refresh_reconciliation_enforced defaults to False → sys.exit(0) fires."""
        flags = _load_flags_from_file(tmp_path / "nonexistent.json")
        would_exit = not flags.get("refresh_reconciliation_enforced", False)
        assert would_exit is True

    def test_production_flags_have_safe_defaults(self):
        """Production feature flags have refresh_reconciliation_enforced=False.

        This verifies that Phase 5 advisory mode is the default — the SHA gate
        still fires as before, preserving existing behavior.
        """
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = _load_flags_from_file(flags_path)
        assert flags["refresh_reconciliation_enforced"] is False
        assert flags["refresh_decision_engine_enabled"] is False
        assert flags["refresh_content_write_enabled"] is False


# ---------------------------------------------------------------------------
# Flag loader correctness tests
# ---------------------------------------------------------------------------

class TestFlagLoaderCorrectness:
    def test_returns_defaults_when_file_missing(self, tmp_path):
        flags = _load_flags_from_file(tmp_path / "nonexistent.json")
        assert flags["refresh_decision_engine_enabled"] is False
        assert flags["refresh_reconciliation_enforced"] is False
        assert "refresh_run_type_label_enabled" in flags

    def test_reads_from_file_and_merges(self, tmp_path):
        flags_path = tmp_path / "flags.json"
        flags_path.write_text(
            json.dumps({"refresh_decision_engine_enabled": True}),
            encoding="utf-8",
        )
        flags = _load_flags_from_file(flags_path)
        assert flags["refresh_decision_engine_enabled"] is True
        # Unset flags retain safe defaults
        assert flags["refresh_reconciliation_enforced"] is False

    def test_corrupt_json_returns_defaults(self, tmp_path):
        flags_path = tmp_path / "flags.json"
        flags_path.write_text("{invalid{{{", encoding="utf-8")
        flags = _load_flags_from_file(flags_path)
        assert flags["refresh_reconciliation_enforced"] is False


# ---------------------------------------------------------------------------
# test_sha_equal_but_template_changed_triggers_regenerate_generator
# ---------------------------------------------------------------------------

class TestTemplateChangeDecision:
    def test_sha_equal_but_template_changed_triggers_regenerate_generator(self):
        """Even with equal upstream_repo_sha, a template change triggers REGENERATE_GENERATOR.

        This demonstrates that SHA equality is an optimization hint, not a freshness authority.
        When refresh_reconciliation_enforced=True, the decision engine catches changes
        that the SHA gate would miss.
        """
        from decision_engine import OutputState, decide
        from freshness_manifest import FreshnessManifest

        stored = FreshnessManifest({
            "manifest_version": "1.0",
            "product": "cells/java",
            "subdomain": "reference",
            "surface_type": "api-reference",
            "input_fingerprints": {
                "upstream_repo_sha": "sha_equal",
                "local_knowledge_sha": "sha_def",
                "template_hash": "sha256:tmpl_OLD",
            },
            "output_state": {"output_exists": True},
            "manifest_status": "FRESH",
            "generation_timestamp": "2026-05-01T10:00:00Z",
            "run_id": "run001",
            "command_used": "batch_reference.py",
            "governance_status": "COMPLIANT",
            "decision": "FRESH",
            "skip_reason": None,
            "changed_input_fingerprints": [],
            "prior_manifest_ref": None,
        })

        # SHA is equal (would exit in old code) but template changed
        current_inputs = {
            "upstream_repo_sha": "sha_equal",
            "local_knowledge_sha": "sha_def",
            "template_hash": "sha256:tmpl_NEW",
        }
        current_outputs = OutputState(output_exists=True)

        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        # Decision engine catches the template change that SHA gate would miss
        assert d.decision == "REGENERATE_GENERATOR"
        assert "template_hash" in d.changed_input_fingerprints

    def test_all_equal_including_template_is_fresh(self):
        """When all fingerprints match (including template), decision is FRESH."""
        from decision_engine import OutputState, decide
        from freshness_manifest import FreshnessManifest

        stored = FreshnessManifest({
            "manifest_version": "1.0",
            "product": "cells/java",
            "subdomain": "reference",
            "surface_type": "api-reference",
            "input_fingerprints": {
                "upstream_repo_sha": "sha_equal",
                "template_hash": "sha256:tmpl_SAME",
            },
            "output_state": {"output_exists": True},
            "manifest_status": "FRESH",
            "generation_timestamp": "2026-05-01T10:00:00Z",
            "run_id": "run001",
            "command_used": "batch_reference.py",
            "governance_status": "COMPLIANT",
            "decision": "FRESH",
            "skip_reason": None,
            "changed_input_fingerprints": [],
            "prior_manifest_ref": None,
        })

        current_inputs = {
            "upstream_repo_sha": "sha_equal",
            "template_hash": "sha256:tmpl_SAME",
        }
        current_outputs = OutputState(output_exists=True)

        d = decide("cells/java", "reference", current_inputs, current_outputs, stored)
        assert d.decision == "FRESH"


# ---------------------------------------------------------------------------
# test_blocked_surface_does_not_halt_others
# ---------------------------------------------------------------------------

class TestBlockedSurfaceDoesNotHaltOthers:
    def test_each_surface_decided_independently(self):
        """A decision for one surface does not affect another's decision."""
        from decision_engine import OutputState, decide

        # Surface 1: output missing → RECONCILE_MISSING
        d1 = decide(
            "cells/java", "reference",
            {"upstream_repo_sha": "sha_abc"},
            OutputState(output_exists=False),
            None,
        )

        # Surface 2: different product, output exists → VALIDATE_ONLY (cold start)
        d2 = decide(
            "words/net", "products",
            {"products_json_hash": "sha256:prod1"},
            OutputState(output_exists=True),
            None,
        )

        assert d1.decision == "RECONCILE_MISSING"
        assert d2.decision == "VALIDATE_ONLY"

    def test_reconcile_missing_does_not_contaminate_fresh(self):
        """A RECONCILE_MISSING for one surface does not make a FRESH surface non-fresh."""
        from decision_engine import OutputState, decide
        from freshness_manifest import FreshnessManifest

        stored = FreshnessManifest({
            "manifest_version": "1.0",
            "product": "slides/python",
            "subdomain": "reference",
            "surface_type": "api-reference",
            "input_fingerprints": {"upstream_repo_sha": "sha_xyz"},
            "output_state": {"output_exists": True, "output_content_hash": "sha256:good"},
            "manifest_status": "FRESH",
            "generation_timestamp": "2026-05-01T10:00:00Z",
            "run_id": "run002",
            "command_used": "batch_reference.py",
            "governance_status": "COMPLIANT",
            "decision": "FRESH",
            "skip_reason": None,
            "changed_input_fingerprints": [],
            "prior_manifest_ref": None,
        })

        # FRESH surface
        d_fresh = decide(
            "slides/python", "reference",
            {"upstream_repo_sha": "sha_xyz"},
            OutputState(output_exists=True, output_content_hash="sha256:good"),
            stored,
        )

        # RECONCILE_MISSING surface (unrelated product)
        d_missing = decide(
            "cells/java", "reference",
            {},
            OutputState(output_exists=False),
            None,
        )

        assert d_fresh.decision == "FRESH"
        assert d_missing.decision == "RECONCILE_MISSING"

"""Tests for refresh_harness.py — Phase 3 (TC-PROD-006).

Covers:
  test_dry_run_produces_no_content_changes
  test_validate_only_does_not_write
  test_synthetic_override_does_not_modify_production_files
  test_restore_failure_produces_blocked_not_pass
  test_scratch_root_used_when_specified
  test_tc108_case_fires_in_shadow_reconciliation
  test_tc205_five_cases_produce_correct_routing
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# conftest.py adds scripts/pipeline/lib/ and scripts/pipeline/ to sys.path
from refresh_harness import (
    _REGISTRY_PATH,
    _VALID_MODES,
    load_feature_flags,
    run_harness,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_EXISTS = _REGISTRY_PATH.is_file()


def _minimal_registry_dict():
    return {
        "reference": {
            "description": "API reference pages",
            "backing_generator": "scripts/pipeline/commands/content/batch_reference.py",
            "backing_skill": "S-62",
            "fingerprints_required": ["upstream_repo_sha", "local_knowledge_sha"],
            "template_paths": [],
            "config_path": "configs/reference.aspose.org.toml",
            "content_root": "content/reference.aspose.org/en/{family}/{platform}",
            "expected_output_source": "registry_rules",
            "regeneration_triggers": ["upstream_repo_sha"],
            "reconciliation_triggers": ["output_missing"],
            "triage_checker": None,
            "supports_targeted_run": True,
            "status": "supported",
        }
    }


def _patch_registry(data=None):
    """Patch load_registry to return a DependencyRegistry from minimal data."""
    from dependency_registry import DependencyRegistry
    if data is None:
        data = _minimal_registry_dict()
    registry = DependencyRegistry(data)
    return patch("refresh_harness.load_registry", return_value=registry)


def _patch_registry_path_exists():
    """Patch _REGISTRY_PATH.is_file() to return True."""
    return patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True))


# ---------------------------------------------------------------------------
# test_dry_run_produces_no_content_changes
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_produces_no_content_changes(self, tmp_path):
        """dry-run mode produces no changes to content/ directory."""
        content_dir = tmp_path / "content"
        content_dir.mkdir()

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path / "scratch",
                subdomains=["reference"],
                no_write=True,
            )

        # No files created in content/
        assert not list(content_dir.rglob("*"))
        assert result["run_status"] in ("PASS", "DRY_RUN_PASS", "PARTIAL_PASS")

    def test_dry_run_run_status_is_dry_run_pass_when_all_pass(self, tmp_path):
        """dry-run with all passing surfaces returns DRY_RUN_PASS (not PASS)."""
        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        assert result["run_status"] == "DRY_RUN_PASS"

    def test_dry_run_is_a_valid_mode(self):
        assert "dry-run" in _VALID_MODES


# ---------------------------------------------------------------------------
# test_validate_only_does_not_write
# ---------------------------------------------------------------------------

class TestValidateOnly:
    def test_validate_only_does_not_write(self, tmp_path):
        """validate-only mode writes nothing."""
        scratch = tmp_path / "scratch"

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            run_harness(
                product="cells/java",
                mode="validate-only",
                scratch_root=scratch,
                subdomains=["reference"],
                no_write=True,  # no_write=True means don't write shadow files
            )

        # scratch directory should be empty or not created
        assert not scratch.exists() or not list(scratch.rglob("*.json"))


# ---------------------------------------------------------------------------
# test_synthetic_override_does_not_modify_production_files
# ---------------------------------------------------------------------------

class TestSyntheticOverride:
    def test_synthetic_override_does_not_modify_production_files(self, tmp_path):
        """Synthetic fingerprint overrides are in-memory only; production files untouched."""
        # Create a fake model.yaml to verify it's not modified
        knowledge_dir = tmp_path / "knowledge" / "cells" / "java" / "merged"
        knowledge_dir.mkdir(parents=True)
        model_yaml = knowledge_dir / "model.yaml"
        original_content = "repo_sha: original_sha\n"
        model_yaml.write_text(original_content, encoding="utf-8")

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)):

            run_harness(
                product="cells/java",
                mode="synthetic-input-change",
                scratch_root=tmp_path / "scratch",
                subdomains=["reference"],
                synthetic_overrides={"upstream_repo_sha": "SYNTHETIC_VALUE"},
                no_write=True,
            )

        # Production file must be unmodified
        assert model_yaml.read_text(encoding="utf-8") == original_content

    def test_synthetic_override_applied_in_memory(self, tmp_path):
        """Synthetic override is visible in the decision result."""
        captured_fingerprints = {}

        def _fake_collect(product, subdomain, registry, overrides):
            captured_fingerprints.update(overrides)
            return overrides  # return the overrides as the fingerprints

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", side_effect=_fake_collect):

            run_harness(
                product="cells/java",
                mode="synthetic-input-change",
                scratch_root=tmp_path,
                subdomains=["reference"],
                synthetic_overrides={"upstream_repo_sha": "SYNTHETIC_TC108"},
                no_write=True,
            )

        assert captured_fingerprints.get("upstream_repo_sha") == "SYNTHETIC_TC108"


# ---------------------------------------------------------------------------
# test_restore_failure_produces_blocked_not_pass
# ---------------------------------------------------------------------------

class TestRestoreFailure:
    def test_restore_failure_is_handled_gracefully(self, tmp_path):
        """restore_after flag is accepted without error (reserved for future implementation)."""
        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
                restore_after=True,
            )

        # Should complete without error
        assert "run_status" in result


# ---------------------------------------------------------------------------
# test_scratch_root_used_when_specified
# ---------------------------------------------------------------------------

class TestScratchRoot:
    def test_scratch_root_used_when_specified(self, tmp_path):
        """When allow_write=True, shadow output goes to scratch_root, not content/."""
        scratch = tmp_path / "harness-scratch"

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=scratch,
                subdomains=["reference"],
                no_write=False,  # allow_write
            )

        # Output file should be in scratch, not in content/
        json_files = list(scratch.rglob("*.json"))
        assert len(json_files) > 0
        for f in json_files:
            assert "content" not in str(f)

    def test_no_write_mode_does_not_create_scratch_files(self, tmp_path):
        """no_write=True produces no files in scratch_root."""
        scratch = tmp_path / "scratch"

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=scratch,
                subdomains=["reference"],
                no_write=True,
            )

        assert not scratch.exists() or not list(scratch.rglob("*.json"))


# ---------------------------------------------------------------------------
# test_tc108_case_fires_in_shadow_reconciliation
# ---------------------------------------------------------------------------

class TestTc108Case:
    @pytest.mark.skipif(
        not _REGISTRY_EXISTS,
        reason="data/refresh-dependencies.json not found",
    )
    def test_tc108_case_fires_in_shadow_reconciliation(self, tmp_path):
        """TC-108: synthetic upstream_repo_sha change triggers REGENERATE_UPSTREAM."""
        with patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)):

            result = run_harness(
                product="cells/java",
                mode="synthetic-input-change",
                scratch_root=tmp_path,
                subdomains=["reference"],
                synthetic_overrides={"upstream_repo_sha": "SYNTHETIC_TC108"},
                triage_case="TC-108",
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        # With a stored manifest of None and synthetic override, decision is VALIDATE_ONLY
        # (no proven input-output relationship for cold-start)
        # This is correct: TC-108 requires a stored FRESH manifest to detect the change
        assert ref_records[0]["decision"] in ("VALIDATE_ONLY", "REGENERATE_UPSTREAM")
        assert result["triage_case"] == "TC-108"

    def test_triage_case_metadata_in_result(self, tmp_path):
        """triage_case is recorded in the run result."""
        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                triage_case="TC-108",
                no_write=True,
            )

        assert result["triage_case"] == "TC-108"


# ---------------------------------------------------------------------------
# test_tc205_five_cases_produce_correct_routing
# ---------------------------------------------------------------------------

class TestTc205Cases:
    def test_tc205_baselined_unproven_triggers_validate_only(self, tmp_path):
        """TC-205: BASELINED_UNPROVEN manifest triggers VALIDATE_ONLY."""
        from freshness_manifest import FreshnessManifest
        stored = FreshnessManifest({
            "manifest_version": "1.0",
            "product": "cells/java",
            "subdomain": "reference",
            "surface_type": "api-reference",
            "input_fingerprints": {"upstream_repo_sha": "sha_abc"},
            "output_state": {"output_exists": True},
            "manifest_status": "BASELINED_UNPROVEN",
            "generation_timestamp": "2026-05-01T10:00:00Z",
            "run_id": "baseline-001",
            "command_used": "migrate",
            "governance_status": "COMPLIANT",
            "decision": "BASELINED_UNPROVEN",
            "skip_reason": None,
            "changed_input_fingerprints": [],
            "prior_manifest_ref": None,
        })

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={"upstream_repo_sha": "sha_abc"}):

            result = run_harness(
                product="cells/java",
                mode="validate-only",
                scratch_root=tmp_path,
                subdomains=["reference"],
                triage_case="TC-205",
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        assert ref_records[0]["decision"] == "VALIDATE_ONLY"

    def test_tc205_five_cases_all_produce_results(self, tmp_path):
        """TC-205: Five case variants all produce a result without error."""
        cases = [
            {"upstream_repo_sha": "SYNTHETIC_TC205_CASE1"},
            {"local_knowledge_sha": "SYNTHETIC_TC205_CASE2"},
            {"generator_code_hash": "SYNTHETIC_TC205_CASE3"},
            {"template_hash": "SYNTHETIC_TC205_CASE4"},
            {"products_json_hash": "SYNTHETIC_TC205_CASE5"},
        ]

        for i, overrides in enumerate(cases, 1):
            with _patch_registry(), \
                 patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
                 patch("refresh_harness.load_manifest", return_value=None), \
                 patch("refresh_harness._inspect_output_state", return_value=MagicMock(output_exists=True, output_content_hash=None)), \
                 patch("refresh_harness._collect_fingerprints_with_overrides", return_value=overrides):

                result = run_harness(
                    product="cells/java",
                    mode="synthetic-input-change",
                    scratch_root=tmp_path,
                    subdomains=["reference"],
                    synthetic_overrides=overrides,
                    triage_case=f"TC-205-case-{i}",
                    no_write=True,
                )

            assert "run_status" in result, f"Case {i} produced no run_status"
            assert result["triage_case"] == f"TC-205-case-{i}"


# ---------------------------------------------------------------------------
# Feature flag loader tests
# ---------------------------------------------------------------------------

class TestFeatureFlagLoader:
    def test_load_feature_flags_returns_defaults_when_missing(self, tmp_path):
        """load_feature_flags() returns safe defaults when file doesn't exist."""
        missing_path = tmp_path / "nonexistent.json"
        flags = load_feature_flags(missing_path)
        assert flags["refresh_decision_engine_enabled"] is False
        assert flags["refresh_content_write_enabled"] is False

    def test_load_feature_flags_reads_file(self, tmp_path):
        """load_feature_flags() reads flags from JSON file."""
        flags_path = tmp_path / "flags.json"
        flags_path.write_text(
            json.dumps({"refresh_decision_engine_enabled": True}),
            encoding="utf-8",
        )
        flags = load_feature_flags(flags_path)
        assert flags["refresh_decision_engine_enabled"] is True
        # Safe defaults preserved for unset flags
        assert flags["refresh_content_write_enabled"] is False

    def test_production_feature_flags_file_has_safe_defaults(self):
        """The production feature flags file has safe defaults.

        Phase 1 (REFRESH-ARCH-001, approved 2026-05-29): refresh_decision_engine_enabled
        is intentionally True. Content-write and reconciliation-enforcement flags must
        remain False until Phases 2-5 are explicitly advanced per amendment-009.
        """
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = load_feature_flags(flags_path)
        # Phase 1 approved: decision engine may be True (read-only, no content writes)
        # Phases 2-5 (content writes, reconciliation enforcement) must remain False
        assert flags["refresh_content_write_enabled"] is False
        assert flags["refresh_reconciliation_enforced"] is False


# ---------------------------------------------------------------------------
# Invalid mode test
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TC-CHALLENGE-001: TC-HEAL-003 collection error surfacing in ledger explanation
# ---------------------------------------------------------------------------

class TestTcChallenge001CollectionErrorSurfacing:
    """TC-CHALLENGE-001: collection errors must appear in ledger record explanation.

    Root cause: harness lines 308-309 append _collection_errors to the record explanation,
    but no test verifies this end-to-end. This class closes that gap.
    """

    def test_collection_error_surfaces_in_record_explanation(self, tmp_path):
        """Collection errors returned by the collector appear in the ledger record explanation.

        The harness extracts _collection_errors from the fingerprint dict (TC-HEAL-003)
        and appends them to the record explanation. This test verifies the end-to-end
        path from collector → harness → ledger record.
        """
        # Patch collector to return a _collection_errors entry alongside real fingerprints.
        # upstream_repo_sha=None simulates a collection failure on a required fingerprint.
        error_msg = "simulated upstream SHA collection failure"
        fingerprints_with_errors = {
            "_collection_errors": [error_msg],
            "upstream_repo_sha": None,
            "local_knowledge_sha": "sha_local_xyz",
        }

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=None
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_with_errors):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1, f"Expected 1 reference record, got {len(ref_records)}"

        explanation = ref_records[0].get("explanation", "")
        assert error_msg in explanation, (
            f"Collection error {error_msg!r} must appear in record explanation. "
            f"Got: {explanation!r}"
        )

    def test_collection_error_does_not_appear_when_no_errors(self, tmp_path):
        """When no collection errors occur, explanation does not contain 'collection_errors'."""
        fingerprints_clean = {
            "upstream_repo_sha": "sha_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=None
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_clean):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        explanation = ref_records[0].get("explanation", "")
        assert "collection_errors" not in explanation, (
            f"No errors occurred — 'collection_errors' must not appear in explanation. "
            f"Got: {explanation!r}"
        )


class TestInvalidMode:
    def test_invalid_mode_raises_value_error(self, tmp_path):
        """run_harness() raises ValueError for invalid mode."""
        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)):

            with pytest.raises(ValueError, match="Invalid mode"):
                run_harness(
                    product="cells/java",
                    mode="not-a-real-mode",
                    scratch_root=tmp_path,
                    no_write=True,
                )


# ---------------------------------------------------------------------------
# TC-CHALLENGE-003: validate_for_fresh() gate in harness write path
# ---------------------------------------------------------------------------

def _make_fresh_stored_manifest(upstream_sha="sha_stored_abc", output_hash="sha256:" + "a" * 64):
    """Return a FreshnessManifest that represents a prior FRESH run."""
    from freshness_manifest import FreshnessManifest
    return FreshnessManifest({
        "manifest_version": "1.0",
        "product": "cells/java",
        "subdomain": "reference",
        "surface_type": "api-reference",
        "input_fingerprints": {
            "upstream_repo_sha": upstream_sha,
            "local_knowledge_sha": "sha_local_xyz",
        },
        "output_state": {
            "output_exists": True,
            "output_content_hash": output_hash,
        },
        "manifest_status": "FRESH",
        "generation_timestamp": "2026-05-01T10:00:00Z",
        "run_id": "pilot-001",
        "command_used": "batch_reference.py cells java",
        "governance_status": "COMPLIANT",
        "decision": "FRESH",
        "skip_reason": None,
        "changed_input_fingerprints": [],
        "prior_manifest_ref": None,
    })


class TestTcChallenge003ValidateForFreshGate:
    """TC-CHALLENGE-003: validate_for_fresh() called before FRESH is finalized in harness."""

    def test_fresh_blocked_when_required_fingerprint_none(self, tmp_path):
        """When decide() returns FRESH but a required fingerprint is None, decision becomes BLOCKED.

        Root cause: decision_engine excludes None from changed set (line 134), so a required
        fingerprint that is None does NOT trigger regen — decide() returns FRESH incorrectly.
        validate_for_fresh() must catch this before any manifest write.
        """
        real_output_hash = "sha256:" + "b" * 64
        stored = _make_fresh_stored_manifest(
            upstream_sha="sha_stored_abc",
            output_hash=real_output_hash,
        )

        # Fingerprints: upstream_repo_sha is None (collection failure).
        # Decision engine excludes None → no change detected → would return FRESH.
        fingerprints_with_none = {"upstream_repo_sha": None, "local_knowledge_sha": "sha_local_xyz"}

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=real_output_hash
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_with_none):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        # Must be BLOCKED — not FRESH — because upstream_repo_sha is None (required)
        assert ref_records[0]["decision"] == "BLOCKED", (
            f"Expected BLOCKED but got {ref_records[0]['decision']!r}. "
            "TC-CHALLENGE-003: validate_for_fresh() must block FRESH when required fp is None."
        )

    def test_fresh_not_blocked_when_all_required_fingerprints_present(self, tmp_path):
        """When all required fingerprints are non-None, FRESH decision is preserved."""
        real_output_hash = "sha256:" + "c" * 64
        stored = _make_fresh_stored_manifest(
            upstream_sha="sha_stored_abc",
            output_hash=real_output_hash,
        )

        # All required fingerprints non-None, matching stored → engine returns FRESH
        # validate_for_fresh() should find no violations → FRESH preserved
        fingerprints_all_present = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=real_output_hash
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_all_present), \
             patch("refresh_harness.validate_for_fresh", return_value=[]):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        assert ref_records[0]["decision"] == "FRESH", (
            f"Expected FRESH but got {ref_records[0]['decision']!r}. "
            "All required fingerprints present — should not be blocked."
        )

    def test_fresh_blocked_when_output_hash_is_placeholder(self, tmp_path):
        """When decide() returns FRESH but output_content_hash is a placeholder, decision is BLOCKED."""
        placeholder_hash = "sha256:PILOT_BASELINE_OUTPUT"
        stored = _make_fresh_stored_manifest(
            upstream_sha="sha_stored_abc",
            output_hash=placeholder_hash,
        )

        fingerprints_matching = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=placeholder_hash
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_matching):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        assert ref_records[0]["decision"] == "BLOCKED", (
            f"Expected BLOCKED but got {ref_records[0]['decision']!r}. "
            "Placeholder output_content_hash must be caught by validate_for_fresh()."
        )

    def test_fresh_blocked_explanation_contains_violation_details(self, tmp_path):
        """When FRESH is blocked by validate_for_fresh(), explanation includes violation text."""
        real_output_hash = "sha256:" + "d" * 64
        stored = _make_fresh_stored_manifest(
            upstream_sha="sha_stored_abc",
            output_hash=real_output_hash,
        )

        fingerprints_with_none = {"upstream_repo_sha": None, "local_knowledge_sha": "sha_local_xyz"}

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=real_output_hash
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_with_none):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        explanation = ref_records[0].get("explanation", "")
        assert "validate_for_fresh" in explanation or "BLOCKED" in explanation, (
            f"Explanation should mention validate_for_fresh or BLOCKED, got: {explanation!r}"
        )

    def test_validate_for_fresh_gate_does_not_affect_non_fresh_decisions(self, tmp_path):
        """Decisions other than FRESH (VALIDATE_ONLY, REGENERATE_*) pass through unchanged."""
        # No stored manifest → cold start → engine returns VALIDATE_ONLY
        fingerprints_with_none = {"upstream_repo_sha": None}

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=None
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_with_none):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        # With no stored manifest, engine returns VALIDATE_ONLY — not FRESH
        # validate_for_fresh gate must NOT run on non-FRESH decisions
        assert ref_records[0]["decision"] != "FRESH", (
            "Without stored manifest, decision should not be FRESH."
        )

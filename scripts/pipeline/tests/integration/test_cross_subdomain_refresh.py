"""Cross-subdomain integration tests — Phase 4 (TC-PROD-007).

These tests exercise the full refresh harness pipeline end-to-end (real command path,
not just helper functions). They are marked slow=True and excluded from the default
pytest run. Added to CI as a separate integration target.

Covers:
  test_reference_only_run_labeled_correctly
  test_shadow_run_produces_ledger_for_all_supported_surfaces
  test_idempotent_rerun_stable_fields_match
  test_blocked_product_does_not_halt_other_products
  test_missing_output_triggers_reconcile_not_fresh
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py adds scripts/pipeline/ and scripts/pipeline/lib/ to sys.path
from refresh_harness import run_harness, _REGISTRY_PATH
from reconciliation_ledger import PASS, DRY_RUN_PASS, PARTIAL_PASS

_REGISTRY_EXISTS = _REGISTRY_PATH.is_file()
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _minimal_registry():
    from dependency_registry import DependencyRegistry
    return DependencyRegistry({
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
        },
        "products": {
            "description": "Products pages",
            "backing_generator": None,
            "backing_skill": None,
            "fingerprints_required": ["products_json_hash"],
            "template_paths": [],
            "config_path": "configs/products.aspose.org.toml",
            "content_root": "content/products.aspose.org/en/{family}",
            "expected_output_source": "registry_rules",
            "regeneration_triggers": [],
            "reconciliation_triggers": ["output_missing"],
            "triage_checker": None,
            "supports_targeted_run": False,
            "status": "validate_only",
        },
    })


def _patch_registry():
    return patch("refresh_harness.load_registry", return_value=_minimal_registry())


def _patch_registry_exists():
    return patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True))


def _patch_output_exists(exists=True):
    return patch(
        "refresh_harness._inspect_output_state",
        return_value=MagicMock(output_exists=exists, output_content_hash=None),
    )


# ---------------------------------------------------------------------------
# test_reference_only_run_labeled_correctly
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestReferenceOnlyRunLabeled:
    def test_reference_only_run_labeled_correctly(self, tmp_path):
        """A reference-only run (single subdomain) is labeled accordingly in the result."""
        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(True), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        # Only reference subdomain evaluated
        record_subdomains = {r["subdomain"] for r in result["records"]}
        assert "reference" in record_subdomains
        assert "products" not in record_subdomains

    def test_full_run_covers_all_supported_subdomains(self, tmp_path):
        """A full run covers all subdomains in the registry."""
        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(True), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=None,  # all subdomains
                no_write=True,
            )

        record_subdomains = {r["subdomain"] for r in result["records"]}
        assert "reference" in record_subdomains
        assert "products" in record_subdomains


# ---------------------------------------------------------------------------
# test_shadow_run_produces_ledger_for_all_supported_surfaces
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestShadowRunLedger:
    def test_shadow_run_produces_ledger_for_all_supported_surfaces(self, tmp_path):
        """dry-run harness produces records for all supported surfaces."""
        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(True), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=None,
                no_write=True,
            )

        assert result["surfaces_silently_skipped"] == 0
        assert len(result["records"]) >= 2  # reference + products

    def test_shadow_run_silent_skip_count_is_zero(self, tmp_path):
        """surfaces_silently_skipped is 0 in a complete shadow run."""
        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(True), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=None,
                no_write=True,
            )

        assert result["surfaces_silently_skipped"] == 0


# ---------------------------------------------------------------------------
# test_idempotent_rerun_stable_fields_match
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestIdempotentRerun:
    def test_idempotent_rerun_stable_fields_match(self, tmp_path):
        """Running validate-only twice for the same product produces identical stable fields.

        Stable fields (must match): decision, surfaces_silently_skipped, run_status.
        Excluded: run_id, generation timestamps.
        """
        kwargs = dict(
            product="cells/java",
            mode="validate-only",
            scratch_root=tmp_path,
            subdomains=["reference"],
            no_write=True,
        )

        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(True), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result1 = run_harness(**kwargs)

        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(True), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result2 = run_harness(**kwargs)

        # Stable fields must match
        assert result1["run_status"] == result2["run_status"]
        assert result1["surfaces_silently_skipped"] == result2["surfaces_silently_skipped"]

        # Per-record decisions must match
        decisions1 = sorted(r["decision"] for r in result1["records"])
        decisions2 = sorted(r["decision"] for r in result2["records"])
        assert decisions1 == decisions2

    def test_idempotent_with_same_fingerprints(self, tmp_path):
        """Same fingerprints always produce the same decision."""
        fingerprints = {"upstream_repo_sha": "sha_abc", "local_knowledge_sha": "sha_def"}

        kwargs = dict(
            product="cells/java",
            mode="dry-run",
            scratch_root=tmp_path,
            subdomains=["reference"],
            no_write=True,
        )

        for _ in range(2):
            with _patch_registry(), _patch_registry_exists(), \
                 patch("refresh_harness.load_manifest", return_value=None), \
                 _patch_output_exists(True), \
                 patch("refresh_harness._collect_fingerprints_with_overrides", return_value=fingerprints):

                results = [run_harness(**kwargs) for _ in range(2)]

        decisions = [r["records"][0]["decision"] for r in results]
        assert decisions[0] == decisions[1]


# ---------------------------------------------------------------------------
# test_blocked_product_does_not_halt_other_products
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestBlockedProductDoesNotHaltOthers:
    def test_blocked_product_does_not_halt_other_products(self, tmp_path):
        """A BLOCKED surface for one product does not prevent evaluation of others.

        Each product's run_harness call is independent. This test verifies that
        separate calls for different products complete regardless of each other's status.
        """
        call_results = []

        for product in ["cells/java", "words/net", "slides/python"]:
            # Make one product appear blocked (no output)
            output_exists = product != "words/net"

            with _patch_registry(), _patch_registry_exists(), \
                 patch("refresh_harness.load_manifest", return_value=None), \
                 patch("refresh_harness._inspect_output_state",
                       return_value=MagicMock(output_exists=output_exists, output_content_hash=None)), \
                 patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

                result = run_harness(
                    product=product,
                    mode="dry-run",
                    scratch_root=tmp_path,
                    subdomains=["reference"],
                    no_write=True,
                )

            call_results.append(result)

        # All three should have completed (not raised)
        assert len(call_results) == 3

        # words/net had no output — its decision should be RECONCILE_MISSING
        words_result = next(r for r in call_results if r["product"] == "words/net")
        words_ref = next(
            rec for rec in words_result["records"] if rec["subdomain"] == "reference"
        )
        assert words_ref["decision"] == "RECONCILE_MISSING"

        # cells/java had output — should complete with some non-missing decision
        cells_result = next(r for r in call_results if r["product"] == "cells/java")
        cells_ref = next(
            rec for rec in cells_result["records"] if rec["subdomain"] == "reference"
        )
        assert cells_ref["decision"] != "RECONCILE_MISSING"


# ---------------------------------------------------------------------------
# test_missing_output_triggers_reconcile_not_fresh
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestMissingOutputReconcile:
    def test_missing_output_triggers_reconcile_not_fresh(self, tmp_path):
        """Missing output triggers RECONCILE_MISSING decision, not FRESH."""
        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(False), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        ref_record = next(
            r for r in result["records"] if r["subdomain"] == "reference"
        )
        assert ref_record["decision"] == "RECONCILE_MISSING"
        assert ref_record["decision"] != "FRESH"

    def test_present_output_does_not_trigger_reconcile(self, tmp_path):
        """Existing output does not trigger RECONCILE_MISSING."""
        with _patch_registry(), _patch_registry_exists(), \
             patch("refresh_harness.load_manifest", return_value=None), \
             _patch_output_exists(True), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path,
                subdomains=["reference"],
                no_write=True,
            )

        ref_record = next(
            r for r in result["records"] if r["subdomain"] == "reference"
        )
        assert ref_record["decision"] != "RECONCILE_MISSING"

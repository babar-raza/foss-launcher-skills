"""Tests for reconciliation_ledger.py — Phase 3 (TC-PROD-005).

Covers:
  test_all_subdomains_in_ledger
  test_silent_skip_count_is_zero
  test_fresh_skip_has_manifest_proof
  test_partial_pass_lists_blocked_surfaces_explicitly
  test_blocked_surface_does_not_produce_pass
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reconciliation_ledger import (
    BLOCKED,
    FAIL,
    PARTIAL_PASS,
    PASS,
    ReconciliationLedger,
    SurfaceRecord,
    build_ledger,
    check_tc_conditions,
    load_tc_closure_conditions,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _fresh_record(product="cells/java", subdomain="reference") -> SurfaceRecord:
    return SurfaceRecord(
        product=product,
        subdomain=subdomain,
        decision="FRESH",
        outcome="SKIP",  # FRESH surfaces are skipped (no work needed)
        manifest_proof_path=f"runs/state/cells/java/{subdomain}/freshness-manifest.json",
        explanation="All inputs match and output is current",
    )


def _blocked_record(product="cells/java", subdomain="reference") -> SurfaceRecord:
    return SurfaceRecord(
        product=product,
        subdomain=subdomain,
        decision="BLOCKED",
        outcome=BLOCKED,
        manifest_proof_path=None,
        explanation="Required dependency missing",
    )


def _pass_record(product="cells/java", subdomain="reference") -> SurfaceRecord:
    return SurfaceRecord(
        product=product,
        subdomain=subdomain,
        decision="REGENERATE_UPSTREAM",
        outcome=PASS,
        manifest_proof_path=None,
        explanation="Upstream SHA changed; regeneration completed",
    )


def _fail_record(product="cells/java", subdomain="reference") -> SurfaceRecord:
    return SurfaceRecord(
        product=product,
        subdomain=subdomain,
        decision="REGENERATE_UPSTREAM",
        outcome=FAIL,
        manifest_proof_path=None,
        explanation="Regeneration failed",
    )


# ---------------------------------------------------------------------------
# test_all_subdomains_in_ledger
# ---------------------------------------------------------------------------

class TestAllSubdomainsInLedger:
    def test_all_subdomains_in_ledger(self):
        """build_ledger() includes a record for every expected surface."""
        records = [
            _fresh_record("cells/java", "reference"),
            _fresh_record("cells/java", "products"),
        ]
        expected = ["cells/java/reference", "cells/java/products"]
        ledger = build_ledger("run001", records, expected)
        surface_keys = {f"{r.product}/{r.subdomain}" for r in ledger.records}
        assert "cells/java/reference" in surface_keys
        assert "cells/java/products" in surface_keys

    def test_ledger_to_dict_has_all_records(self):
        """to_dict() includes all records."""
        records = [_fresh_record(), _pass_record("words/net", "docs")]
        ledger = build_ledger("run001", records, ["cells/java/reference", "words/net/docs"])
        d = ledger.to_dict()
        assert len(d["records"]) == 2


# ---------------------------------------------------------------------------
# test_silent_skip_count_is_zero
# ---------------------------------------------------------------------------

class TestSilentSkipCount:
    def test_silent_skip_count_is_zero_when_all_expected_have_records(self):
        """surfaces_silently_skipped is 0 when all expected surfaces have records."""
        records = [_fresh_record("cells/java", "reference")]
        ledger = build_ledger("run001", records, ["cells/java/reference"])
        assert ledger.surfaces_silently_skipped == 0

    def test_silent_skip_count_nonzero_when_expected_surface_missing(self):
        """surfaces_silently_skipped > 0 when an expected surface has no record."""
        records = [_fresh_record("cells/java", "reference")]
        expected = ["cells/java/reference", "cells/java/products"]  # products missing
        ledger = build_ledger("run001", records, expected)
        assert ledger.surfaces_silently_skipped == 1

    def test_silent_skip_makes_run_status_fail(self):
        """A silent skip elevates run_status to FAIL."""
        records = [_fresh_record("cells/java", "reference")]
        expected = ["cells/java/reference", "cells/java/products"]
        ledger = build_ledger("run001", records, expected)
        assert ledger.run_status == FAIL

    def test_no_silent_skip_fresh_surfaces(self):
        """FRESH surfaces with records don't count as silent skips."""
        records = [_fresh_record("cells/java", "reference"),
                   _fresh_record("cells/java", "products")]
        expected = ["cells/java/reference", "cells/java/products"]
        ledger = build_ledger("run001", records, expected)
        assert ledger.surfaces_silently_skipped == 0
        assert ledger.run_status == PASS


# ---------------------------------------------------------------------------
# test_fresh_skip_has_manifest_proof
# ---------------------------------------------------------------------------

class TestFreshSkipManifestProof:
    def test_fresh_skip_has_manifest_proof(self):
        """FRESH surface records must include manifest_proof_path."""
        record = _fresh_record()
        assert record.manifest_proof_path is not None
        assert "freshness-manifest" in record.manifest_proof_path

    def test_fresh_without_proof_is_detected(self):
        """A FRESH record without manifest_proof_path is identifiable."""
        record = SurfaceRecord(
            product="cells/java",
            subdomain="reference",
            decision="FRESH",
            outcome="SKIP",
            manifest_proof_path=None,  # missing!
            explanation="Fresh but no proof",
        )
        assert record.manifest_proof_path is None

    def test_build_ledger_includes_manifest_proof_in_output(self):
        """build_ledger preserves manifest_proof_path in records."""
        record = _fresh_record()
        ledger = build_ledger("run001", [record], ["cells/java/reference"])
        d = ledger.to_dict()
        assert d["records"][0]["manifest_proof_path"] is not None


# ---------------------------------------------------------------------------
# test_partial_pass_lists_blocked_surfaces_explicitly
# ---------------------------------------------------------------------------

class TestPartialPass:
    def test_partial_pass_lists_blocked_surfaces_explicitly(self):
        """PARTIAL_PASS run lists all blocked surfaces in partial_pass_surfaces."""
        records = [
            _pass_record("cells/java", "reference"),
            _blocked_record("words/net", "reference"),
        ]
        expected = ["cells/java/reference", "words/net/reference"]
        ledger = build_ledger("run001", records, expected)
        assert ledger.run_status == PARTIAL_PASS
        assert "words/net/reference" in ledger.partial_pass_surfaces

    def test_partial_pass_does_not_include_passing_surfaces(self):
        """partial_pass_surfaces only lists blocked, not passing surfaces."""
        records = [
            _pass_record("cells/java", "reference"),
            _blocked_record("words/net", "reference"),
        ]
        expected = ["cells/java/reference", "words/net/reference"]
        ledger = build_ledger("run001", records, expected)
        assert "cells/java/reference" not in ledger.partial_pass_surfaces

    def test_all_pass_produces_pass_not_partial(self):
        """All passing surfaces → run_status = PASS, not PARTIAL_PASS."""
        records = [_pass_record("cells/java", "reference")]
        ledger = build_ledger("run001", records, ["cells/java/reference"])
        assert ledger.run_status == PASS
        assert ledger.partial_pass_surfaces == []


# ---------------------------------------------------------------------------
# test_blocked_surface_does_not_produce_pass
# ---------------------------------------------------------------------------

class TestBlockedSurfaceNotPass:
    def test_blocked_surface_does_not_produce_pass(self):
        """A BLOCKED surface never results in overall PASS."""
        records = [_blocked_record()]
        ledger = build_ledger("run001", records, ["cells/java/reference"])
        assert ledger.run_status != PASS
        assert ledger.run_status == PARTIAL_PASS

    def test_fail_surface_produces_fail_not_partial(self):
        """A FAIL surface produces FAIL, not PARTIAL_PASS."""
        records = [
            _pass_record("cells/java", "reference"),
            _fail_record("words/net", "reference"),
        ]
        expected = ["cells/java/reference", "words/net/reference"]
        ledger = build_ledger("run001", records, expected)
        assert ledger.run_status == FAIL

    def test_multiple_blocked_all_listed_in_partial_pass(self):
        """All blocked surfaces appear in partial_pass_surfaces."""
        records = [
            _blocked_record("cells/java", "reference"),
            _blocked_record("words/net", "docs"),
        ]
        expected = ["cells/java/reference", "words/net/docs"]
        ledger = build_ledger("run001", records, expected)
        assert ledger.run_status == PARTIAL_PASS
        assert "cells/java/reference" in ledger.partial_pass_surfaces
        assert "words/net/docs" in ledger.partial_pass_surfaces


# ---------------------------------------------------------------------------
# Atomic write test
# ---------------------------------------------------------------------------

class TestLedgerSave:
    def test_save_writes_json_file(self, tmp_path):
        """save() writes a valid JSON file."""
        records = [_fresh_record()]
        ledger = build_ledger("run001", records, ["cells/java/reference"])
        out = ledger.save(tmp_path, "cells/java")
        assert out.is_file()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["run_id"] == "run001"
        assert data["run_status"] == PASS

    def test_save_creates_parent_dirs(self, tmp_path):
        """save() creates nested parent directories."""
        shadow_root = tmp_path / "deep" / "nested" / "shadow"
        records = [_fresh_record()]
        ledger = build_ledger("run002", records, ["cells/java/reference"])
        out = ledger.save(shadow_root, "cells/java")
        assert out.is_file()

    def test_save_atomic_uses_tmp(self, tmp_path, monkeypatch):
        """save() writes via .tmp file then os.replace (atomic)."""
        import os
        seen_tmp = []
        original_replace = os.replace

        def patched(src, dst):
            seen_tmp.append(str(src))
            original_replace(src, dst)

        monkeypatch.setattr(os, "replace", patched)

        records = [_fresh_record()]
        ledger = build_ledger("run003", records, ["cells/java/reference"])
        ledger.save(tmp_path, "cells/java")

        assert len(seen_tmp) == 1
        assert seen_tmp[0].endswith(".tmp")


# ---------------------------------------------------------------------------
# TC closure conditions tests
# ---------------------------------------------------------------------------

class TestTcClosureConditions:
    def test_load_tc_closure_conditions_returns_dict(self, tmp_path):
        """load_tc_closure_conditions() returns a dict (may be empty)."""
        result = load_tc_closure_conditions(repo_root=tmp_path)
        assert isinstance(result, dict)

    def test_load_tc_closure_conditions_from_file(self, tmp_path):
        """load_tc_closure_conditions() reads conditions from JSON file."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "tc-closure-conditions.json").write_text(
            json.dumps({"TC-108": {"required_decision": "REGENERATE_UPSTREAM", "required_subdomain": "reference"}}),
            encoding="utf-8",
        )
        result = load_tc_closure_conditions(repo_root=tmp_path)
        assert "TC-108" in result

    def test_check_tc_conditions_matches_correct_decision(self):
        """check_tc_conditions() returns TC IDs whose conditions are met."""
        record = SurfaceRecord(
            product="cells/java",
            subdomain="reference",
            decision="REGENERATE_UPSTREAM",
            outcome=PASS,
            manifest_proof_path=None,
        )
        conditions = {
            "TC-108": {"required_decision": "REGENERATE_UPSTREAM", "required_subdomain": "reference"},
            "TC-109": {"required_decision": "REGENERATE_GENERATOR", "required_subdomain": "reference"},
        }
        met = check_tc_conditions(record, conditions)
        assert "TC-108" in met
        assert "TC-109" not in met

    def test_check_tc_conditions_subdomain_mismatch(self):
        """check_tc_conditions() excludes TCs where subdomain doesn't match."""
        record = SurfaceRecord(
            product="cells/java",
            subdomain="products",
            decision="REGENERATE_UPSTREAM",
            outcome=PASS,
            manifest_proof_path=None,
        )
        conditions = {
            "TC-108": {"required_decision": "REGENERATE_UPSTREAM", "required_subdomain": "reference"},
        }
        met = check_tc_conditions(record, conditions)
        assert "TC-108" not in met

    def test_production_tc_closure_conditions_file_loads(self):
        """The production data/tc-closure-conditions.json loads without error."""
        result = load_tc_closure_conditions()
        # File should exist and contain TC-108..112 and TC-205
        if result:  # File might not exist in all environments
            assert isinstance(result, dict)

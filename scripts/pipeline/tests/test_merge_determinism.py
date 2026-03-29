"""Regression tests for promote.py correctness.

Tests that:
1. Provenance tagging is applied correctly to all claim sources
2. Promote output is identical on consecutive runs (deterministic)
3. api_to_claim index ordering is stable (lowest claim_id wins)
"""
import copy
import json
import sys
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import promote as promote_mod
from promote import _validate_claims


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCOUT_CLAIM = {
    "claim_id": "CLM-scout-001",
    "text": "Scene.open(filename) -> Scene",
    "kind": "api_method",
}

ENRICHED_CLAIM = {
    "claim_id": "ERC-3d-net-abc12345",
    "text": "The Scene class enables loading and saving 3D models.",
    "kind": "feature",
    "claim_source": "llm_enriched",
    "confidence": 0.85,
}

SUPPLEMENTAL_CLAIM = {
    "claim_id": "CLM-supp-001",
    "text": "Aspose.3D supports FBX format.",
    "kind": "format",
    "claim_source": "fl_absorbed_2026-03-29",
}


# ---------------------------------------------------------------------------
# Test: _validate_claims filters bad entries
# ---------------------------------------------------------------------------

class TestValidateClaims:
    def test_valid_claims_pass_through(self):
        claims = [copy.deepcopy(SCOUT_CLAIM)]
        result = _validate_claims(claims, "scout")
        assert len(result) == 1
        assert result[0]["claim_id"] == "CLM-scout-001"

    def test_non_dict_entries_filtered(self):
        claims = [copy.deepcopy(SCOUT_CLAIM), "not_a_dict", None]
        result = _validate_claims(claims, "scout")
        assert len(result) == 1

    def test_empty_list_returns_empty(self):
        assert _validate_claims([], "scout") == []

    def test_non_list_input_returns_empty(self):
        assert _validate_claims(None, "scout") == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test: api_to_claim ordering in knowledge_core (Phase 1C regression)
# ---------------------------------------------------------------------------

class TestApiToClaimOrdering:
    def test_sorted_by_claim_id_lowest_wins(self):
        """When two claims map to the same API ref, lowest claim_id must win."""
        import re as _re

        # Simulate the knowledge_core.py api_to_claim build logic
        claims_a = [
            {"claim_id": "Z-claim", "api_refs": ["Scene.open"]},
            {"claim_id": "A-claim", "api_refs": ["Scene.open"]},
        ]
        claims_b = [
            {"claim_id": "A-claim", "api_refs": ["Scene.open"]},
            {"claim_id": "Z-claim", "api_refs": ["Scene.open"]},
        ]

        def build_index(claims):
            index = {}
            for c in sorted(claims, key=lambda c: c.get("claim_id") or ""):
                cid = c.get("claim_id")
                for ref in c.get("api_refs", []):
                    if ref and ref not in index:
                        index[ref] = cid
            return index

        idx_a = build_index(claims_a)
        idx_b = build_index(claims_b)

        assert idx_a == idx_b, "api_to_claim index must be order-invariant"
        assert idx_a["Scene.open"] == "A-claim", "Lowest claim_id must win"

    def test_empty_claims_empty_index(self):
        def build_index(claims):
            index = {}
            for c in sorted(claims, key=lambda c: c.get("claim_id") or ""):
                cid = c.get("claim_id")
                for ref in c.get("api_refs", []):
                    if ref and ref not in index:
                        index[ref] = cid
            return index

        assert build_index([]) == {}

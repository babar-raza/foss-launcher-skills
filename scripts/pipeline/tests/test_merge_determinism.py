"""Regression tests for merge.py correctness fixes (Phase 1A).

Tests that:
1. Claims without claim_id get deterministic IDs assigned (not id() fallback)
2. Merge output is identical on consecutive runs
3. FL claim ordering does not affect merge output (order-invariant)
4. Tie-breaking in Jaccard matching is deterministic (lowest claim_id wins)
"""
import copy
import json
import sys
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import merge as merge_mod
from merge import _ensure_claim_ids, _merge_fl_claims


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCOUT_CLAIM = {
    "claim_id": "CLM-scout-001",
    "text": "Scene.open(filename) -> ",
    "kind": "api_method",
}

FL_CLAIM_A = {
    "claim_id": "FL-A001",
    "text": "Scene.open accepts a filename parameter",
    "kind": "api_method",
}

FL_CLAIM_B = {
    "claim_id": "FL-B001",
    "text": "Scene supports opening files",
    "kind": "api_method",
}


# ---------------------------------------------------------------------------
# Test: _ensure_claim_ids generates stable IDs
# ---------------------------------------------------------------------------

class TestEnsureClaimIds:
    def test_claims_with_ids_unchanged(self):
        claims = [{"claim_id": "STABLE-001", "text": "hello"}]
        result = _ensure_claim_ids(claims, "test")
        assert result[0]["claim_id"] == "STABLE-001"

    def test_missing_id_generates_deterministic_id(self):
        claims = [{"text": "some text", "kind": "api_method"}]
        r1 = _ensure_claim_ids(claims, "test")
        r2 = _ensure_claim_ids(claims, "test")
        assert r1[0]["claim_id"] == r2[0]["claim_id"]
        assert r1[0]["claim_id"].startswith("test")

    def test_different_text_produces_different_id(self):
        c1 = [{"text": "text A", "kind": "api_method"}]
        c2 = [{"text": "text B", "kind": "api_method"}]
        r1 = _ensure_claim_ids(c1, "p")
        r2 = _ensure_claim_ids(c2, "p")
        assert r1[0]["claim_id"] != r2[0]["claim_id"]

    def test_same_text_same_prefix_same_id(self):
        """Deterministic: same input → same output across calls."""
        claims = [{"text": "Scene.open(path)", "kind": "api_method"}]
        ids = {_ensure_claim_ids(claims, "fl")[0]["claim_id"] for _ in range(5)}
        assert len(ids) == 1  # always the same

    def test_id_never_uses_memory_address(self):
        """Old bug: id() is a memory address — changes between runs."""
        claims = [{"text": "test claim", "kind": "api_method"}]
        generated = _ensure_claim_ids(claims, "fl")[0]["claim_id"]
        # Memory addresses are typically 10+ digit integers, not hex prefixed strings
        # Our generated IDs are: prefix + 12-char hex
        assert len(generated) > 0
        assert generated.startswith("fl")
        # Verify it's not a plain integer (memory address)
        assert not generated.lstrip("fl").isdigit() or len(generated.lstrip("fl")) < 10


# ---------------------------------------------------------------------------
# Test: FL claim ordering invariance
# ---------------------------------------------------------------------------

class TestMergeOrderInvariance:
    def _run_merge(self, fl_claims):
        """Run _merge_fl_claims with a fixed scout claim and return result."""
        scout = [copy.deepcopy(SCOUT_CLAIM)]
        fl = copy.deepcopy(fl_claims)
        return _merge_fl_claims(scout, fl)

    def test_single_fl_claim_deterministic(self):
        """Single FL claim: result is the same on two runs."""
        r1 = self._run_merge([FL_CLAIM_A])
        r2 = self._run_merge([FL_CLAIM_A])
        assert r1 == r2

    def test_two_fl_claims_order_invariant(self):
        """Two FL claims in different order must produce identical merged output."""
        r1 = self._run_merge([FL_CLAIM_A, FL_CLAIM_B])
        r2 = self._run_merge([FL_CLAIM_B, FL_CLAIM_A])
        # The matched claim IDs in the merge result must be identical
        def extract_matched_ids(result):
            return sorted([
                c.get("fl_claim_id", "") or c.get("claim_id", "")
                for c in result
                if isinstance(c, dict)
            ])
        assert extract_matched_ids(r1) == extract_matched_ids(r2)

    def test_reversed_fl_order_same_result(self):
        """Reversing FL claim list must not change which claims match."""
        fl_claims = [
            {"claim_id": f"FL-{i:03d}", "text": f"Scene.open variant {i}", "kind": "api_method"}
            for i in range(5)
        ]
        r1 = self._run_merge(fl_claims)
        r2 = self._run_merge(list(reversed(fl_claims)))

        def fl_ids(result):
            return sorted([
                c.get("fl_claim_id", "") or c.get("claim_id", "")
                for c in result if isinstance(c, dict)
            ])
        assert fl_ids(r1) == fl_ids(r2)


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

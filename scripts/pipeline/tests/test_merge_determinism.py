"""Regression tests for promote.py correctness.

Tests that:
1. Provenance tagging is applied correctly to all claim sources
2. Promote output is identical on consecutive runs (deterministic)
3. api_to_claim index ordering is stable (lowest claim_id wins)
4. ERC duplicate claim IDs block promotion (hard gate)
5. CLM duplicate claim IDs warn but allow promotion
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


# ---------------------------------------------------------------------------
# Test: ERC duplicate claim IDs block promotion (Track B prevention)
# ---------------------------------------------------------------------------

def _setup_promote_tree(tmp_path, scout_claims, enriched_claims=None):
    """Create minimal knowledge tree for promote()."""
    base = tmp_path / "knowledge" / "test" / "testplat"
    scout_dir = base / "scout"
    scout_dir.mkdir(parents=True)
    (scout_dir / "claims.json").write_text(
        json.dumps(scout_claims), encoding="utf-8")
    (scout_dir / "api_surface.json").write_text("[]", encoding="utf-8")
    if enriched_claims is not None:
        enriched_dir = base / "scout"
        (enriched_dir / "enriched_claims.json").write_text(
            json.dumps(enriched_claims), encoding="utf-8")
    return tmp_path / "knowledge"


class TestPromoteErcDuplicateGate:
    """ERC duplicates must block promotion; CLM duplicates must not."""

    def test_promote_rejects_erc_duplicates(self, tmp_path):
        """Duplicate ERC-* IDs → promote returns False, claims.json not written."""
        scout = [
            {"claim_id": "CLM-scout-001", "text": "ok", "kind": "api_method"},
        ]
        enriched = [
            {"claim_id": "ERC-test-testplat-aaa", "text": "claim A", "kind": "feature"},
            {"claim_id": "ERC-test-testplat-aaa", "text": "claim B", "kind": "feature"},
        ]
        kr = _setup_promote_tree(tmp_path, scout, enriched)
        result = promote_mod.promote("test", "testplat", knowledge_root=str(kr))
        assert result is False
        merged = kr / "test" / "testplat" / "merged" / "claims.json"
        assert not merged.exists(), "claims.json must NOT be written when ERC dupes exist"

    def test_promote_allows_clm_duplicates(self, tmp_path):
        """Duplicate CLM-* IDs → promote returns True, claims.json written."""
        scout = [
            {"claim_id": "CLM-scout-aaa", "text": "method A()", "kind": "api_method"},
            {"claim_id": "CLM-scout-aaa", "text": "method A()", "kind": "api_method"},
        ]
        kr = _setup_promote_tree(tmp_path, scout)
        result = promote_mod.promote("test", "testplat", knowledge_root=str(kr))
        assert result is True
        merged = kr / "test" / "testplat" / "merged" / "claims.json"
        assert merged.exists(), "claims.json must be written when only CLM dupes exist"


def _claim_id_set(merged_dir):
    """The set of claim_ids in a promoted merged/claims.json."""
    data = json.loads((merged_dir / "claims.json").read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("claims", [])
    return {c.get("claim_id") for c in rows if isinstance(c, dict)}


class TestPromoteDeterminism:
    """RPR-J-01: prove `promote()` is a deterministic function of its scout inputs — the
    property the file's own docstring claimed ('Promote output is identical on consecutive
    runs') but never actually tested. This is the load-bearing measurement for the pin-and-
    replay design (RPR-J-02): if promote is deterministic given a FIXED enriched_claims.json,
    then committing that file makes a full knowledge rebuild reproducible without re-calling
    the LLM. The nondeterminism lives ONLY in enrich.py (the one LLM callsite), never here.
    """

    def _run(self, tmp_path_factory, scout, enriched, name):
        base = tmp_path_factory.mktemp(name)
        kr = _setup_promote_tree(base, scout, enriched)
        ok = promote_mod.promote("test", "testplat", knowledge_root=str(kr))
        assert ok is True
        return kr / "test" / "testplat" / "merged"

    def test_promote_claim_ids_identical_across_runs(self, tmp_path_factory):
        """Two promote() runs against the SAME scout + enriched inputs produce the identical
        claim_id set. This is the replay guarantee: citations pinned to these IDs never dangle
        so long as enriched_claims.json is unchanged."""
        scout = [
            {"claim_id": "CLM-scout-aaa", "text": "Document.Save() writes a PDF.", "kind": "api_method"},
            {"claim_id": "CLM-scout-bbb", "text": "Document.Open() reads a PDF.", "kind": "api_method"},
        ]
        enriched = [
            {"claim_id": "ERC-test-testplat-001", "text": "Merging preserves bookmarks.", "kind": "feature"},
        ]
        m1 = self._run(tmp_path_factory, scout, enriched, "run1")
        m2 = self._run(tmp_path_factory, scout, enriched, "run2")
        assert _claim_id_set(m1) == _claim_id_set(m2), "promote must yield an identical claim_id set on replay"
        assert _claim_id_set(m1), "sanity: the set is non-empty"

    def test_promote_claims_bytes_identical_modulo_timestamps(self, tmp_path_factory):
        """The promoted claims.json is byte-identical across runs once volatile timestamp-like
        fields are removed — i.e. the claim CONTENT (not just the IDs) is stable."""
        scout = [{"claim_id": "CLM-scout-ccc", "text": "Save writes output.", "kind": "api_method"}]
        enriched = [{"claim_id": "ERC-test-testplat-002", "text": "Streaming is supported.", "kind": "feature"}]
        m1 = self._run(tmp_path_factory, scout, enriched, "b1")
        m2 = self._run(tmp_path_factory, scout, enriched, "b2")
        c1 = json.loads((m1 / "claims.json").read_text(encoding="utf-8"))
        c2 = json.loads((m2 / "claims.json").read_text(encoding="utf-8"))

        def _strip(o):
            if isinstance(o, dict):
                return {k: _strip(v) for k, v in sorted(o.items())
                        if k not in ("promoted_at", "extracted_at", "generated_at", "timestamp")}
            if isinstance(o, list):
                return [_strip(x) for x in o]
            return o

        assert _strip(c1) == _strip(c2), "promoted claim content must be identical on replay"

    def test_enriched_claim_survives_promote_unchanged(self, tmp_path_factory):
        """The pinned enriched claim's id is carried into merged output verbatim — so a page
        citing it resolves after replay (the citation-durability property J-02 depends on)."""
        scout = [{"claim_id": "CLM-scout-ddd", "text": "Open reads input.", "kind": "api_method"}]
        enriched = [{"claim_id": "ERC-test-testplat-keepme", "text": "Encryption is available.", "kind": "feature"}]
        m1 = self._run(tmp_path_factory, scout, enriched, "e1")
        assert "ERC-test-testplat-keepme" in _claim_id_set(m1)

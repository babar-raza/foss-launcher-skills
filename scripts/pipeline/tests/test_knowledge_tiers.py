"""Tests for lib/knowledge_tiers.py — RPR-J-07 claim-id tiering."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from knowledge_tiers import claim_tier, is_tier1_claim_id, is_tier2_claim_id


class TestClaimTier:
    def test_clm_prefix_is_tier1(self):
        assert claim_tier("CLM-cells-abc12345") == 1

    def test_erc_prefix_is_tier2(self):
        assert claim_tier("ERC-cells-python-abc12345") == 2

    def test_unrecognized_prefix_is_tier0(self):
        assert claim_tier("CL-999") == 0
        assert claim_tier("FOO-bar-123") == 0

    def test_empty_string_is_tier0(self):
        assert claim_tier("") == 0

    def test_none_is_tier0(self):
        assert claim_tier(None) == 0

    def test_non_string_is_tier0(self):
        assert claim_tier(12345) == 0
        assert claim_tier(["CLM-x"]) == 0


class TestIsTier1ClaimId:
    def test_clm_id_is_tier1(self):
        assert is_tier1_claim_id("CLM-pdf-04f590a1") is True

    def test_erc_id_is_not_tier1(self):
        assert is_tier1_claim_id("ERC-pdf-net-04f590a1") is False

    def test_unrecognized_id_is_not_tier1(self):
        """Unrecognized scheme must NOT be treated as tier1 -- callers using
        is_tier1_claim_id to decide "safe to skip" must stay conservative."""
        assert is_tier1_claim_id("CL-999") is False


class TestIsTier2ClaimId:
    def test_erc_id_is_tier2(self):
        assert is_tier2_claim_id("ERC-pdf-net-04f590a1") is True

    def test_clm_id_is_not_tier2(self):
        assert is_tier2_claim_id("CLM-pdf-04f590a1") is False

    def test_unrecognized_id_is_not_tier2(self):
        """The critical safety property: an unrecognized/malformed claim_id
        must NOT be granted Tier-2 leniency by a naive truthiness check --
        it must explicitly fail is_tier2_claim_id so callers keep blocking."""
        assert is_tier2_claim_id("CL-999") is False
        assert is_tier2_claim_id("") is False
        assert is_tier2_claim_id(None) is False

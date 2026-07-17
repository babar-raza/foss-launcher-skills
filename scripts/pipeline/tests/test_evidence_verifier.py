"""Tests for evidence_verifier.py — verify_evidence pure function.

Uses a minimal FakeKnowledge stub to avoid loading real knowledge models.
Covers:
  - Missing evidence block → WARN
  - Missing model_sha → WARN
  - Stale model_sha → WARN
  - Valid model_sha → no warning
  - Unknown claim_id → FAIL (when claim_ids populated)
  - Valid claim_id → no error
  - Empty claim_ids set → warn (can't validate)
  - Unknown API class → FAIL
  - Unknown API member → FAIL
  - Valid API class + member → no error
  - Re-export compatibility: verify_evidence importable from knowledge_core
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evidence_verifier import verify_evidence


# ---------------------------------------------------------------------------
# Minimal stub for Knowledge (duck-typed — no real disk access needed)
# ---------------------------------------------------------------------------

class FakeKnowledge:
    """Minimal duck-type substitute for Knowledge. No file I/O."""

    def __init__(
        self,
        repo_sha: str = "abc12345",
        claim_ids: set | None = None,
        classes: dict | None = None,
        methods: dict | None = None,
        properties: dict | None = None,
        enum_members: dict | None = None,
    ):
        self.repo_sha = repo_sha
        self.claim_ids = claim_ids if claim_ids is not None else set()
        self.classes = classes if classes is not None else {}
        self._methods = methods if methods is not None else {}
        self._properties = properties if properties is not None else {}
        self._enum_members = enum_members if enum_members is not None else {}

    def has_method(self, cls_name: str, member: str) -> bool:
        return member in self._methods.get(cls_name, set())

    def has_property(self, cls_name: str, member: str) -> bool:
        return member in self._properties.get(cls_name, set())

    def has_enum_member(self, cls_name: str, member: str) -> bool:
        return member in self._enum_members.get(cls_name, set())


FAKE_FILE = Path("/content/cells/python/guide.md")


def _severities(findings) -> list[str]:
    return [f.level for f in findings]


def _messages(findings) -> list[str]:
    return [f.message for f in findings]


# ---------------------------------------------------------------------------
# Missing / malformed evidence block
# ---------------------------------------------------------------------------

class TestMissingEvidence:
    def test_no_evidence_key_returns_warn(self):
        fm = {}
        k = FakeKnowledge()
        results = verify_evidence(fm, k, FAKE_FILE)
        assert len(results) == 1
        assert results[0].level == "WARN"
        assert "Missing" in results[0].message

    def test_evidence_none_returns_warn(self):
        fm = {"evidence": None}
        k = FakeKnowledge()
        results = verify_evidence(fm, k, FAKE_FILE)
        assert len(results) == 1
        assert results[0].level == "WARN"

    def test_evidence_not_dict_returns_warn(self):
        fm = {"evidence": "not-a-dict"}
        k = FakeKnowledge()
        results = verify_evidence(fm, k, FAKE_FILE)
        assert len(results) == 1
        assert results[0].level == "WARN"

    def test_missing_evidence_returns_early(self):
        """When evidence block is absent, returns immediately (no further checks)."""
        fm = {}
        k = FakeKnowledge(claim_ids={"c1"}, classes={"Workbook": {}})
        results = verify_evidence(fm, k, FAKE_FILE)
        assert len(results) == 1  # only the missing-block warning


# ---------------------------------------------------------------------------
# model_sha staleness
# ---------------------------------------------------------------------------

class TestModelSha:
    def test_missing_model_sha_warns(self):
        # evidence must be non-empty dict to pass the presence check
        fm = {"evidence": {"apis": []}}
        k = FakeKnowledge(repo_sha="abc12345")
        results = verify_evidence(fm, k, FAKE_FILE)
        msgs = _messages(results)
        assert any("model_sha" in m for m in msgs)

    def test_stale_sha_warns(self):
        fm = {"evidence": {"model_sha": "old00000"}}
        k = FakeKnowledge(repo_sha="abc12345")
        results = verify_evidence(fm, k, FAKE_FILE)
        assert any("stale" in m.lower() or "Evidence stale" in m for m in _messages(results))

    def test_matching_sha_no_warn(self):
        fm = {"evidence": {"model_sha": "abc12345"}}
        k = FakeKnowledge(repo_sha="abc12345")
        results = verify_evidence(fm, k, FAKE_FILE)
        # No SHA warnings; no other findings either (no claims/apis)
        sha_msgs = [m for m in _messages(results) if "sha" in m.lower() or "stale" in m.lower()]
        assert sha_msgs == []


# ---------------------------------------------------------------------------
# Claim ID validation
# ---------------------------------------------------------------------------

class TestClaimIds:
    def test_unknown_claim_id_fails_when_index_populated(self):
        fm = {"evidence": {"model_sha": "abc12345", "claims": ["bad-id"]}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids={"c1", "c2"})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert len(fails) == 1
        assert "bad-id" in fails[0].message

    def test_valid_claim_id_no_error(self):
        fm = {"evidence": {"model_sha": "abc12345", "claims": ["c1"]}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids={"c1", "c2"})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert fails == []

    def test_empty_claim_ids_set_warns_when_claims_present(self):
        """Cannot validate IDs when claim index is empty → WARN."""
        fm = {"evidence": {"model_sha": "abc12345", "claims": ["c1"]}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids=set())
        results = verify_evidence(fm, k, FAKE_FILE)
        warns = [r for r in results if r.level == "WARN"]
        assert any("validate claim IDs" in m for m in _messages(warns))

    def test_empty_claim_ids_no_warn_when_no_claims(self):
        """If no claims in evidence, empty claim index is not flagged."""
        fm = {"evidence": {"model_sha": "abc12345"}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids=set())
        results = verify_evidence(fm, k, FAKE_FILE)
        claim_warns = [r for r in results if "claim" in r.message.lower() and r.level == "WARN"]
        assert claim_warns == []

    def test_multiple_unknown_claims_each_fail(self):
        fm = {"evidence": {"model_sha": "abc12345", "claims": ["bad1", "bad2"]}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids={"c1"})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert len(fails) == 2

    def test_unknown_tier2_erc_claim_id_warns_not_fails(self):
        """RPR-J-07: a missing Tier-2 (ERC-*) claim_id is expected enrichment
        churn, not a defect -- it must WARN, never FAIL."""
        fm = {"evidence": {"model_sha": "abc12345", "claims": ["ERC-pdf-net-deadbeef"]}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids={"CLM-pdf-aaaa1111"})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        warns = [r for r in results if r.level == "WARN"]
        assert fails == []
        assert any("ERC-pdf-net-deadbeef" in m for m in _messages(warns))

    def test_unknown_tier1_clm_claim_id_still_fails(self):
        """A missing Tier-1 (CLM-*) claim_id is a real signal and must still
        block, unchanged by RPR-J-07."""
        fm = {"evidence": {"model_sha": "abc12345", "claims": ["CLM-pdf-deadbeef"]}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids={"CLM-pdf-aaaa1111"})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert len(fails) == 1
        assert "CLM-pdf-deadbeef" in fails[0].message

    def test_mixed_tier1_and_tier2_unknown_claims_split_correctly(self):
        fm = {"evidence": {"model_sha": "abc12345",
                           "claims": ["CLM-pdf-deadbeef", "ERC-pdf-net-deadbeef"]}}
        k = FakeKnowledge(repo_sha="abc12345", claim_ids={"CLM-pdf-aaaa1111"})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        warns = [r for r in results if r.level == "WARN"]
        assert len(fails) == 1 and "CLM-pdf-deadbeef" in fails[0].message
        assert any("ERC-pdf-net-deadbeef" in m for m in _messages(warns))


# ---------------------------------------------------------------------------
# API reference validation
# ---------------------------------------------------------------------------

class TestApiValidation:
    def test_unknown_class_fails(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["UnknownClass"]}}
        k = FakeKnowledge(repo_sha="abc12345", classes={"Workbook": {}})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert len(fails) == 1
        assert "UnknownClass" in fails[0].message

    def test_unknown_member_fails(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Workbook.NoSuchMethod"]}}
        k = FakeKnowledge(
            repo_sha="abc12345",
            classes={"Workbook": {}},
            methods={"Workbook": {"Save"}},
        )
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert len(fails) == 1
        assert "NoSuchMethod" in fails[0].message

    def test_valid_method_no_fail(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Workbook.Save"]}}
        k = FakeKnowledge(
            repo_sha="abc12345",
            classes={"Workbook": {}},
            methods={"Workbook": {"Save"}},
        )
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert fails == []

    def test_valid_property_no_fail(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Workbook.Name"]}}
        k = FakeKnowledge(
            repo_sha="abc12345",
            classes={"Workbook": {}},
            properties={"Workbook": {"Name"}},
        )
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert fails == []

    def test_valid_enum_member_no_fail(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["FileFormat.Xlsx"]}}
        k = FakeKnowledge(
            repo_sha="abc12345",
            classes={"FileFormat": {}},
            enum_members={"FileFormat": {"Xlsx"}},
        )
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert fails == []

    def test_class_only_ref_valid(self):
        """api_ref without dot — validates class existence only."""
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Workbook"]}}
        k = FakeKnowledge(repo_sha="abc12345", classes={"Workbook": {}})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert fails == []

    def test_empty_api_ref_skipped(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["", None, "Workbook"]}}
        k = FakeKnowledge(repo_sha="abc12345", classes={"Workbook": {}})
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert fails == []


# ---------------------------------------------------------------------------
# Tier-gating for unknown member (FIX-HOOK-01)
# ---------------------------------------------------------------------------

class TestTierGatedMemberCheck:
    """surface_tier >= 2 → WARN instead of FAIL for unknown members."""

    def _knowledge(self, tier: int):
        k = FakeKnowledge(
            repo_sha="abc12345",
            classes={"Document": {}},
        )
        k.surface_tier = tier
        return k

    def test_tier1_unknown_member_is_fail(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Document.Save"]}}
        k = self._knowledge(1)
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert len(fails) == 1
        assert "unknown member" in fails[0].message

    def test_tier2_unknown_member_is_warn_not_fail(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Document.Save"]}}
        k = self._knowledge(2)
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        warns = [r for r in results if r.level == "WARN" and "unknown member" in r.message]
        assert fails == []
        assert len(warns) == 1

    def test_tier3_unknown_member_is_warn_not_fail(self):
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Document.Save"]}}
        k = self._knowledge(3)
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        warns = [r for r in results if r.level == "WARN" and "unknown member" in r.message]
        assert fails == []
        assert len(warns) == 1

    def test_no_surface_tier_attr_defaults_to_tier1_behaviour(self):
        """When knowledge has no surface_tier, getattr default=1 → FAIL."""
        fm = {"evidence": {"model_sha": "abc12345", "apis": ["Document.Save"]}}
        k = FakeKnowledge(repo_sha="abc12345", classes={"Document": {}})
        # FakeKnowledge has no surface_tier attribute — getattr should fall back to 1
        assert not hasattr(k, "surface_tier")
        results = verify_evidence(fm, k, FAKE_FILE)
        fails = [r for r in results if r.level == "FAIL"]
        assert len(fails) == 1


# ---------------------------------------------------------------------------
# Migration complete (R-3b) — verify_evidence now lives only in evidence_verifier
# ---------------------------------------------------------------------------

class TestMigrationComplete:
    def test_verify_evidence_not_in_knowledge_core(self):
        """R-3b: re-export stub removed; knowledge_core no longer exports verify_evidence."""
        import knowledge_core as kc
        assert not hasattr(kc, "verify_evidence")

    def test_canonical_import_still_works(self):
        """Canonical import from evidence_verifier remains functional."""
        from evidence_verifier import verify_evidence
        assert callable(verify_evidence)

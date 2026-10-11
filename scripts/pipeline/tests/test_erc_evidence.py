"""Tests for ERC- claim indexing in knowledge_core.py and evidence/mapper.py.

Covers the E2 pipeline fix: ERC- claims are now indexed by class name in
api_to_claim and resolved by the evidence mapper for constructor/import usage.
"""
import json
import shutil
import textwrap
from pathlib import Path

import pytest

# conftest.py adds scripts/pipeline/ to sys.path
from knowledge_core import Knowledge


_FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_knowledge(tmp_path, api_surface=None, claims=None, model=None):
    """Build a Knowledge object from inline data, falling back to fixtures."""
    merged = tmp_path / "knowledge" / "test" / "python" / "merged"
    merged.mkdir(parents=True)

    if api_surface is not None:
        (merged / "api_surface.json").write_text(json.dumps(api_surface))
    else:
        shutil.copy(_FIXTURES / "fake_api_surface.json", merged / "api_surface.json")

    if claims is not None:
        (merged / "claims.json").write_text(json.dumps(claims))
    else:
        shutil.copy(_FIXTURES / "fake_claims.json", merged / "claims.json")

    if model is not None:
        import yaml
        (merged / "model.yaml").write_text(yaml.dump(model))
    else:
        shutil.copy(_FIXTURES / "fake_model.yaml", merged / "model.yaml")

    return Knowledge("test", "python", knowledge_root=tmp_path / "knowledge")


# ---------------------------------------------------------------------------
# knowledge_core.py — ERC- bold notation extraction
# ---------------------------------------------------------------------------

class TestERCBoldNotation:
    """ERC- claims with **ClassName** bold notation → class-only key in api_to_claim."""

    def test_bold_classname_indexed(self, tmp_path):
        """**Scene** in claim text → api_to_claim['Scene'] = 'ERC-fake-001'."""
        k = _make_knowledge(tmp_path)
        assert k.api_to_claim.get("Scene") == "ERC-fake-001"

    def test_bold_node_indexed(self, tmp_path):
        """**Node** in claim text → api_to_claim['Node'] = 'ERC-fake-002'."""
        k = _make_knowledge(tmp_path)
        assert k.api_to_claim.get("Node") == "ERC-fake-002"

    def test_clm_method_key_not_overwritten_by_erc(self, tmp_path):
        """CLM- 'Scene.open' key must NOT be overwritten by ERC- 'Scene' key."""
        k = _make_knowledge(tmp_path)
        # CLM- sorts before ERC-, so Scene.open keeps its CLM- claim
        assert k.api_to_claim.get("Scene.open") == "CLM-3d-001abc"
        # ERC- Scene is a separate class-only key — no conflict
        assert k.api_to_claim.get("Scene") == "ERC-fake-001"

    def test_multiple_bold_names_in_one_claim(self, tmp_path):
        """A claim with multiple **bold** names registers all of them."""
        claims = [
            {
                "claim_id": "ERC-multi-001",
                "text": "**FbxImporter** and **FbxExporter** handle FBX format.",
            }
        ]
        api_surface = [
            {"name": "FbxImporter", "methods": [], "properties": [], "enum_members": [], "bases": []},
            {"name": "FbxExporter", "methods": [], "properties": [], "enum_members": [], "bases": []},
        ]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        assert k.api_to_claim.get("FbxImporter") == "ERC-multi-001"
        assert k.api_to_claim.get("FbxExporter") == "ERC-multi-001"


# ---------------------------------------------------------------------------
# knowledge_core.py — ERC- leading-word extraction (Java-style)
# ---------------------------------------------------------------------------

class TestERCLeadingWord:
    """ERC- claims without bold notation: first word validated against self.classes."""

    def test_leading_known_class_indexed(self, tmp_path):
        """'A3DObject is the base...' → api_to_claim['A3DObject'] = 'ERC-fake-003'."""
        k = _make_knowledge(tmp_path)
        assert k.api_to_claim.get("A3DObject") == "ERC-fake-003"

    def test_leading_unknown_word_rejected(self, tmp_path):
        """'The library provides...' → 'The' is not in classes → not indexed."""
        k = _make_knowledge(tmp_path)
        assert "The" not in k.api_to_claim

    def test_leading_sentence_starters_rejected(self, tmp_path):
        """Common English starters must not pollute api_to_claim."""
        claims = [
            {"claim_id": "ERC-en-001", "text": "This class extends Object."},
            {"claim_id": "ERC-en-002", "text": "Developers can use the API."},
            {"claim_id": "ERC-en-003", "text": "Each instance is independent."},
        ]
        api_surface = [{"name": "Foo", "methods": [], "properties": [], "enum_members": [], "bases": []}]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        assert "This" not in k.api_to_claim
        assert "Developers" not in k.api_to_claim
        assert "Each" not in k.api_to_claim

    def test_bold_takes_precedence_over_leading_word(self, tmp_path):
        """If claim has **Bold** names, leading word is not checked."""
        claims = [
            {
                "claim_id": "ERC-prec-001",
                "text": "The **AssetInfo** class stores metadata.",
            }
        ]
        api_surface = [
            {"name": "AssetInfo", "methods": [], "properties": [], "enum_members": [], "bases": []},
        ]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        assert k.api_to_claim.get("AssetInfo") == "ERC-prec-001"
        assert "The" not in k.api_to_claim


# ---------------------------------------------------------------------------
# knowledge_core.py — claim_ids set
# ---------------------------------------------------------------------------

class TestClaimIdsSet:
    """All claim IDs (CLM- and ERC-) must appear in self.claim_ids."""

    def test_erc_claims_in_claim_ids(self, tmp_path):
        k = _make_knowledge(tmp_path)
        assert "ERC-fake-001" in k.claim_ids
        assert "ERC-fake-002" in k.claim_ids
        assert "ERC-fake-003" in k.claim_ids
        assert "ERC-fake-004" in k.claim_ids

    def test_clm_claims_in_claim_ids(self, tmp_path):
        k = _make_knowledge(tmp_path)
        assert "CLM-3d-001abc" in k.claim_ids
        assert "CLM-3d-005abc" in k.claim_ids


# ---------------------------------------------------------------------------
# evidence/mapper.py — constructor fallback and class-only fallback
# ---------------------------------------------------------------------------

class TestMapperFallback:
    """mapper._map_tokens_to_evidence falls back to class-only key for ERC-."""

    def test_constructor_init_resolves_to_erc(self, tmp_path):
        """A token with member_name='__init__' falls back to class-only → ERC-."""
        from unittest.mock import MagicMock
        from evidence.mapper import _map_tokens_to_evidence

        k = _make_knowledge(tmp_path)

        # Simulate a token for Scene() constructor call
        tok = MagicMock()
        tok.class_name = "Scene"
        tok.member_name = "__init__"

        claim_ids, api_refs = _map_tokens_to_evidence([tok], k)
        assert "ERC-fake-001" in claim_ids

    def test_method_call_uses_clm_first(self, tmp_path):
        """A token for Scene.open should resolve to CLM-, not ERC-."""
        from unittest.mock import MagicMock
        from evidence.mapper import _map_tokens_to_evidence

        k = _make_knowledge(tmp_path)

        tok = MagicMock()
        tok.class_name = "Scene"
        tok.member_name = "open"

        claim_ids, api_refs = _map_tokens_to_evidence([tok], k)
        assert "CLM-3d-001abc" in claim_ids

    def test_unknown_method_falls_back_to_erc(self, tmp_path):
        """A token for Scene.some_unknown_method falls back to class-only ERC-."""
        from unittest.mock import MagicMock
        from evidence.mapper import _map_tokens_to_evidence

        k = _make_knowledge(tmp_path)

        tok = MagicMock()
        tok.class_name = "Scene"
        tok.member_name = "some_unknown_method"

        claim_ids, api_refs = _map_tokens_to_evidence([tok], k)
        # Should fall back to class-only key → ERC-fake-001
        assert "ERC-fake-001" in claim_ids


# ---------------------------------------------------------------------------
# knowledge_core.py — CLM- property claim indexing (Bug E1 fix — 2026-04-07)
# ---------------------------------------------------------------------------

class TestCLMPropertyClaims:
    """CLM- property/field claims must be indexed in api_to_claim (format:
    'ClassName.member property of type X').  Before the fix only method claims
    (with parens) were indexed; property claims were silently dropped."""

    def test_property_claim_indexed(self, tmp_path):
        """'AutoFilter.Range property of type string' → api_to_claim['AutoFilter.Range']."""
        claims = [
            {
                "claim_id": "CLM-prop-001",
                "text": "AutoFilter.Range property of type string",
                "kind": "property",
            }
        ]
        api_surface = [
            {"name": "AutoFilter", "methods": [], "properties": ["Range"],
             "enum_members": [], "bases": []},
        ]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        assert k.api_to_claim.get("AutoFilter.Range") == "CLM-prop-001", (
            "CLM- property claim 'AutoFilter.Range property of type string' must be "
            "indexed under 'AutoFilter.Range' in api_to_claim."
        )

    def test_field_claim_indexed(self, tmp_path):
        """'Cell.Value field of type object' → api_to_claim['Cell.Value']."""
        claims = [
            {"claim_id": "CLM-field-001", "text": "Cell.Value field of type object", "kind": "field"},
        ]
        api_surface = [
            {"name": "Cell", "methods": [], "properties": ["Value"],
             "enum_members": [], "bases": []},
        ]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        assert k.api_to_claim.get("Cell.Value") == "CLM-field-001"

    def test_event_claim_indexed(self, tmp_path):
        """'Workbook.Saved event of type EventHandler' → api_to_claim['Workbook.Saved']."""
        claims = [
            {"claim_id": "CLM-evt-001", "text": "Workbook.Saved event of type EventHandler"},
        ]
        api_surface = [
            {"name": "Workbook", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
        ]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        assert k.api_to_claim.get("Workbook.Saved") == "CLM-evt-001"

    def test_method_claim_still_indexed(self, tmp_path):
        """Method claims (with parens) continue to work alongside property claims."""
        claims = [
            {"claim_id": "CLM-method-001", "text": "Workbook.Save(path) -> void"},
            {"claim_id": "CLM-prop-002", "text": "Workbook.FileName property of type string"},
        ]
        api_surface = [
            {"name": "Workbook", "methods": ["Save"], "properties": ["FileName"],
             "enum_members": [], "bases": []},
        ]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        assert k.api_to_claim.get("Workbook.Save") == "CLM-method-001"
        assert k.api_to_claim.get("Workbook.FileName") == "CLM-prop-002"

    def test_method_wins_over_property_for_same_key(self, tmp_path):
        """If a CLM- method and property share the same key, CLM- sorts first wins."""
        # CLM- sorts before CLM- (same prefix); alphabetical order determines winner.
        # "CLM-a" < "CLM-b", so CLM-a wins.
        claims = [
            {"claim_id": "CLM-a-001", "text": "Obj.Member(args) -> void"},  # method
            {"claim_id": "CLM-b-001", "text": "Obj.Member property of type X"},  # property
        ]
        api_surface = [
            {"name": "Obj", "methods": ["Member"], "properties": ["Member"],
             "enum_members": [], "bases": []},
        ]
        k = _make_knowledge(tmp_path, api_surface=api_surface, claims=claims)
        # First claim wins (alphabetically smallest claim_id = CLM-a-001)
        assert k.api_to_claim.get("Obj.Member") == "CLM-a-001"

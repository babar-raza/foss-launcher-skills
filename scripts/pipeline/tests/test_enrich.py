"""Tests for enrich.py — pure helpers and no-LLM mode.

Covers:
  - _tokenize: pure function
  - _is_duplicate: deduplication logic
  - _validate_claim: confidence and kind filtering
  - _docstring_coverage: pure function
  - _extract_api_names: pure function
  - _assign_ids: ID assignment
  - enrich() with no_llm=True: writes empty output, returns True
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import enrich as _enrich_module
from enrich import (
    _tokenize,
    _is_duplicate,
    _validate_claim,
    _docstring_coverage,
    _extract_api_names,
    _assign_ids,
    enrich,
    _build_member_doc_facts,
    _build_member_doc_prompt,
    _build_prompt,
    _DEDUP_OVERLAP_THRESHOLD,
    _MIN_CONFIDENCE,
    _CLAIM_KINDS,
    _VALID_PAGE_ROLES,
)


# ---------------------------------------------------------------------------
# _tokenize — pure function
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic(self):
        result = _tokenize("Workbook supports loading files")
        assert "workbook" in result
        assert "supports" in result

    def test_returns_set(self):
        assert isinstance(_tokenize("hello"), set)

    def test_empty(self):
        assert _tokenize("") == set()

    def test_lowercased(self):
        assert "workbook" in _tokenize("WORKBOOK")


# ---------------------------------------------------------------------------
# _is_duplicate — deduplication logic
# ---------------------------------------------------------------------------

class TestIsDuplicate:
    def test_identical_texts_are_duplicate(self):
        claim = {"text": "Workbook loads xlsx files efficiently"}
        existing = [{"text": "Workbook loads xlsx files efficiently"}]
        assert _is_duplicate(claim, existing)

    def test_high_overlap_is_duplicate(self):
        # Overlap >= _DEDUP_OVERLAP_THRESHOLD (0.7)
        claim = {"text": "workbook loads xlsx spreadsheet files save"}
        existing = [{"text": "workbook loads xlsx spreadsheet files export"}]
        # Compute overlap manually: shared = workbook, loads, xlsx, spreadsheet, files
        # union ~ 7 words → overlap 5/7 ~ 0.71 > 0.7 → duplicate
        assert _is_duplicate(claim, existing)

    def test_low_overlap_is_not_duplicate(self):
        claim = {"text": "generate pdf report output document export"}
        existing = [{"text": "workbook loads xlsx spreadsheet files save"}]
        assert not _is_duplicate(claim, existing)

    def test_empty_candidate_is_not_duplicate(self):
        assert not _is_duplicate({"text": ""}, [{"text": "something here"}])

    def test_empty_existing_list(self):
        assert not _is_duplicate({"text": "Workbook loads files"}, [])

    def test_threshold_constant_is_used(self):
        # Verify the threshold used matches the module constant
        claim = {"text": "a b c d e f g h i j"}
        # Create existing claim that shares exactly threshold fraction
        existing = [{"text": "a b c d e f g h i j"}]
        assert _is_duplicate(claim, existing)

    def test_api_method_overloads_not_merged(self):
        """Method overloads that differ only by one parameter must survive dedup."""
        candidate = {"text": "Document.Save(string, SaveOptions)", "kind": "api_method"}
        existing = [{"text": "Document.Save(string)", "kind": "api_method"}]
        assert not _is_duplicate(candidate, existing)

    def test_api_method_exact_duplicate_still_merged(self):
        """Identical api_method claims are still detected as duplicates."""
        candidate = {"text": "Document.Save(string)", "kind": "api_method"}
        existing = [{"text": "Document.Save(string)", "kind": "api_method"}]
        assert _is_duplicate(candidate, existing)

    def test_feature_claims_still_use_jaccard(self):
        """Non-API claims above 0.7 Jaccard overlap are still merged."""
        candidate = {"text": "workbook loads xlsx spreadsheet files save", "kind": "feature"}
        existing = [{"text": "workbook loads xlsx spreadsheet files export", "kind": "feature"}]
        assert _is_duplicate(candidate, existing)

    def test_api_constructor_overloads_not_merged(self):
        """Constructor overloads must survive dedup."""
        candidate = {"text": "Workbook(string, LoadOptions)", "kind": "api_constructor"}
        existing = [{"text": "Workbook(string)", "kind": "api_constructor"}]
        assert not _is_duplicate(candidate, existing)

    def test_mixed_kind_api_vs_feature_uses_exact(self):
        """When one claim is api_method, exact match is required even if other is feature."""
        candidate = {"text": "workbook loads xlsx spreadsheet files save", "kind": "api_method"}
        existing = [{"text": "workbook loads xlsx spreadsheet files export", "kind": "feature"}]
        assert not _is_duplicate(candidate, existing)


# ---------------------------------------------------------------------------
# _validate_claim — filtering
# ---------------------------------------------------------------------------

class TestValidateClaim:
    def _api_names(self):
        return {"workbook", "save", "worksheet", "addrow"}

    def test_valid_claim_passes(self):
        claim = {
            "text": "Workbook supports saving xlsx files.",
            "kind": "api",
            "confidence": 0.9,
        }
        assert _validate_claim(claim, self._api_names())

    def test_low_confidence_rejected(self):
        claim = {"text": "Some claim.", "kind": "api", "confidence": _MIN_CONFIDENCE - 0.01}
        assert not _validate_claim(claim, self._api_names())

    def test_exact_min_confidence_accepted(self):
        claim = {"text": "Workbook loads data.", "kind": "api", "confidence": _MIN_CONFIDENCE}
        assert _validate_claim(claim, self._api_names())

    def test_invalid_kind_rejected(self):
        claim = {"text": "Some text.", "kind": "unknown_kind", "confidence": 0.9}
        assert not _validate_claim(claim, set())

    def test_missing_text_rejected(self):
        claim = {"kind": "api", "confidence": 0.9}
        assert not _validate_claim(claim, set())

    def test_missing_kind_rejected(self):
        claim = {"text": "Workbook loads data.", "confidence": 0.9}
        assert not _validate_claim(claim, set())

    def test_non_dict_rejected(self):
        assert not _validate_claim("not a dict", set())
        assert not _validate_claim(None, set())

    def test_camelcase_with_known_api_passes(self):
        claim = {"text": "Use Workbook.Save to export files.", "kind": "api", "confidence": 0.8}
        assert _validate_claim(claim, {"workbook", "save"})

    def test_camelcase_with_unknown_api_rejected(self):
        # CamelCase word not in known API names → hallucination check fails
        claim = {"text": "Use FakeClass.DoSomething to export.", "kind": "api", "confidence": 0.8}
        assert not _validate_claim(claim, {"workbook", "save"})

    def test_all_valid_kinds_accepted(self):
        api_names = set()
        for kind in _CLAIM_KINDS:
            claim = {"text": "plain text without camelcase.", "kind": kind, "confidence": 0.8}
            assert _validate_claim(claim, api_names), f"kind={kind!r} should be valid"


# ---------------------------------------------------------------------------
# _docstring_coverage — pure function
# ---------------------------------------------------------------------------

class TestDocstringCoverage:
    def test_all_with_docs(self):
        api = [
            {"name": "Workbook", "doc": "Represents a workbook."},
            {"name": "Worksheet", "doc": "Represents a worksheet."},
        ]
        assert _docstring_coverage(api) == 1.0

    def test_none_with_docs(self):
        api = [
            {"name": "Workbook", "doc": ""},
            {"name": "Worksheet", "doc": ""},
        ]
        assert _docstring_coverage(api) == 0.0

    def test_partial(self):
        api = [
            {"name": "Workbook", "doc": "Has a doc."},
            {"name": "Worksheet", "doc": ""},
        ]
        assert _docstring_coverage(api) == 0.5

    def test_private_classes_excluded(self):
        api = [
            {"name": "_Internal", "doc": "Has doc."},
            {"name": "Public", "doc": ""},
        ]
        # _Internal is excluded (starts with _), only Public counts → 0/1 = 0.0
        assert _docstring_coverage(api) == 0.0

    def test_empty_api_surface(self):
        assert _docstring_coverage([]) == 0.0


# ---------------------------------------------------------------------------
# _extract_api_names — pure function
# ---------------------------------------------------------------------------

class TestExtractApiNames:
    def test_extracts_class_and_method_names(self):
        api = [
            {"name": "Workbook",
             "methods": [{"name": "save"}, {"name": "load"}],
             "properties": [{"name": "FileName"}],
             "enum_members": []},
        ]
        names = _extract_api_names(api)
        assert "workbook" in names
        assert "save" in names
        assert "load" in names
        assert "filename" in names

    def test_extracts_enum_members(self):
        api = [{"name": "ExportFormat", "enum_members": [{"name": "PDF"}, "XLSX"]}]
        names = _extract_api_names(api)
        assert "pdf" in names
        assert "xlsx" in names

    def test_empty_api_returns_empty_set(self):
        assert _extract_api_names([]) == set()


# ---------------------------------------------------------------------------
# _assign_ids — ID assignment
# ---------------------------------------------------------------------------

class TestAssignIds:
    def test_assigns_erc_id(self):
        claims = [{"text": "Workbook loads files.", "kind": "api", "confidence": 0.9}]
        result = _assign_ids(claims, "cells", "python")
        assert result[0]["claim_id"].startswith("ERC-")
        assert "cells" in result[0]["claim_id"]
        assert "python" in result[0]["claim_id"]

    def test_overwrites_sequential_erc_id(self):
        # LLM batches produce sequential IDs (ERC-001, ERC-002, ...) that must
        # be replaced with stable hash-based IDs to prevent cross-batch duplicates.
        import hashlib
        claims = [{"text": "text", "kind": "api", "claim_id": "ERC-cells-python-001"}]
        result = _assign_ids(claims, "cells", "python")
        expected = "ERC-cells-python-" + hashlib.sha256(
            ("text" + "|" + "api").encode()
        ).hexdigest()[:8]
        assert result[0]["claim_id"] == expected

    def test_stable_for_same_text(self):
        claims1 = [{"text": "Workbook loads xlsx.", "kind": "api"}]
        claims2 = [{"text": "Workbook loads xlsx.", "kind": "api"}]
        r1 = _assign_ids(claims1, "cells", "python")
        r2 = _assign_ids(claims2, "cells", "python")
        assert r1[0]["claim_id"] == r2[0]["claim_id"]

    def test_globally_unique_ids_large_batch(self):
        """100 claims with distinct text+kind must produce 100 unique IDs."""
        claims = [
            {"text": f"Method_{i}() does thing {i}.", "kind": f"kind_{i % 5}"}
            for i in range(100)
        ]
        result = _assign_ids(claims, "slides", "java")
        ids = [c["claim_id"] for c in result]
        assert len(set(ids)) == len(ids), (
            f"Hash collision: {len(ids)} claims but only {len(set(ids))} unique IDs"
        )


# ---------------------------------------------------------------------------
# enrich() with no_llm=True — integration smoke test
# ---------------------------------------------------------------------------

class TestEnrichNoLlm:
    def _setup_scout_dir(self, tmp_path: Path) -> Path:
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        return scout_dir

    def test_no_llm_returns_true(self, tmp_path):
        self._setup_scout_dir(tmp_path)
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        assert result is True

    def test_no_llm_writes_output_file(self, tmp_path):
        scout_dir = self._setup_scout_dir(tmp_path)
        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        out_path = scout_dir / "enriched_claims.json"
        assert out_path.exists(), "enriched_claims.json must be written"

    def test_no_llm_output_is_valid_json(self, tmp_path):
        scout_dir = self._setup_scout_dir(tmp_path)
        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "claims" in data

    def test_no_llm_output_has_empty_claims(self, tmp_path):
        scout_dir = self._setup_scout_dir(tmp_path)
        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        assert data["claims"] == []


# ---------------------------------------------------------------------------
# enrich() with rehash_only=True — re-hash existing claims without LLM
# ---------------------------------------------------------------------------

class TestEnrichRehashOnly:
    def _setup_with_existing(self, tmp_path: Path) -> Path:
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        # Write existing enriched claims with sequential (buggy) IDs
        existing = {
            "generated_at": "2026-04-04T00:00:00",
            "model": "gpt-oss",
            "source": "enrich.py (S-37)",
            "family": "cells",
            "platform": "python",
            "api_surface_sha": "abc123",
            "claim_count": 3,
            "claims": [
                {"text": "Workbook loads xlsx files.", "kind": "api", "confidence": 0.95, "claim_id": "ERC-cells-python-001"},
                {"text": "Workbook.save() writes xlsx output.", "kind": "api", "confidence": 0.9, "claim_id": "ERC-cells-python-002"},
                {"text": "Workbook supports CSV import.", "kind": "feature", "confidence": 0.85, "claim_id": "ERC-cells-python-001"},
            ],
        }
        (scout_dir / "enriched_claims.json").write_text(json.dumps(existing), encoding="utf-8")
        return scout_dir

    def test_rehash_only_returns_true(self, tmp_path):
        self._setup_with_existing(tmp_path)
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), rehash_only=True)
        assert result is True

    def test_rehash_only_preserves_claim_count(self, tmp_path):
        scout_dir = self._setup_with_existing(tmp_path)
        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), rehash_only=True)
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        assert len(data["claims"]) == 3

    def test_rehash_only_produces_unique_ids(self, tmp_path):
        """Two claims that had the same sequential ID must get different hash IDs."""
        scout_dir = self._setup_with_existing(tmp_path)
        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), rehash_only=True)
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        ids = [c["claim_id"] for c in data["claims"]]
        # All 3 claims have different text+kind combos → 3 unique IDs
        assert len(set(ids)) == 3, f"Expected 3 unique IDs, got {len(set(ids))}: {ids}"

    def test_rehash_only_eliminates_sequential_ids(self, tmp_path):
        scout_dir = self._setup_with_existing(tmp_path)
        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), rehash_only=True)
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        import re
        for c in data["claims"]:
            assert not re.match(r"^ERC-.*-\d{1,3}$", c["claim_id"]), \
                f"Sequential ID still present: {c['claim_id']}"

    def test_rehash_only_preserves_claim_text(self, tmp_path):
        scout_dir = self._setup_with_existing(tmp_path)
        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), rehash_only=True)
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        texts = sorted(c["text"] for c in data["claims"])
        assert texts == sorted([
            "Workbook loads xlsx files.",
            "Workbook.save() writes xlsx output.",
            "Workbook supports CSV import.",
        ])

    def test_missing_api_surface_returns_false(self, tmp_path):
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        # No api_surface.json
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        assert result is False


# ---------------------------------------------------------------------------
# _build_member_doc_facts — pure helper for FIX-1
# ---------------------------------------------------------------------------

class TestBuildMemberDocFacts:
    def _cls(self):
        return {
            "name": "Workbook",
            "methods": [
                {"name": "Save", "params": [{"name": "path", "type": "str"}], "return_type": "bool", "doc": ""},
                {"name": "Load", "params": [{"name": "path", "type": "str"}], "return_type": "void", "doc": "Loads from file."},
            ],
            "properties": [
                {"name": "FileName", "type": "str", "doc": ""},
                "Sheets",  # string-form property
            ],
        }

    def test_class_header_present(self):
        facts = _build_member_doc_facts(self._cls())
        assert "Class: Workbook" in facts

    def test_method_signatures_present(self):
        facts = _build_member_doc_facts(self._cls())
        assert "method Save" in facts
        assert "method Load" in facts

    def test_property_names_present(self):
        facts = _build_member_doc_facts(self._cls())
        assert "property FileName" in facts
        assert "property Sheets" in facts

    def test_private_members_excluded(self):
        cls = {"name": "Workbook", "methods": [{"name": "_internal", "params": [], "doc": ""}], "properties": []}
        facts = _build_member_doc_facts(cls)
        assert "_internal" not in facts

    def test_return_type_included(self):
        facts = _build_member_doc_facts(self._cls())
        assert "-> bool" in facts

    def test_doc_snippet_included_when_present(self):
        facts = _build_member_doc_facts(self._cls())
        assert "Loads from file" in facts


class TestBuildMemberDocPrompt:
    def _cls(self):
        return {
            "name": "Workbook",
            "methods": [{"name": "Save", "params": [], "return_type": "bool", "doc": ""}],
            "properties": [{"name": "FileName", "type": "str", "doc": ""}],
        }

    def test_returns_two_strings(self):
        sys_p, user_p = _build_member_doc_prompt("cells", "net", self._cls(), "")
        assert isinstance(sys_p, str)
        assert isinstance(user_p, str)

    def test_class_name_in_prompt(self):
        _, user_p = _build_member_doc_prompt("cells", "net", self._cls(), "")
        assert "Workbook" in user_p

    def test_member_doc_claim_source_in_instructions(self):
        _, user_p = _build_member_doc_prompt("cells", "net", self._cls(), "")
        assert "llm_member_doc" in user_p

    def test_classname_memberformat_rule_stated(self):
        _, user_p = _build_member_doc_prompt("cells", "net", self._cls(), "")
        assert "Workbook.MemberName" in user_p

    def test_json_array_output_format_stated(self):
        _, user_p = _build_member_doc_prompt("cells", "net", self._cls(), "")
        assert "JSON array" in user_p


# ---------------------------------------------------------------------------
# enrich() mode parameter — no_llm smoke test
# ---------------------------------------------------------------------------

class TestEnrichModeParameter:
    def _setup_scout_dir(self, tmp_path: Path) -> Path:
        scout_dir = tmp_path / "knowledge" / "cells" / "net" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "", "kind": "class",
             "file": "aspose/cells/workbook.cs",
             "methods": [{"name": "Save", "params": [], "return_type": "bool", "doc": ""}],
             "properties": [{"name": "FileName", "type": "str", "doc": ""}],
             "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        return scout_dir

    def test_member_doc_mode_no_llm_returns_true(self, tmp_path):
        """mode='member-doc' with no_llm=True must return True (idempotent)."""
        self._setup_scout_dir(tmp_path)
        result = enrich("cells", "net",
                        knowledge_root=str(tmp_path / "knowledge"),
                        no_llm=True, mode="member-doc")
        assert result is True

    def test_both_mode_no_llm_returns_true(self, tmp_path):
        self._setup_scout_dir(tmp_path)
        result = enrich("cells", "net",
                        knowledge_root=str(tmp_path / "knowledge"),
                        no_llm=True, mode="both")
        assert result is True

    def test_default_mode_is_capability(self, tmp_path):
        """Default mode (no mode kwarg) still works — backward compat."""
        self._setup_scout_dir(tmp_path)
        result = enrich("cells", "net",
                        knowledge_root=str(tmp_path / "knowledge"),
                        no_llm=True)
        assert result is True


# ---------------------------------------------------------------------------
# S-5: page_role field — validation, prompt, and ID stability
# ---------------------------------------------------------------------------

class TestPageRoleValidation:
    """Test that page_role is validated correctly in _validate_claim()."""

    def _api_names(self):
        return {"workbook", "save"}

    def test_valid_page_role_docs_passes(self):
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9, "page_role": "docs"}
        assert _validate_claim(claim, self._api_names())

    def test_valid_page_role_product_passes(self):
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9, "page_role": "product"}
        assert _validate_claim(claim, self._api_names())

    def test_valid_page_role_kb_passes(self):
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9, "page_role": "kb"}
        assert _validate_claim(claim, self._api_names())

    def test_valid_page_role_reference_passes(self):
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9, "page_role": "reference"}
        assert _validate_claim(claim, self._api_names())

    def test_invalid_page_role_rejected(self):
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9, "page_role": "invalid"}
        assert not _validate_claim(claim, self._api_names())

    def test_missing_page_role_passes_backward_compat(self):
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9}
        assert _validate_claim(claim, self._api_names())

    def test_validate_does_not_mutate_input(self):
        """_validate_claim must not add page_role key to dict that lacks it."""
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9}
        _validate_claim(claim, self._api_names())
        assert "page_role" not in claim

    def test_null_page_role_passes(self):
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.9, "page_role": None}
        assert _validate_claim(claim, self._api_names())

    def test_all_valid_page_roles_accepted(self):
        for role in _VALID_PAGE_ROLES:
            claim = {"text": "plain text no camelcase.", "kind": "api",
                     "confidence": 0.8, "page_role": role}
            assert _validate_claim(claim, set()), f"page_role={role!r} should be valid"


class TestPageRoleIdStability:
    """page_role must NOT affect claim ID (text + kind only)."""

    def test_same_id_regardless_of_page_role(self):
        claims_a = [{"text": "Workbook loads xlsx.", "kind": "api", "page_role": "docs"}]
        claims_b = [{"text": "Workbook loads xlsx.", "kind": "api", "page_role": "product"}]
        claims_c = [{"text": "Workbook loads xlsx.", "kind": "api"}]
        ra = _assign_ids(claims_a, "cells", "python")
        rb = _assign_ids(claims_b, "cells", "python")
        rc = _assign_ids(claims_c, "cells", "python")
        assert ra[0]["claim_id"] == rb[0]["claim_id"] == rc[0]["claim_id"]


class TestPageRoleInPrompt:
    """The capability prompt should include page_role instructions."""

    def test_capability_prompt_contains_page_role(self):
        _, user = _build_prompt("words", "python", "facts", "context")
        assert "page_role" in user
        assert "product" in user
        assert "docs" in user
        assert "kb" in user
        assert "reference" in user


class TestMemberDocPageRole:
    """Member-doc claims must get page_role='reference' automatically."""

    def test_member_doc_claim_gets_reference_role(self):
        """Simulate member-doc processing: validate then set page_role."""
        claim = {"text": "Workbook.Save writes the file.", "kind": "api",
                 "confidence": 0.80, "claim_source": "llm_member_doc"}
        api_names = {"workbook", "save"}
        assert _validate_claim(claim, api_names)
        # Member-doc loop sets page_role after validation
        claim["page_role"] = "reference"
        assert claim["page_role"] == "reference"

    def test_capability_claim_gets_none_via_setdefault(self):
        """Capability loop normalizes missing page_role to None via setdefault."""
        claim = {"text": "Workbook supports xlsx.", "kind": "api",
                 "confidence": 0.90}
        api_names = {"workbook"}
        assert _validate_claim(claim, api_names)
        claim.setdefault("page_role", None)
        assert claim["page_role"] is None


# ---------------------------------------------------------------------------
# TC-2: LLM error-response dict handling in enrich() capability loop
# ---------------------------------------------------------------------------

class TestEnrichLlmErrorResponse:
    """TC-2: enrich() must log ERROR and continue (not abort) when LLM returns
    a non-list dict without a 'claims' key (e.g. {"error": "rate_limited"}).
    """

    def _setup_scout_dir(self, tmp_path: Path) -> Path:
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        return scout_dir

    def test_llm_error_response_logs_error_and_does_not_raise(self, tmp_path, caplog):
        """LLM returns {"error": "rate_limited"} → ERROR logged; enrich() does not raise.

        TC-2 contract: the capability loop uses `continue` on error responses (not raise/break),
        so the ERROR log is emitted and the function exits cleanly (returns False because the
        write-protection guard fires when 0 claims are produced from a live-LLM run).
        """
        import logging
        self._setup_scout_dir(tmp_path)
        # VH-02 fix 1: mock preflight so LLM path is always taken regardless of environment
        with patch.object(_enrich_module, "_preflight_check", return_value={"professionalize": "ok"}), \
             patch.object(_enrich_module, "_llm_call", return_value=({"error": "rate_limited"}, "professionalize/gpt-oss")):
            with caplog.at_level(logging.DEBUG, logger="enrich"):
                result = enrich(
                    "cells", "python",
                    knowledge_root=str(tmp_path / "knowledge"),
                    no_llm=False,
                )
        # Write-protection guard fires (0 claims from live LLM) → False, not an exception
        assert result is False, (
            "enrich() must return False (write-protection guard) when LLM error response "
            "produces 0 claims — not raise an exception"
        )
        # VH-02 fix 2: use getMessage() not r.message (standard LogRecord API)
        error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("non-list" in msg for msg in error_msgs), (
            "Expected an ERROR log mentioning 'non-list' response; got ERROR messages: "
            + str(error_msgs)
        )

    def test_llm_error_response_writes_no_claims(self, tmp_path):
        """LLM returns {"error": "rate_limited"} → write-protection fires; no output file written."""
        scout_dir = self._setup_scout_dir(tmp_path)
        with patch.object(_enrich_module, "_llm_call", return_value=({"error": "rate_limited"}, "professionalize/gpt-oss")):
            enrich(
                "cells", "python",
                knowledge_root=str(tmp_path / "knowledge"),
                no_llm=False,
            )
        out_path = scout_dir / "enriched_claims.json"
        # Write-protection guard refuses to write 0-claim output from live LLM
        assert not out_path.exists(), (
            "enriched_claims.json must NOT be written when write-protection fires "
            "after an LLM error response"
        )


# ---------------------------------------------------------------------------
# TC-04: model_used accuracy
# ---------------------------------------------------------------------------

class TestModelUsedAccuracy:
    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    def test_model_field_shows_actual_provider(self, _mock_pre, _mock_clone, tmp_path):
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        claims = [
            {"text": "Workbook.save persists the workbook to disk.", "kind": "api",
             "confidence": 0.85, "grounding": ["Workbook"]}
        ]
        with patch("enrich._llm_call", return_value=(claims, "ollama/llama3.1:latest")):
            result = enrich("cells", "python",
                          knowledge_root=str(tmp_path / "knowledge"),
                          reports_root=str(tmp_path / "reports"))
        assert result is True
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        assert "ollama" in data["model"]


# ---------------------------------------------------------------------------
# TC-06: run_stats
# ---------------------------------------------------------------------------

class TestRunStats:
    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    def test_run_stats_in_output(self, _mock_pre, _mock_clone, tmp_path):
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        claims = [
            {"text": "Workbook.save persists the workbook to disk.", "kind": "api",
             "confidence": 0.85, "grounding": ["Workbook"]}
        ]
        with patch("enrich._llm_call", return_value=(claims, "professionalize/gpt-oss")):
            enrich("cells", "python",
                   knowledge_root=str(tmp_path / "knowledge"),
                   reports_root=str(tmp_path / "reports"))
        data = json.loads((scout_dir / "enriched_claims.json").read_text(encoding="utf-8"))
        assert "run_stats" in data
        rs = data["run_stats"]
        expected_keys = {
            "batches_attempted", "batches_succeeded", "batches_failed",
            "claims_raw", "claims_rejected", "claims_deduplicated",
            "claims_accepted", "claims_stub_demoted", "claims_final",
            "model_used", "preflight", "preserved_existing", "preserved_stale",
            "duration_seconds",
        }
        assert expected_keys.issubset(set(rs.keys()))
        assert rs["duration_seconds"] >= 0
        assert rs["batches_attempted"] == rs["batches_succeeded"]


# ---------------------------------------------------------------------------
# TC-07: enrichment report
# ---------------------------------------------------------------------------

class TestEnrichmentReport:
    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    def test_report_written(self, _mock_pre, _mock_clone, tmp_path):
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        claims = [
            {"text": "Workbook.save persists the workbook to disk.", "kind": "api",
             "confidence": 0.85, "grounding": ["Workbook"]}
        ]
        with patch("enrich._llm_call", return_value=(claims, "professionalize/gpt-oss")):
            enrich("cells", "python",
                   knowledge_root=str(tmp_path / "knowledge"),
                   reports_root=str(tmp_path / "reports"))
        report_dir = tmp_path / "reports" / "enrichment"
        assert report_dir.exists()
        reports = list(report_dir.glob("cells-python-*.json"))
        assert len(reports) >= 1
        report_data = json.loads(reports[0].read_text(encoding="utf-8"))
        assert report_data["family"] == "cells"
        assert "run_stats" in report_data


# ---------------------------------------------------------------------------
# TC-10: malformed enriched_claims.json warning
# ---------------------------------------------------------------------------

class TestMalformedEnrichedWarning:
    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    def test_malformed_json_warns(self, _mock_pre, _mock_clone, tmp_path, caplog):
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        (scout_dir / "enriched_claims.json").write_text("{broken", encoding="utf-8")
        claims = [
            {"text": "Workbook.save persists the workbook to disk.", "kind": "api",
             "confidence": 0.85, "grounding": ["Workbook"]}
        ]
        import logging
        with caplog.at_level(logging.WARNING):
            with patch("enrich._llm_call", return_value=(claims, "professionalize/gpt-oss")):
                enrich("cells", "python",
                       knowledge_root=str(tmp_path / "knowledge"),
                       reports_root=str(tmp_path / "reports"))
        assert any("Could not parse existing enriched_claims.json" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# TC-09T: Pipeline state manifest observability
# ---------------------------------------------------------------------------

class TestPipelineStateManifest:
    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    def test_manifest_contains_enrichment_fields(self, _mock_pre, _mock_clone, tmp_path):
        """TC-09: pipeline_state.json must include enrichment_status and run_stats_summary."""
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "aspose/cells/workbook.py",
             "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        claims = [
            {"text": "Workbook.save persists the workbook to disk.", "kind": "api",
             "confidence": 0.85, "grounding": ["Workbook"]}
        ]
        with patch("enrich._llm_call", return_value=(claims, "professionalize/gpt-oss")):
            enrich("cells", "python",
                   knowledge_root=str(tmp_path / "knowledge"),
                   reports_root=str(tmp_path / "reports"))

        # out_path.parents[2] resolves to knowledge/cells/ (not knowledge/cells/python/)
        state_path = tmp_path / "knowledge" / "cells" / ".pipeline_state.json"
        assert state_path.exists(), f"pipeline_state.json not found at {state_path}"
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        enrich_step = state_data.get("enrich", {})
        assert "enrichment_status" in enrich_step, f"Missing enrichment_status in {enrich_step.keys()}"
        assert enrich_step["enrichment_status"] == "success"
        assert "run_stats_summary" in enrich_step
        assert "batches" in enrich_step["run_stats_summary"]
        assert "rejected" in enrich_step["run_stats_summary"]


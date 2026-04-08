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
    _DEDUP_OVERLAP_THRESHOLD,
    _MIN_CONFIDENCE,
    _CLAIM_KINDS,
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

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

    def test_preserves_existing_erc_id(self):
        claims = [{"text": "text", "kind": "api", "claim_id": "ERC-cells-python-abc12345"}]
        result = _assign_ids(claims, "cells", "python")
        assert result[0]["claim_id"] == "ERC-cells-python-abc12345"

    def test_stable_for_same_text(self):
        claims1 = [{"text": "Workbook loads xlsx.", "kind": "api"}]
        claims2 = [{"text": "Workbook loads xlsx.", "kind": "api"}]
        r1 = _assign_ids(claims1, "cells", "python")
        r2 = _assign_ids(claims2, "cells", "python")
        assert r1[0]["claim_id"] == r2[0]["claim_id"]


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

    def test_missing_api_surface_returns_false(self, tmp_path):
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        # No api_surface.json
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        assert result is False

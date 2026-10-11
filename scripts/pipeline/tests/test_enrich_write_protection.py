"""Tests for enrich.py write protection (S1-4 fix).

Ensures that LLM failures never overwrite non-empty enriched_claims.json
with empty output, and that --no-llm preserves existing claims.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from enrich import enrich


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_scout_dir(tmp_path: Path, *, existing_claims: list | None = None) -> Path:
    """Create minimal scout directory with api_surface.json and optional existing enriched claims."""
    scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
    scout_dir.mkdir(parents=True)
    api_surface = [
        {"name": "Workbook", "doc": "A workbook.", "kind": "class",
         "file": "aspose/cells/workbook.py",
         "methods": [{"name": "save"}], "properties": [], "enum_members": []},
        {"name": "Worksheet", "doc": "A worksheet.", "kind": "class",
         "file": "aspose/cells/worksheet.py",
         "methods": [{"name": "get_cell"}], "properties": [], "enum_members": []},
    ]
    (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")

    if existing_claims is not None:
        existing_data = {
            "generated_at": "2026-04-10T00:00:00",
            "model": "gpt-oss",
            "source": "enrich.py (S-37)",
            "family": "cells",
            "platform": "python",
            "api_surface_sha": "abc123",
            "claim_count": len(existing_claims),
            "claims": existing_claims,
        }
        (scout_dir / "enriched_claims.json").write_text(
            json.dumps(existing_data), encoding="utf-8"
        )
    return scout_dir


_SAMPLE_CLAIMS = [
    {
        "claim_id": "ERC-cells-python-aabbccdd",
        "text": "Workbook supports loading XLSX files.",
        "kind": "capability",
        "confidence": 0.85,
        "grounding": ["Workbook"],
        "page_role": None,
    },
    {
        "claim_id": "ERC-cells-python-eeff0011",
        "text": "Worksheet provides cell access methods.",
        "kind": "capability",
        "confidence": 0.80,
        "grounding": ["Worksheet"],
        "page_role": None,
    },
]


# ---------------------------------------------------------------------------
# Write protection: empty claims on LLM failure
# ---------------------------------------------------------------------------

class TestWriteProtectionLlmFailure:
    """When LLM fails and produces 0 new claims, enriched_claims.json must NOT be overwritten."""

    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    @patch("enrich._llm_call", return_value=(None, ""))
    def test_empty_claims_returns_false_on_llm_failure(self, _mock_llm, _mock_pre, _mock_clone, tmp_path):
        """First run (no existing file) + LLM failure = return False, no file written."""
        scout_dir = _setup_scout_dir(tmp_path)
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"))
        assert result is False
        out_path = scout_dir / "enriched_claims.json"
        assert not out_path.exists(), "Empty enriched_claims.json must NOT be written on LLM failure"

    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    @patch("enrich._llm_call", return_value=(None, ""))
    def test_existing_claims_preserved_on_llm_failure(self, _mock_llm, _mock_pre, _mock_clone, tmp_path):
        """Existing claims + LLM failure = return True, existing file untouched."""
        scout_dir = _setup_scout_dir(tmp_path, existing_claims=_SAMPLE_CLAIMS)
        out_path = scout_dir / "enriched_claims.json"
        original_content = out_path.read_text(encoding="utf-8")

        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"))
        assert result is True

        # File must still exist with original content (not rewritten)
        assert out_path.exists()
        current_content = out_path.read_text(encoding="utf-8")
        assert current_content == original_content, "Existing claims must be preserved without rewrite"

    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "ok"})
    @patch("enrich._llm_call", return_value=(None, ""))
    def test_existing_claims_count_unchanged_on_llm_failure(self, _mock_llm, _mock_pre, _mock_clone, tmp_path):
        """Existing claims must retain their count after LLM failure."""
        _setup_scout_dir(tmp_path, existing_claims=_SAMPLE_CLAIMS)
        scout_dir = tmp_path / "knowledge" / "cells" / "python" / "scout"
        out_path = scout_dir / "enriched_claims.json"

        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"))

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(data["claims"]) == len(_SAMPLE_CLAIMS)


# ---------------------------------------------------------------------------
# --no-llm protection: preserve existing claims
# ---------------------------------------------------------------------------

class TestNoLlmPreservesExisting:
    """--no-llm must not overwrite existing enriched claims."""

    def test_no_llm_preserves_existing_claims(self, tmp_path):
        """--no-llm with existing claims = return True, file untouched."""
        scout_dir = _setup_scout_dir(tmp_path, existing_claims=_SAMPLE_CLAIMS)
        out_path = scout_dir / "enriched_claims.json"
        original_content = out_path.read_text(encoding="utf-8")

        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        assert result is True

        current_content = out_path.read_text(encoding="utf-8")
        assert current_content == original_content, "--no-llm must not overwrite existing claims"

    def test_no_llm_writes_empty_when_no_existing(self, tmp_path):
        """--no-llm with no existing file = write empty file (original behavior)."""
        scout_dir = _setup_scout_dir(tmp_path)
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)
        assert result is True

        out_path = scout_dir / "enriched_claims.json"
        assert out_path.exists()
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["claims"] == []

    def test_no_llm_existing_claim_count_preserved(self, tmp_path):
        """--no-llm must not reduce claim count."""
        scout_dir = _setup_scout_dir(tmp_path, existing_claims=_SAMPLE_CLAIMS)
        out_path = scout_dir / "enriched_claims.json"

        enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"), no_llm=True)

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(data["claims"]) == len(_SAMPLE_CLAIMS)


# ---------------------------------------------------------------------------
# TC-05: Preflight failure preservation
# ---------------------------------------------------------------------------

class TestPreflightPreservation:

    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "unreachable", "ollama": "unreachable"})
    def test_preflight_fail_preserves_existing(self, _mock_pre, _mock_clone, tmp_path):
        scout_dir = _setup_scout_dir(tmp_path, existing_claims=_SAMPLE_CLAIMS)
        out_path = scout_dir / "enriched_claims.json"
        original_content = out_path.read_text(encoding="utf-8")
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"))
        assert result is False
        assert out_path.exists()
        assert out_path.read_text(encoding="utf-8") == original_content

    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "unreachable", "ollama": "unreachable"})
    def test_preflight_fail_no_file_created(self, _mock_pre, _mock_clone, tmp_path):
        scout_dir = _setup_scout_dir(tmp_path)
        out_path = scout_dir / "enriched_claims.json"
        result = enrich("cells", "python", knowledge_root=str(tmp_path / "knowledge"))
        assert result is False
        assert not out_path.exists()

# ---------------------------------------------------------------------------
# TC-08T: Stale SHA mismatch detection on preflight failure
# ---------------------------------------------------------------------------

class TestPreflightStaleDetection:

    @patch("enrich.clone_exists", return_value=False)
    @patch("enrich._preflight_check", return_value={"professionalize": "unreachable", "ollama": "unreachable"})
    def test_preflight_preserves_stale_claims_with_warning(self, _mock_pre, _mock_clone, tmp_path, caplog):
        """TC-08: When preflight fails and preserved claims have mismatched api_surface_sha,
        run_stats should flag preserved_stale=True and log a warning."""
        import logging
        scout_dir = _setup_scout_dir(tmp_path, existing_claims=_SAMPLE_CLAIMS)
        # _setup_scout_dir writes api_surface_sha="abc123" which differs from computed SHA
        out_path = scout_dir / "enriched_claims.json"
        assert out_path.exists()

        with caplog.at_level(logging.WARNING):
            result = enrich("cells", "python",
                           knowledge_root=str(tmp_path / "knowledge"),
                           reports_root=str(tmp_path / "reports"))

        assert result is False
        assert out_path.exists()  # preserved

        # Check report for preserved_stale flag
        report_dir = tmp_path / "reports" / "enrichment"
        reports = list(report_dir.glob("cells-python-*.json"))
        assert len(reports) >= 1
        import json as _json
        report = _json.loads(reports[0].read_text(encoding="utf-8"))
        assert report["run_stats"]["preserved_stale"] is True

        # Check warning was logged
        assert any("STALE" in msg for msg in caplog.messages)


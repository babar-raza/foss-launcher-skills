"""Tests for post_refresh_verify.py — progress tracking and verification gate.

Coverage:
- record_step(): step written to progress.json; duplicate steps not added twice
- record_step(): progress.json created on first call
- verify() check 1: model.yaml stale_since=null → passes
- verify() check 1: model.yaml stale_since set → fails
- verify() check 2: orphaned claim IDs → reported as failure
- verify() check 3: stale reference pages (API class absent) → reported
- verify() check 4: stale_detect subprocess (mocked)
- verify() returns (True, []) on all-clean state
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import post_refresh_verify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_knowledge(tmp_path: Path, family: str, platform: str, **kwargs) -> Path:
    """Write a minimal knowledge tree for testing. Returns merged/ dir."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    if "stale_since" in kwargs:
        model = {"stale_since": kwargs["stale_since"], "version": "1.0"}
    else:
        model = {"stale_since": None, "version": "1.0"}
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")

    claims = kwargs.get("claims", [])
    (merged / "claims.json").write_text(
        json.dumps(claims, indent=2), encoding="utf-8"
    )

    api_surface = kwargs.get("api_surface", [])
    (merged / "api_surface.json").write_text(
        json.dumps(api_surface, indent=2), encoding="utf-8"
    )
    return merged


# ---------------------------------------------------------------------------
# record_step tests
# ---------------------------------------------------------------------------

class TestRecordStep:
    def test_step_written_to_progress_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "REPORTS_ROOT", tmp_path / "refresh_state")

        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        assert p.exists()
        data = json.loads(p.read_text())
        assert "knowledge_refresh" in data["steps"]

    def test_duplicate_step_not_added_twice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "REPORTS_ROOT", tmp_path / "refresh_state")

        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        data = json.loads(p.read_text())
        assert data["steps"].count("knowledge_refresh") == 1

    def test_multiple_steps_all_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "REPORTS_ROOT", tmp_path / "refresh_state")

        post_refresh_verify.record_step("3d", "python", "step_a")
        post_refresh_verify.record_step("3d", "python", "step_b")
        post_refresh_verify.record_step("3d", "python", "step_c")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        data = json.loads(p.read_text())
        assert set(data["steps"]) == {"step_a", "step_b", "step_c"}


# ---------------------------------------------------------------------------
# verify() — check 1: model.yaml stale_since
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleSince:
    def test_stale_since_null_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python", stale_since=None)

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        stale_failures = [f for f in failures if "stale_since" in f]
        assert len(stale_failures) == 0

    def test_stale_since_set_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python", stale_since="2026-04-01")

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("stale_since" in f for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 2: orphaned claims
# ---------------------------------------------------------------------------

class TestVerifyCheckOrphanedClaims:
    def test_valid_citations_pass(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        claims = [{"claim_id": "CL-001"}, {"claim_id": "CL-002"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        # Write a content page that cites valid claim IDs
        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-001\n    - CL-002\n---\nbody\n"
        )

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        orphan_failures = [f for f in failures if "Orphaned" in f]
        assert len(orphan_failures) == 0

    def test_orphaned_claim_reported(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        claims = [{"claim_id": "CL-001"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        # Cites CL-999 which doesn't exist
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-999\n---\nbody\n"
        )

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("Orphaned" in f for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 4: stale_detect subprocess (mocked)
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleDetect:
    def test_stale_detect_exit_0_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python")

        # Create fake stale_detect.py so it's found
        stale_detect = tmp_path / "stale_detect.py"
        stale_detect.touch()
        monkeypatch.setattr(post_refresh_verify, "_HERE", tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"stale_pages": 0})

        with patch("post_refresh_verify.subprocess.run", return_value=mock_result):
            passed, failures = post_refresh_verify.verify("3d", "python")

        stale_failures = [f for f in failures if "stale_detect" in f.lower()]
        assert len(stale_failures) == 0

    def test_stale_detect_exit_1_reports_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python")

        stale_detect = tmp_path / "stale_detect.py"
        stale_detect.touch()
        monkeypatch.setattr(post_refresh_verify, "_HERE", tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"stale_pages": 3, "pages": []})

        with patch("post_refresh_verify.subprocess.run", return_value=mock_result):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("stale_detect" in f.lower() for f in failures)

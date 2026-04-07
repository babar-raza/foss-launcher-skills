"""Tests for scripts/pipeline/refresh_knowledge.py — TC-02 additions.

Tests cover:
- knowledge_delta.json is written with correct structure after a successful refresh
- --check-only returns "stale" without modifying any file
- --no-auto-fetch skips update_clone call
- knowledge_delta.json is NOT written when promote.py fails
- Graceful handling when no clone exists
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

_PIPELINE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claims(ids: list[str]) -> list[dict]:
    return [
        {"claim_id": cid, "kind": "api_method", "text": f"text for {cid}", "confidence": 1.0}
        for cid in ids
    ]


def _make_apis(names: list[str]) -> list[dict]:
    return [{"name": n, "kind": "class_declaration", "methods": [], "properties": []} for n in names]


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_model_yaml(path: Path, repo_sha: str, stale_since=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"repo_sha": repo_sha, "stale_since": stale_since, "family": "testfam", "platform": "testplat"}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixture: minimal knowledge directory tree
# ---------------------------------------------------------------------------

@pytest.fixture()
def knowledge_dir(tmp_path):
    """Set up a fake knowledge directory with old claims/apis and model.yaml."""
    family, platform = "testfam", "testplat"
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    _write_json(merged / "claims.json", _make_claims(["CLM-old-001", "CLM-old-002"]))
    _write_json(merged / "api_surface.json", _make_apis(["OldClass", "SharedClass"]))
    _write_model_yaml(merged / "model.yaml", repo_sha="aabbccdd" * 5)

    return tmp_path, family, platform, merged


# ---------------------------------------------------------------------------
# Happy path: knowledge_delta.json written after successful refresh
# ---------------------------------------------------------------------------

def test_write_knowledge_delta_correct_structure(knowledge_dir):
    """_write_knowledge_delta produces correct delta structure."""
    tmp_path, family, platform, merged = knowledge_dir

    # Set up bak dir (old state)
    bak_dir = tmp_path / "knowledge" / family / platform / "merged.bak"
    bak_dir.mkdir(parents=True)
    _write_json(bak_dir / "claims.json", _make_claims(["CLM-old-001", "CLM-old-002"]))
    _write_json(bak_dir / "api_surface.json", _make_apis(["OldClass", "SharedClass"]))

    # Update merged (new state): remove CLM-old-002, add CLM-new-001, keep CLM-old-001 modified
    new_claims = [
        {"claim_id": "CLM-old-001", "kind": "api_method", "text": "MODIFIED TEXT", "confidence": 1.0},
        {"claim_id": "CLM-new-001", "kind": "api_method", "text": "new claim", "confidence": 0.9},
    ]
    _write_json(merged / "claims.json", new_claims)
    _write_json(merged / "api_surface.json", _make_apis(["NewClass", "SharedClass"]))

    import refresh_knowledge as rk
    rk._write_knowledge_delta(family, platform, bak_dir, merged, "newsha123" * 5, "oldsha123" * 5)

    delta_path = merged / "knowledge_delta.json"
    assert delta_path.is_file()

    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    assert set(delta.keys()) == {
        "generated_at", "base_sha", "current_sha",
        "new_claims", "removed_claims", "modified_claims",
        "new_apis", "removed_apis", "modified_apis",
    }
    assert delta["new_claims"] == ["CLM-new-001"]
    assert delta["removed_claims"] == ["CLM-old-002"]
    assert delta["modified_claims"] == ["CLM-old-001"]
    assert delta["new_apis"] == ["NewClass"]
    assert delta["removed_apis"] == ["OldClass"]
    assert delta["modified_apis"] == []  # SharedClass not modified (same members)
    assert delta["current_sha"] == "newsha123" * 5
    assert delta["base_sha"] == "oldsha123" * 5


# ---------------------------------------------------------------------------
# Happy path: --check-only returns "stale" without modifying any file
# ---------------------------------------------------------------------------

def test_refresh_check_only_no_modifications(knowledge_dir, monkeypatch):
    """refresh(..., check_only=True) returns 'stale' without touching any file."""
    tmp_path, family, platform, merged = knowledge_dir
    model_path = merged / "model.yaml"
    before_mtime = model_path.stat().st_mtime
    delta_path = merged / "knowledge_delta.json"

    import refresh_knowledge as rk

    # Patch KNOWLEDGE_ROOT to use tmp
    monkeypatch.setattr(rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge")

    # Patch clone to return a different SHA (stale)
    monkeypatch.setattr(rk, "_clone_dir", lambda f, p: tmp_path / "fake_clone")
    monkeypatch.setattr(rk, "_head_sha", lambda path: "ffff0000" * 5)

    # Patch update_clone to return same "upstream" sha
    monkeypatch.setattr(rk, "_update_clone", lambda f, p: "ffff0000" * 5)

    result = rk.refresh(family, platform, check_only=True, auto_fetch=True)

    assert result == "stale"
    # model.yaml must NOT have changed mtime
    assert model_path.stat().st_mtime == before_mtime
    # knowledge_delta.json must NOT be written
    assert not delta_path.exists()


# ---------------------------------------------------------------------------
# Happy path: --no-auto-fetch skips update_clone call
# ---------------------------------------------------------------------------

def test_refresh_no_auto_fetch_skips_update_clone(knowledge_dir, monkeypatch):
    """refresh(..., auto_fetch=False) never calls update_clone."""
    tmp_path, family, platform, merged = knowledge_dir

    import refresh_knowledge as rk
    monkeypatch.setattr(rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
    monkeypatch.setattr(rk, "_clone_dir", lambda f, p: tmp_path / "fake_clone")

    # Clone HEAD matches model SHA → "current" without needing to fetch
    stored_sha = "aabbccdd" * 5
    monkeypatch.setattr(rk, "_head_sha", lambda path: stored_sha)

    called = []
    monkeypatch.setattr(rk, "_update_clone", lambda f, p: called.append(1) or "newsha")

    result = rk.refresh(family, platform, check_only=False, auto_fetch=False)

    assert result == "current"
    assert called == [], "update_clone must not be called when auto_fetch=False"


# ---------------------------------------------------------------------------
# Failing path: promote.py fails → knowledge_delta.json NOT written
# ---------------------------------------------------------------------------

def test_refresh_delta_not_written_on_promote_failure(knowledge_dir, monkeypatch):
    """When promote.py fails, knowledge_delta.json is not written."""
    tmp_path, family, platform, merged = knowledge_dir

    import refresh_knowledge as rk
    monkeypatch.setattr(rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
    monkeypatch.setattr(rk, "_clone_dir", lambda f, p: tmp_path / "fake_clone")
    monkeypatch.setattr(rk, "_head_sha", lambda path: "ffff0000" * 5)
    monkeypatch.setattr(rk, "_update_clone", lambda f, p: "ffff0000" * 5)
    monkeypatch.setattr(rk, "_run_completeness_check", lambda f, p: None)

    # Mock _run: scout succeeds, enrich best-effort, promote fails
    def fake_run(cmd, label):
        if label == "promote":
            return False
        return True

    monkeypatch.setattr(rk, "_run", fake_run)

    result = rk.refresh(family, platform, check_only=False, auto_fetch=False)

    assert result == "failed"
    delta_path = merged / "knowledge_delta.json"
    assert not delta_path.exists(), "knowledge_delta.json must not be written when promote fails"


# ---------------------------------------------------------------------------
# Failing path: no clone → returns "no_clone" cleanly
# ---------------------------------------------------------------------------

def test_refresh_no_clone_returns_no_clone(knowledge_dir, monkeypatch):
    """refresh() returns 'no_clone' when clone cache is missing."""
    tmp_path, family, platform, merged = knowledge_dir

    import refresh_knowledge as rk
    monkeypatch.setattr(rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
    monkeypatch.setattr(rk, "_clone_dir", lambda f, p: tmp_path / "nonexistent_clone")
    monkeypatch.setattr(rk, "_head_sha", lambda path: None)

    result = rk.refresh(family, platform, auto_clone=False, auto_fetch=False)
    assert result == "no_clone"

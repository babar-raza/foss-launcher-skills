"""Tests for scripts/pipeline/post_refresh_verify.py (TC-05).

Tests cover:
- --step records step as complete in progress.json
- --verify on clean product exits 0
- --status prints current progress
- --verify when stale pages exist exits 1 with page list
- --verify when orphaned claims present exits 1 with claim IDs
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

_PIPELINE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import post_refresh_verify as prv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_model_yaml(merged: Path, repo_sha: str = "abc" * 13, stale_since=None) -> None:
    merged.mkdir(parents=True, exist_ok=True)
    data = {"repo_sha": repo_sha, "stale_since": stale_since, "family": "testfam", "platform": "testplat"}
    (merged / "model.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_claims(merged: Path, claim_ids: list[str]) -> None:
    merged.mkdir(parents=True, exist_ok=True)
    claims = [{"claim_id": cid, "kind": "api_method", "text": f"text {cid}", "confidence": 1.0}
              for cid in claim_ids]
    (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")


def _write_api_surface(merged: Path, class_names: list[str]) -> None:
    merged.mkdir(parents=True, exist_ok=True)
    api = [{"name": n, "kind": "class_definition", "methods": [], "properties": []} for n in class_names]
    (merged / "api_surface.json").write_text(json.dumps(api), encoding="utf-8")


def _write_content_page(path: Path, claims: list[str] | None = None, model_sha: str = "abc" * 13) -> None:
    """Write a minimal content page with optional evidence citations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"model_sha": model_sha}
    if claims is not None:
        evidence["claims"] = claims
    fm = {"title": "Test Page", "evidence": evidence}
    content = "---\n" + yaml.safe_dump(fm) + "---\n\nBody.\n"
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Set up a minimal test environment."""
    family, platform = "testfam", "testplat"
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    monkeypatch.setattr(prv, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
    monkeypatch.setattr(prv, "CONTENT_ROOT", tmp_path / "content")
    monkeypatch.setattr(prv, "REPORTS_ROOT", tmp_path / "reports" / "refresh_state")

    return tmp_path, family, platform, merged


# ---------------------------------------------------------------------------
# Happy path: --step records step as complete
# ---------------------------------------------------------------------------

def test_record_step_writes_progress(env, monkeypatch):
    """record_step() records a step name in progress.json."""
    tmp_path, family, platform, merged = env

    prv.record_step(family, platform, "knowledge_refresh")

    progress_path = tmp_path / "reports" / "refresh_state" / family / platform / "progress.json"
    assert progress_path.is_file()
    data = json.loads(progress_path.read_text(encoding="utf-8"))
    assert "knowledge_refresh" in data["steps"]


def test_record_step_idempotent(env):
    """record_step() called twice with same step does not duplicate."""
    tmp_path, family, platform, merged = env

    prv.record_step(family, platform, "knowledge_refresh")
    prv.record_step(family, platform, "knowledge_refresh")

    progress_path = tmp_path / "reports" / "refresh_state" / family / platform / "progress.json"
    data = json.loads(progress_path.read_text(encoding="utf-8"))
    assert data["steps"].count("knowledge_refresh") == 1


# ---------------------------------------------------------------------------
# Happy path: --verify on clean product exits 0
# ---------------------------------------------------------------------------

def test_verify_passes_on_clean_product(env, monkeypatch):
    """verify() returns (True, []) when knowledge is clean."""
    tmp_path, family, platform, merged = env

    _write_model_yaml(merged, stale_since=None)
    _write_claims(merged, ["CLM-001", "CLM-002"])
    _write_api_surface(merged, ["ClassA"])

    # No content pages → no orphaned claims check to fail
    # Stub stale_detect to simulate 0 stale pages
    monkeypatch.setattr(prv, "_HERE", tmp_path / "no_scripts")  # no stale_detect.py present

    passed, failures = prv.verify(family, platform)
    assert passed is True
    assert failures == []


# ---------------------------------------------------------------------------
# Happy path: --status prints progress
# ---------------------------------------------------------------------------

def test_print_status_no_error(env, capsys):
    """print_status() prints progress without raising."""
    tmp_path, family, platform, merged = env

    prv.record_step(family, platform, "step_one")
    prv.print_status(family, platform)

    captured = capsys.readouterr()
    assert "step_one" in captured.out
    assert family in captured.out


# ---------------------------------------------------------------------------
# Failing path: --verify when stale_since is set exits 1
# ---------------------------------------------------------------------------

def test_verify_fails_when_stale_since_set(env, monkeypatch):
    """verify() returns failure when stale_since is non-null in model.yaml."""
    tmp_path, family, platform, merged = env

    _write_model_yaml(merged, stale_since="2026-04-01")
    _write_claims(merged, [])
    _write_api_surface(merged, [])
    monkeypatch.setattr(prv, "_HERE", tmp_path / "no_scripts")

    passed, failures = prv.verify(family, platform)
    assert passed is False
    assert any("stale_since" in f for f in failures)


# ---------------------------------------------------------------------------
# Failing path: --verify when orphaned claims present exits 1 with claim IDs
# ---------------------------------------------------------------------------

def test_verify_fails_on_orphaned_claims(env, monkeypatch):
    """verify() reports failure when content pages cite claims not in claims.json."""
    tmp_path, family, platform, merged = env

    _write_model_yaml(merged, stale_since=None)
    # Only CLM-001 exists in claims.json; page cites CLM-001 and CLM-GHOST
    _write_claims(merged, ["CLM-001"])
    _write_api_surface(merged, [])
    monkeypatch.setattr(prv, "_HERE", tmp_path / "no_scripts")

    # Create a content page that cites CLM-GHOST (not in claims.json)
    page = tmp_path / "content" / "docs.aspose.org" / "en" / family / platform / "page.md"
    _write_content_page(page, claims=["CLM-001", "CLM-GHOST"])

    passed, failures = prv.verify(family, platform)
    assert passed is False
    assert any("CLM-GHOST" in f for f in failures)

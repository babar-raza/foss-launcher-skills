"""Tests for local_profile.py — CI isolation and profile validation.

Covers:
- No profile file → strict mode
- Expired profile → strict mode
- CI=true forces strict regardless of valid profile
- GITHUB_ACTIONS=true forces strict
- Valid profile returns configured mode
- Malformed JSON → strict mode
- Wrong schema_version → strict mode
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import sys
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline" / "commands" / "governance"))
from local_profile import load_profile, get_mode, is_ci, validate_profile


def _make_profile(tmp_path: Path, data: dict | str) -> Path:
    """Create .local/governance.json under tmp_path and return repo_root."""
    local_dir = tmp_path / ".local"
    local_dir.mkdir(parents=True, exist_ok=True)
    profile = local_dir / "governance.json"
    if isinstance(data, str):
        profile.write_text(data, encoding="utf-8")
    else:
        profile.write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def _valid_profile_data(mode: str = "balanced-local") -> dict:
    return {
        "schema_version": 1,
        "profile": mode,
        "operator": "test-user",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "expires_at": (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat(),
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure CI env vars are unset unless explicitly set in test."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def test_no_profile_returns_strict(tmp_path):
    """Missing .local/governance.json → strict mode."""
    result = load_profile(tmp_path)
    assert result == {"profile": "strict"}
    assert get_mode(tmp_path) == "strict"


def test_expired_profile_returns_strict(tmp_path):
    """Expired expires_at → strict mode."""
    data = _valid_profile_data()
    data["expires_at"] = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
    repo = _make_profile(tmp_path, data)
    assert get_mode(repo) == "strict"


def test_ci_env_forces_strict(tmp_path, monkeypatch):
    """CI=true + valid profile → strict mode."""
    monkeypatch.setenv("CI", "true")
    repo = _make_profile(tmp_path, _valid_profile_data())
    assert get_mode(repo) == "strict"


def test_github_actions_forces_strict(tmp_path, monkeypatch):
    """GITHUB_ACTIONS=true + valid profile → strict mode."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    repo = _make_profile(tmp_path, _valid_profile_data())
    assert get_mode(repo) == "strict"


def test_valid_profile_returns_configured_mode(tmp_path):
    """Valid file → returns configured mode."""
    repo = _make_profile(tmp_path, _valid_profile_data("balanced-local"))
    assert get_mode(repo) == "balanced-local"


def test_malformed_profile_returns_strict(tmp_path):
    """Bad JSON → strict mode."""
    repo = _make_profile(tmp_path, "{invalid json!!")
    assert get_mode(repo) == "strict"


def test_wrong_schema_version_returns_strict(tmp_path):
    """schema_version=999 → strict mode."""
    data = _valid_profile_data()
    data["schema_version"] = 999
    repo = _make_profile(tmp_path, data)
    assert get_mode(repo) == "strict"

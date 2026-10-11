"""Tests for scripts/ci/check_skill_registry_json.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "ci" / "checks"))

from check_skill_registry_json import check, _discover_canonical, REGISTRY_PATH


class TestDiscoverCanonical:
    def test_returns_nonempty(self):
        canonical = _discover_canonical()
        assert len(canonical) > 0

    def test_all_have_skill_ids(self):
        canonical = _discover_canonical()
        for slug, sid in canonical.items():
            assert sid.startswith("S-"), f"{slug} has invalid ID: {sid}"

    def test_no_readme(self):
        canonical = _discover_canonical()
        assert "readme" not in canonical
        assert "README" not in canonical


class TestCheck:
    def test_passes_when_registry_current(self):
        """With a freshly generated registry.json, check should pass."""
        errors = check()
        assert errors == [], f"Unexpected errors: {errors}"

    def test_detects_missing_registry(self, tmp_path, monkeypatch):
        """If registry.json doesn't exist, check should fail."""
        import check_skill_registry_json as mod
        monkeypatch.setattr(mod, "REGISTRY_PATH", tmp_path / "nonexistent.json")
        errors = mod.check()
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_detects_stale_count(self, tmp_path, monkeypatch):
        """If registry has wrong skill_count, check should fail."""
        import check_skill_registry_json as mod
        stale = tmp_path / "registry.json"
        stale.write_text(json.dumps({
            "skill_count": 1,
            "skills": [{"slug": "fake", "id": "S-999"}],
        }))
        monkeypatch.setattr(mod, "REGISTRY_PATH", stale)
        errors = mod.check()
        assert any("mismatch" in e for e in errors)


class TestMain:
    def test_exit_0_when_current(self):
        import check_skill_registry_json as mod
        assert mod.main([]) == 0

    def test_json_output(self, capsys):
        import check_skill_registry_json as mod
        mod.main(["--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["passed"] is True

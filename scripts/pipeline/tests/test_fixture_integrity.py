"""Test fixture integrity — all fixtures must parse as valid JSON/YAML."""
import json
import sys
from pathlib import Path

import pytest
import yaml

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestFixtureIntegrity:
    """Verify all fixture files parse without errors."""

    def test_golden_api_surface_parses(self):
        path = _FIXTURES_DIR / "knowledge" / "golden" / "font_python" / "api_surface.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 3
        names = {e["name"] for e in data}
        assert names == {"Font", "FontType", "GlyphId"}

    def test_golden_model_yaml_parses(self):
        path = _FIXTURES_DIR / "knowledge" / "golden" / "font_python" / "model.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["family"] == "font"
        assert data["platform"] == "python"
        assert data["stale_since"] is None
        assert data["repo_sha"] == "fixture_sha_golden_001"

    def test_golden_claims_parses(self):
        path = _FIXTURES_DIR / "knowledge" / "golden" / "font_python" / "claims.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 4
        assert all("id" in c and "text" in c for c in data)

    def test_golden_formats_parses(self):
        path = _FIXTURES_DIR / "knowledge" / "golden" / "font_python" / "formats.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "formats" in data
        assert len(data["formats"]) == 2

    def test_stale_model_has_stale_since(self):
        path = _FIXTURES_DIR / "knowledge" / "stale" / "font_python" / "model.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["stale_since"] is not None

    def test_corrupted_model_missing_fields(self):
        path = _FIXTURES_DIR / "knowledge" / "corrupted" / "font_python" / "model.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "platform" not in data

    def test_naming_edge_cases_parses(self):
        path = _FIXTURES_DIR / "naming" / "edge_cases.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 10
        assert all("input" in e and "expected_slug" in e for e in data)

    def test_all_json_fixtures_parse(self):
        """Every .json file in fixtures/ must parse without errors."""
        json_files = list(_FIXTURES_DIR.rglob("*.json"))
        assert len(json_files) > 0, "No JSON fixtures found"
        for jf in json_files:
            try:
                json.loads(jf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                pytest.fail(f"Invalid JSON in {jf.relative_to(_FIXTURES_DIR)}: {exc}")

    def test_all_yaml_fixtures_parse(self):
        """Every .yaml file in fixtures/ must parse without errors."""
        yaml_files = list(_FIXTURES_DIR.rglob("*.yaml"))
        assert len(yaml_files) > 0, "No YAML fixtures found"
        for yf in yaml_files:
            try:
                yaml.safe_load(yf.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                pytest.fail(f"Invalid YAML in {yf.relative_to(_FIXTURES_DIR)}: {exc}")

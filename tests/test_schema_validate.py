"""Tests for scripts/schema_validate.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from schema_validate import load_schema, validate, _structural_validate


def test_load_schema_pef():
    schema = load_schema("pef")
    assert schema["title"] == "Product Evidence File (PEF)"
    assert "required" in schema


def test_load_schema_not_found():
    try:
        load_schema("nonexistent_schema_xyz")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass


def test_structural_validate_passes_valid():
    schema = load_schema("pef")
    data = {
        "schema_version": 1,
        "family": "words",
        "platform": "python",
        "display_name": "Aspose.Words",
        "materialized_at": "2026-01-01T00:00:00+00:00",
        "source_sha": "abc123",
        "provenance_summary": {
            "dual": 2, "dual_fuzzy": 0,
            "scout_only": 1, "external_only": 1,
            "total": 4, "dual_pct": 50.0
        },
        "api_confidence": "medium",
        "claims": [],
        "api_surface": [],
        "formats": [],
    }
    errors = _structural_validate(data, schema)
    assert errors == []


def test_structural_validate_missing_required():
    schema = load_schema("pef")
    data = {"schema_version": 1, "family": "words"}
    errors = _structural_validate(data, schema)
    assert any("platform" in e for e in errors)


def test_structural_validate_wrong_type():
    schema = load_schema("pef")
    data = {
        "schema_version": "not_an_int",
        "family": "words",
        "platform": "python",
        "display_name": "Aspose.Words",
        "materialized_at": "2026-01-01T00:00:00+00:00",
        "source_sha": "abc123",
        "provenance_summary": {},
        "api_confidence": "low",
        "claims": [],
        "api_surface": [],
        "formats": [],
    }
    errors = _structural_validate(data, schema)
    assert any("schema_version" in e for e in errors)


def test_validate_decision_schema():
    data = {
        "schema_version": 1,
        "family": "words",
        "platform": "python",
        "decided_at": "2026-01-01T00:00:00+00:00",
        "pages": [],
        "summary": {
            "create": 0, "update": 0, "enhance": 0,
            "verify_only": 0, "no_change": 0, "total": 0
        }
    }
    errors = _structural_validate(data, load_schema("decision"))
    assert errors == []


# ---------------------------------------------------------------------------
# Config schema validation
# ---------------------------------------------------------------------------

def test_load_config_schema():
    """config.schema.json loads and has expected required fields."""
    schema = load_schema("config")
    assert schema["title"] == "foss-launcher-skills configuration"
    required = schema["required"]
    assert "content_repo" in required
    assert "sites" in required
    assert "governance" in required


def test_config_schema_valid_minimal(minimal_config):
    """minimal_config fixture passes config schema validation."""
    schema = load_schema("config")
    errors = _structural_validate(minimal_config["data"], schema)
    assert errors == [], f"minimal_config should be valid, got: {errors}"


def test_config_schema_actual_config():
    """Actual config.yaml from repo passes config schema validation."""
    import yaml
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if not config_path.exists():
        pytest.skip("config.yaml not found")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    schema = load_schema("config")
    errors = _structural_validate(config, schema)
    assert errors == [], f"config.yaml should be valid, got: {errors}"


def test_config_schema_missing_required():
    """Missing required key detected by config schema."""
    schema = load_schema("config")
    # Missing governance, forbidden_paths, sites
    data = {"content_repo": "", "knowledge_path": "k/", "evidence_path": "e/"}
    errors = _structural_validate(data, schema)
    assert any("governance" in e for e in errors)
    assert any("forbidden_paths" in e for e in errors)
    assert any("sites" in e for e in errors)


def test_config_schema_wrong_type():
    """Wrong type for forbidden_paths detected by config schema."""
    schema = load_schema("config")
    data = {
        "content_repo": "",
        "sites": {},
        "knowledge_path": "k/",
        "evidence_path": "e/",
        "forbidden_paths": "should-be-array",
        "governance": {},
    }
    errors = _structural_validate(data, schema)
    assert any("forbidden_paths" in e for e in errors)

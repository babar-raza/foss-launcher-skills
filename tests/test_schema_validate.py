"""Tests for scripts/schema_validate.py."""
import sys
from pathlib import Path

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

"""Tests for S-98 enrichment output JSON schemas (TC-004)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

_LIB_DIR = str(Path(__file__).resolve().parent.parent / "scripts" / "pipeline" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from enrichment.schemas import (
    COVERAGE_MATRIX_SCHEMA,
    CANDIDATE_LIST_SCHEMA,
    DENOMINATOR_CHECK_SCHEMA,
    HANDOFF_MANIFEST_SCHEMA,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(rel_path: str) -> dict:
    """Load a JSON file relative to repo root."""
    fp = REPO_ROOT / rel_path
    if not fp.exists():
        pytest.skip(f"{rel_path} not found (pilot output not present)")
    return json.loads(fp.read_text(encoding="utf-8"))


def _validate(instance: dict, schema: dict) -> None:
    """Validate a dict against a JSON schema."""
    jsonschema.validate(instance=instance, schema=schema)


# ---------------------------------------------------------------------------
# Schema self-consistency tests
# ---------------------------------------------------------------------------

class TestSchemasAreValid:
    """Verify the schemas themselves are valid JSON Schema drafts."""

    @pytest.mark.parametrize("schema", [
        COVERAGE_MATRIX_SCHEMA,
        CANDIDATE_LIST_SCHEMA,
        DENOMINATOR_CHECK_SCHEMA,
        HANDOFF_MANIFEST_SCHEMA,
    ])
    def test_schema_is_valid(self, schema):
        jsonschema.Draft7Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# Validate font/python pilot outputs
# ---------------------------------------------------------------------------

class TestFontPythonSchemas:
    """Validate font/python pilot outputs against schemas."""

    def test_coverage_matrix(self):
        data = _load_json("reports/enrichment/font/python/coverage-matrix.json")
        _validate(data, COVERAGE_MATRIX_SCHEMA)

    def test_candidate_list(self):
        data = _load_json("reports/enrichment/font/python/candidate-list.json")
        _validate(data, CANDIDATE_LIST_SCHEMA)

    def test_denominator_check(self):
        data = _load_json("reports/enrichment/font/python/denominator-check.json")
        _validate(data, DENOMINATOR_CHECK_SCHEMA)

    def test_handoff_manifest(self):
        data = _load_json("reports/enrichment/font/python/handoff-manifest.json")
        _validate(data, HANDOFF_MANIFEST_SCHEMA)


# ---------------------------------------------------------------------------
# Validate slides/python pilot outputs
# ---------------------------------------------------------------------------

class TestSlidesPythonSchemas:
    """Validate slides/python pilot outputs against schemas."""

    def test_coverage_matrix(self):
        data = _load_json("reports/enrichment/slides/python/coverage-matrix.json")
        _validate(data, COVERAGE_MATRIX_SCHEMA)

    def test_candidate_list(self):
        data = _load_json("reports/enrichment/slides/python/candidate-list.json")
        _validate(data, CANDIDATE_LIST_SCHEMA)

    def test_denominator_check(self):
        data = _load_json("reports/enrichment/slides/python/denominator-check.json")
        _validate(data, DENOMINATOR_CHECK_SCHEMA)

    def test_handoff_manifest(self):
        data = _load_json("reports/enrichment/slides/python/handoff-manifest.json")
        _validate(data, HANDOFF_MANIFEST_SCHEMA)


# ---------------------------------------------------------------------------
# Negative validation tests
# ---------------------------------------------------------------------------

class TestSchemaRejectsInvalid:
    """Verify schemas reject malformed data."""

    def test_denominator_missing_valid(self):
        bad = {"total_candidates": 5, "bucket_sum": 5, "buckets": {}, "delta": 0}
        with pytest.raises(jsonschema.ValidationError):
            _validate(bad, DENOMINATOR_CHECK_SCHEMA)

    def test_manifest_missing_dry_run(self):
        bad = {"family": "x", "platform": "y", "manifest_items": []}
        with pytest.raises(jsonschema.ValidationError):
            _validate(bad, HANDOFF_MANIFEST_SCHEMA)

    def test_candidate_score_out_of_range(self):
        bad = {
            "family": "x", "platform": "y",
            "candidates": [{"cluster": "a", "subdomain": "docs", "action": "create", "disposition": "generate_now", "score": 2.0}],
            "denominator": {"total": 1, "generate_now": 1, "update_existing": 0, "deferred_to_backlog": 0, "rejected_with_reason": 0},
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate(bad, CANDIDATE_LIST_SCHEMA)

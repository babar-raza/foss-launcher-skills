"""Tests for freshness_manifest.py — Phase 1 (TC-PROD-001).

Covers:
  test_load_save_roundtrip
  test_missing_manifest_returns_none_not_default
  test_migrate_from_missing_status_is_baselined_unproven_not_fresh
  test_missing_required_field_raises_validation_error
  test_atomic_write_uses_tmp_then_replace
  test_schema_structure_valid
  test_sample_instance_validates_against_schema
  test_with_updates_returns_new_instance
  test_load_corrupt_json_returns_none
  test_load_invalid_status_returns_none
  test_save_creates_parent_dirs
  test_manifest_status_vocabulary_complete
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# conftest.py adds scripts/pipeline/lib/ to sys.path
from freshness_manifest import (
    REQUIRED_FIELDS,
    VALID_STATUSES,
    FreshnessManifest,
    ValidationError,
    load,
    migrate_from_missing,
    save,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _minimal_manifest_data(**overrides) -> dict:
    """Return a minimal valid manifest dict."""
    data = {
        "manifest_version": "1.0",
        "product": "cells/java",
        "subdomain": "reference",
        "surface_type": "api-reference",
        "input_fingerprints": {
            "upstream_repo_sha": "abc123",
            "local_knowledge_sha": "abc123",
        },
        "output_state": {
            "output_exists": True,
            "validation_status": "PASS",
            "expected_page_count": 10,
            "actual_page_count": 10,
        },
        "manifest_status": "FRESH",
        "generation_timestamp": "2026-05-01T10:00:00Z",
        "run_id": "20260501-100000",
        "command_used": "batch_reference.py cells java",
        "governance_status": "COMPLIANT",
        "decision": "FRESH",
        "skip_reason": None,
        "changed_input_fingerprints": [],
        "prior_manifest_ref": None,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Core load/save tests
# ---------------------------------------------------------------------------

def test_load_save_roundtrip(tmp_path):
    """Saving then loading a manifest returns an equivalent instance."""
    state_root = tmp_path / "state"
    data = _minimal_manifest_data()
    manifest = FreshnessManifest(data)

    save(manifest, state_root=state_root)
    loaded = load("cells/java", "reference", state_root=state_root)

    assert loaded is not None
    assert loaded.product == "cells/java"
    assert loaded.subdomain == "reference"
    assert loaded.manifest_status == "FRESH"
    assert loaded.run_id == "20260501-100000"
    assert loaded.to_dict() == data


def test_missing_manifest_returns_none_not_default(tmp_path):
    """load() returns None when no manifest file exists — not a default value."""
    state_root = tmp_path / "state"
    result = load("cells/java", "reference", state_root=state_root)
    assert result is None


def test_load_corrupt_json_returns_none(tmp_path):
    """load() returns None silently for corrupt JSON (does not raise)."""
    state_root = tmp_path / "state"
    path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json{{", encoding="utf-8")

    result = load("cells/java", "reference", state_root=state_root)
    assert result is None


def test_load_invalid_status_returns_none(tmp_path):
    """load() returns None for a manifest with an unrecognised status."""
    state_root = tmp_path / "state"
    data = _minimal_manifest_data(manifest_status="NOT_A_REAL_STATUS")
    path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")

    result = load("cells/java", "reference", state_root=state_root)
    assert result is None


def test_save_creates_parent_dirs(tmp_path):
    """save() creates nested parent directories that do not yet exist."""
    state_root = tmp_path / "deep" / "nested" / "state"
    manifest = FreshnessManifest(_minimal_manifest_data())
    save(manifest, state_root=state_root)

    expected = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"
    assert expected.is_file()


# ---------------------------------------------------------------------------
# Atomic write test
# ---------------------------------------------------------------------------

def test_atomic_write_uses_tmp_then_replace(tmp_path, monkeypatch):
    """save() writes to a .tmp file and then os.replaces it atomically."""
    state_root = tmp_path / "state"
    path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"
    tmp_path_expected = path.with_suffix(".tmp")

    seen_tmp: list[str] = []
    original_replace = os.replace

    def patched_replace(src, dst):
        seen_tmp.append(str(src))
        original_replace(src, dst)

    monkeypatch.setattr(os, "replace", patched_replace)

    manifest = FreshnessManifest(_minimal_manifest_data())
    save(manifest, state_root=state_root)

    assert len(seen_tmp) == 1
    assert seen_tmp[0].endswith(".tmp")
    assert path.is_file()


# ---------------------------------------------------------------------------
# migrate_from_missing tests
# ---------------------------------------------------------------------------

def test_migrate_from_missing_status_is_baselined_unproven_not_fresh():
    """migrate_from_missing() MUST set BASELINED_UNPROVEN, never FRESH.

    This is a hard rule: cold-start migrations cannot claim freshness
    because the input-output relationship has not been proven by a governed run.
    """
    disk_state = {
        "surface_type": "api-reference",
        "input_fingerprints": {"upstream_repo_sha": "abc123"},
        "output_state": {"output_exists": True},
        "run_id": "baseline-2026-05-01",
    }
    manifest = migrate_from_missing("cells/java", "reference", disk_state)

    assert manifest.manifest_status == "BASELINED_UNPROVEN"
    assert manifest.manifest_status != "FRESH"


def test_migrate_from_missing_populates_product_and_subdomain():
    manifest = migrate_from_missing("slides/python", "docs", {})
    assert manifest.product == "slides/python"
    assert manifest.subdomain == "docs"


def test_migrate_from_missing_empty_disk_state():
    """migrate_from_missing() works with an empty disk_state dict."""
    manifest = migrate_from_missing("cells/java", "kb", {})
    assert manifest.manifest_status == "BASELINED_UNPROVEN"
    assert manifest.output_state == {"output_exists": False}


# ---------------------------------------------------------------------------
# ValidationError tests
# ---------------------------------------------------------------------------

def test_missing_required_field_raises_validation_error():
    """FreshnessManifest constructor raises ValidationError for missing required fields."""
    data = _minimal_manifest_data()
    del data["manifest_status"]

    with pytest.raises(ValidationError, match="manifest_status"):
        FreshnessManifest(data)


def test_invalid_status_raises_validation_error():
    """FreshnessManifest constructor raises ValidationError for invalid status."""
    data = _minimal_manifest_data(manifest_status="MADE_UP_STATUS")

    with pytest.raises(ValidationError, match="Invalid manifest_status"):
        FreshnessManifest(data)


def test_missing_output_exists_raises_validation_error():
    """FreshnessManifest requires output_state.output_exists."""
    data = _minimal_manifest_data()
    data["output_state"] = {}  # missing output_exists

    with pytest.raises(ValidationError, match="output_exists"):
        FreshnessManifest(data)


# ---------------------------------------------------------------------------
# with_updates immutability test
# ---------------------------------------------------------------------------

def test_with_updates_returns_new_instance():
    """with_updates() returns a new instance without modifying the original."""
    original = FreshnessManifest(_minimal_manifest_data())
    updated = original.with_updates(manifest_status="VALIDATE_ONLY", run_id="new-run-id")

    assert original.manifest_status == "FRESH"
    assert updated.manifest_status == "VALIDATE_ONLY"
    assert updated.run_id == "new-run-id"
    assert original.run_id == "20260501-100000"


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_schema_structure_valid():
    """The JSON schema file is itself structurally valid (Draft-7)."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "data" / "schemas" / "freshness-manifest-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)


def test_sample_instance_validates_against_schema():
    """A valid manifest dict passes the JSON schema."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "data" / "schemas" / "freshness-manifest-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    instance = _minimal_manifest_data()
    jsonschema.validate(instance, schema)


def test_manifest_status_vocabulary_complete():
    """VALID_STATUSES contains all statuses listed in the plan (Section G)."""
    expected = {
        "FRESH",
        "BASELINED_UNPROVEN",
        "REGENERATE_UPSTREAM",
        "REGENERATE_GENERATOR",
        "REGENERATE_METADATA",
        "REGENERATE_POLICY",
        "RECONCILE_MISSING",
        "RECONCILE_DRIFTED",
        "VALIDATE_ONLY",
        "BLOCKED",
        "DRY_RUN_PASS",
        "PARTIAL_PASS",
    }
    assert VALID_STATUSES == expected

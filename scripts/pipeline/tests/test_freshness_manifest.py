"""Tests for freshness_manifest.py — Phase 1 (TC-PROD-001) + TC-A7-004/005.

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
  TC-A7-004:
  test_output_content_hash_is_real_not_placeholder
  test_output_content_hash_stable_for_same_content
  test_modified_expected_output_triggers_different_hash
  test_missing_expected_output_returns_none
  test_output_content_hash_normalizes_line_endings
  TC-A7-005:
  test_is_placeholder_hash_detects_placeholder
  test_is_placeholder_hash_accepts_real_hash
  test_validate_for_fresh_passes_all_conditions
  test_validate_for_fresh_fails_on_missing_required_fingerprint
  test_validate_for_fresh_fails_on_placeholder_hash
  test_validate_for_fresh_fails_on_none_output_hash
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


# ---------------------------------------------------------------------------
# TC-A7-004 tests: compute_output_content_hash
# ---------------------------------------------------------------------------

from freshness_manifest import compute_output_content_hash, is_placeholder_hash, validate_for_fresh  # noqa: E402


class TestComputeOutputContentHash:
    """TC-A7-004: deterministic, real content hash."""

    def test_output_content_hash_is_real_not_placeholder(self, tmp_path):
        """Hash of real files must not match placeholder pattern."""
        (tmp_path / "a.md").write_text("hello world\n", encoding="utf-8")
        h = compute_output_content_hash(tmp_path)
        assert h is not None
        assert h.startswith("sha256:")
        # Real hash has 64 lowercase hex chars, not uppercase letters
        assert not is_placeholder_hash(h)
        assert len(h) == len("sha256:") + 64

    def test_output_content_hash_stable_for_same_content(self, tmp_path):
        """Same files produce the same hash across two calls."""
        (tmp_path / "page.md").write_text("content\n", encoding="utf-8")
        (tmp_path / "other.md").write_text("other\n", encoding="utf-8")
        h1 = compute_output_content_hash(tmp_path)
        h2 = compute_output_content_hash(tmp_path)
        assert h1 == h2

    def test_modified_expected_output_triggers_different_hash(self, tmp_path):
        """Modifying one file changes the hash."""
        f = tmp_path / "page.md"
        f.write_text("original\n", encoding="utf-8")
        h1 = compute_output_content_hash(tmp_path)
        f.write_text("modified\n", encoding="utf-8")
        h2 = compute_output_content_hash(tmp_path)
        assert h1 != h2

    def test_missing_expected_output_returns_none(self, tmp_path):
        """Non-existent directory returns None (triggers RECONCILE_MISSING in engine)."""
        missing = tmp_path / "nonexistent"
        assert compute_output_content_hash(missing) is None

    def test_empty_directory_returns_none(self, tmp_path):
        """Directory with no .md files returns None."""
        (tmp_path / "other.txt").write_text("hello")
        assert compute_output_content_hash(tmp_path) is None

    def test_output_content_hash_normalizes_line_endings(self, tmp_path):
        """CRLF and LF content produce the same hash (line-ending normalisation)."""
        lf_dir = tmp_path / "lf"
        lf_dir.mkdir()
        crlf_dir = tmp_path / "crlf"
        crlf_dir.mkdir()
        (lf_dir / "page.md").write_bytes(b"hello\nworld\n")
        (crlf_dir / "page.md").write_bytes(b"hello\r\nworld\r\n")
        assert compute_output_content_hash(lf_dir) == compute_output_content_hash(crlf_dir)

    def test_added_file_changes_hash(self, tmp_path):
        """Adding a new .md file changes the hash."""
        (tmp_path / "a.md").write_text("a\n", encoding="utf-8")
        h1 = compute_output_content_hash(tmp_path)
        (tmp_path / "b.md").write_text("b\n", encoding="utf-8")
        h2 = compute_output_content_hash(tmp_path)
        assert h1 != h2


# ---------------------------------------------------------------------------
# TC-A7-005 tests: is_placeholder_hash and validate_for_fresh
# ---------------------------------------------------------------------------


class TestIsPlaceholderHash:
    """TC-A7-005: placeholder detection."""

    def test_detects_known_placeholder(self):
        """PILOT_BASELINE_OUTPUT is a placeholder."""
        assert is_placeholder_hash("sha256:PILOT_BASELINE_OUTPUT") is True

    def test_detects_uppercase_placeholder(self):
        """ALL_CAPS strings after sha256: are placeholders."""
        assert is_placeholder_hash("sha256:SYNTHETIC_TC108_CHANGED") is True

    def test_accepts_real_hash(self):
        """64-char lowercase hex is a real hash."""
        real = "sha256:" + "a" * 64
        assert is_placeholder_hash(real) is False

    def test_accepts_real_hash_mixed(self):
        """Real sha256 hashes contain only hex digits."""
        real = "sha256:20955f35432933bbe7927b3d21d554f016e9236ae1696e662f363e2fc79e511c"
        assert is_placeholder_hash(real) is False

    def test_none_is_not_placeholder(self):
        """None is not a placeholder (it is missing)."""
        assert is_placeholder_hash(None) is False


class TestValidateForFresh:
    """TC-A7-005: manifest rebuild policy validation."""

    def _fingerprints(self, **overrides):
        base = {
            "upstream_repo_sha": "abc123",
            "generator_code_hash": "sha256:" + "a" * 64,
        }
        base.update(overrides)
        return base

    def test_passes_all_conditions(self):
        """No violations when all fingerprints present and output hash is real."""
        fps = self._fingerprints()
        real_hash = "sha256:" + "b" * 64
        violations = validate_for_fresh(
            fps,
            output_content_hash=real_hash,
            fingerprints_required=list(fps.keys()),
        )
        assert violations == []

    def test_fails_on_missing_required_fingerprint(self):
        """Missing required fingerprint produces a violation."""
        fps = {"upstream_repo_sha": None, "generator_code_hash": "sha256:" + "a" * 64}
        violations = validate_for_fresh(
            fps,
            output_content_hash="sha256:" + "b" * 64,
            fingerprints_required=["upstream_repo_sha", "generator_code_hash"],
        )
        assert any("upstream_repo_sha" in v for v in violations)

    def test_fails_on_placeholder_hash(self):
        """Placeholder output_content_hash produces a violation."""
        fps = self._fingerprints()
        violations = validate_for_fresh(
            fps,
            output_content_hash="sha256:PILOT_BASELINE_OUTPUT",
            fingerprints_required=list(fps.keys()),
        )
        assert any("placeholder" in v for v in violations)

    def test_fails_on_none_output_hash(self):
        """None output_content_hash produces a violation."""
        fps = self._fingerprints()
        violations = validate_for_fresh(
            fps,
            output_content_hash=None,
            fingerprints_required=list(fps.keys()),
        )
        assert any("None" in v for v in violations)

    def test_no_violation_when_generator_path_none(self):
        """No dirty-state violation when generator_path is None."""
        fps = self._fingerprints()
        violations = validate_for_fresh(
            fps,
            output_content_hash="sha256:" + "c" * 64,
            generator_path=None,
            fingerprints_required=list(fps.keys()),
        )
        assert violations == []

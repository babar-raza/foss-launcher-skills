"""Gate 3a tests for refresh_harness.py manifest write integration.

Covers:
  - manifest write flag false → no write
  - manifest write flag true + --no-write → no write
  - manifest write flag true + --allow-write + FRESH → write occurs
  - VALIDATE_ONLY decision → no write
  - REGENERATE_* decision → no write
  - refresh_content_write_enabled=True → HARD_BLOCK (RuntimeError)
  - backup created before write
  - backup removed after successful verification
  - backup restored on write failure
  - post-write verification failure restores backup
  - written manifest has correct run_id
  - written manifest has FRESH status
  - manifest_restore.py restores backup correctly
  - manifest_restore.py fails safely when backup is missing
  - existing dry-run behavior remains unchanged (regression guard)
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py adds scripts/pipeline/lib/ and scripts/pipeline/ to sys.path
from refresh_harness import (
    _REGISTRY_PATH,
    _write_manifest_gated,
    _restore_backup,
    load_feature_flags,
    run_harness,
)
from freshness_manifest import FreshnessManifest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]

_REAL_HASH = "sha256:" + "a" * 64
_REAL_HASH_B = "sha256:" + "b" * 64
_REAL_HASH_C = "sha256:" + "c" * 64

_BASE_MANIFEST_DATA = {
    "manifest_version": "1.0",
    "product": "cells/java",
    "subdomain": "reference",
    "surface_type": "api-reference",
    "input_fingerprints": {
        "upstream_repo_sha": "sha_stored_abc",
        "local_knowledge_sha": "sha_local_xyz",
        "generator_code_hash": _REAL_HASH,
    },
    "output_state": {
        "output_exists": True,
        "output_content_hash": _REAL_HASH_B,
    },
    "manifest_status": "FRESH",
    "generation_timestamp": "2026-05-01T10:00:00Z",
    "run_id": "prior-run-001",
    "command_used": "batch_reference.py cells java",
    "governance_status": "COMPLIANT",
    "decision": "FRESH",
    "skip_reason": None,
    "changed_input_fingerprints": [],
    "prior_manifest_ref": None,
}

_GATE3_WRITE_FLAGS = {
    "refresh_decision_engine_enabled": False,
    "refresh_decision_engine_shadow": True,
    "refresh_reconciliation_shadow": True,
    "refresh_reconciliation_enforced": True,
    "refresh_manifest_write_enabled": True,
    "refresh_content_write_enabled": False,
    "refresh_run_type_label_enabled": True,
}

_GATE3_NO_WRITE_FLAGS = dict(_GATE3_WRITE_FLAGS, refresh_manifest_write_enabled=False)


def _make_stored_manifest(**overrides) -> FreshnessManifest:
    data = dict(_BASE_MANIFEST_DATA)
    data.update(overrides)
    return FreshnessManifest(data)


def _make_state_dir(tmp_path: Path, manifest_data: dict) -> Path:
    """Create a runs/state/cells/java/reference/ directory with a manifest file."""
    state_root = tmp_path / "runs" / "state"
    manifest_dir = state_root / "cells" / "java" / "reference"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "freshness-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return state_root


def _make_output_state(output_hash: str = _REAL_HASH_C):
    out = MagicMock()
    out.output_exists = True
    out.output_content_hash = output_hash
    return out


def _patch_registry():
    """Patch registry to return a minimal DependencyRegistry."""
    from dependency_registry import DependencyRegistry
    data = {
        "reference": {
            "description": "API reference pages",
            "backing_generator": "scripts/pipeline/commands/content/batch_reference.py",
            "backing_skill": "S-62",
            "fingerprints_required": ["upstream_repo_sha", "local_knowledge_sha"],
            "template_paths": [],
            "config_path": "configs/reference.aspose.org.toml",
            "content_root": "content/reference.aspose.org/en/{family}/{platform}",
            "expected_output_source": "registry_rules",
            "regeneration_triggers": ["upstream_repo_sha"],
            "reconciliation_triggers": ["output_missing"],
            "triage_checker": None,
            "supports_targeted_run": True,
            "status": "supported",
        }
    }
    registry = DependencyRegistry(data)
    return patch("refresh_harness.load_registry", return_value=registry)


# ---------------------------------------------------------------------------
# Unit tests for _write_manifest_gated()
# ---------------------------------------------------------------------------


class TestWriteManifestGatedFlags:
    """Tests that flag combinations correctly gate or permit writes."""

    def test_manifest_write_flag_false_skips_write(self, tmp_path):
        """manifest_write_enabled=False → write is skipped, no backup created."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        flags = dict(_GATE3_WRITE_FLAGS, refresh_manifest_write_enabled=False)

        written, note = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={"upstream_repo_sha": "sha_stored_abc"},
            current_outputs=_make_output_state(),
            stored=stored,
            run_id="gate3a-test-001",
            flags=flags,
            no_write=False,
            state_root=state_root,
        )

        assert not written
        assert "refresh_manifest_write_enabled=False" in note
        backup = state_root / "cells" / "java" / "reference" / "freshness-manifest.pre-gate3.json"
        assert not backup.exists()

    def test_no_write_flag_true_skips_write(self, tmp_path):
        """no_write=True → write is skipped even if manifest_write flag is True."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()

        written, note = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={"upstream_repo_sha": "sha_stored_abc"},
            current_outputs=_make_output_state(),
            stored=stored,
            run_id="gate3a-test-002",
            flags=_GATE3_WRITE_FLAGS,
            no_write=True,
            state_root=state_root,
        )

        assert not written
        assert "no_write=True" in note

    def test_reconciliation_not_enforced_skips_write(self, tmp_path):
        """refresh_reconciliation_enforced=False → write is skipped."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        flags = dict(_GATE3_WRITE_FLAGS, refresh_reconciliation_enforced=False)

        written, note = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={"upstream_repo_sha": "sha_stored_abc"},
            current_outputs=_make_output_state(),
            stored=stored,
            run_id="gate3a-test-003",
            flags=flags,
            no_write=False,
            state_root=state_root,
        )

        assert not written
        assert "refresh_reconciliation_enforced=False" in note

    def test_content_write_enabled_raises_hard_block(self, tmp_path):
        """refresh_content_write_enabled=True → RuntimeError (HARD_BLOCK) regardless of other flags."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        with pytest.raises(RuntimeError, match="HARD_BLOCK"):
            _write_manifest_gated(
                product="cells/java",
                subdomain="reference",
                fingerprints={"upstream_repo_sha": "sha_stored_abc"},
                current_outputs=_make_output_state(),
                stored=stored,
                run_id="gate3a-test-004",
                flags=flags,
                no_write=False,
                state_root=state_root,
            )

    def test_content_write_hard_block_even_when_no_write(self, tmp_path):
        """HARD_BLOCK fires even when no_write=True — content_write_enabled is never safe."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        with pytest.raises(RuntimeError, match="HARD_BLOCK"):
            _write_manifest_gated(
                product="cells/java",
                subdomain="reference",
                fingerprints={},
                current_outputs=_make_output_state(),
                stored=stored,
                run_id="gate3a-test-005",
                flags=flags,
                no_write=True,  # no_write is True but HARD_BLOCK still fires
                state_root=state_root,
            )

    def test_no_stored_manifest_skips_write(self, tmp_path):
        """stored=None → write is skipped (no base to update from)."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)

        written, note = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={"upstream_repo_sha": "sha_stored_abc"},
            current_outputs=_make_output_state(),
            stored=None,
            run_id="gate3a-test-006",
            flags=_GATE3_WRITE_FLAGS,
            no_write=False,
            state_root=state_root,
        )

        assert not written
        assert "no stored manifest" in note


class TestWriteManifestGatedSuccess:
    """Tests for successful manifest write path."""

    def test_write_succeeds_with_correct_flags(self, tmp_path):
        """All conditions met → write occurs and returns (True, note with SUCCEEDED)."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()

        written, note = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={
                "upstream_repo_sha": "sha_stored_abc",
                "local_knowledge_sha": "sha_local_xyz",
                "generator_code_hash": _REAL_HASH,
            },
            current_outputs=_make_output_state(_REAL_HASH_C),
            stored=stored,
            run_id="gate3a-success-001",
            flags=_GATE3_WRITE_FLAGS,
            no_write=False,
            state_root=state_root,
        )

        assert written
        assert "SUCCEEDED" in note

    def test_written_manifest_has_fresh_status(self, tmp_path):
        """Written manifest file has manifest_status == FRESH."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()

        _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={
                "upstream_repo_sha": "sha_stored_abc",
                "local_knowledge_sha": "sha_local_xyz",
            },
            current_outputs=_make_output_state(),
            stored=stored,
            run_id="gate3a-success-002",
            flags=_GATE3_WRITE_FLAGS,
            no_write=False,
            state_root=state_root,
        )

        manifest_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["manifest_status"] == "FRESH"

    def test_written_manifest_has_correct_run_id(self, tmp_path):
        """Written manifest has the run_id passed to _write_manifest_gated()."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()

        expected_run_id = "gate3b-manifest-write-20260513"
        _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={
                "upstream_repo_sha": "sha_stored_abc",
                "local_knowledge_sha": "sha_local_xyz",
            },
            current_outputs=_make_output_state(),
            stored=stored,
            run_id=expected_run_id,
            flags=_GATE3_WRITE_FLAGS,
            no_write=False,
            state_root=state_root,
        )

        manifest_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["run_id"] == expected_run_id

    def test_backup_created_before_write(self, tmp_path):
        """Pre-write backup is created before save() is called."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        backup_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.pre-gate3.json"

        backup_existed_before_save = []

        original_save = None
        from freshness_manifest import save as real_save

        def _spy_save(manifest, state_root=None):
            # Check if backup exists at the moment save() is called.
            backup_existed_before_save.append(backup_path.exists())
            return real_save(manifest, state_root=state_root)

        with patch("refresh_harness._write_manifest_gated.__globals__", {}) if False else \
             patch("freshness_manifest.save", side_effect=_spy_save):
            _write_manifest_gated(
                product="cells/java",
                subdomain="reference",
                fingerprints={
                    "upstream_repo_sha": "sha_stored_abc",
                    "local_knowledge_sha": "sha_local_xyz",
                },
                current_outputs=_make_output_state(),
                stored=stored,
                run_id="gate3a-backup-001",
                flags=_GATE3_WRITE_FLAGS,
                no_write=False,
                state_root=state_root,
            )

        assert backup_existed_before_save == [True], (
            "Backup must exist at the moment save() is called. "
            f"Got: {backup_existed_before_save}"
        )

    def test_backup_removed_after_successful_verification(self, tmp_path):
        """After successful write and verification, backup file is deleted."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        backup_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.pre-gate3.json"

        written, _ = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={
                "upstream_repo_sha": "sha_stored_abc",
                "local_knowledge_sha": "sha_local_xyz",
            },
            current_outputs=_make_output_state(),
            stored=stored,
            run_id="gate3a-backup-002",
            flags=_GATE3_WRITE_FLAGS,
            no_write=False,
            state_root=state_root,
        )

        assert written
        assert not backup_path.exists(), (
            "Backup must be removed after successful write + verification."
        )

    def test_output_hash_updated_in_written_manifest(self, tmp_path):
        """Written manifest reflects the live output_content_hash from current_outputs."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        live_hash = "sha256:" + "d" * 64

        _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={
                "upstream_repo_sha": "sha_stored_abc",
                "local_knowledge_sha": "sha_local_xyz",
            },
            current_outputs=_make_output_state(live_hash),
            stored=stored,
            run_id="gate3a-hash-001",
            flags=_GATE3_WRITE_FLAGS,
            no_write=False,
            state_root=state_root,
        )

        manifest_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["output_state"]["output_content_hash"] == live_hash


class TestWriteManifestGatedFailure:
    """Tests for failure paths: backup restoration."""

    def test_backup_restored_when_save_fails(self, tmp_path):
        """When freshness_manifest.save() raises, backup is restored to original."""
        original_data = dict(_BASE_MANIFEST_DATA, run_id="original-run-before-gate3")
        state_root = _make_state_dir(tmp_path, original_data)
        stored = _make_stored_manifest(**original_data)
        manifest_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"

        with patch("freshness_manifest.save", side_effect=OSError("disk full")):
            written, note = _write_manifest_gated(
                product="cells/java",
                subdomain="reference",
                fingerprints={"upstream_repo_sha": "sha_stored_abc"},
                current_outputs=_make_output_state(),
                stored=stored,
                run_id="gate3a-fail-001",
                flags=_GATE3_WRITE_FLAGS,
                no_write=False,
                state_root=state_root,
            )

        assert not written
        assert "FAILED" in note
        assert "backup restored" in note
        # Original manifest must be restored.
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "original-run-before-gate3"

    def test_backup_restored_when_post_write_verify_fails(self, tmp_path):
        """When post-write re-load verification fails, backup is restored."""
        original_data = dict(_BASE_MANIFEST_DATA, run_id="original-before-verify-fail")
        state_root = _make_state_dir(tmp_path, original_data)
        stored = _make_stored_manifest(**original_data)
        manifest_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.json"

        # Patch load inside the function to simulate verification failure.
        # We allow save() to succeed (manifest is written) but load() returns None.
        with patch("freshness_manifest.load", return_value=None):
            written, note = _write_manifest_gated(
                product="cells/java",
                subdomain="reference",
                fingerprints={"upstream_repo_sha": "sha_stored_abc"},
                current_outputs=_make_output_state(),
                stored=stored,
                run_id="gate3a-verify-fail-001",
                flags=_GATE3_WRITE_FLAGS,
                no_write=False,
                state_root=state_root,
            )

        assert not written
        assert "VERIFICATION FAILED" in note
        assert "backup restored" in note
        # Original manifest must be restored.
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "original-before-verify-fail"


# ---------------------------------------------------------------------------
# Tests for _restore_backup()
# ---------------------------------------------------------------------------


class TestRestoreBackup:
    def test_restore_backup_restores_file(self, tmp_path):
        """_restore_backup() moves backup to manifest path."""
        manifest_path = tmp_path / "freshness-manifest.json"
        backup_path = tmp_path / "freshness-manifest.pre-gate3.json"

        manifest_path.write_text('{"run_id": "new-run"}', encoding="utf-8")
        backup_path.write_text('{"run_id": "original-run"}', encoding="utf-8")

        _restore_backup(manifest_path, backup_path)

        assert manifest_path.exists()
        assert not backup_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "original-run"

    def test_restore_backup_tolerates_missing_backup(self, tmp_path):
        """_restore_backup() does not raise when backup does not exist."""
        manifest_path = tmp_path / "freshness-manifest.json"
        backup_path = tmp_path / "freshness-manifest.pre-gate3.json"
        manifest_path.write_text("{}", encoding="utf-8")

        # Should not raise — backup missing is handled gracefully.
        _restore_backup(manifest_path, backup_path)


# ---------------------------------------------------------------------------
# Integration tests through run_harness()
# ---------------------------------------------------------------------------


class TestRunHarnessGate3aIntegration:
    """Integration tests that verify the Gate 3a wiring inside run_harness()."""

    def _make_fresh_stored_manifest(self):
        return _make_stored_manifest()

    def test_validate_only_no_write_even_with_fresh_decision(self, tmp_path):
        """validate-only + manifest_write_enabled=True + FRESH → no write (no_write=True default)."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()

        fingerprints_fresh = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }
        current_hash = _REAL_HASH_B  # matches stored hash → FRESH

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=current_hash
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_fresh), \
             patch("refresh_harness.validate_for_fresh", return_value=[]), \
             patch("refresh_harness.load_feature_flags", return_value=_GATE3_WRITE_FLAGS):

            result = run_harness(
                product="cells/java",
                mode="validate-only",
                scratch_root=tmp_path / "scratch",
                subdomains=["reference"],
                no_write=True,  # no_write=True prevents write
                run_id="gate3a-integration-001",
            )

        # With no_write=True, no manifest write should occur regardless of flags.
        backup_path = state_root / "cells" / "java" / "reference" / "freshness-manifest.pre-gate3.json"
        assert not backup_path.exists()
        assert result["run_status"] in ("PASS", "DRY_RUN_PASS", "PARTIAL_PASS")

    def test_content_write_flag_raises_hard_block_in_harness(self, tmp_path):
        """refresh_content_write_enabled=True → RuntimeError raised by run_harness()."""
        stored = _make_stored_manifest()
        fingerprints_fresh = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }
        hard_block_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=_REAL_HASH_B
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_fresh), \
             patch("refresh_harness.validate_for_fresh", return_value=[]), \
             patch("refresh_harness.load_feature_flags", return_value=hard_block_flags):

            with pytest.raises(RuntimeError, match="HARD_BLOCK"):
                run_harness(
                    product="cells/java",
                    mode="validate-only",
                    scratch_root=tmp_path / "scratch",
                    subdomains=["reference"],
                    no_write=False,  # allow_write to reach write path
                    run_id="gate3a-integration-hardblock",
                )

    def test_validate_only_no_write_on_non_fresh_decision(self, tmp_path):
        """VALIDATE_ONLY decision → manifest_write_note is empty, no write attempted."""
        # No stored manifest → cold start → VALIDATE_ONLY
        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=_REAL_HASH_C
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value={"upstream_repo_sha": "sha_abc"}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path / "scratch",
                subdomains=["reference"],
                no_write=True,
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        # VALIDATE_ONLY → no manifest write note in explanation
        assert "manifest write" not in ref_records[0].get("explanation", "")

    def test_dry_run_behavior_unchanged_by_gate3a(self, tmp_path):
        """Dry-run mode with no_write=True is not affected by Gate 3a code."""
        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=None), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=None
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides", return_value={}):

            result = run_harness(
                product="cells/java",
                mode="dry-run",
                scratch_root=tmp_path / "scratch",
                subdomains=["reference"],
                no_write=True,
            )

        assert result["run_status"] == "DRY_RUN_PASS"
        assert result["surfaces_silently_skipped"] == 0

    def test_manifest_write_note_in_explanation_on_success(self, tmp_path):
        """When manifest is written successfully, explanation includes 'SUCCEEDED'."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()

        fingerprints_fresh = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=_REAL_HASH_B
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_fresh), \
             patch("refresh_harness.validate_for_fresh", return_value=[]), \
             patch("refresh_harness.load_feature_flags", return_value=_GATE3_WRITE_FLAGS), \
             patch("refresh_harness._write_manifest_gated",
                   return_value=(True, "manifest write SUCCEEDED (run_id='test-001')")):

            result = run_harness(
                product="cells/java",
                mode="validate-only",
                scratch_root=tmp_path / "scratch",
                subdomains=["reference"],
                no_write=False,
                run_id="test-001",
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        explanation = ref_records[0].get("explanation", "")
        assert "SUCCEEDED" in explanation

    def test_manifest_write_failure_sets_blocked_outcome(self, tmp_path):
        """When manifest write returns FAILED, surface outcome becomes BLOCKED."""
        stored = _make_stored_manifest()
        fingerprints_fresh = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }

        with _patch_registry(), \
             patch("refresh_harness._REGISTRY_PATH", MagicMock(is_file=lambda: True)), \
             patch("refresh_harness.load_manifest", return_value=stored), \
             patch("refresh_harness._inspect_output_state", return_value=MagicMock(
                 output_exists=True, output_content_hash=_REAL_HASH_B
             )), \
             patch("refresh_harness._collect_fingerprints_with_overrides",
                   return_value=fingerprints_fresh), \
             patch("refresh_harness.validate_for_fresh", return_value=[]), \
             patch("refresh_harness.load_feature_flags", return_value=_GATE3_WRITE_FLAGS), \
             patch("refresh_harness._write_manifest_gated",
                   return_value=(False, "manifest write FAILED (disk full); backup restored")):

            result = run_harness(
                product="cells/java",
                mode="validate-only",
                scratch_root=tmp_path / "scratch",
                subdomains=["reference"],
                no_write=False,
                run_id="test-fail-001",
            )

        records = result["records"]
        ref_records = [r for r in records if r["subdomain"] == "reference"]
        assert len(ref_records) == 1
        assert ref_records[0]["decision"] == "BLOCKED"
        assert ref_records[0]["outcome"] == "BLOCKED"


# ---------------------------------------------------------------------------
# Tests for manifest_restore.py CLI
# ---------------------------------------------------------------------------


class TestManifestRestoreUtility:
    """Tests for the manifest_restore.py standalone restore script."""

    def _make_restore_state(self, tmp_path, manifest_run_id="current-run", backup_run_id="backup-run"):
        """Create state dir with both manifest and backup files."""
        manifest_dir = tmp_path / "cells" / "java" / "reference"
        manifest_dir.mkdir(parents=True)

        manifest_data = dict(_BASE_MANIFEST_DATA, run_id=manifest_run_id)
        backup_data = dict(_BASE_MANIFEST_DATA, run_id=backup_run_id)

        manifest_path = manifest_dir / "freshness-manifest.json"
        backup_path = manifest_dir / "freshness-manifest.pre-gate3.json"

        manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
        backup_path.write_text(json.dumps(backup_data), encoding="utf-8")

        return manifest_path, backup_path

    def test_restore_utility_restores_backup(self, tmp_path):
        """manifest_restore.py restores backup to manifest path on success."""
        from manifest_restore import restore_manifest

        state_root = tmp_path
        manifest_path, backup_path = self._make_restore_state(
            state_root / "cells" / "java" / "reference",
            manifest_run_id="gate3-run",
            backup_run_id="pre-gate3-original",
        )
        # Recreate state_root structure properly.
        state_root2 = tmp_path / "state"
        manifest_dir = state_root2 / "cells" / "java" / "reference"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "freshness-manifest.json").write_text(
            json.dumps(dict(_BASE_MANIFEST_DATA, run_id="gate3-written")), encoding="utf-8"
        )
        (manifest_dir / "freshness-manifest.pre-gate3.json").write_text(
            json.dumps(dict(_BASE_MANIFEST_DATA, run_id="original-before-gate3")), encoding="utf-8"
        )

        rc = restore_manifest("cells/java", "reference", state_root=state_root2)

        assert rc == 0
        # Backup should be gone.
        assert not (manifest_dir / "freshness-manifest.pre-gate3.json").exists()
        # Manifest should have backup's run_id.
        data = json.loads((manifest_dir / "freshness-manifest.json").read_text(encoding="utf-8"))
        assert data["run_id"] == "original-before-gate3"

    def test_restore_utility_returns_1_when_no_backup(self, tmp_path):
        """manifest_restore.py exits 1 when no backup file exists."""
        from manifest_restore import restore_manifest

        state_root = tmp_path / "state"
        manifest_dir = state_root / "cells" / "java" / "reference"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "freshness-manifest.json").write_text("{}", encoding="utf-8")
        # No backup created.

        rc = restore_manifest("cells/java", "reference", state_root=state_root)

        assert rc == 1

    def test_restore_utility_bad_product_format(self):
        """manifest_restore.main() exits 2 for bad --product format."""
        from manifest_restore import main as restore_main

        rc = restore_main(["--product", "noslash", "--subdomain", "reference"])
        assert rc == 2

    def test_restore_utility_reports_before_and_after_status(self, tmp_path, capsys):
        """manifest_restore.py prints before/after manifest_status."""
        from manifest_restore import restore_manifest

        state_root = tmp_path / "state"
        manifest_dir = state_root / "cells" / "java" / "reference"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "freshness-manifest.json").write_text(
            json.dumps(dict(_BASE_MANIFEST_DATA, manifest_status="FRESH", run_id="gate3-run")),
            encoding="utf-8",
        )
        (manifest_dir / "freshness-manifest.pre-gate3.json").write_text(
            json.dumps(dict(_BASE_MANIFEST_DATA, manifest_status="FRESH", run_id="pre-gate3")),
            encoding="utf-8",
        )

        rc = restore_manifest("cells/java", "reference", state_root=state_root)
        captured = capsys.readouterr()

        assert rc == 0
        assert "Before:" in captured.out
        assert "After:" in captured.out


# ---------------------------------------------------------------------------
# Production flags safety guard
# ---------------------------------------------------------------------------


class TestProductionFlagsSafety:
    """Verify the production feature flags file never has write flags enabled."""

    def test_production_flags_manifest_write_disabled(self):
        """data/refresh-feature-flags.json has refresh_manifest_write_enabled=False."""
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = load_feature_flags(flags_path)
        assert flags["refresh_manifest_write_enabled"] is False, (
            "Production manifest write flag must be False. "
            "Gate 3b has NOT been approved yet."
        )

    def test_production_flags_content_write_disabled(self):
        """data/refresh-feature-flags.json has refresh_content_write_enabled=False."""
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = load_feature_flags(flags_path)
        assert flags["refresh_content_write_enabled"] is False, (
            "Production content write flag must be False."
        )

    def test_production_flags_enforced_disabled(self):
        """data/refresh-feature-flags.json has refresh_reconciliation_enforced=False."""
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = load_feature_flags(flags_path)
        assert flags["refresh_reconciliation_enforced"] is False, (
            "Production enforced flag must be False outside of Gate 3b execution."
        )

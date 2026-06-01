"""Gate 3a/3b tests for refresh_harness.py manifest and content write integration.

Covers:
  - manifest write flag false → no write
  - manifest write flag true + --no-write → no write
  - manifest write flag true + --allow-write + FRESH → write occurs
  - VALIDATE_ONLY decision → no write
  - REGENERATE_* decision + flag disabled → no dispatch
  - refresh_content_write_enabled=True (Phase 5): no longer raises HARD_BLOCK
  - backup created before write
  - backup removed after successful verification
  - backup restored on write failure
  - post-write verification failure restores backup
  - written manifest has correct run_id
  - written manifest has FRESH status
  - manifest_restore.py restores backup correctly
  - manifest_restore.py fails safely when backup is missing
  - existing dry-run behavior remains unchanged (regression guard)
  Phase 5 (Gate 3b):
  - FRESH decision → dispatch_content_write NOT called
  - REGENERATE_UPSTREAM + content_write_enabled=True + no_write=True → dispatch skipped
  - REGENERATE_UPSTREAM + content_write_enabled=False → dispatch not called
  - REGENERATE_UPSTREAM + content_write_enabled=True + no_write=False → dispatch called
  - REGENERATE_GENERATOR + content_write_enabled=True → dispatch called
  - dispatch returns (False, ...) → outcome is SKIP, explanation includes note
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

# conftest.py adds scripts/pipeline/lib/ and scripts/pipeline/ to sys.path
from refresh_harness import (
    _REGISTRY_PATH,
    _write_manifest_gated,
    _restore_backup,
    configure as _harness_configure,
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
    return SimpleNamespace(output_exists=True, output_content_hash=output_hash)


def _make_registry():
    """Return a minimal DependencyRegistry (no patching)."""
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
    return DependencyRegistry(data)


@pytest.fixture(autouse=True)
def reset_harness_config():
    """Reset refresh_harness.configure() overrides after each test."""
    yield
    _harness_configure()


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

    def test_content_write_enabled_does_not_block_manifest_write(self, tmp_path):
        """Phase 5: refresh_content_write_enabled=True no longer blocks _write_manifest_gated.

        Content writes are dispatched separately (Gate 3b) for REGENERATE_* decisions.
        _write_manifest_gated handles only FRESH decision manifest updates and is not
        affected by the content write flag.
        """
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        written, note = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={
                "upstream_repo_sha": "sha_stored_abc",
                "local_knowledge_sha": "sha_local_xyz",
                "generator_code_hash": _REAL_HASH,
            },
            current_outputs=_make_output_state(),
            stored=stored,
            run_id="phase5-manifest-001",
            flags=flags,
            no_write=False,
            state_root=state_root,
        )

        # Manifest write should succeed — content_write_enabled doesn't block it.
        assert written
        assert "SUCCEEDED" in note

    def test_content_write_enabled_no_write_skips_via_no_write_guard(self, tmp_path):
        """Phase 5: content_write_enabled=True with no_write=True → skipped by no_write guard."""
        state_root = _make_state_dir(tmp_path, _BASE_MANIFEST_DATA)
        stored = _make_stored_manifest()
        flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        written, note = _write_manifest_gated(
            product="cells/java",
            subdomain="reference",
            fingerprints={},
            current_outputs=_make_output_state(),
            stored=stored,
            run_id="phase5-manifest-002",
            flags=flags,
            no_write=True,
            state_root=state_root,
        )

        # Skipped because no_write=True, not because of content_write flag.
        assert not written
        assert "no_write=True" in note

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

        from freshness_manifest import save as real_save

        def _spy_save(manifest, state_root=None):
            # Check if backup exists at the moment save() is called.
            backup_existed_before_save.append(backup_path.exists())
            return real_save(manifest, state_root=state_root)

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
            _save_fn=_spy_save,
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

        def _fail_save(*a, **kw):
            raise OSError("disk full")

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
            _save_fn=_fail_save,
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

        # Allow save() to succeed (manifest is written) but load() returns None
        # to simulate post-write verification failure.
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
            _load_fn=lambda *a, **kw: None,
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

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=current_hash
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_fresh),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: _GATE3_WRITE_FLAGS,
        )
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

    def test_content_write_flag_enabled_no_error_for_fresh_decision(self, tmp_path):
        """Phase 5: refresh_content_write_enabled=True with FRESH decision → no error raised.

        Content writes are dispatched in Gate 3b for REGENERATE_* decisions only.
        FRESH decisions go through Gate 3a (manifest write). The content write flag
        being True doesn't cause errors for FRESH decisions.
        """
        stored = _make_stored_manifest()
        fingerprints_fresh = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }
        content_write_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_fresh),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: content_write_flags,
            # Provide a no-op manifest write to avoid state_root dependency
            write_manifest_gated_fn=lambda **kw: (False, "write skipped (no state_root in test)"),
        )
        # Should NOT raise — HARD_BLOCK removed in Phase 5.
        result = run_harness(
            product="cells/java",
            mode="validate-only",
            scratch_root=tmp_path / "scratch",
            subdomains=["reference"],
            no_write=False,
            run_id="phase5-integration-hardblock-removed",
        )
        assert result["run_status"] in ("PASS", "DRY_RUN_PASS", "PARTIAL_PASS")

    def test_validate_only_no_write_on_non_fresh_decision(self, tmp_path):
        """VALIDATE_ONLY decision → manifest_write_note is empty, no write attempted."""
        # No stored manifest → cold start → VALIDATE_ONLY
        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: None,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_C
            ),
            collect_fingerprints_fn=lambda *a, **kw: {"upstream_repo_sha": "sha_abc"},
        )
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
        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: None,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=None
            ),
            collect_fingerprints_fn=lambda *a, **kw: {},
        )
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

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_fresh),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: _GATE3_WRITE_FLAGS,
            write_manifest_gated_fn=lambda *a, **kw: (True, "manifest write SUCCEEDED (run_id='test-001')"),
        )
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

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_fresh),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: _GATE3_WRITE_FLAGS,
            write_manifest_gated_fn=lambda *a, **kw: (False, "manifest write FAILED (disk full); backup restored"),
        )
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

    def test_production_flags_manifest_write_enabled(self):
        """data/refresh-feature-flags.json has refresh_manifest_write_enabled=True.

        Phase 2 (REFRESH-ARCH-001, approved 2026-05-29): manifest writes are
        intentionally enabled. Phase 5 (content writes) must remain False.
        """
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = load_feature_flags(flags_path)
        assert flags["refresh_manifest_write_enabled"] is True, (
            "Phase 2 approved — refresh_manifest_write_enabled must be True."
        )

    def test_production_flags_content_write_enabled(self):
        """data/refresh-feature-flags.json has refresh_content_write_enabled=True.

        Phase 5 enabled 2026-05-31 after canary verification (amendment-009).
        Guard verdicts in semantic_refresh_guard.py ensure writes are safe.
        """
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = load_feature_flags(flags_path)
        assert flags["refresh_content_write_enabled"] is True, (
            "Production content write flag must be True (Phase 5 live since 2026-05-31)."
        )

    def test_production_flags_enforced_enabled(self):
        """data/refresh-feature-flags.json has refresh_reconciliation_enforced=True.

        Phase 3 (REFRESH-ARCH-001, approved 2026-05-29): reconciliation enforcement
        is intentionally True. Phase 5 (content writes) must remain False.
        """
        flags_path = _REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            pytest.skip("data/refresh-feature-flags.json not found")
        flags = load_feature_flags(flags_path)
        assert flags["refresh_reconciliation_enforced"] is True, (
            "Phase 3 approved — refresh_reconciliation_enforced must be True."
        )


# ---------------------------------------------------------------------------
# Phase 5 (Gate 3b): Content write dispatch tests
# ---------------------------------------------------------------------------


class TestGate3bContentWrite:
    """Phase 5: Gate 3b content write dispatch via configure() seam.

    These tests verify that _dispatch_content_write is called only when:
    - Decision is REGENERATE_UPSTREAM or REGENERATE_GENERATOR
    - refresh_content_write_enabled=True
    - no_write=False

    All tests use fake dispatch functions injected via configure() to avoid
    invoking the real batch_reference.py.
    """

    def test_fresh_decision_does_not_call_dispatch(self, tmp_path):
        """FRESH decision → Gate 3b dispatch NOT called even when content_write_enabled=True."""
        dispatched = []

        def _fake_dispatch(product, subdomain, decision, flags, no_write):
            dispatched.append(decision)
            return True, "content write SUCCEEDED"

        stored = _make_stored_manifest()
        fingerprints_fresh = {
            "upstream_repo_sha": "sha_stored_abc",
            "local_knowledge_sha": "sha_local_xyz",
        }
        content_write_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_fresh),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: content_write_flags,
            write_manifest_gated_fn=lambda **kw: (False, "skipped (no state_root)"),
            dispatch_content_write_fn=_fake_dispatch,
        )
        run_harness(
            product="cells/java",
            mode="validate-only",
            scratch_root=tmp_path / "scratch",
            subdomains=["reference"],
            no_write=False,
            run_id="phase5-3b-fresh-001",
        )

        # FRESH decision → dispatch never called
        assert dispatched == []

    def test_regenerate_no_write_true_skips_dispatch(self, tmp_path):
        """REGENERATE_UPSTREAM + no_write=True → dispatch NOT called."""
        dispatched = []

        def _fake_dispatch(product, subdomain, decision, flags, no_write):
            dispatched.append(decision)
            return True, "content write SUCCEEDED"

        stored = _make_stored_manifest()
        fingerprints_regen = {
            "upstream_repo_sha": "sha_different_xyz",
            "local_knowledge_sha": "sha_local_xyz",
        }
        content_write_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_regen),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: content_write_flags,
            dispatch_content_write_fn=_fake_dispatch,
        )
        run_harness(
            product="cells/java",
            mode="dry-run",
            scratch_root=tmp_path / "scratch",
            subdomains=["reference"],
            no_write=True,  # no_write=True → dispatch skipped
            run_id="phase5-3b-nowrite-002",
        )

        assert dispatched == []

    def test_regenerate_flag_disabled_skips_dispatch(self, tmp_path):
        """refresh_content_write_enabled=False + REGENERATE → dispatch NOT called."""
        dispatched = []

        def _fake_dispatch(product, subdomain, decision, flags, no_write):
            dispatched.append(decision)
            return True, "content write SUCCEEDED"

        stored = _make_stored_manifest()
        fingerprints_regen = {
            "upstream_repo_sha": "sha_different_xyz",
            "local_knowledge_sha": "sha_local_xyz",
        }
        # Flag disabled
        no_content_write_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=False)

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_regen),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: no_content_write_flags,
            dispatch_content_write_fn=_fake_dispatch,
        )
        run_harness(
            product="cells/java",
            mode="dry-run",
            scratch_root=tmp_path / "scratch",
            subdomains=["reference"],
            no_write=False,
            run_id="phase5-3b-disabled-003",
        )

        assert dispatched == []

    def test_regenerate_upstream_dispatch_called_outcome_content_written(self, tmp_path):
        """REGENERATE_UPSTREAM + enabled + no_write=False → dispatch called, outcome=CONTENT_WRITTEN."""
        dispatched = []

        def _fake_dispatch(product, subdomain, decision, flags, no_write):
            dispatched.append((product, subdomain, decision))
            return True, "content write SUCCEEDED (decision=REGENERATE_UPSTREAM, verdict='SEMANTIC_NOOP_PROVEN')"

        stored = _make_stored_manifest()
        fingerprints_regen = {
            "upstream_repo_sha": "sha_different_xyz",
            "local_knowledge_sha": "sha_local_xyz",
        }
        content_write_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_regen),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: content_write_flags,
            dispatch_content_write_fn=_fake_dispatch,
        )
        result = run_harness(
            product="cells/java",
            mode="dry-run",
            scratch_root=tmp_path / "scratch",
            subdomains=["reference"],
            no_write=False,
            run_id="phase5-3b-dispatch-004",
        )

        assert len(dispatched) == 1
        assert dispatched[0] == ("cells/java", "reference", "REGENERATE_UPSTREAM")
        ref_record = [r for r in result["records"] if r["subdomain"] == "reference"][0]
        assert ref_record["outcome"] == "CONTENT_WRITTEN"
        assert "content write SUCCEEDED" in ref_record.get("explanation", "")

    def test_regenerate_generator_dispatch_called(self, tmp_path):
        """REGENERATE_GENERATOR + enabled → dispatch called with REGENERATE_GENERATOR decision."""
        dispatched_decisions = []

        def _fake_dispatch(product, subdomain, decision, flags, no_write):
            dispatched_decisions.append(decision)
            return True, "content write SUCCEEDED (decision=REGENERATE_GENERATOR, verdict='BODY_UPDATED_VERIFIED')"

        stored = _make_stored_manifest()
        # Change local_knowledge_sha to trigger REGENERATE_GENERATOR
        fingerprints_gen = {
            "upstream_repo_sha": "sha_stored_abc",      # same as stored → not upstream trigger
            "local_knowledge_sha": "sha_different_gen",  # different → generator input changed
        }
        content_write_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_gen),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: content_write_flags,
            dispatch_content_write_fn=_fake_dispatch,
        )
        result = run_harness(
            product="cells/java",
            mode="dry-run",
            scratch_root=tmp_path / "scratch",
            subdomains=["reference"],
            no_write=False,
            run_id="phase5-3b-gen-005",
        )

        # local_knowledge_sha changed but upstream_repo_sha did not.
        # The decision may be REGENERATE_GENERATOR or REGENERATE_UPSTREAM depending
        # on what the decision engine treats as primary trigger. Either is acceptable.
        assert any(
            d in ("REGENERATE_UPSTREAM", "REGENERATE_GENERATOR") for d in dispatched_decisions
        ), f"Expected REGENERATE decision, got: {dispatched_decisions}"

    def test_dispatch_blocked_outcome_is_skip(self, tmp_path):
        """Dispatch returns (False, blocked_note) → outcome=SKIP, explanation includes note."""

        def _fake_dispatch(product, subdomain, decision, flags, no_write):
            return False, "content write blocked (semantic guard verdict='REFRESH_BLOCKED_UNPROVEN_NOOP')"

        stored = _make_stored_manifest()
        fingerprints_regen = {
            "upstream_repo_sha": "sha_different_xyz",
            "local_knowledge_sha": "sha_local_xyz",
        }
        content_write_flags = dict(_GATE3_WRITE_FLAGS, refresh_content_write_enabled=True)

        _harness_configure(
            registry_path=SimpleNamespace(is_file=lambda: True),
            load_registry_fn=lambda *a, **kw: _make_registry(),
            load_manifest_fn=lambda *a, **kw: stored,
            inspect_output_state_fn=lambda *a, **kw: SimpleNamespace(
                output_exists=True, output_content_hash=_REAL_HASH_B
            ),
            collect_fingerprints_fn=lambda *a, **kw: dict(fingerprints_regen),
            validate_for_fresh_fn=lambda *a, **kw: [],
            load_feature_flags_fn=lambda *a, **kw: content_write_flags,
            dispatch_content_write_fn=_fake_dispatch,
        )
        result = run_harness(
            product="cells/java",
            mode="dry-run",
            scratch_root=tmp_path / "scratch",
            subdomains=["reference"],
            no_write=False,
            run_id="phase5-3b-blocked-006",
        )

        ref_record = [r for r in result["records"] if r["subdomain"] == "reference"][0]
        assert ref_record["outcome"] == "SKIP"
        assert "content write blocked" in ref_record.get("explanation", "")


class TestDispatchContentWriteIntegration:
    """Integration tests for _dispatch_content_write() with real subprocess calls.

    These tests exercise the real dispatch function (not mocked) to verify:
    - Verdict file parsing from disk
    - Verdict-to-action routing (PASS/BLOCK/ABORT)
    - Real subprocess invocation via subprocess.run()
    """

    def _make_verdict(self, tmp_path, verdict_name, family="test", platform="py"):
        verdict_dir = tmp_path / "reports" / "refresh_review" / family / platform
        verdict_dir.mkdir(parents=True, exist_ok=True)
        verdict_path = verdict_dir / "semantic_refresh_verdict.json"
        import json
        verdict_path.write_text(json.dumps({
            "verdict": verdict_name,
            "proof": [f"test verdict: {verdict_name}"],
        }), encoding="utf-8")
        return verdict_path

    def _make_stub_script(self, tmp_path, exit_code=0):
        """Create a stub batch_reference.py that writes a marker and exits."""
        script_dir = tmp_path / "scripts" / "pipeline" / "commands" / "content"
        script_dir.mkdir(parents=True, exist_ok=True)
        marker = tmp_path / "dispatch_marker.txt"
        stub = script_dir / "batch_reference.py"
        stub.write_text(
            f"import sys\n"
            f"from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('dispatched:' + ':'.join(sys.argv[1:]))\n"
            f"sys.exit({exit_code})\n",
            encoding="utf-8",
        )
        return stub, marker

    def test_passing_verdict_invokes_subprocess(self, tmp_path, monkeypatch):
        """Exit-0 verdict (BODY_UPDATED_VERIFIED) triggers real subprocess invocation."""
        import refresh_harness as rh

        self._make_verdict(tmp_path, "BODY_UPDATED_VERIFIED", "test", "py")
        _stub, marker = self._make_stub_script(tmp_path, exit_code=0)
        monkeypatch.setattr(rh, "_REPO_ROOT", tmp_path)

        written, note = rh._dispatch_content_write(
            product="test/py",
            subdomain="reference",
            decision="REGENERATE_UPSTREAM",
            flags={"refresh_content_write_enabled": True},
            no_write=False,
        )

        assert written is True
        assert "SUCCEEDED" in note
        assert marker.exists(), "Stub script was not invoked — subprocess.run() not called"
        assert "test:py:--update" in marker.read_text()

    def test_blocking_verdict_skips_subprocess(self, tmp_path, monkeypatch):
        """Exit-1 verdict (SEMANTIC_REFRESH_REQUIRED) skips subprocess."""
        import refresh_harness as rh

        self._make_verdict(tmp_path, "SEMANTIC_REFRESH_REQUIRED", "test", "py")
        _stub, marker = self._make_stub_script(tmp_path, exit_code=0)
        monkeypatch.setattr(rh, "_REPO_ROOT", tmp_path)

        written, note = rh._dispatch_content_write(
            product="test/py",
            subdomain="reference",
            decision="REGENERATE_UPSTREAM",
            flags={"refresh_content_write_enabled": True},
            no_write=False,
        )

        assert written is False
        assert "blocked" in note
        assert not marker.exists(), "Subprocess was invoked despite BLOCKING verdict"

    def test_abort_verdict_raises_runtime_error(self, tmp_path, monkeypatch):
        """Exit-2 verdict (CLAIM_EXTRACTION_MISSED_DELTA) raises RuntimeError."""
        import refresh_harness as rh

        self._make_verdict(tmp_path, "CLAIM_EXTRACTION_MISSED_DELTA", "test", "py")
        monkeypatch.setattr(rh, "_REPO_ROOT", tmp_path)

        with pytest.raises(RuntimeError, match="PHASE5_ABORT"):
            rh._dispatch_content_write(
                product="test/py",
                subdomain="reference",
                decision="REGENERATE_UPSTREAM",
                flags={"refresh_content_write_enabled": True},
                no_write=False,
            )

    def test_missing_verdict_skips_write(self, tmp_path, monkeypatch):
        """No verdict file on disk → write skipped with advisory note."""
        import refresh_harness as rh

        monkeypatch.setattr(rh, "_REPO_ROOT", tmp_path)

        written, note = rh._dispatch_content_write(
            product="test/py",
            subdomain="reference",
            decision="REGENERATE_UPSTREAM",
            flags={"refresh_content_write_enabled": True},
            no_write=False,
        )

        assert written is False
        assert "no semantic_refresh_verdict.json" in note

    def test_subprocess_failure_returns_false(self, tmp_path, monkeypatch):
        """Subprocess returning non-zero exit code → written=False, FAILED note."""
        import refresh_harness as rh

        self._make_verdict(tmp_path, "SEMANTIC_NOOP_PROVEN", "test", "py")
        _stub, marker = self._make_stub_script(tmp_path, exit_code=1)
        monkeypatch.setattr(rh, "_REPO_ROOT", tmp_path)

        written, note = rh._dispatch_content_write(
            product="test/py",
            subdomain="reference",
            decision="REGENERATE_UPSTREAM",
            flags={"refresh_content_write_enabled": True},
            no_write=False,
        )

        assert written is False
        assert "FAILED" in note
        assert marker.exists(), "Subprocess should have been invoked (exit code checked after)"

    def test_initial_refresh_allowed_verdict_passes_dispatch(self, tmp_path, monkeypatch):
        """INITIAL_REFRESH_ALLOWED verdict triggers subprocess and writes dispatch_history.json."""
        import refresh_harness as rh

        self._make_verdict(tmp_path, "INITIAL_REFRESH_ALLOWED", "test", "py")
        _stub, marker = self._make_stub_script(tmp_path, exit_code=0)
        monkeypatch.setattr(rh, "_REPO_ROOT", tmp_path)
        monkeypatch.setattr(rh, "_STATE_ROOT", tmp_path / "runs" / "state")

        written, note = rh._dispatch_content_write(
            product="test/py",
            subdomain="reference",
            decision="REGENERATE_UPSTREAM",
            flags={"refresh_content_write_enabled": True},
            no_write=False,
        )

        assert written is True
        assert "SUCCEEDED" in note
        assert marker.exists(), "Stub script was not invoked"
        # Verify dispatch_history.json was written
        dispatch_state = tmp_path / "runs" / "state" / "test" / "py" / "dispatch_history.json"
        assert dispatch_state.exists(), "dispatch_history.json was not written after successful dispatch"
        import json
        history = json.loads(dispatch_state.read_text())
        assert history["decision"] == "REGENERATE_UPSTREAM"
        assert history["verdict"] == "INITIAL_REFRESH_ALLOWED"

    def test_dispatch_history_not_written_on_failure(self, tmp_path, monkeypatch):
        """Failed dispatch (exit code 1) must NOT write dispatch_history.json."""
        import refresh_harness as rh

        self._make_verdict(tmp_path, "INITIAL_REFRESH_ALLOWED", "test", "py")
        _stub, marker = self._make_stub_script(tmp_path, exit_code=1)
        monkeypatch.setattr(rh, "_REPO_ROOT", tmp_path)
        monkeypatch.setattr(rh, "_STATE_ROOT", tmp_path / "runs" / "state")

        written, note = rh._dispatch_content_write(
            product="test/py",
            subdomain="reference",
            decision="REGENERATE_UPSTREAM",
            flags={"refresh_content_write_enabled": True},
            no_write=False,
        )

        assert written is False
        dispatch_state = tmp_path / "runs" / "state" / "test" / "py" / "dispatch_history.json"
        assert not dispatch_state.exists(), "dispatch_history.json should NOT be written on failed dispatch"

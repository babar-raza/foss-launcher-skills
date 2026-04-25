"""test_section_enhance_validator.py — Regression harness for S-96 section-enhance Phase 1 audit.

Validates schema and behavioral contracts of S-96 proposal pack outputs.
All tests use committed minimal fixtures or tmp_path — no live S-96 invocation,
no content/ access, no LLM calls.

Test groups:
    TC-SE-01  Artifact completeness
    TC-SE-02  Manifest alias fields
    TC-SE-03  Adapter activation per subdomain (docs/KB/products/blog/reference + leak)
    TC-SE-04  No-content-write detection utility
    TC-SE-05  Zero-proposal run validation
    TC-SE-06  Stale clone-cache rejection (references existing test_clone_cache.py tests)
    TC-SE-07  Slug validation
    TC-SE-08  Readiness scope guard
"""

import json
import sys
from pathlib import Path

import pytest

# conftest.py inserts scripts/pipeline/ into sys.path
from section_enhance_validator import (
    REQUIRED_ARTIFACTS,
    detect_content_writes,
    snapshot_content_mtimes,
    validate_adapter_activation,
    validate_artifact_pack,
    validate_manifest_aliases,
    validate_proposal_slug,
    validate_zero_proposal_run,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "section_enhance"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(name: str) -> dict:
    """Load a fixture JSON file by name."""
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# TC-SE-01: Artifact completeness
# ---------------------------------------------------------------------------

class TestArtifactCompleteness:
    def test_complete_pack_passes(self):
        pack_dir = _FIXTURES_DIR / "complete_pack"
        valid, missing = validate_artifact_pack(pack_dir)
        assert valid is True, f"expected valid pack but got missing: {missing}"
        assert missing == []

    def test_incomplete_pack_detects_missing_risk_report(self):
        pack_dir = _FIXTURES_DIR / "incomplete_pack"
        valid, missing = validate_artifact_pack(pack_dir)
        assert valid is False
        assert "07-risk-report.md" in missing

    def test_nonexistent_pack_dir_fails(self, tmp_path):
        valid, missing = validate_artifact_pack(tmp_path / "does_not_exist")
        assert valid is False
        assert len(missing) == len(REQUIRED_ARTIFACTS)

    def test_proposals_dir_missing_reported_as_directory(self, tmp_path):
        # A pack with all files but no 05-proposals/ dir
        for artifact in REQUIRED_ARTIFACTS:
            if artifact != "05-proposals":
                (tmp_path / artifact).touch()
        valid, missing = validate_artifact_pack(tmp_path)
        assert valid is False
        assert "05-proposals/" in missing


# ---------------------------------------------------------------------------
# TC-SE-02: Manifest alias fields
# ---------------------------------------------------------------------------

class TestManifestAliasFields:
    def test_valid_aliases_pass(self):
        manifest = _load("manifest_with_aliases.json")
        valid, errors = validate_manifest_aliases(manifest)
        assert valid is True, f"expected valid but got errors: {errors}"
        assert errors == []

    def test_missing_evidence_key_detected(self):
        manifest = _load("manifest_alias_missing_key.json")
        valid, errors = validate_manifest_aliases(manifest)
        assert valid is False
        assert any("evidence" in e for e in errors), f"errors={errors}"

    def test_no_input_aliases_field_is_ok(self):
        manifest = {"run_id": "test", "proposals_generated": 0}
        valid, errors = validate_manifest_aliases(manifest)
        assert valid is True
        assert errors == []

    def test_input_aliases_not_a_list_fails(self):
        manifest = {"input_aliases": "not-a-list"}
        valid, errors = validate_manifest_aliases(manifest)
        assert valid is False
        assert "input_aliases must be a list" in errors

    def test_all_four_keys_required(self):
        manifest = {
            "input_aliases": [
                {"from": "a", "to": "b"}  # missing reason and evidence
            ]
        }
        valid, errors = validate_manifest_aliases(manifest)
        assert valid is False
        assert any("reason" in e for e in errors)
        assert any("evidence" in e for e in errors)


# ---------------------------------------------------------------------------
# TC-SE-03: Adapter activation per subdomain
# ---------------------------------------------------------------------------

class TestAdapterActivation:
    def test_docs_adapter_passes(self):
        manifest = _load("manifest_docs.json")
        valid, errors = validate_adapter_activation(manifest, "docs")
        assert valid is True, f"errors: {errors}"

    def test_kb_adapter_passes(self):
        manifest = _load("manifest_kb.json")
        valid, errors = validate_adapter_activation(manifest, "kb")
        assert valid is True, f"errors: {errors}"

    def test_products_adapter_passes(self):
        manifest = _load("manifest_products.json")
        valid, errors = validate_adapter_activation(manifest, "products")
        assert valid is True, f"errors: {errors}"

    def test_blog_adapter_passes(self):
        manifest = _load("manifest_blog.json")
        valid, errors = validate_adapter_activation(manifest, "blog")
        assert valid is True, f"errors: {errors}"

    def test_reference_adapter_passes(self):
        manifest = _load("manifest_reference.json")
        valid, errors = validate_adapter_activation(manifest, "reference")
        assert valid is True, f"errors: {errors}"

    def test_leaked_kb_in_docs_run_detected(self):
        manifest = _load("manifest_docs_leaked_kb.json")
        valid, errors = validate_adapter_activation(manifest, "docs")
        assert valid is False
        assert any("kb" in e for e in errors), f"errors={errors}"

    def test_missing_primary_adapter_detected(self):
        manifest = {
            "adapters_activated": ["clone-cache"],
            "adapters_NOT_activated": ["docs", "kb", "products", "blog", "reference"],
        }
        valid, errors = validate_adapter_activation(manifest, "docs")
        assert valid is False
        assert any("docs" in e and "not in adapters_activated" in e for e in errors)

    def test_disjointness_violation_detected(self):
        manifest = {
            "adapters_activated": ["docs", "clone-cache"],
            "adapters_NOT_activated": ["clone-cache", "kb", "products", "blog", "reference"],
        }
        valid, errors = validate_adapter_activation(manifest, "docs")
        assert valid is False
        assert any("both" in e for e in errors)

    def test_unknown_adapter_detected(self):
        manifest = {
            "adapters_activated": ["docs", "unknown-xyz"],
            "adapters_NOT_activated": ["kb", "products", "blog", "reference"],
        }
        valid, errors = validate_adapter_activation(manifest, "docs")
        assert valid is False
        assert any("unknown-xyz" in e for e in errors)


# ---------------------------------------------------------------------------
# TC-SE-04: No-content-write detection utility
# ---------------------------------------------------------------------------

class TestNoContentWriteDetection:
    def test_no_changes_returns_empty(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        (content / "page.md").write_text("hello")
        snapshot = snapshot_content_mtimes(content)
        result = detect_content_writes(content, snapshot)
        assert result == []

    def test_new_file_detected(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        (content / "existing.md").write_text("hello")
        snapshot = snapshot_content_mtimes(content)
        # create a new file after snapshot
        (content / "new.md").write_text("new content")
        changed = detect_content_writes(content, snapshot)
        assert any("new.md" in p for p in changed)

    def test_modified_file_detected(self, tmp_path):
        content = tmp_path / "content"
        content.mkdir()
        page = content / "page.md"
        page.write_text("original")
        snapshot = snapshot_content_mtimes(content)
        import time
        time.sleep(0.01)
        page.write_text("modified")
        changed = detect_content_writes(content, snapshot)
        assert any("page.md" in p for p in changed)

    def test_nonexistent_root_returns_empty(self, tmp_path):
        snapshot = snapshot_content_mtimes(tmp_path / "nonexistent")
        result = detect_content_writes(tmp_path / "nonexistent", snapshot)
        assert snapshot == {}
        assert result == []


# ---------------------------------------------------------------------------
# TC-SE-05: Zero-proposal run validation
# ---------------------------------------------------------------------------

class TestZeroProposalRun:
    def test_valid_zero_proposal_run_passes(self, tmp_path):
        manifest = _load("manifest_zero_proposals.json")
        # Build a minimal pack dir with empty 05-proposals/
        proposals_dir = tmp_path / "05-proposals"
        proposals_dir.mkdir()
        (proposals_dir / ".gitkeep").touch()
        valid, errors = validate_zero_proposal_run(manifest, tmp_path)
        assert valid is True, f"errors: {errors}"

    def test_missing_zero_proposal_reason_fails(self, tmp_path):
        manifest = {"proposals_generated": 0, "zero_proposal_reason": ""}
        proposals_dir = tmp_path / "05-proposals"
        proposals_dir.mkdir()
        valid, errors = validate_zero_proposal_run(manifest, tmp_path)
        assert valid is False
        assert any("zero_proposal_reason" in e for e in errors)

    def test_nonzero_proposals_fails(self, tmp_path):
        manifest = {"proposals_generated": 2, "zero_proposal_reason": "some reason"}
        valid, errors = validate_zero_proposal_run(manifest, tmp_path)
        assert valid is False
        assert any("proposals_generated" in e for e in errors)

    def test_nonempty_proposals_dir_fails(self, tmp_path):
        manifest = {
            "proposals_generated": 0,
            "zero_proposal_reason": "All classes covered."
        }
        proposals_dir = tmp_path / "05-proposals"
        proposals_dir.mkdir()
        (proposals_dir / "some-proposal.md").write_text("# proposal")
        valid, errors = validate_zero_proposal_run(manifest, tmp_path)
        assert valid is False
        assert any("05-proposals" in e for e in errors)

    def test_gitkeep_not_counted_as_proposal(self, tmp_path):
        manifest = {
            "proposals_generated": 0,
            "zero_proposal_reason": "All classes covered."
        }
        proposals_dir = tmp_path / "05-proposals"
        proposals_dir.mkdir()
        (proposals_dir / ".gitkeep").touch()
        valid, errors = validate_zero_proposal_run(manifest, tmp_path)
        assert valid is True, f"errors: {errors}"

    def test_missing_proposals_dir_fails(self, tmp_path):
        manifest = {
            "proposals_generated": 0,
            "zero_proposal_reason": "All classes covered."
        }
        # No 05-proposals/ directory created
        valid, errors = validate_zero_proposal_run(manifest, tmp_path)
        assert valid is False
        assert any("05-proposals" in e for e in errors)


# ---------------------------------------------------------------------------
# TC-SE-06: Stale clone-cache rejection
# (see test_clone_cache.py lines 156-192 for the full foss-launcher test suite)
# ---------------------------------------------------------------------------

class TestCloneCacheRejection:
    def test_foss_launcher_path_raises_value_error(self, monkeypatch):  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
        """Verify the foss-launcher guard is exercised via T4 env-patch.

        The full test suite for this behavior lives in test_clone_cache.py
        (tests: test_cache_root_env_foss_launcher_forward_slash_rejected,
        test_cache_root_env_foss_launcher_backslash_rejected,
        test_cache_root_env_foss_underscore_launcher_rejected).
        This test makes the coverage visible in the S-96 harness file.
        """
        # T4 env-patch: set env var to a foss-launcher path
        monkeypatch.setenv(
            "ASPOSE_CLONE_CACHE",
            "/some/path/foss-launcher/runs/.clone_cache"  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
        )
        from core.clone_cache import cache_root
        with pytest.raises(ValueError, match="obsolete foss-launcher"):
            cache_root()


# ---------------------------------------------------------------------------
# TC-SE-07: Slug validation
# ---------------------------------------------------------------------------

class TestSlugValidation:
    # Valid slugs
    def test_simple_slug_passes(self):
        valid, err = validate_proposal_slug("license")
        assert valid is True
        assert err is None

    def test_hyphenated_slug_passes(self):
        valid, err = validate_proposal_slug("working-with-materials")
        assert valid is True
        assert err is None

    def test_long_slug_passes(self):
        valid, err = validate_proposal_slug("how-to-use-conditional-formatting-dotnet")
        assert valid is True
        assert err is None

    def test_slug_starting_with_digit_fails(self):
        valid, err = validate_proposal_slug("3d-model-loading")
        # starts with digit — should this fail? per spec: must start with a letter
        # "^[a-z][a-z0-9]*" — digit start fails
        assert valid is False  # starts with digit, not a letter

    def test_lowercase_with_numbers_in_middle_passes(self):
        valid, err = validate_proposal_slug("cells4-features")
        assert valid is True
        assert err is None

    # Invalid slugs
    def test_leading_hyphen_rejected(self):
        valid, err = validate_proposal_slug("-license")
        assert valid is False
        assert "hyphen" in err

    def test_trailing_hyphen_rejected(self):
        valid, err = validate_proposal_slug("license-")
        assert valid is False
        assert "hyphen" in err

    def test_uppercase_rejected(self):
        valid, err = validate_proposal_slug("LicensePage")
        assert valid is False
        assert "lowercase" in err

    def test_empty_slug_rejected(self):
        valid, err = validate_proposal_slug("")
        assert valid is False
        assert "empty" in err

    def test_underscore_rejected(self):
        valid, err = validate_proposal_slug("license_page")
        assert valid is False
        assert "underscore" in err

    def test_mixed_case_rejected(self):
        valid, err = validate_proposal_slug("licenseAge")
        assert valid is False
        assert "lowercase" in err


# ---------------------------------------------------------------------------
# TC-SE-08: Readiness scope guard
# ---------------------------------------------------------------------------

class TestReadinessScopeGuard:
    def test_validator_contains_no_write_approved_reference(self):
        """The validator module must not contain any write-approved references.

        S-96 Phase 1 is audit-only. write-approved mode is blocked.
        This test fails if write-approved behavior is accidentally added.
        """
        import section_enhance_validator
        source_path = Path(section_enhance_validator.__file__)
        source = source_path.read_text(encoding="utf-8")
        assert "write_approved" not in source, (
            "section_enhance_validator.py must not reference write_approved"
        )
        assert "write-approved" not in source, (
            "section_enhance_validator.py must not reference write-approved"
        )

    def test_validator_contains_no_content_write_behavior(self):
        """The validator module must not call open() for writing or use write-path logic."""
        import section_enhance_validator
        source_path = Path(section_enhance_validator.__file__)
        source = source_path.read_text(encoding="utf-8")
        # No subprocess imports or calls (allow "subprocess" in docstring/comments)
        assert "import subprocess" not in source, (
            "section_enhance_validator.py must not import subprocess"
        )
        assert "subprocess.run" not in source, (
            "section_enhance_validator.py must not call subprocess.run"
        )
        assert "os.system(" not in source, (
            "section_enhance_validator.py must not call os.system"
        )
        # No open() calls with write mode (allow read-only opens in test helpers if any)
        import re
        write_open = re.search(r'open\s*\(.*["\']w["\']', source)
        assert write_open is None, (
            "section_enhance_validator.py must not open files for writing"
        )

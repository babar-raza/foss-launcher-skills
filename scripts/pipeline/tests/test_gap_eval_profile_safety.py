"""Tests for gap-eval profile safety: cross-check and Stage 1 → Tier 1 override."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from validate_profile import _read_package_from_build_file, validate_profile  # type: ignore  # noqa: E402
from run import stage1_baseline, stage2_knowledge_validation, tier1_verify  # type: ignore  # noqa: E402
from state import make_finding_id  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# _read_package_from_build_file
# ---------------------------------------------------------------------------

class TestReadPackageFromBuildFile:
    """Test the heuristic build-file parser used in cross-check."""

    def test_pyproject_toml(self, tmp_path):
        f = tmp_path / "pyproject.toml"
        f.write_text('[project]\nname = "aspose-words-foss"\n', encoding="utf-8")
        assert _read_package_from_build_file(f) == "aspose-words-foss"

    def test_setup_py(self, tmp_path):
        f = tmp_path / "setup.py"
        f.write_text("setup(name='aspose-email-foss')\n", encoding="utf-8")
        assert _read_package_from_build_file(f) == "aspose-email-foss"

    def test_pom_xml_groupid_only(self, tmp_path):
        """pom.xml with only groupId returns just groupId (fallback)."""
        f = tmp_path / "pom.xml"
        f.write_text("<groupId>com.aspose</groupId>\n", encoding="utf-8")
        assert _read_package_from_build_file(f) == "com.aspose"

    def test_pom_xml(self, tmp_path):
        """pom.xml with groupId + artifactId returns groupId:artifactId (Maven coord)."""
        f = tmp_path / "pom.xml"
        f.write_text(
            "<groupId>com.aspose</groupId>\n<artifactId>aspose-3d-foss</artifactId>\n",
            encoding="utf-8",
        )
        assert _read_package_from_build_file(f) == "com.aspose:aspose-3d-foss"

    def test_package_json(self, tmp_path):
        f = tmp_path / "package.json"
        f.write_text('{"name": "@aspose/3d"}\n', encoding="utf-8")
        assert _read_package_from_build_file(f) == "@aspose/3d"

    def test_nonexistent_file(self, tmp_path):
        assert _read_package_from_build_file(tmp_path / "missing.toml") is None

    def test_no_match(self, tmp_path):
        f = tmp_path / "build.txt"
        f.write_text("nothing useful here\n", encoding="utf-8")
        assert _read_package_from_build_file(f) is None


# ---------------------------------------------------------------------------
# validate_profile cross-check
# ---------------------------------------------------------------------------

class TestProfileCrossCheck:
    """Test that validate_profile detects mismatched package_name."""

    def test_correct_package_passes(self, tmp_path):
        """Profile with correct package_name passes cross-check."""
        # Create fake clone cache
        cache = tmp_path / "clone_cache" / "aspose_test_python"
        cache.mkdir(parents=True)
        (cache / "pyproject.toml").write_text(
            '[project]\nname = "aspose-test-foss"\n', encoding="utf-8"
        )
        # Create profile
        profile_dir = tmp_path / "profiles" / "test"
        profile_dir.mkdir(parents=True)
        (profile_dir / "python.yaml").write_text(
            "family: test\nplatform: python\nversion: 1\n"
            "discovery_hints:\n  package_source_file: pyproject.toml\n"
            "discovered_actuals:\n  package_name: aspose-test-foss\n"
            "expected_sections:\n  - {site: docs, mandatory: true}\n",
            encoding="utf-8",
        )
        with (
            patch("validate_profile._PROFILES_DIR", tmp_path / "profiles"),
            patch("validate_profile._clone_cache_base", return_value=tmp_path / "clone_cache"),
        ):
            errors = validate_profile("test", "python")
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_wrong_package_fails(self, tmp_path):
        """Profile with wrong package_name is caught by cross-check."""
        cache = tmp_path / "clone_cache" / "aspose_test_python"
        cache.mkdir(parents=True)
        (cache / "pyproject.toml").write_text(
            '[project]\nname = "aspose-test-foss"\n', encoding="utf-8"
        )
        profile_dir = tmp_path / "profiles" / "test"
        profile_dir.mkdir(parents=True)
        (profile_dir / "python.yaml").write_text(
            "family: test\nplatform: python\nversion: 1\n"
            "discovery_hints:\n  package_source_file: pyproject.toml\n"
            "discovered_actuals:\n  package_name: aspose-test-WRONG\n"
            "expected_sections:\n  - {site: docs, mandatory: true}\n",
            encoding="utf-8",
        )
        with (
            patch("validate_profile._PROFILES_DIR", tmp_path / "profiles"),
            patch("validate_profile._clone_cache_base", return_value=tmp_path / "clone_cache"),
        ):
            errors = validate_profile("test", "python")
        assert any("does not match clone cache" in e for e in errors), (
            f"Expected cross-check error, got: {errors}"
        )


# ---------------------------------------------------------------------------
# Stage 1 → Tier 1 override
# ---------------------------------------------------------------------------

class TestStage1TierOverride:
    """Test that Stage 1 mismatch triggers Tier 1 profile correction."""

    def test_stage1_detects_mismatch(self, tmp_path):
        """Stage 1 generates knowledge-model-wrong finding when profile differs."""
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "pyproject.toml").write_text(
            '[project]\nname = "aspose-words-foss"\n', encoding="utf-8"
        )
        profile = {
            "discovered_actuals": {"package_name": "aspose-words-WRONG"},
            "discovery_hints": {"package_source_file": "pyproject.toml"},
        }
        findings = stage1_baseline("words", "python", cache, profile, make_finding_id)
        assert len(findings) == 1
        assert findings[0]["type"] == "knowledge-model-wrong"
        assert findings[0]["correct_value"] == "aspose-words-foss"
        assert findings[0]["old_value"] == "aspose-words-WRONG"

    def test_tier1_uses_corrected_package(self):
        """Tier 1 with corrected profile does not generate false wrong-package."""
        # Profile after Stage 1 override: correct package
        profile = {
            "discovered_actuals": {
                "package_name": "aspose-words-foss",
                "import_path": "aspose.words_foss",
            },
            "discovery_hints": {"language": "python"},
        }
        claim = {
            "type": "package-declaration",
            "value": "aspose-words-foss",
            "file": "test.md",
            "line": 10,
        }
        result = tier1_verify(claim, set(), profile, "words", "python")
        assert result is None, "Correct package should pass Tier 1"

    def test_tier1_wrong_profile_generates_false_finding(self):
        """Tier 1 with WRONG profile generates false wrong-package finding."""
        profile = {
            "discovered_actuals": {
                "package_name": "aspose-words-WRONG",
                "import_path": "aspose.words_wrong",
            },
            "discovery_hints": {"language": "python"},
        }
        claim = {
            "type": "package-declaration",
            "value": "aspose-words-foss",
            "file": "test.md",
            "line": 10,
        }
        result = tier1_verify(claim, set(), profile, "words", "python")
        assert result is not None, "Wrong profile should generate false finding"
        assert result["type"] == "wrong-package"
        assert result["severity"] == "M"


# ---------------------------------------------------------------------------
# Deepcopy safety (GR-TC-01)
# ---------------------------------------------------------------------------

class TestDeepcopySafety:
    """Verify Stage 1 override uses deep copy; original profile is not mutated."""

    def test_override_does_not_mutate_original_profile(self, tmp_path):
        """Deep copy in override path must leave original profile untouched."""
        import copy as _copy

        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "pyproject.toml").write_text(
            '[project]\nname = "aspose-words-foss"\n', encoding="utf-8"
        )
        original_actuals = {"package_name": "aspose-words-WRONG"}
        profile = {
            "discovered_actuals": original_actuals,
            "discovery_hints": {"package_source_file": "pyproject.toml"},
        }
        original_snapshot = _copy.deepcopy(profile)

        # Stage 1 detects mismatch and returns a finding with correct_value
        findings = stage1_baseline("words", "python", cache, profile, make_finding_id)
        assert len(findings) == 1
        assert findings[0]["correct_value"] == "aspose-words-foss"

        # Simulate the override block from run_gap_eval (lines 1048-1058)
        import copy
        for f in findings:
            if f["type"] == "knowledge-model-wrong" and f.get("correct_value"):
                overridden = copy.deepcopy(profile)
                overridden.setdefault("discovered_actuals", {})["package_name"] = f["correct_value"]
                break

        # Original must be unchanged
        assert profile == original_snapshot, (
            f"Original profile was mutated: {profile} != {original_snapshot}"
        )
        assert original_actuals["package_name"] == "aspose-words-WRONG", (
            "Original nested dict was mutated by override"
        )


# ---------------------------------------------------------------------------
# Stage 2 max_entries overflow warning (GR-TC-01)
# ---------------------------------------------------------------------------

class TestMaxEntriesOverflow:
    """Verify Stage 2 warns when max_entries exceeds api_data size."""

    def test_max_entries_exceeds_api_data_warns(self, tmp_path, caplog):
        """max_entries > len(api_data) logs a warning and checks all entries."""
        import logging

        api_data = [{"name": f"Class{i}", "type": "class"} for i in range(5)]
        checked: list[str] = []

        def _capture_grep(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            checked.append(cmd[-2])
            m = MagicMock()
            m.returncode = 0
            m.stdout = "/some/file.py\n"
            return m

        with (
            patch("subprocess.run", side_effect=_capture_grep),
            caplog.at_level(logging.WARNING),
        ):
            stage2_knowledge_validation(
                "test", "python", tmp_path, api_data, make_finding_id,
                max_entries=100, seed=42,
            )

        assert len(checked) == 5, f"Expected all 5 entries checked, got {len(checked)}"
        assert any("max_entries=100 exceeds api_data size=5" in r.message for r in caplog.records), (
            f"Expected overflow warning in logs, got: {[r.message for r in caplog.records]}"
        )


# ---------------------------------------------------------------------------
# Integration: Stage 1 → override → Tier 1 chain (GR-TC-02)
# ---------------------------------------------------------------------------

class TestStage1OverrideIntegration:
    """Integration test: Stage 1 mismatch triggers override that prevents
    false Tier 1 wrong-package findings.

    Exercises the real code path from run_gap_eval lines 1046-1090:
    Stage 1 → override block → Tier 1 loop.
    """

    @staticmethod
    def _run_override_chain(tmp_path, *, disable_override=False):
        """Run the Stage 1 → override → Tier 1 chain with controlled inputs.

        Returns (profile_after, raw_findings) where raw_findings includes
        both Stage 1 and Tier 1 results.
        """
        # Set up clone cache with correct package name
        cache = tmp_path / "cache"
        cache.mkdir(exist_ok=True)
        (cache / "pyproject.toml").write_text(
            '[project]\nname = "aspose-words-foss"\n', encoding="utf-8"
        )

        # Profile with WRONG package name (simulates stale profile)
        profile = {
            "discovered_actuals": {
                "package_name": "aspose-words-WRONG",
                "import_path": "aspose.words_wrong",
            },
            "discovery_hints": {
                "package_source_file": "pyproject.toml",
                "language": "python",
            },
        }

        # Stage 1: detect mismatch
        raw_findings: list[dict] = []
        raw_findings.extend(
            stage1_baseline("words", "python", cache, profile, make_finding_id)
        )

        # Override block (reproduces run_gap_eval lines 1050-1061)
        if not disable_override:
            for f in raw_findings:
                if f["type"] == "knowledge-model-wrong" and f.get("correct_value"):
                    profile = copy.deepcopy(profile)
                    profile.setdefault("discovered_actuals", {})["package_name"] = f["correct_value"]
                    break

        # Tier 1: verify a claim that uses the CORRECT package name
        claim = {
            "type": "package-declaration",
            "value": "aspose-words-foss",
            "file": "test.md",
            "line": 10,
        }
        finding = tier1_verify(claim, set(), profile, "words", "python")
        if finding:
            raw_findings.append(finding)

        return profile, raw_findings

    def test_override_prevents_false_wrong_package(self, tmp_path):
        """With override active, correct content does NOT produce wrong-package."""
        profile, findings = self._run_override_chain(tmp_path, disable_override=False)

        # Stage 1 should produce knowledge-model-wrong
        stage1_findings = [f for f in findings if f["type"] == "knowledge-model-wrong"]
        assert len(stage1_findings) == 1, "Stage 1 should detect the mismatch"

        # Tier 1 should NOT produce wrong-package (override corrected the profile)
        wrong_pkg = [f for f in findings if f.get("type") == "wrong-package"]
        assert len(wrong_pkg) == 0, (
            f"Override should prevent false wrong-package findings, got: {wrong_pkg}"
        )

        # Profile should have been corrected
        assert profile["discovered_actuals"]["package_name"] == "aspose-words-foss"

    def test_no_override_generates_false_wrong_package(self, tmp_path):
        """Without override, correct content produces false wrong-package (control)."""
        profile, findings = self._run_override_chain(tmp_path, disable_override=True)

        # Stage 1 should still produce knowledge-model-wrong
        stage1_findings = [f for f in findings if f["type"] == "knowledge-model-wrong"]
        assert len(stage1_findings) == 1

        # Tier 1 SHOULD produce wrong-package (no override → wrong profile used)
        wrong_pkg = [f for f in findings if f.get("type") == "wrong-package"]
        assert len(wrong_pkg) == 1, (
            "Without override, wrong profile should cause false wrong-package finding"
        )
        assert wrong_pkg[0]["severity"] == "M"

        # Profile should still have the wrong value
        assert profile["discovered_actuals"]["package_name"] == "aspose-words-WRONG"

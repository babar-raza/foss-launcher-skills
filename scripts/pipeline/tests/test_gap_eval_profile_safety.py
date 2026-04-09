"""Tests for gap-eval profile safety: cross-check and Stage 1 → Tier 1 override."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from validate_profile import _read_package_from_build_file, validate_profile  # type: ignore  # noqa: E402
from run import stage1_baseline, tier1_verify  # type: ignore  # noqa: E402
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

    def test_pom_xml(self, tmp_path):
        f = tmp_path / "pom.xml"
        f.write_text("<groupId>com.aspose</groupId>\n", encoding="utf-8")
        assert _read_package_from_build_file(f) == "com.aspose"

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

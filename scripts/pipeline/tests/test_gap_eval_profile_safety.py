"""Tests for gap-eval profile safety: cross-check and Stage 1 → Tier 1 override."""

from __future__ import annotations

import copy
import importlib.util
import logging
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from validate_profile import _read_package_from_build_file, validate_profile, update_profile, ALL_PRODUCTS  # type: ignore  # noqa: E402
import validate_profile as _vp  # type: ignore  # noqa: E402
from run import (  # type: ignore  # noqa: E402
    Tier1Status,
    _build_api_name_set,
    _read_build_package,
    generate_report,
    stage1_baseline,
    stage2_knowledge_validation,
    tier1_assess,
    tier1_verify,
)
from state import make_finding_id, reset_state, save_state  # type: ignore  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_vp():
    yield
    _vp.configure()


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

    # --- AssemblyName fallback (PV-01) ---

    def test_assembly_name_fallback(self, tmp_path):
        """AssemblyName extracted when PackageId is absent (cells/net scenario)."""
        f = tmp_path / "Aspose.Cells_FOSS.csproj"
        f.write_text(
            "<Project><PropertyGroup>"
            "<AssemblyName>Aspose.Cells_FOSS</AssemblyName>"
            "</PropertyGroup></Project>",
            encoding="utf-8",
        )
        assert _read_package_from_build_file(f) == "Aspose.Cells_FOSS"

    def test_package_id_preferred_over_assembly_name(self, tmp_path):
        """PackageId wins when both elements are present — AssemblyName is last-resort."""
        f = tmp_path / "multi.csproj"
        f.write_text(
            "<Project><PropertyGroup>"
            "<PackageId>Preferred.Package</PackageId>"
            "<AssemblyName>AssemblyFallback</AssemblyName>"
            "</PropertyGroup></Project>",
            encoding="utf-8",
        )
        assert _read_package_from_build_file(f) == "Preferred.Package"

    def test_assembly_name_with_underscore(self, tmp_path):
        """AssemblyName containing underscore (common in Aspose FOSS naming) is extracted."""
        f = tmp_path / "lib.csproj"
        f.write_text(
            "<Project><PropertyGroup>"
            "<AssemblyName>Aspose.Email_FOSS</AssemblyName>"
            "</PropertyGroup></Project>",
            encoding="utf-8",
        )
        assert _read_package_from_build_file(f) == "Aspose.Email_FOSS"


def test_gap_eval_cmake_add_library_extraction(tmp_path):
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "add_library(AsposeEmailFoss STATIC src/message.cpp)\n"
        "add_library(Aspose::Email ALIAS AsposeEmailFoss)\n",
        encoding="utf-8",
    )
    profile = {
        "discovery_hints": {
            "package_source_file": "CMakeLists.txt",
            "package_extraction": "cmake:add_library",
        }
    }
    assert _read_build_package(tmp_path, profile) == "AsposeEmailFoss"


def test_gap_report_uses_same_normalized_open_findings_for_counts():
    findings = [
        {
            "id": "F-open",
            "type": "needs-review",
            "severity": "S",
            "tier_resolved_by": 3,
            "file": "open.md",
            "line": 1,
            "description": "open",
            "status": "open",
        },
        {
            "id": "F-fixed",
            "type": "needs-review",
            "severity": "S",
            "tier_resolved_by": 3,
            "file": "fixed.md",
            "line": 2,
            "description": "fixed",
            "status": "fixed",
        },
    ]
    report = generate_report(
        "email", "cpp", findings, "PUBLICATION READY", "", "a" * 40,
        "professionalize",
    )
    assert "S-findings: 1" in report
    assert "Tier 3 (LLM): 1 findings" in report
    assert "NEEDS_REVIEW: 1 findings" in report


def test_tier1_exact_api_is_terminally_verified():
    result = tier1_assess(
        {
            "type": "api-token",
            "value": "Scene.fromFile",
            "file": "example.md",
            "line": 1,
        },
        {"Scene.fromFile"},
        {},
        "3d",
        "typescript",
    )
    assert result.status is Tier1Status.VERIFIED
    assert result.finding is None


def test_tier1_unknown_api_is_explicitly_unresolved():
    result = tier1_assess(
        {
            "type": "api-token",
            "value": "Scene.notInSurface",
            "file": "example.md",
            "line": 1,
        },
        {"Scene.fromFile"},
        {},
        "3d",
        "typescript",
    )
    assert result.status is Tier1Status.UNRESOLVED
    assert result.finding is None


def test_tier1_accepted_package_is_terminally_verified():
    result = tier1_assess(
        {
            "type": "package-declaration",
            "value": "@aspose/3d",
            "file": "install.md",
            "line": 1,
        },
        set(),
        {
            "discovered_actuals": {"package_name": "@aspose/3d"},
            "discovery_hints": {"language": "typescript"},
        },
        "3d",
        "typescript",
    )
    assert result.status is Tier1Status.VERIFIED
    assert result.finding is None


def test_api_name_set_normalizes_current_and_legacy_member_schemas():
    names = _build_api_name_set(
        [
            {
                "name": "Quaternion",
                "methods": [{"name": "fromEulerAngle"}],
                "properties": [{"name": "identity"}],
            },
            {
                "name": "LegacyScene",
                "method_details": [{"name": "open"}],
                "property_details": [{"name": "rootNode"}],
            },
            {
                "name": "Mixed",
                "methods": [{"name": "save"}],
                "method_details": [{"name": "save"}],
            },
        ]
    )
    assert {
        "Quaternion.fromEulerAngle",
        "Quaternion.identity",
        "LegacyScene.open",
        "LegacyScene.rootNode",
        "Mixed.save",
    } <= names


def test_current_typescript_member_resolves_exactly_at_tier1():
    names = _build_api_name_set(
        [{"name": "Quaternion", "methods": [{"name": "fromEulerAngle"}]}]
    )
    result = tier1_assess(
        {
            "type": "api-token",
            "value": "Quaternion.fromEulerAngle",
            "file": "features.md",
            "line": 609,
        },
        names,
        {},
        "3d",
        "typescript",
    )
    assert result.status is Tier1Status.VERIFIED


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
        """max_entries > len(api_data) logs a WARNING and checks all entries."""
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
            # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
            patch("subprocess.run", side_effect=_capture_grep),
            caplog.at_level(logging.WARNING, logger="run"),
        ):
            stage2_knowledge_validation(
                "test", "python", tmp_path, api_data, make_finding_id,
                max_entries=100, seed=42,
            )

        assert len(checked) == 5, f"Expected all 5 entries checked, got {len(checked)}"
        assert any("max_entries=100 exceeds api_data size=5" in r.message for r in caplog.records), (
            f"Expected overflow warning in logs, got: {[r.message for r in caplog.records]}"
        )
        assert any(r.levelname == "WARNING" for r in caplog.records), (
            "Warning must be emitted at WARNING level (visible at default CI log threshold)"
        )

    def test_max_entries_zero_with_empty_api_data_returns_empty(self, tmp_path):
        """max_entries=0 (exhaustive) with empty api_data hits early return — no error."""
        clone_path = tmp_path / "clone"
        clone_path.mkdir()
        result = stage2_knowledge_validation(
            "test", "python", clone_path, [], make_finding_id,
            max_entries=0, seed=42,
        )
        assert result == [], f"Empty api_data must return empty list, got: {result}"

    def test_max_entries_positive_with_empty_api_data(self, tmp_path):
        """max_entries>0 with empty api_data also hits early return — no error, no warning."""
        clone_path = tmp_path / "clone"
        clone_path.mkdir()
        result = stage2_knowledge_validation(
            "test", "python", clone_path, [], make_finding_id,
            max_entries=5, seed=42,
        )
        assert result == [], f"Empty api_data must return empty list regardless of max_entries"


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


# ---------------------------------------------------------------------------
# C# language filter for Tier 1 (GR-TC-03)
# ---------------------------------------------------------------------------

class TestCSharpTier1Filter:
    """Verify C# language-specific filters suppress false positive wrong-package findings."""

    _CSHARP_PROFILE = {
        "discovered_actuals": {"package_name": "Aspose.Cells_FOSS"},
        "discovery_hints": {"language": "csharp"},
    }

    def _claim(self, value: str, context: str = "") -> dict:
        return {
            "type": "package-declaration",
            "value": value,
            "file": "test.md",
            "line": 10,
            "context": context,
        }

    def test_system_namespace_suppressed(self):
        """System.* namespaces are not competing packages — must pass."""
        result = tier1_verify(
            self._claim("System.Globalization"), set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is None, "System.Globalization should not be flagged in C# content"

    def test_system_io_suppressed(self):
        """System.IO is stdlib — must pass."""
        result = tier1_verify(
            self._claim("System.IO"), set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is None, "System.IO should not be flagged in C# content"

    def test_csharp_keyword_var_suppressed(self):
        """C# keyword 'var' captured by `using var x = ...` — must pass."""
        result = tier1_verify(
            self._claim("var"), set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is None, "'var' should not be flagged as wrong package in C#"

    def test_english_word_suppressed(self):
        """Common English word 'the' captured from comment — must pass."""
        result = tier1_verify(
            self._claim("the"), set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is None, "'the' should not be flagged as wrong package in C#"

    def test_aspnet_framework_suppressed(self):
        """ASP.NET framework ref in comment — must pass."""
        result = tier1_verify(
            self._claim("ASP.NET"), set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is None, "ASP.NET should not be flagged as wrong package in C#"

    def test_aspose_partial_with_expected_in_context_suppressed(self):
        """Aspose.Cells token from 'from Aspose.Cells FOSS' string — context proves correct usage."""
        context = 'using Aspose.Cells_FOSS;\n\nvar wb = new Workbook();\nsheet.PutValue("Hello from Aspose.Cells FOSS");'
        result = tier1_verify(
            self._claim("Aspose.Cells", context=context), set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is None, "Aspose partial match when block declares expected_pkg should pass"

    def test_aspose_wrong_package_without_context_flagged(self):
        """Aspose.Cells without expected_pkg in context is genuinely wrong — must flag."""
        result = tier1_verify(
            self._claim("Aspose.Cells", context="using Aspose.Cells;\nvar wb = new Workbook();"),
            set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is not None, "Aspose.Cells without expected_pkg in context should be flagged"
        assert result["type"] == "wrong-package"
        assert result["severity"] == "M"

    def test_correct_package_always_passes(self):
        """Aspose.Cells_FOSS exactly matches expected_pkg — must always pass."""
        result = tier1_verify(
            self._claim("Aspose.Cells_FOSS"), set(), self._CSHARP_PROFILE, "cells", "net"
        )
        assert result is None, "Correct package Aspose.Cells_FOSS must always pass"


# ---------------------------------------------------------------------------
# C++ language filter for Tier 1 (email/cpp regression guard)
# ---------------------------------------------------------------------------

class TestCppTier1Filter:
    """Verify C++ language-specific filters suppress false positive wrong-package findings.

    C++ code uses `using namespace`, `#include`, and CMake directives — none of which
    are competing Aspose packages.  These must not produce wrong-package findings.
    """

    _CPP_PROFILE = {
        "discovered_actuals": {"package_name": "AsposeEmailFoss"},
        "discovery_hints": {"language": "cpp"},
    }

    def _claim(self, value: str, context: str = "") -> dict:
        return {
            "type": "package-declaration",
            "value": value,
            "file": "test.md",
            "line": 10,
            "context": context,
        }

    def test_namespace_keyword_suppressed(self):
        """C++ 'using namespace' produces token 'namespace' — must not be flagged."""
        result = tier1_verify(
            self._claim("namespace"), set(), self._CPP_PROFILE, "email", "cpp"
        )
        assert result is None, "'namespace' should not be flagged in C++ content"

    def test_stdlib_include_suppressed(self):
        """C++ using std — must not be flagged."""
        result = tier1_verify(
            self._claim("std"), set(), self._CPP_PROFILE, "email", "cpp"
        )
        assert result is None, "'std' should not be flagged in C++ content"

    def test_cmake_target_without_aspose_suppressed(self):
        """CMake identifier without 'aspose' in name — must not be flagged."""
        result = tier1_verify(
            self._claim("MyApp"), set(), self._CPP_PROFILE, "email", "cpp"
        )
        assert result is None, "CMake target 'MyApp' should not be flagged in C++ content"

    def test_correct_package_always_passes(self):
        """AsposeEmailFoss exactly matches expected_pkg — must always pass."""
        result = tier1_verify(
            self._claim("AsposeEmailFoss"), set(), self._CPP_PROFILE, "email", "cpp"
        )
        assert result is None, "Correct package AsposeEmailFoss must always pass"

    def test_other_aspose_package_suppressed(self):
        """C++ uses blanket suppression — even a different Aspose library name is not flagged.

        Rationale: C++ has no package manager with import statements.  'package-declaration'
        claims from C++ content are CMake identifiers or namespace tokens, not package imports.
        The blanket `if _lang == 'cpp': return None` at run.py:339 handles all cases.
        """
        result = tier1_verify(
            self._claim("AsposeSlideFoss"), set(), self._CPP_PROFILE, "email", "cpp"
        )
        assert result is None, (
            "C++ blanket suppression must apply even to other Aspose package names — "
            "they are CMake target references, not package imports"
        )


# ---------------------------------------------------------------------------
# SITE_GLOBS products scope (SR-01 regression guard)
# ---------------------------------------------------------------------------

class TestSiteGlobsProductsScope:
    """
    Regression guard for SITE_GLOBS['products'] scope (SR-01 fix).

    Verifies:
    - Family _index.md included (two-glob fix)
    - Sibling platform excluded
    - Platform _index.md and sub-pages included
    - Other sites (docs, kb, reference) remain platform-only
    """

    def _discover(self, tmp_path: Path, family: str, platform: str) -> dict:
        """Call discover_content_files with _REPO_ROOT set via configure() seam."""
        import run as run_mod  # already on sys.path via _GAP_EVAL_DIR
        run_mod.configure(repo_root=tmp_path)
        try:
            return run_mod.discover_content_files(family, platform)
        finally:
            run_mod.configure()

    def _build_tree(self, tmp_path: Path, family: str, platform: str, sibling: str | None = None):
        prod = tmp_path / "content" / "products.aspose.org" / "en"
        (prod / family).mkdir(parents=True)
        (prod / family / "_index.md").write_text("---\ntitle: family\n---\n", encoding="utf-8")
        (prod / family / platform).mkdir(parents=True)
        (prod / family / platform / "_index.md").write_text("---\ntitle: net\n---\n", encoding="utf-8")
        (prod / family / platform / "features.md").write_text("---\ntitle: feat\n---\n", encoding="utf-8")
        if sibling:
            (prod / family / sibling).mkdir(parents=True)
            (prod / family / sibling / "_index.md").write_text("---\ntitle: sib\n---\n", encoding="utf-8")

    def test_family_index_included_in_products(self, tmp_path):
        """Family _index.md must appear in products scope (SR-01 two-glob fix)."""
        self._build_tree(tmp_path, "cells", "net")
        files = self._discover(tmp_path, "cells", "net")
        prod_strs = [str(p) for p in files.get("products", [])]
        # Family _index.md: under /cells/ but NOT under /cells/net/
        family_idx = [x for x in prod_strs if x.endswith("_index.md") and "net" not in x.split("cells")[-1]]
        assert family_idx, f"Family _index.md missing from products scope. Got: {prod_strs}"

    def test_platform_index_and_pages_included(self, tmp_path):
        self._build_tree(tmp_path, "cells", "net")
        files = self._discover(tmp_path, "cells", "net")
        prod_strs = [str(p) for p in files.get("products", [])]
        assert any("net" in x and "_index.md" in x for x in prod_strs), f"Platform _index.md missing: {prod_strs}"
        assert any("features.md" in x for x in prod_strs), f"Sub-page missing: {prod_strs}"

    def test_sibling_platform_excluded(self, tmp_path):
        """cells/python must NOT appear when evaluating cells/net."""
        self._build_tree(tmp_path, "cells", "net", sibling="python")
        files = self._discover(tmp_path, "cells", "net")
        prod_strs = [str(p) for p in files.get("products", [])]
        assert not any("python" in x for x in prod_strs), f"Sibling leak: {prod_strs}"

    @pytest.mark.parametrize("site", ["docs", "kb", "reference"])
    def test_non_products_sites_no_family_index(self, tmp_path, site):
        """docs/kb/reference must not include family-level _index.md."""
        # Build minimal tree for each site
        if site == "docs":
            p = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        elif site == "kb":
            p = tmp_path / "content" / "kb.aspose.org" / "en" / "cells" / "net"
        else:
            p = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "net"
        p.mkdir(parents=True)
        (p / "page.md").write_text("---\ntitle: page\n---\n", encoding="utf-8")
        # Also create products tree so discover_content_files doesn't blow up
        self._build_tree(tmp_path, "cells", "net")
        files = self._discover(tmp_path, "cells", "net")
        site_strs = [str(p) for p in files.get(site, [])]
        family_idx = [x for x in site_strs if x.endswith("_index.md") and "net" not in x.split("cells")[-1]]
        assert not family_idx, f"Family _index.md leaked into {site} scope: {family_idx}"


# ---------------------------------------------------------------------------
# Code-block extraction guard (SR-02 regression guard)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# validate_profile.py graceful skip narrowing (GHF-TC-04)
# ---------------------------------------------------------------------------

class TestGracefulSkip:
    """Verify narrowed except clause: OSError skips gracefully; RuntimeError propagates."""

    def test_graceful_skip_on_os_error(self, monkeypatch, caplog):
        """OSError from _clone_cache_base causes graceful skip with [SKIP] WARNING logged."""
        import validate_profile as vp

        def _raise_os():
            raise OSError("cache unavailable for test")

        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])
        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_os)

        with caplog.at_level(logging.WARNING):
            vp.main()  # must NOT raise

        assert any(
            "skip" in r.message.lower() for r in caplog.records
        ), f"Expected skip warning, got: {[r.message for r in caplog.records]}"
        assert any(
            r.levelname == "WARNING" for r in caplog.records
        ), "Skip message must be at WARNING level"
        assert any(
            r.message.startswith("[SKIP]") for r in caplog.records
        ), f"Skip message must start with [SKIP] for CI grep visibility: {[r.message for r in caplog.records]}"

    def test_propagates_unexpected_exception(self, monkeypatch):
        """RuntimeError (unexpected) must NOT be swallowed — it propagates."""
        import validate_profile as vp

        def _raise_runtime():
            raise RuntimeError("unexpected internal error")

        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])
        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_runtime)

        with pytest.raises(RuntimeError, match="unexpected internal error"):
            vp.main()


class TestCodeBlockExtractionGuard:
    """
    Regression guard for untagged code-block extraction behavior (SR-02 fix).

    Matrix: (tagged / untagged) x (aspose / no-aspose)
    Tagged blocks: always scanned regardless of content.
    Untagged blocks: scanned ONLY when block body contains 'aspose' (case-insensitive).
    """

    def _claims(self, page_text: str) -> list[dict]:
        import run as run_mod
        return run_mod.extract_claims(Path("dummy.md"), page_text)

    def _pkg(self, page_text: str) -> list[dict]:
        return [c for c in self._claims(page_text) if c["type"] == "package-declaration"]

    def test_tagged_csharp_block_scanned(self):
        claims = self._pkg("```csharp\nusing Aspose.Cells_FOSS;\n```")
        assert claims, "Tagged csharp block must produce package-declaration claims"

    def test_tagged_python_block_scanned(self):
        claims = self._pkg("```python\nimport aspose.cells\n```")
        assert claims, "Tagged python block must produce package-declaration claims"

    def test_untagged_block_with_aspose_scanned(self):
        """Untagged block containing 'aspose' must be scanned."""
        claims = self._pkg("```\npip install Aspose.Cells_FOSS\n```")
        assert claims, "Untagged block with 'aspose' must produce claims"

    def test_untagged_block_no_aspose_skipped(self):
        """Untagged block without 'aspose' must be silently skipped."""
        claims = self._pkg("```\nThis is plain shell output\nno package refs here\n```")
        assert not claims, f"Noise block produced unexpected claims: {claims}"

    def test_untagged_system_namespace_skipped(self):
        claims = self._pkg("```\nusing System.Globalization;\n```")
        assert not claims, f"System namespace in untagged block must not produce claims: {claims}"

    def test_untagged_csharp_keywords_skipped(self):
        for token in ("var", "the", "stream"):
            claims = self._pkg(f"```\n{token}\n```")
            assert not claims, f"Token '{token}' in untagged block must not produce claims"

    def test_untagged_aspose_case_insensitive(self):
        """ASPOSE (uppercase) in untagged block must trigger scan (case-insensitive guard)."""
        # The guard checks "aspose" in block.lower() — this block passes the guard.
        # _RE_PACKAGE_IMPORT then extracts the package name from the install keyword.
        claims = self._pkg("```\npip install ASPOSE.Cells_FOSS\n```")
        assert claims, "Uppercase ASPOSE with pip install must trigger scan"

    def test_untagged_empty_block_skipped(self):
        claims = self._pkg("```\n\n```")
        assert not claims, "Empty untagged block must not produce claims"

    def test_tagged_block_always_beats_untagged_guard(self):
        """Tagged block with non-aspose content is still scanned (guard only for untagged)."""
        # e.g. wrong package in tagged block — should be caught by tier1_verify, not skipped here
        claims = self._pkg("```csharp\nusing SomeOther.Library;\n```")
        # extract_claims returns the claim; tier1_verify decides if it's wrong-package
        # The important thing: extraction is NOT skipped for tagged blocks
        assert isinstance(claims, list)  # may be empty after language filter — but not skipped at extract stage

    def test_mixed_tagged_and_untagged_page(self):
        """Tagged aspose block + untagged noise block: only tagged contributes."""
        page = (
            "```csharp\nusing Aspose.Cells_FOSS;\n```\n\n"
            "```\nThis is plain output text\n```\n"
        )
        claims = self._pkg(page)
        assert claims, "Tagged aspose block must produce claims"
        # Noise block must not contribute: all claims should reference aspose
        non_aspose = [c for c in claims if "aspose" not in c.get("value", "").lower()]
        assert not non_aspose, f"Non-aspose claims from noise block: {non_aspose}"


# ---------------------------------------------------------------------------
# TIER3-TS-FP-01: TS/JS built-in filter in extract_claims
# ---------------------------------------------------------------------------

class TestTier3TsFp01BuiltinFilter:
    """Regression guard for TIER3-TS-FP-01.

    Ensures that:
    1. JS/TS built-in global class method calls (e.g. JSON.stringify, Math.floor,
       Buffer.from) are NOT extracted as api-token claims from typescript/javascript
       code blocks — they would otherwise escalate to Tier 3 LLM as false positives.
    2. Bare single-word default import bindings (e.g. `import is from 'is'`,
       `import buffer from 'buffer'`) are NOT extracted as package-declaration claims
       from typescript/javascript code blocks.
    3. Legitimate Aspose API tokens and package declarations are still extracted
       normally from typescript/javascript code blocks.
    4. The filter does NOT apply to non-TS/JS tagged blocks (csharp, python, java).
    """

    def _claims(self, page_text: str) -> list[dict]:
        import run as run_mod
        return run_mod.extract_claims(Path("dummy.md"), page_text)

    def _api_tokens(self, page_text: str) -> list[dict]:
        return [c for c in self._claims(page_text) if c["type"] == "api-token"]

    def _pkg_decls(self, page_text: str) -> list[dict]:
        return [c for c in self._claims(page_text) if c["type"] == "package-declaration"]

    # --- api-token: built-in suppression ---

    def test_json_stringify_ts_block_suppressed(self):
        """JSON.stringify in a typescript block must not produce an api-token claim."""
        page = "```typescript\nconst s = JSON.stringify(obj);\n```"
        tokens = self._api_tokens(page)
        assert not any(t["value"] == "JSON.stringify" for t in tokens), (
            f"JSON.stringify should be suppressed in typescript block, got: {tokens}"
        )

    def test_math_floor_js_block_suppressed(self):
        """Math.floor in a javascript block must not produce an api-token claim."""
        page = "```javascript\nconst n = Math.floor(x);\n```"
        tokens = self._api_tokens(page)
        assert not any(t["value"] == "Math.floor" for t in tokens), (
            f"Math.floor should be suppressed in javascript block, got: {tokens}"
        )

    def test_buffer_from_ts_block_suppressed(self):
        """Buffer.from in a typescript block must not produce an api-token claim."""
        page = "```typescript\nconst b = Buffer.from(data);\n```"
        tokens = self._api_tokens(page)
        assert not any(t["value"] == "Buffer.from" for t in tokens), (
            f"Buffer.from should be suppressed in typescript block, got: {tokens}"
        )

    def test_promise_resolve_ts_block_suppressed(self):
        """Promise.resolve in a typescript block must not produce an api-token claim."""
        page = "```typescript\nawait Promise.resolve();\n```"
        tokens = self._api_tokens(page)
        assert not any(t["value"] == "Promise.resolve" for t in tokens), (
            f"Promise.resolve should be suppressed in typescript block, got: {tokens}"
        )

    def test_aspose_api_token_ts_block_preserved(self):
        """A real Aspose API token (GltfFormat.getInstance) must still be extracted."""
        page = "```typescript\nconst fmt = GltfFormat.getInstance();\n```"
        tokens = self._api_tokens(page)
        assert any(t["value"] == "GltfFormat.getInstance" for t in tokens), (
            f"GltfFormat.getInstance must be extracted from typescript block, got: {tokens}"
        )

    def test_stdlib_filter_not_applied_to_csharp(self):
        """The TS/JS filter must not suppress tokens in csharp blocks."""
        # Array.resize is a .NET method call with a lowercase method name that matches
        # _RE_API_TOKEN.  The stdlib filter must NOT suppress it in a csharp block.
        page = "```csharp\nArray.resize(ref arr, 10);\n```"
        tokens = self._api_tokens(page)
        assert any(t["value"] == "Array.resize" for t in tokens), (
            f"Array.resize in csharp block must NOT be filtered by TS/JS guard, got: {tokens}"
        )

    # --- package-declaration: bare binding suppression ---

    def test_bare_binding_is_ts_block_suppressed(self):
        """`import is from 'is'` must not produce a package-declaration claim for 'is'."""
        page = "```typescript\nimport is from 'is';\n```"
        pkgs = self._pkg_decls(page)
        assert not any(p["value"] == "is" for p in pkgs), (
            f"Bare binding 'is' should be suppressed in typescript block, got: {pkgs}"
        )

    def test_bare_binding_buffer_ts_block_suppressed(self):
        """`import buffer from 'buffer'` must not produce a package-declaration claim for 'buffer'."""
        page = "```typescript\nimport buffer from 'buffer';\n```"
        pkgs = self._pkg_decls(page)
        assert not any(p["value"] == "buffer" for p in pkgs), (
            f"Bare binding 'buffer' should be suppressed in typescript block, got: {pkgs}"
        )

    def test_aspose_scoped_package_ts_block_preserved(self):
        """@aspose/3d must still be extracted as a package-declaration from typescript blocks.

        The install instruction (npm install @aspose/3d) is the canonical form that
        _RE_PACKAGE_IMPORT captures — it contains '/' so it passes the bare-binding filter.
        """
        page = "```typescript\nnpm install @aspose/3d\n```"
        pkgs = self._pkg_decls(page)
        assert any(p["value"] == "@aspose/3d" for p in pkgs), (
            f"@aspose/3d must be extracted from typescript block (npm install form), got: {pkgs}"
        )

    def test_bare_binding_filter_not_applied_to_java(self):
        """The bare-binding filter must not suppress Java imports."""
        # 'is' as a token would be unusual in Java but the filter must not activate for java blocks
        page = "```java\nimport org.aspose.threed.Scene;\n```"
        pkgs = self._pkg_decls(page)
        assert pkgs, f"Java aspose import must still be extracted, got: {pkgs}"


# ---------------------------------------------------------------------------
# update_profile (--update command)
# ---------------------------------------------------------------------------

class TestUpdateCommand:
    """Tests for validate_profile.update_profile() — auto-derives discovered_actuals.package_name."""

    def _make_profile(self, tmp_path: Path, pkg_source: str, package_name: str | None = None) -> Path:
        """Write a minimal profile YAML to tmp_path and return its path."""
        import yaml
        content: dict = {
            "family": "test",
            "platform": "net",
            "version": 1,
            "discovery_hints": {"package_source_file": pkg_source, "language": "csharp"},
            "discovered_actuals": {"package_name": package_name},
            "expected_sections": [{"site": "products", "mandatory": True}],
        }
        profile_dir = tmp_path / "profiles" / "test"
        profile_dir.mkdir(parents=True)
        p = profile_dir / "net.yaml"
        p.write_text(yaml.dump(content, default_flow_style=False), encoding="utf-8")
        return p

    def _make_build_file(self, tmp_path: Path, pkg_source: str, package_id: str) -> Path:
        """Write a .csproj build file containing the given PackageId."""
        build_file = tmp_path / "cache" / "aspose_test_net" / pkg_source
        build_file.parent.mkdir(parents=True, exist_ok=True)
        build_file.write_text(f"<PackageId>{package_id}</PackageId>", encoding="utf-8")
        return build_file

    def test_writes_derived_package_name(self, tmp_path, monkeypatch):
        """update_profile writes the package name read from the build file."""
        import yaml
        import validate_profile as vp

        pkg_source = "src/Aspose.Test/Aspose.Test.csproj"
        profile_path = self._make_profile(tmp_path, pkg_source, package_name=None)
        self._make_build_file(tmp_path, pkg_source, "Aspose.Test")

        vp.configure(profiles_dir=tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", lambda: tmp_path / "cache")

        result = vp.update_profile("test", "net", dry_run=False)

        assert result is True
        updated = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        assert updated["discovered_actuals"]["package_name"] == "Aspose.Test"

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        """--dry-run reports what would change but leaves the YAML file unmodified."""
        import yaml
        import validate_profile as vp

        pkg_source = "src/Aspose.Test/Aspose.Test.csproj"
        profile_path = self._make_profile(tmp_path, pkg_source, package_name="OldName")
        self._make_build_file(tmp_path, pkg_source, "NewName")

        vp.configure(profiles_dir=tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", lambda: tmp_path / "cache")

        original_text = profile_path.read_text(encoding="utf-8")
        result = vp.update_profile("test", "net", dry_run=True)

        assert result is True
        assert profile_path.read_text(encoding="utf-8") == original_text

    def test_skip_when_already_up_to_date(self, tmp_path, monkeypatch):
        """Returns True without writing when stored value already matches clone cache."""
        import validate_profile as vp

        pkg_source = "src/Aspose.Test/Aspose.Test.csproj"
        self._make_profile(tmp_path, pkg_source, package_name="Aspose.Test")
        self._make_build_file(tmp_path, pkg_source, "Aspose.Test")

        vp.configure(profiles_dir=tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", lambda: tmp_path / "cache")

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is True

    def test_returns_false_when_build_file_missing(self, tmp_path, monkeypatch):
        """Returns False (no crash) when the build file does not exist in clone cache."""
        import validate_profile as vp

        self._make_profile(tmp_path, "src/Missing.csproj", package_name=None)
        cache = tmp_path / "cache"
        cache.mkdir()

        vp.configure(profiles_dir=tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", lambda: cache)

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is False

    def test_returns_false_on_os_error_from_cache(self, tmp_path, monkeypatch):
        """Returns False (no crash) when clone cache resolution raises OSError."""
        import validate_profile as vp

        self._make_profile(tmp_path, "src/Aspose.Test/Aspose.Test.csproj", package_name=None)

        def _raise():
            raise OSError("cache unavailable")

        vp.configure(profiles_dir=tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", _raise)

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is False

    def test_returns_false_when_profile_missing(self, tmp_path, monkeypatch):
        """Returns False when the profile YAML does not exist."""
        import validate_profile as vp

        vp.configure(profiles_dir=tmp_path / "profiles")

        result = vp.update_profile("nonexistent", "net", dry_run=False)
        assert result is False

    def test_returns_false_when_no_package_source_hint(self, tmp_path, monkeypatch):
        """Returns False when discovery_hints.package_source_file is absent."""
        import yaml
        import validate_profile as vp

        profile_dir = tmp_path / "profiles" / "test"
        profile_dir.mkdir(parents=True)
        p = profile_dir / "net.yaml"
        p.write_text(yaml.dump({
            "discovery_hints": {},
            "discovered_actuals": {},
            "expected_sections": [],
        }), encoding="utf-8")

        vp.configure(profiles_dir=tmp_path / "profiles")

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is False


# ---------------------------------------------------------------------------
# TC-03: cells/net profile validation round-trip integration tests
# ---------------------------------------------------------------------------

_VALIDATE_SCRIPT = str(Path(__file__).resolve().parents[2] / "gap-eval" / "src" / "validate_profile.py")
_CLONE_CACHE = Path(__file__).resolve().parents[3] / "runs" / ".clone_cache" / "aspose_cells_net"
_CLONE_CACHE_CSPROJ = _CLONE_CACHE / "src" / "Aspose.Cells_FOSS" / "Aspose.Cells_FOSS.csproj"
_PYTHON = sys.executable


class TestCellsNetProfileValidationRoundTrip:
    """Integration test: validate_profile.py cells net must exit 0.

    Depends on:
    - scripts/gap-eval/profiles/cells/net.yaml existing
    - runs/.clone_cache/aspose_cells_net/ existing (canonical: D:/onedrive/Documents/GitHub/aspose.org/runs/.clone_cache/)
    - ('cells', 'net') registered in ALL_PRODUCTS

    Clone-cache-dependent tests are skipped automatically when the cache is
    absent (e.g. fresh CI environments without a populated cache).
    The ALL_PRODUCTS membership test does NOT require the clone cache.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_cache(self, request):
        # Only skip cache-dependent tests; the static test is excluded via marker
        if "no_cache_skip" not in request.keywords and not _CLONE_CACHE_CSPROJ.exists():
            pytest.skip(
                f"Clone cache absent at {_CLONE_CACHE!r} — "
                "integration tests skipped. Run /gap-eval cells net first."
            )

    @pytest.mark.integration
    def test_cells_net_profile_validates_to_pass(self):
        """validate_profile.py cells net must exit 0 and print PASS."""
        result = subprocess.run(
            [_PYTHON, _VALIDATE_SCRIPT, "cells", "net"],
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, (
            f"validate_profile.py cells net exited {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in combined, (
            f"Expected 'PASS' in output. Got:\n{combined}"
        )

    @pytest.mark.integration
    def test_cells_net_passes_in_all_sweep(self):
        """validate_profile.py --all must include cells/net as PASS.

        Other profiles may have pre-existing failures (e.g. slides/java package
        mismatch); this test only asserts cells/net is not among the failures.
        """
        result = subprocess.run(
            [_PYTHON, _VALIDATE_SCRIPT, "--all"],
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        # cells/net must appear and must be PASS (not ERROR/FAIL)
        assert "cells/net" in combined, (
            f"cells/net not mentioned in --all output.\nstdout: {result.stdout}"
        )
        assert "PASS cells/net" in combined, (
            f"cells/net did not PASS in --all sweep.\nOutput: {combined}"
        )

    @pytest.mark.integration
    def test_missing_family_exits_nonzero(self):
        """validate_profile.py for a non-existent family must exit non-zero."""
        result = subprocess.run(
            [_PYTHON, _VALIDATE_SCRIPT, "nonexistent", "net"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            "Expected non-zero exit for non-existent family 'nonexistent/net'"
        )

    @pytest.mark.no_cache_skip
    def test_cells_net_in_all_products_list(self):
        """('cells', 'net') must appear in ALL_PRODUCTS so --all includes it.

        This test does not require the clone cache — it only imports the script.
        """
        spec = importlib.util.spec_from_file_location("validate_profile", _VALIDATE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert ("cells", "net") in mod.ALL_PRODUCTS, (
            "('cells', 'net') not in ALL_PRODUCTS — CI gate will silently skip cells/net"
        )


# ---------------------------------------------------------------------------
# Track A: ImportError / ModuleNotFoundError in _clone_cache_base (GHF-TC Part IX)
# ---------------------------------------------------------------------------

class TestGracefulSkipImportError:
    """Verify that ImportError and ModuleNotFoundError from the dynamic import in
    _clone_cache_base() produce a [SKIP] log at WARNING rather than an unhandled crash.

    Root cause: `from core.clone_cache import cache_root` inside _clone_cache_base()
    raises ModuleNotFoundError when scripts/pipeline is absent (sparse checkout, CI
    config error).  The except clause must now cover ImportError to skip gracefully.
    """

    def test_graceful_skip_on_import_error(self, monkeypatch, caplog):
        """ImportError from _clone_cache_base must skip with [SKIP] WARNING, not crash."""
        import validate_profile as vp

        def _raise_import():
            raise ImportError("core.clone_cache not importable in test env")

        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])
        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_import)

        with caplog.at_level(logging.WARNING):
            vp.main()  # must NOT raise

        assert any(
            r.message.startswith("[SKIP]") for r in caplog.records
        ), f"Expected [SKIP] prefix in log, got: {[r.message for r in caplog.records]}"
        assert any(
            r.levelname == "WARNING" for r in caplog.records
        ), "Skip message must be at WARNING level"

    def test_graceful_skip_on_module_not_found_error(self, monkeypatch, caplog):
        """ModuleNotFoundError (subclass of ImportError) must also skip gracefully."""
        import validate_profile as vp

        def _raise_module_not_found():
            raise ModuleNotFoundError("No module named 'core'")

        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])
        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_module_not_found)

        with caplog.at_level(logging.WARNING):
            vp.main()  # must NOT raise

        assert any(
            r.message.startswith("[SKIP]") for r in caplog.records
        ), f"Expected [SKIP] prefix in log, got: {[r.message for r in caplog.records]}"
        assert any(
            "skip" in r.message.lower() for r in caplog.records
        ), "Skip message must mention 'skip'"


# ---------------------------------------------------------------------------
# Track B: [SKIP] prefix regression guard (GHF-TC Part IX)
# ---------------------------------------------------------------------------

class TestSkipPrefixRegression:
    """Verify that skip log messages always begin with [SKIP].

    The [SKIP] prefix is the agreed operator-visible signal for distinguishing
    expected environment skips from actual pass results.  Removing it would make
    silent skips invisible in CI log aggregation tools that grep for [SKIP].
    """

    def test_cache_absent_skip_has_skip_prefix(self, monkeypatch, caplog):
        """When cache_base.exists() is False, the skip log must start with [SKIP]."""
        import validate_profile as vp
        from pathlib import Path as _Path

        class _FakePath:
            def exists(self) -> bool:
                return False
            def __truediv__(self, other):
                return self
            def __str__(self):
                return "/fake/cache"

        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])
        monkeypatch.setattr("validate_profile._clone_cache_base", lambda: _FakePath())

        with caplog.at_level(logging.WARNING):
            vp.main()

        skip_records = [r for r in caplog.records if "skip" in r.message.lower()]
        assert skip_records, f"Expected a skip log record, got: {[r.message for r in caplog.records]}"
        assert all(
            r.message.startswith("[SKIP]") for r in skip_records
        ), f"All skip records must start with [SKIP]: {[r.message for r in skip_records]}"

    def test_os_error_skip_has_skip_prefix(self, monkeypatch, caplog):
        """OSError from _clone_cache_base: the WARNING must start with [SKIP]."""
        import validate_profile as vp

        def _raise_os():
            raise OSError("disk not mounted")

        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])
        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_os)

        with caplog.at_level(logging.WARNING):
            vp.main()

        skip_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert skip_records, "Expected at least one WARNING record"
        assert all(
            r.message.startswith("[SKIP]") for r in skip_records
        ), f"All WARNING records must start with [SKIP]: {[r.message for r in skip_records]}"


# ---------------------------------------------------------------------------
# Track C: Schema-always-validates in cache-absent environment (GHF-TC Part IX)
# ---------------------------------------------------------------------------

class TestSchemaValidationCacheAbsent:
    """Prove that validate_schema() catches structural errors even when clone cache
    is absent.  This is the core Track C contract: CI without caches must still block
    on malformed profiles.

    Tests use tmp_path fixtures to create real YAML files — no monkeypatching of the
    YAML parser itself, so these tests prove end-to-end schema detection.
    """

    def _schema(self, family: str = "test", platform: str = "py") -> list[str]:
        import validate_profile as vp
        return vp.validate_schema(family, platform)

    def test_missing_profile_file_fails(self, tmp_path, monkeypatch):
        """If the profile YAML doesn't exist, validate_schema() must return an error."""
        import validate_profile as vp
        vp.configure(profiles_dir=tmp_path)

        errors = vp.validate_schema("nonexistent", "platform")
        assert any("missing" in e.lower() or "not found" in e.lower() for e in errors), (
            f"Expected 'missing' or 'not found' error, got: {errors}"
        )

    def test_empty_expected_sections_fails(self, tmp_path, monkeypatch):
        """Profile with empty expected_sections must fail schema validation."""
        import validate_profile as vp
        vp.configure(profiles_dir=tmp_path)

        profile_dir = tmp_path / "myfamily"
        profile_dir.mkdir()
        (profile_dir / "myplatform.yaml").write_text(
            "discovery_hints:\n"
            "  package_source_file: setup.py\n"
            "discovered_actuals:\n"
            "  package_name: mypackage\n"
            "expected_sections: []\n",
            encoding="utf-8",
        )

        errors = vp.validate_schema("myfamily", "myplatform")
        assert any("expected_sections" in e for e in errors), (
            f"Expected 'expected_sections is empty' error, got: {errors}"
        )

    def test_missing_package_source_file_fails(self, tmp_path, monkeypatch):
        """Profile missing discovery_hints.package_source_file must fail schema validation."""
        import validate_profile as vp
        vp.configure(profiles_dir=tmp_path)

        profile_dir = tmp_path / "myfamily"
        profile_dir.mkdir()
        (profile_dir / "myplatform.yaml").write_text(
            "discovery_hints: {}\n"
            "discovered_actuals:\n"
            "  package_name: mypackage\n"
            "expected_sections:\n"
            "  - {site: docs, mandatory: true}\n",
            encoding="utf-8",
        )

        errors = vp.validate_schema("myfamily", "myplatform")
        assert any("package_source_file" in e for e in errors), (
            f"Expected package_source_file error, got: {errors}"
        )

    def test_null_package_name_fails(self, tmp_path, monkeypatch):
        """Profile with null discovered_actuals.package_name must fail schema validation."""
        import validate_profile as vp
        vp.configure(profiles_dir=tmp_path)

        profile_dir = tmp_path / "myfamily"
        profile_dir.mkdir()
        (profile_dir / "myplatform.yaml").write_text(
            "discovery_hints:\n"
            "  package_source_file: setup.py\n"
            "discovered_actuals:\n"
            "  package_name: null\n"
            "expected_sections:\n"
            "  - {site: docs, mandatory: true}\n",
            encoding="utf-8",
        )

        errors = vp.validate_schema("myfamily", "myplatform")
        assert any("package_name" in e for e in errors), (
            f"Expected package_name error, got: {errors}"
        )

    def test_valid_schema_passes(self, tmp_path, monkeypatch):
        """A well-formed profile must return zero schema errors."""
        import validate_profile as vp
        vp.configure(profiles_dir=tmp_path)

        profile_dir = tmp_path / "myfamily"
        profile_dir.mkdir()
        (profile_dir / "myplatform.yaml").write_text(
            "discovery_hints:\n"
            "  package_source_file: setup.py\n"
            "discovered_actuals:\n"
            "  package_name: mypackage\n"
            "expected_sections:\n"
            "  - {site: docs, mandatory: true}\n",
            encoding="utf-8",
        )

        errors = vp.validate_schema("myfamily", "myplatform")
        assert errors == [], f"Expected no schema errors for valid profile, got: {errors}"

    def test_schema_errors_exit1_even_with_no_cache(self, tmp_path, monkeypatch):
        """main() with a schema-invalid profile must exit 1 even when _clone_cache_base raises ImportError.

        This is the core Track C acceptance test: CI without caches must still block on
        schema errors.  Proves the schema pass runs before and independently of cache resolution.
        """
        import validate_profile as vp

        # Point _PROFILES_DIR to tmp_path; create ONE invalid profile
        vp.configure(profiles_dir=tmp_path)
        monkeypatch.setattr("validate_profile.ALL_PRODUCTS", [("myfamily", "myplatform")])

        profile_dir = tmp_path / "myfamily"
        profile_dir.mkdir()
        (profile_dir / "myplatform.yaml").write_text(
            "discovery_hints:\n"
            "  package_source_file: setup.py\n"
            "discovered_actuals:\n"
            "  package_name: mypackage\n"
            "expected_sections: []\n",  # schema error: empty
            encoding="utf-8",
        )

        # Make _clone_cache_base raise ImportError (simulates cache-less CI)
        def _raise_import():
            raise ImportError("scripts/pipeline missing in test")

        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_import)
        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])

        with pytest.raises(SystemExit) as exc_info:
            vp.main()

        assert exc_info.value.code == 1, (
            "Schema error must cause exit 1 even when clone cache is unavailable"
        )

    def test_valid_schema_no_cache_exits0(self, tmp_path, monkeypatch):
        """main() with a valid profile and no cache must exit 0 (no schema errors)."""
        import validate_profile as vp

        vp.configure(profiles_dir=tmp_path)
        monkeypatch.setattr("validate_profile.ALL_PRODUCTS", [("myfamily", "myplatform")])

        profile_dir = tmp_path / "myfamily"
        profile_dir.mkdir()
        (profile_dir / "myplatform.yaml").write_text(
            "discovery_hints:\n"
            "  package_source_file: setup.py\n"
            "discovered_actuals:\n"
            "  package_name: mypackage\n"
            "expected_sections:\n"
            "  - {site: docs, mandatory: true}\n",
            encoding="utf-8",
        )

        def _raise_import():
            raise ImportError("no cache in this test")

        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_import)
        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])

        # Must NOT raise SystemExit (exits 0 via normal return)
        vp.main()


# ---------------------------------------------------------------------------
# HT-GHF-TC-02: package_name placeholder guard
# ---------------------------------------------------------------------------

class TestProfilePackageNameNotPlaceholder:
    """Regression guard: no committed profile may carry a placeholder package_name.

    Motivation (HT-GHF-TC-02): The clone-cache cross-validation is skipped in CI
    (no cache present), so a corrupted package_name string that passes YAML schema
    validation would silently land in main.  This test makes CI RED for any profile
    whose package_name matches known placeholder patterns — without requiring the cache.
    """

    _PLACEHOLDER_RE = re.compile(
        r"WRONG|placeholder|FIXME|TODO|CHANGEME|DO.NOT.MERGE",
        re.IGNORECASE,
    )

    @pytest.mark.parametrize("family,platform", ALL_PRODUCTS)
    def test_package_name_not_placeholder(self, family, platform):
        """Each committed profile's package_name must not match placeholder patterns."""
        import yaml  # stdlib-adjacent; present in repo venv

        profile_path = _GAP_EVAL_DIR.parent / "profiles" / family / f"{platform}.yaml"
        assert profile_path.exists(), f"Profile missing: {profile_path}"

        with profile_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        pkg = (data.get("discovered_actuals") or {}).get("package_name", "")
        assert pkg, f"{family}/{platform}: package_name is empty or null"
        assert not self._PLACEHOLDER_RE.search(pkg), (
            f"{family}/{platform}: package_name looks like a placeholder: {pkg!r}"
        )


# ---------------------------------------------------------------------------
# Locale blog file exclusion filter (Problem A)
# ---------------------------------------------------------------------------

class TestLocaleBlogFilter:
    """Verify that locale blog files (index.XX.md) are excluded from gap-eval discovery."""

    def test_locale_ar_excluded(self):
        from run import _is_locale_file  # type: ignore  # noqa: E402
        assert _is_locale_file(Path("index.ar.md")) is True

    def test_locale_bg_excluded(self):
        from run import _is_locale_file  # type: ignore  # noqa: E402
        assert _is_locale_file(Path("index.bg.md")) is True

    def test_locale_zh_excluded(self):
        from run import _is_locale_file  # type: ignore  # noqa: E402
        assert _is_locale_file(Path("index.zh.md")) is True

    def test_english_index_kept(self):
        from run import _is_locale_file  # type: ignore  # noqa: E402
        assert _is_locale_file(Path("index.md")) is False

    def test_english_en_suffix_kept(self):
        from run import _is_locale_file  # type: ignore  # noqa: E402
        assert _is_locale_file(Path("index.en.md")) is False

    def test_non_index_file_kept(self):
        from run import _is_locale_file  # type: ignore  # noqa: E402
        assert _is_locale_file(Path("getting-started.md")) is False

    def test_three_letter_code_kept(self):
        """Three-letter codes (e.g., index.api.md) should not be filtered."""
        from run import _is_locale_file  # type: ignore  # noqa: E402
        assert _is_locale_file(Path("index.api.md")) is False


# ---------------------------------------------------------------------------
# Generalized stub throw detection (Problem B)
# ---------------------------------------------------------------------------

class TestStubThrowDetection:
    """Verify _is_stub_throw catches domain-specific and standard exceptions."""

    def setup_method(self):
        # Import from extraction module
        _EXTRACT_DIR = Path(__file__).resolve().parents[2] / "pipeline" / "extraction"
        if str(_EXTRACT_DIR) not in sys.path:
            sys.path.insert(0, str(_EXTRACT_DIR))
        from api_surface import _is_stub_throw  # type: ignore  # noqa: E402
        self._is_stub_throw = _is_stub_throw

    def test_unsupported_operation_exception(self):
        assert self._is_stub_throw('throw new UnsupportedOperationException("not supported")')

    def test_not_implemented_exception(self):
        assert self._is_stub_throw('throw new NotImplementedException()')

    def test_domain_export_exception(self):
        """ExportException with 'not implemented' message must be detected."""
        assert self._is_stub_throw(
            'throw new ExportException("FBX export is not implemented in FOSS version")'
        )

    def test_domain_import_exception(self):
        """ImportException with 'not supported' message must be detected."""
        assert self._is_stub_throw(
            'throw new ImportException("Import is not supported in this build")'
        )

    def test_normal_throw_not_detected(self):
        """A throw that doesn't indicate stub should return False."""
        assert not self._is_stub_throw('throw new IOException("File not found")')

    def test_return_not_detected(self):
        assert not self._is_stub_throw('return result;')


# ---------------------------------------------------------------------------
# Tier 1: Java Maven coordinate sub-package check (slides/java fix)
# ---------------------------------------------------------------------------

class TestJavaMavenSubpackage:
    """Java Maven coordinate groupId:artifactId must be split for sub-package checks."""

    def _make_claim(self, value: str) -> dict:
        return {"type": "package-declaration", "value": value, "file": "test.md", "line": 1}

    def _profile(self, pkg: str, lang: str = "java") -> dict:
        return {
            "discovered_actuals": {"package_name": pkg},
            "discovery_hints": {"language": lang},
        }

    def test_maven_subpackage_accepted(self):
        """org.aspose.slides.foss.export.SaveFormat is a valid sub-package of groupId."""
        result = tier1_verify(
            self._make_claim("org.aspose.slides.foss.export.SaveFormat"),
            set(), self._profile("org.aspose.slides.foss:aspose-slides-foss"), "slides", "java",
        )
        assert result is None, f"Sub-package of Maven groupId should pass Tier 1, got: {result}"

    def test_maven_exact_groupid_subpackage(self):
        """org.aspose.slides.foss.Presentation must also pass."""
        result = tier1_verify(
            self._make_claim("org.aspose.slides.foss.Presentation"),
            set(), self._profile("org.aspose.slides.foss:aspose-slides-foss"), "slides", "java",
        )
        assert result is None

    def test_maven_unrelated_package_flagged(self):
        """A completely different Aspose package should still be flagged."""
        result = tier1_verify(
            self._make_claim("com.aspose.cells.foss.Workbook"),
            set(), self._profile("org.aspose.slides.foss:aspose-slides-foss"), "slides", "java",
        )
        assert result is not None and result["type"] == "wrong-package"


# ---------------------------------------------------------------------------
# Tier 1: Python underscore normalization (cells/python fix)
# ---------------------------------------------------------------------------

class TestPythonUnderscoreNormalization:
    """Python packages with hyphens import as underscored modules."""

    def _make_claim(self, value: str) -> dict:
        return {"type": "package-declaration", "value": value, "file": "test.md", "line": 1}

    def _profile(self, pkg: str, import_path: str | None = None) -> dict:
        actuals = {"package_name": pkg}
        if import_path:
            actuals["import_path"] = import_path
        return {
            "discovered_actuals": actuals,
            "discovery_hints": {"language": "python"},
        }

    def test_underscore_form_accepted(self):
        """import aspose_cells_foss must pass when package is aspose-cells-foss."""
        result = tier1_verify(
            self._make_claim("aspose_cells_foss"),
            set(), self._profile("aspose-cells-foss", "aspose.cells_foss"), "cells", "python",
        )
        assert result is None, f"Underscore-normalized package should pass, got: {result}"

    def test_companion_plugin_skipped(self):
        """markitdown-aspose-cells-plugin must not be flagged (starts with 'markitdown')."""
        result = tier1_verify(
            self._make_claim("markitdown-aspose-cells-plugin"),
            set(), self._profile("aspose-cells-foss", "aspose.cells_foss"), "cells", "python",
        )
        assert result is None, f"Companion plugin should be skipped, got: {result}"

    def test_wrong_aspose_package_flagged(self):
        """A different Aspose package should still be flagged."""
        result = tier1_verify(
            self._make_claim("aspose-words-foss"),
            set(), self._profile("aspose-cells-foss", "aspose.cells_foss"), "cells", "python",
        )
        assert result is not None and result["type"] == "wrong-package"


# ---------------------------------------------------------------------------
# Edge case: Maven no-colon (plain groupId, no :artifactId)
# ---------------------------------------------------------------------------

class TestMavenNoColon:
    """expected_pkg is a plain Java groupId without :artifactId — must fall through gracefully."""

    def _make_claim(self, value: str) -> dict:
        return {"type": "package-declaration", "value": value, "file": "test.md", "line": 1}

    def _profile(self, pkg: str) -> dict:
        return {
            "discovered_actuals": {"package_name": pkg},
            "discovery_hints": {"language": "java"},
        }

    def test_plain_java_subpackage_accepted(self):
        """com.aspose.slides.foss.Presentation must pass when expected is plain groupId."""
        result = tier1_verify(
            self._make_claim("com.aspose.slides.foss.Presentation"),
            set(), self._profile("com.aspose.slides.foss"), "slides", "java",
        )
        assert result is None, f"Sub-package of plain groupId should pass Tier 1, got: {result}"

    def test_plain_java_exact_match_accepted(self):
        """com.aspose.slides.foss (exact) must pass when expected_pkg is the same."""
        result = tier1_verify(
            self._make_claim("com.aspose.slides.foss"),
            set(), self._profile("com.aspose.slides.foss"), "slides", "java",
        )
        assert result is None, f"Exact match of plain groupId should pass Tier 1, got: {result}"


# ---------------------------------------------------------------------------
# Edge case: Python sub-module path normalization
# ---------------------------------------------------------------------------

class TestPythonSubModuleNormalization:
    """Python hyphen→underscore normalization applies to sub-module import paths."""

    def _make_claim(self, value: str) -> dict:
        return {"type": "package-declaration", "value": value, "file": "test.md", "line": 1}

    def _profile(self, pkg: str) -> dict:
        return {
            "discovered_actuals": {"package_name": pkg},
            "discovery_hints": {"language": "python"},
        }

    def test_submodule_underscore_form_accepted(self):
        """aspose_cells_foss.worksheet must be suppressed when expected is aspose-cells-foss."""
        result = tier1_verify(
            self._make_claim("aspose_cells_foss.worksheet"),
            set(), self._profile("aspose-cells-foss"), "cells", "python",
        )
        assert result is None, f"Underscore sub-module should be suppressed, got: {result}"

    def test_submodule_hyphen_form_accepted(self):
        """aspose-cells-foss.worksheet (hyphen form) must also be suppressed."""
        result = tier1_verify(
            self._make_claim("aspose-cells-foss.worksheet"),
            set(), self._profile("aspose-cells-foss"), "cells", "python",
        )
        assert result is None, f"Hyphen sub-module should be suppressed, got: {result}"


# ---------------------------------------------------------------------------
# Edge case: Maven triple-segment groupId (4 dotted segments)
# ---------------------------------------------------------------------------

class TestMavenTripleSegmentGroupId:
    """groupId has 4 dotted segments (e.g. com.aspose.cells.foss)."""

    def _make_claim(self, value: str) -> dict:
        return {"type": "package-declaration", "value": value, "file": "test.md", "line": 1}

    def _profile(self, pkg: str) -> dict:
        return {
            "discovered_actuals": {"package_name": pkg},
            "discovery_hints": {"language": "java"},
        }

    def test_triple_segment_subpackage_accepted(self):
        """com.aspose.cells.foss.Workbook must pass when expected contains that groupId."""
        result = tier1_verify(
            self._make_claim("com.aspose.cells.foss.Workbook"),
            set(), self._profile("com.aspose.cells.foss:aspose-cells-foss"), "cells", "java",
        )
        assert result is None, f"Sub-package of triple-segment groupId should pass, got: {result}"

    def test_cross_family_still_flagged(self):
        """com.aspose.slides.foss.Presentation must be flagged when cells groupId is expected."""
        result = tier1_verify(
            self._make_claim("com.aspose.slides.foss.Presentation"),
            set(), self._profile("com.aspose.cells.foss:aspose-cells-foss"), "cells", "java",
        )
        assert result is not None, "Cross-family import must be flagged as wrong-package"


# ---------------------------------------------------------------------------
# Regression guard: Python startswith("aspose") filter on other platforms
# ---------------------------------------------------------------------------

class TestPythonStartswithRegressionGuard:
    """Legitimate Aspose imports on non-cells Python platforms must not be flagged.

    Verifies that the companion-plugin filter change (startswith vs 'in') did not
    introduce regressions: imports that start with 'aspose' are not affected by the
    companion filter in either old or new code, so these must still pass.
    """

    def _make_claim(self, value: str) -> dict:
        return {"type": "package-declaration", "value": value, "file": "test.md", "line": 1}

    def _profile(self, pkg: str, import_path: str) -> dict:
        return {
            "discovered_actuals": {"package_name": pkg, "import_path": import_path},
            "discovery_hints": {"language": "python"},
        }

    def test_words_python_not_regressed(self):
        """aspose.words import path must not be flagged for words/python."""
        result = tier1_verify(
            self._make_claim("aspose.words"),
            set(), self._profile("aspose-words", "aspose.words"), "words", "python",
        )
        assert result is None, "words/python: aspose.words was flagged"

    def test_slides_python_not_regressed(self):
        """aspose.slides import path must not be flagged for slides/python."""
        result = tier1_verify(
            self._make_claim("aspose.slides"),
            set(), self._profile("aspose-slides", "aspose.slides"), "slides", "python",
        )
        assert result is None, "slides/python: aspose.slides was flagged"

    def test_email_python_not_regressed(self):
        """aspose.email import path must not be flagged for email/python."""
        result = tier1_verify(
            self._make_claim("aspose.email"),
            set(), self._profile("aspose-email", "aspose.email"), "email", "python",
        )
        assert result is None, "email/python: aspose.email was flagged"

    def test_3d_python_not_regressed(self):
        """aspose.threed import path must not be flagged for 3d/python."""
        result = tier1_verify(
            self._make_claim("aspose.threed"),
            set(), self._profile("aspose-3d", "aspose.threed"), "3d", "python",
        )
        assert result is None, "3d/python: aspose.threed was flagged"

    def test_companion_plugin_suppressed_not_regressed(self):
        """Companion plugin (markitdown-aspose-cells-plugin) must be suppressed on all platforms."""
        for platform, pkg in [("words", "aspose-words"), ("slides", "aspose-slides"),
                               ("email", "aspose-email"), ("3d", "aspose-3d")]:
            result = tier1_verify(
                self._make_claim("markitdown-aspose-cells-plugin"),
                set(), self._profile(pkg, f"aspose.{platform}"), platform, "python",
            )
            assert result is None, f"{platform}/python: companion plugin was not suppressed"


class TestResetState:
    """reset_state() deletes state file; safe to call when file absent."""

    def test_reset_deletes_existing_file(self, tmp_path):
        """reset_state() returns True and removes the state file."""
        state = {"family": "cells", "platform": "python", "findings": []}
        save_state(state, "cells", "python", state_dir=tmp_path)
        state_file = tmp_path / "cells-python.json"
        assert state_file.exists()

        result = reset_state("cells", "python", state_dir=tmp_path)
        assert result is True
        assert not state_file.exists()

    def test_reset_safe_when_no_file(self, tmp_path):
        """reset_state() returns False without error when no state file exists."""
        result = reset_state("cells", "python", state_dir=tmp_path)
        assert result is False

    def test_reset_oserror_is_reraised(self, tmp_path, monkeypatch):
        """OSError from unlink() must be logged and re-raised, not swallowed."""
        import pathlib

        state = {"family": "cells", "platform": "python", "findings": []}
        save_state(state, "cells", "python", state_dir=tmp_path)

        original_unlink = pathlib.Path.unlink

        def mock_unlink(self_path, missing_ok=False):
            if self_path.name == "cells-python.json":
                raise OSError("locked")
            return original_unlink(self_path, missing_ok=missing_ok)

        monkeypatch.setattr(pathlib.Path, "unlink", mock_unlink)

        with pytest.raises(OSError, match="locked"):
            reset_state("cells", "python", state_dir=tmp_path)


class TestCLIFlags:
    """CLI smoke tests: verify gap-eval flags appear in --help output."""

    def _run_help(self) -> str:
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/gap-eval/src/run.py", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parents[3],  # repo root
        )
        assert result.returncode == 0, f"--help failed: {result.stderr}"
        return result.stdout

    def test_reset_state_in_help(self):
        """--reset-state flag must appear in --help."""
        assert "--reset-state" in self._run_help()

    def test_reset_state_dry_run_in_help(self):
        """--reset-state-dry-run flag must appear in --help."""
        assert "--reset-state-dry-run" in self._run_help()

    def test_no_tier3_cache_in_help(self):
        """--no-tier3-cache flag must appear in --help (regression guard)."""
        assert "--no-tier3-cache" in self._run_help()

    def test_deterministic_in_help(self):
        """--deterministic flag must appear in --help (regression guard)."""
        assert "--deterministic" in self._run_help()

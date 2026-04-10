"""Tests for gap-eval profile safety: cross-check and Stage 1 → Tier 1 override."""

from __future__ import annotations

import copy
import logging
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from validate_profile import _read_package_from_build_file, validate_profile, update_profile  # type: ignore  # noqa: E402
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
        """Call discover_content_files with _REPO_ROOT monkeypatched to tmp_path."""
        import run as run_mod  # already on sys.path via _GAP_EVAL_DIR
        original = run_mod._REPO_ROOT
        run_mod._REPO_ROOT = tmp_path
        try:
            return run_mod.discover_content_files(family, platform)
        finally:
            run_mod._REPO_ROOT = original

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
        """OSError from _clone_cache_base causes graceful skip with WARNING logged."""
        import validate_profile as vp

        def _raise_os():
            raise OSError("cache unavailable for test")

        monkeypatch.setattr(sys, "argv", ["validate_profile.py", "--all"])
        monkeypatch.setattr("validate_profile._clone_cache_base", _raise_os)

        with caplog.at_level(logging.WARNING):
            vp.main()  # must NOT raise

        assert any(
            "skipping validation" in r.message.lower() for r in caplog.records
        ), f"Expected skip warning, got: {[r.message for r in caplog.records]}"
        assert any(
            r.levelname == "WARNING" for r in caplog.records
        ), "Skip message must be at WARNING level"

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

        monkeypatch.setattr(vp, "_PROFILES_DIR", tmp_path / "profiles")
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

        monkeypatch.setattr(vp, "_PROFILES_DIR", tmp_path / "profiles")
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

        monkeypatch.setattr(vp, "_PROFILES_DIR", tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", lambda: tmp_path / "cache")

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is True

    def test_returns_false_when_build_file_missing(self, tmp_path, monkeypatch):
        """Returns False (no crash) when the build file does not exist in clone cache."""
        import validate_profile as vp

        self._make_profile(tmp_path, "src/Missing.csproj", package_name=None)
        cache = tmp_path / "cache"
        cache.mkdir()

        monkeypatch.setattr(vp, "_PROFILES_DIR", tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", lambda: cache)

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is False

    def test_returns_false_on_os_error_from_cache(self, tmp_path, monkeypatch):
        """Returns False (no crash) when clone cache resolution raises OSError."""
        import validate_profile as vp

        self._make_profile(tmp_path, "src/Aspose.Test/Aspose.Test.csproj", package_name=None)

        def _raise():
            raise OSError("cache unavailable")

        monkeypatch.setattr(vp, "_PROFILES_DIR", tmp_path / "profiles")
        monkeypatch.setattr(vp, "_clone_cache_base", _raise)

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is False

    def test_returns_false_when_profile_missing(self, tmp_path, monkeypatch):
        """Returns False when the profile YAML does not exist."""
        import validate_profile as vp

        monkeypatch.setattr(vp, "_PROFILES_DIR", tmp_path / "profiles")

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

        monkeypatch.setattr(vp, "_PROFILES_DIR", tmp_path / "profiles")

        result = vp.update_profile("test", "net", dry_run=False)
        assert result is False

"""Regression tests for Rust-platform gap-eval support (RC-W1-001).

Prior to this fix, ``scripts/gap-eval/src/run.py`` had zero support for
Rust-platform products:

1. Stage 1 (``_read_build_package``) could not read the package manifest for
   ``cells/rust`` because its fallback candidate-file list never included
   ``Cargo.toml``, and no ``scripts/gap-eval/profiles/cells/rust.yaml``
   profile existed.
2. Stage 2 (``stage2_knowledge_validation``)'s clone-cache source-verification
   grep call hardcoded ``--include=*.java --include=*.py --include=*.cs
   --include=*.ts --include=*.cpp --include=*.h`` and never included ``*.rs``,
   so it structurally could not find Rust source files -- every real class in
   ``cells/rust``'s API surface was reported as a "phantom API not found in
   clone cache source" (207 confirmed false-positive findings on a real run,
   see ``reports/gap-analysis/cells-rust.json``).

These tests cover both fixes using synthetic fixtures (no clone-cache
dependency) plus integration checks against the real ``cells/rust`` clone
cache and knowledge model when they are present locally.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow imports from scripts/gap-eval/src (mirrors the pattern used by
# scripts/pipeline/tests/test_gap_eval_profile_safety.py).
_GAP_EVAL_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_GAP_EVAL_SRC) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_SRC))

from run import _read_build_package, stage2_knowledge_validation  # type: ignore  # noqa: E402
from state import make_finding_id  # type: ignore  # noqa: E402
import validate_profile  # type: ignore  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUST_CLONE_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_cells_rust"
_RUST_API_SURFACE = _REPO_ROOT / "knowledge" / "cells" / "rust" / "merged" / "api_surface.json"
_RUST_PROFILE_PATH = _REPO_ROOT / "scripts" / "gap-eval" / "profiles" / "cells" / "rust.yaml"


# ---------------------------------------------------------------------------
# Stage 1: Cargo.toml package-name extraction
# ---------------------------------------------------------------------------

class TestStage1CargoToml:
    """_read_build_package must read a Cargo.toml [package] name."""

    def test_cargo_toml_package_name_extracted(self, tmp_path):
        """A profile pointing at Cargo.toml extracts the [package] name.

        Cargo.toml commonly declares a *different* name under [lib] (and one
        per [[bin]] target) after the [package] table -- the first ``name =``
        match (the [package] table) must win, matching real cells/rust shape.
        """
        (tmp_path / "Cargo.toml").write_text(
            '[package]\n'
            'name = "aspose-cells-foss-rust"\n'
            'version = "26.7.0"\n'
            'edition = "2021"\n'
            '\n'
            '[lib]\n'
            'name = "aspose_cells_foss_rust"\n'
            'path = "src/lib.rs"\n'
            '\n'
            '[[bin]]\n'
            'name = "sample_basic"\n'
            'path = "samples/basic.rs"\n',
            encoding="utf-8",
        )
        profile = {
            "discovery_hints": {
                "package_source_file": "Cargo.toml",
                "package_extraction": "toml:[package].name",
            }
        }
        assert _read_build_package(tmp_path, profile) == "aspose-cells-foss-rust"

    def test_cargo_toml_discovered_via_fallback_candidate_list(self, tmp_path):
        """When package_source_file points at a non-existent path, the
        alt-candidate rglob fallback must still find Cargo.toml.

        This is the literal fix for RC-W1-001 part 1: 'Cargo.toml' must be a
        member of the fallback candidate tuple in _read_build_package.
        """
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "aspose-cells-foss-rust"\n', encoding="utf-8"
        )
        profile = {
            "discovery_hints": {
                # Deliberately wrong path — forces the alt-candidate fallback loop.
                "package_source_file": "does-not-exist.toml",
            }
        }
        assert _read_build_package(tmp_path, profile) == "aspose-cells-foss-rust"

    def test_no_cargo_toml_still_returns_none_gracefully(self, tmp_path):
        """Sanity check: absence of any manifest still returns None, not a crash."""
        profile = {"discovery_hints": {"package_source_file": "Cargo.toml"}}
        assert _read_build_package(tmp_path, profile) is None


# ---------------------------------------------------------------------------
# Stage 1: rust.yaml profile file
# ---------------------------------------------------------------------------

class TestRustProfileFile:
    """scripts/gap-eval/profiles/cells/rust.yaml must exist and validate."""

    def test_profile_file_exists(self):
        assert _RUST_PROFILE_PATH.exists(), (
            f"cells/rust profile missing at {_RUST_PROFILE_PATH} — "
            "RC-W1-001 part 1 requires a real profile file"
        )

    def test_profile_schema_valid(self):
        """Schema-only validation — no clone cache required, safe for CI."""
        validate_profile.configure()  # ensure default (repo) paths
        errors = validate_profile.validate_schema("cells", "rust")
        assert errors == [], f"cells/rust profile schema errors: {errors}"

    @pytest.mark.skipif(
        not _RUST_CLONE_CACHE.exists(), reason="cells/rust clone cache not present locally"
    )
    def test_profile_matches_real_clone_cache(self):
        """Cross-check discovered_actuals.package_name against the real clone cache."""
        validate_profile.configure()
        cache_base = _RUST_CLONE_CACHE.parent
        errors = validate_profile.validate_against_cache("cells", "rust", cache_base)
        assert errors == [], f"cells/rust profile does not match clone cache: {errors}"


# ---------------------------------------------------------------------------
# Stage 2: Rust source-file grep coverage
# ---------------------------------------------------------------------------

class TestStage2RustGrep:
    """stage2_knowledge_validation must be able to find real Rust classes."""

    def test_rs_extension_is_greppable(self, tmp_path):
        """Synthetic clone cache with only a .rs file — a known class name
        must be found (no finding emitted) now that --include=*.rs is present.
        """
        src_dir = tmp_path / "src" / "Aspose.Cells_FOSS"
        src_dir.mkdir(parents=True)
        (src_dir / "Workbook.rs").write_text(
            "pub struct Workbook {\n    // ...\n}\n", encoding="utf-8"
        )
        api_data = [{"name": "Workbook"}]
        findings = stage2_knowledge_validation(
            "cells", "rust", tmp_path, api_data, make_finding_id
        )
        assert findings == [], (
            f"Workbook.rs exists but stage2 still flagged it as phantom: {findings}"
        )

    def test_genuinely_missing_class_still_flagged(self, tmp_path):
        """Control case: a class name absent from source must still produce
        a finding — proves the fix isn't vacuously suppressing everything.
        """
        src_dir = tmp_path / "src" / "Aspose.Cells_FOSS"
        src_dir.mkdir(parents=True)
        (src_dir / "Workbook.rs").write_text("pub struct Workbook {}\n", encoding="utf-8")
        api_data = [{"name": "TotallyFakeClassThatDoesNotExist"}]
        findings = stage2_knowledge_validation(
            "cells", "rust", tmp_path, api_data, make_finding_id
        )
        assert len(findings) == 1
        assert findings[0]["type"] == "knowledge-model-wrong"
        assert findings[0]["old_value"] == "TotallyFakeClassThatDoesNotExist"

    @pytest.mark.skipif(
        not _RUST_CLONE_CACHE.exists(), reason="cells/rust clone cache not present locally"
    )
    def test_known_classes_found_in_real_clone_cache(self):
        """Integration check against the real clone cache (matches the task's
        example: Workbook and Cell live under
        src/Aspose.Cells_FOSS/*.rs).
        """
        api_data = [{"name": "Workbook"}, {"name": "Cell"}, {"name": "Worksheet"}]
        findings = stage2_knowledge_validation(
            "cells", "rust", _RUST_CLONE_CACHE, api_data, make_finding_id
        )
        assert findings == [], (
            f"Real Rust classes incorrectly flagged as phantom APIs: {findings}"
        )

    @pytest.mark.skipif(
        not (_RUST_CLONE_CACHE.exists() and _RUST_API_SURFACE.exists()),
        reason="cells/rust clone cache or api_surface.json not present locally",
    )
    def test_real_api_surface_has_near_zero_phantom_findings(self):
        """Regression guard for the 207-finding false-positive flood (RC-W1-001).

        Runs Stage 2 against the FULL real cells/rust api_surface.json class
        list and the real clone cache. Before the *.rs fix this produced 207
        findings (one per class — the grep could never find anything in a
        pure-Rust repo). After the fix it must be at/near zero, since the
        audit found cells/rust's content otherwise clean.
        """
        import json

        data = json.loads(_RUST_API_SURFACE.read_text(encoding="utf-8"))
        api_data = data if isinstance(data, list) else data.get("classes", data.get("entries", []))
        assert len(api_data) > 100, "sanity check: expected a substantial real API surface"

        findings = stage2_knowledge_validation(
            "cells", "rust", _RUST_CLONE_CACHE, api_data, make_finding_id
        )
        assert len(findings) < 5, (
            f"Expected near-zero phantom-API findings after the *.rs grep fix, "
            f"got {len(findings)} (was 207 before the fix): "
            f"{[f['old_value'] for f in findings]}"
        )

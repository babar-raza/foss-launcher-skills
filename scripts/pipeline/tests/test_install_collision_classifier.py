"""Tests for install_collision_classifier.py (PKGINSTALL-COLLISION-CLASSIFIER).

The golden-file class runs against REAL data (the live data/package_registry.json
+ the real, already-populated runs/.clone_cache/) rather than synthetic
fixtures, matching this repo's own established precedent (ST-054 TC-12's
CMake-target extraction tests did the same) -- it is strictly more faithful
than a hand-authored snippet for a module whose entire job is "does this
correctly read real source," and the real clone caches are already
committed, tracked assets other tests in this repo already rely on.
"""
from pathlib import Path

import pytest

from install_collision_classifier import (
    CollisionClassification,
    classify_collision_risk,
    configure,
    extract_source_identifiers,
    normalize_identifier,
)


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    configure()  # restore real repo_root after every test


# -- Pure-function unit tests --------------------------------------------

class TestNormalizeIdentifier:
    def test_strips_dots_and_underscores_and_casefolds(self):
        assert normalize_identifier("Aspose.Cells_FOSS") == normalize_identifier("Aspose.Cells.FOSS")
        assert normalize_identifier("Aspose.Cells.FOSS") == "asposecellsfoss"

    def test_distinct_identifiers_stay_distinct(self):
        assert normalize_identifier("aspose-barcode-foss") != normalize_identifier("aspose-page-foss")


class TestExtractSourceIdentifiers:
    def test_net_using_statement(self, tmp_path):
        src = tmp_path / "Program.cs"
        src.write_text("using Aspose.Cells_FOSS;\nnamespace Foo {}\n", encoding="utf-8")
        assert "Aspose.Cells_FOSS" in extract_source_identifiers(tmp_path, "net")

    def test_python_from_import(self, tmp_path):
        src = tmp_path / "example.py"
        src.write_text("from aspose.cells_foss import Workbook\n", encoding="utf-8")
        assert "aspose.cells_foss" in extract_source_identifiers(tmp_path, "python")

    def test_python_bare_import(self, tmp_path):
        src = tmp_path / "example.py"
        src.write_text("import aspose_font\n", encoding="utf-8")
        assert "aspose_font" in extract_source_identifiers(tmp_path, "python")

    def test_go_quoted_import_path(self, tmp_path):
        src = tmp_path / "main.go"
        src.write_text(
            'import (\n\t"github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26/aspose/cells_foss"\n)\n',
            encoding="utf-8",
        )
        found = extract_source_identifiers(tmp_path, "go")
        assert any("aspose-cells-foss" in ident for ident in found)

    def test_typescript_package_import_captured(self, tmp_path):
        src = tmp_path / "example.ts"
        src.write_text('import { Scene } from "@aspose/3d";\n', encoding="utf-8")
        assert "@aspose/3d" in extract_source_identifiers(tmp_path, "typescript")

    def test_typescript_relative_import_not_captured(self, tmp_path):
        """A relative import is never a package-identity collision candidate --
        must not be captured (would otherwise generate false noise)."""
        src = tmp_path / "example.ts"
        src.write_text('import { Workbook } from "../aspose_cells";\n', encoding="utf-8")
        assert extract_source_identifiers(tmp_path, "typescript") == set()

    def test_excludes_node_modules(self, tmp_path):
        nested = tmp_path / "node_modules" / "somepkg"
        nested.mkdir(parents=True)
        (nested / "index.ts").write_text('import { X } from "should-not-appear";\n', encoding="utf-8")
        assert extract_source_identifiers(tmp_path, "typescript") == set()

    def test_unscanned_platform_returns_empty_set(self, tmp_path):
        """cpp (and any platform with no defined extraction pattern) returns
        an empty set, not an error -- matches the original report's own
        treatment (0 identifiers scanned for cells/cpp/email/cpp/pdf/cpp/
        slides/cpp, all resolved SAFE)."""
        (tmp_path / "lib.cpp").write_text("#include <foo>\n", encoding="utf-8")
        assert extract_source_identifiers(tmp_path, "cpp") == set()


class TestClassifyCollisionRiskFailClosed:
    """Every failure mode must resolve to COLLISION_RISK_PENDING_VERIFICATION,
    never silently to SAFE."""

    def test_missing_registry_entry(self):
        result = classify_collision_risk("nonexistent", "platform", registry={})
        assert result.classification == CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION

    def test_missing_clone_cache_directory(self, tmp_path):
        registry = {"cells": {"net": {
            "registry_type": "nuget",
            "candidate": {"name": "Aspose.Cells.FOSS"},
        }}}
        result = classify_collision_risk(
            "cells", "net", registry=registry, clone_cache_root=tmp_path,
        )
        assert result.classification == CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION
        assert "no local clone cache" in result.reason

    def test_no_candidate_identifier(self, tmp_path):
        registry = {"cells": {"net": {"registry_type": "nuget", "candidate": {}}}}
        result = classify_collision_risk("cells", "net", registry=registry, clone_cache_root=tmp_path)
        assert result.classification == CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION


class TestClassifyCollisionRiskFixtures:
    def test_out_of_scope_registry_types(self, tmp_path):
        for registry_type in ("maven", "cargo"):
            registry = {"x": {"y": {"registry_type": registry_type, "candidate": {"name": "whatever"}}}}
            result = classify_collision_risk("x", "y", registry=registry, clone_cache_root=tmp_path)
            assert result.classification == CollisionClassification.NOT_APPLICABLE

    def test_nuget_structural_collision_detected(self, tmp_path):
        cache = tmp_path / "aspose_cells_net"
        cache.mkdir()
        (cache / "Program.cs").write_text("using Aspose.Cells_FOSS;\n", encoding="utf-8")
        registry = {"cells": {"net": {
            "registry_type": "nuget",
            "candidate": {"name": "Aspose.Cells.FOSS"},
        }}}
        result = classify_collision_risk("cells", "net", registry=registry, clone_cache_root=tmp_path)
        assert result.classification == CollisionClassification.COLLISION_RISK_STRUCTURAL
        assert "Aspose.Cells_FOSS" in result.colliding_identifiers

    def test_pypi_naming_convention_divergence_is_safe_not_collision(self, tmp_path):
        """The routine PyPI dist-name-vs-import-name divergence must resolve
        SAFE, not COLLISION_RISK -- this is the corrected reclassification
        vs. the original report's own over-conservative bucketing."""
        cache = tmp_path / "aspose_barcode_python"
        cache.mkdir()
        (cache / "example.py").write_text("from aspose_barcode_foss import Barcode\n", encoding="utf-8")
        registry = {"barcode": {"python": {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-barcode-foss"},
        }}}
        result = classify_collision_risk("barcode", "python", registry=registry, clone_cache_root=tmp_path)
        assert result.classification == CollisionClassification.SAFE_FOR_MECHANICAL_MIGRATION
        assert "aspose_barcode_foss" in result.colliding_identifiers  # normalize-matched, but harmless

    def test_no_matching_identifiers_is_safe(self, tmp_path):
        cache = tmp_path / "aspose_3d_net"
        cache.mkdir()
        (cache / "Program.cs").write_text("using System;\n", encoding="utf-8")
        registry = {"3d": {"net": {
            "registry_type": "nuget",
            "candidate": {"name": "Aspose.3D.FOSS"},
        }}}
        result = classify_collision_risk("3d", "net", registry=registry, clone_cache_root=tmp_path)
        assert result.classification == CollisionClassification.SAFE_FOR_MECHANICAL_MIGRATION
        assert result.colliding_identifiers == frozenset()

    def test_go_modules_candidate_key(self, tmp_path):
        cache = tmp_path / "aspose_cells_go"
        cache.mkdir()
        (cache / "main.go").write_text('import "github.com/other/pkg"\n', encoding="utf-8")
        registry = {"cells": {"go": {
            "registry_type": "go_modules",
            "candidate": {"module_path": "github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26"},
        }}}
        result = classify_collision_risk("cells", "go", registry=registry, clone_cache_root=tmp_path)
        assert result.classification == CollisionClassification.SAFE_FOR_MECHANICAL_MIGRATION
        assert result.candidate == "github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26"


class TestGoldenFileRealPortfolio:
    """Runs against REAL data.package_registry.json + REAL runs/.clone_cache/ --
    pins this session's own independently-verified re-derivation of ST-054
    TC-05's classification report: 26 of 27 tracked products
    SAFE_FOR_MECHANICAL_MIGRATION, only cells/net COLLISION_RISK_STRUCTURAL
    (the confirmed, ground-truth-verified real corruption risk)."""

    _EXPECTED_COLLISION_RISK_STRUCTURAL = {("cells", "net")}

    _ALL_TRACKED_PRODUCTS = [
        ("3d", "net"), ("3d", "python"), ("3d", "typescript"),
        ("barcode", "python"),
        ("cells", "cpp"), ("cells", "go"), ("cells", "net"), ("cells", "python"), ("cells", "typescript"),
        ("email", "cpp"), ("email", "net"), ("email", "python"),
        ("font", "python"),
        ("html", "python"),
        ("note", "python"),
        ("page", "python"),
        ("pdf", "cpp"), ("pdf", "go"), ("pdf", "net"), ("pdf", "python"), ("pdf", "typescript"),
        ("slides", "cpp"), ("slides", "net"), ("slides", "python"),
        ("tex", "python"),
        ("words", "net"), ("words", "python"),
    ]

    def test_real_portfolio_classification_matches_expected(self):
        results = {}
        for family, platform in self._ALL_TRACKED_PRODUCTS:
            results[(family, platform)] = classify_collision_risk(family, platform)

        structural = {
            key for key, r in results.items()
            if r.classification == CollisionClassification.COLLISION_RISK_STRUCTURAL
        }
        pending = {
            key for key, r in results.items()
            if r.classification == CollisionClassification.COLLISION_RISK_PENDING_VERIFICATION
        }
        safe = {
            key for key, r in results.items()
            if r.classification == CollisionClassification.SAFE_FOR_MECHANICAL_MIGRATION
        }

        assert pending == set(), f"no product should be PENDING (missing clone cache): {pending}"
        assert structural == self._EXPECTED_COLLISION_RISK_STRUCTURAL, (
            f"expected only cells/net as COLLISION_RISK_STRUCTURAL, got {structural}"
        )
        assert len(safe) == len(self._ALL_TRACKED_PRODUCTS) - 1

    def test_cells_net_reason_cites_the_real_colliding_identifier(self):
        result = classify_collision_risk("cells", "net")
        assert result.classification == CollisionClassification.COLLISION_RISK_STRUCTURAL
        assert "Aspose.Cells_FOSS" in result.colliding_identifiers

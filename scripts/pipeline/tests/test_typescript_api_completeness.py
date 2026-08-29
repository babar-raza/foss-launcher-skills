"""Tests for scripts/pipeline/commands/diagnostics/typescript_api_completeness.py
(TC-MT040-22, G-TS-10/G-TS-09).

Covers the two hardening fixes plus the new barrel-completeness signal:
1. node_modules/dist/build/test directories are excluded from the regex
   source scan (previously unfiltered -- produced false "missing from
   api_surface" findings from vendored .d.ts files).
2. api_surface kind counts include functions/constants, not just classes.
3. Barrel-export completeness via the G-TS-02a adapter
   (lang.typescript.export_surface()): missing-from-api-surface and
   exported-but-marked-unreachable findings, with the fail-safe (barrel
   unresolvable -> None, no finding) proven explicitly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "commands" / "diagnostics"))

import typescript_api_completeness as tac


@pytest.fixture(autouse=True)
def _isolate_repo_root(tmp_path):
    tac.configure(repo_root=tmp_path)
    yield
    tac.configure(repo_root=None)


def _write_api_surface(tmp_path: Path, family: str, platform: str, entries: list) -> None:
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")


def _write_clone_file(tmp_path: Path, family: str, platform: str, rel_path: str, content: str) -> Path:
    clone_dir = tmp_path / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    file_path = clone_dir / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return clone_dir


class TestNonPublicDirExclusion:

    def test_node_modules_dts_excluded(self, tmp_path):
        _write_clone_file(
            tmp_path, "pdf", "typescript",
            "node_modules/@types/foo/index.d.ts",
            "export class VendoredThing {}\n",
        )
        _write_clone_file(
            tmp_path, "pdf", "typescript",
            "src/document.d.ts",
            "export class Document {}\n",
        )
        exports = tac.extract_ts_exports_from_clone_cache("pdf", "typescript")
        assert exports == {"Document"}
        assert "VendoredThing" not in exports

    def test_dist_build_excluded(self, tmp_path):
        _write_clone_file(
            tmp_path, "pdf", "typescript",
            "dist/index.d.ts",
            "export class BuiltOutput {}\n",
        )
        _write_clone_file(
            tmp_path, "pdf", "typescript",
            "build/generated.d.ts",
            "export class GeneratedOutput {}\n",
        )
        _write_clone_file(
            tmp_path, "pdf", "typescript",
            "src/document.d.ts",
            "export class Document {}\n",
        )
        exports = tac.extract_ts_exports_from_clone_cache("pdf", "typescript")
        assert exports == {"Document"}

    def test_test_dirs_excluded_from_ts_fallback(self, tmp_path):
        # No .d.ts files at all -> falls back to .ts source scan.
        _write_clone_file(
            tmp_path, "pdf", "typescript",
            "test/fixtures/helper.ts",
            "export class TestHelper {}\n",
        )
        _write_clone_file(
            tmp_path, "pdf", "typescript",
            "src/document.ts",
            "export class Document {}\n",
        )
        exports = tac.extract_ts_exports_from_clone_cache("pdf", "typescript")
        assert exports == {"Document"}
        assert "TestHelper" not in exports

    def test_no_clone_cache_returns_empty(self, tmp_path):
        assert tac.extract_ts_exports_from_clone_cache("nothere", "typescript") == set()


class TestApiSurfaceKindCounts:

    def test_counts_functions_and_constants_not_just_classes(self, tmp_path):
        _write_api_surface(tmp_path, "pdf", "typescript", [
            {"name": "Document", "kind": "class_declaration"},
            {"name": "Lexer", "kind": "class_declaration"},
            {"name": "renderDocumentToDocx", "kind": "function"},
            {"name": "Format", "kind": "interface_declaration",
             "properties": [{"name": "STANDARD_STRUCTURE_TYPES", "kind": "constant"}]},
        ])
        counts = tac.load_api_surface_counts("pdf", "typescript")
        assert counts.get("class_declaration") == 2
        assert counts.get("function") == 1
        assert counts.get("constant") == 1

    def test_empty_api_surface_yields_empty_counts(self, tmp_path):
        assert tac.load_api_surface_counts("nothere", "typescript") == {}


class TestBarrelCompleteness:
    """compute_barrel_completeness() reaches through to
    core.clone_cache.clone_path() -- a module with no configure() seam of
    its own (unlike this file's tac.configure()), so these tests monkeypatch
    it directly, matching the established pattern in
    tests/content_eval/test_typescript_code_reachability.py's _fake_clone().
    """

    @pytest.fixture(autouse=True)
    def _redirect_clone_path(self, tmp_path, monkeypatch):
        import core.clone_cache as clone_cache_mod

        def _fake_path(family: str, platform: str) -> Path:
            return tmp_path / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"

        monkeypatch.setattr(clone_cache_mod, "clone_path", _fake_path)

    def _write_barrel_fixture(self, tmp_path, family="pdf", platform="typescript"):
        clone_dir = _write_clone_file(
            tmp_path, family, platform, "package.json",
            '{"name": "@asposefoss/fake", "main": "dist/index.js"}\n',
        )
        (clone_dir / "dist").mkdir(parents=True, exist_ok=True)
        (clone_dir / "dist" / "index.js").write_text("", encoding="utf-8")
        _write_clone_file(
            tmp_path, family, platform, "src/index.ts",
            "export { Document } from './document.js';\n"
            "export { Lexer } from './lexer.js';\n",
        )
        _write_clone_file(tmp_path, family, platform, "src/document.ts", "export class Document {}\n")
        _write_clone_file(tmp_path, family, platform, "src/lexer.ts", "export class Lexer {}\n")
        return clone_dir

    def test_missing_from_api_surface(self, tmp_path):
        self._write_barrel_fixture(tmp_path)
        # api_surface.json only has Document -- Lexer is a real scout gap.
        _write_api_surface(tmp_path, "pdf", "typescript", [
            {"name": "Document", "kind": "class_declaration", "reachable": True},
        ])
        result = tac.compute_barrel_completeness("pdf", "typescript")
        assert result is not None
        assert result["barrel_exports_missing_from_api_surface"] == ["Lexer"]
        assert result["exported_but_marked_unreachable"] == []

    def test_exported_but_marked_unreachable(self, tmp_path):
        self._write_barrel_fixture(tmp_path)
        # Lexer IS barrel-exported (reachable) but api_surface says False --
        # an internal inconsistency, not a missing-entry case.
        _write_api_surface(tmp_path, "pdf", "typescript", [
            {"name": "Document", "kind": "class_declaration", "reachable": True},
            {"name": "Lexer", "kind": "class_declaration", "reachable": False},
        ])
        result = tac.compute_barrel_completeness("pdf", "typescript")
        assert result["barrel_exports_missing_from_api_surface"] == []
        assert result["exported_but_marked_unreachable"] == ["Lexer"]

    def test_fully_consistent_yields_no_findings(self, tmp_path):
        self._write_barrel_fixture(tmp_path)
        _write_api_surface(tmp_path, "pdf", "typescript", [
            {"name": "Document", "kind": "class_declaration", "reachable": True},
            {"name": "Lexer", "kind": "class_declaration", "reachable": True},
        ])
        result = tac.compute_barrel_completeness("pdf", "typescript")
        assert result["barrel_exports_missing_from_api_surface"] == []
        assert result["exported_but_marked_unreachable"] == []
        assert result["barrel_export_count"] == 2

    def test_unresolvable_barrel_is_fail_safe_none(self, tmp_path):
        # No dist/ built, no bare index.ts -- matches the real 3d/typescript
        # clone (live-verified 2026-08-29). Must return None, not a guess.
        _write_clone_file(
            tmp_path, "3d", "typescript", "package.json",
            '{"name": "@asposefoss/fake3d", "main": "dist/index.js"}\n',
        )
        _write_clone_file(tmp_path, "3d", "typescript", "src/shape.ts", "export class Shape {}\n")
        result = tac.compute_barrel_completeness("3d", "typescript")
        assert result is None

    def test_no_clone_cache_is_fail_safe_none(self, tmp_path):
        assert tac.compute_barrel_completeness("nothere", "typescript") is None


class TestConfigureSeam:

    def test_configure_reset_returns_to_real_repo_root(self, tmp_path):
        tac.configure(repo_root=tmp_path)
        assert tac._REPO_ROOT == tmp_path
        tac.configure(repo_root=None)
        assert tac._REPO_ROOT == tac._DEFAULT_REPO_ROOT

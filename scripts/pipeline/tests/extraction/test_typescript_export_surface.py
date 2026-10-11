"""Tests for TypeScript export_surface() -- the real barrel/reachability
implementation (TC-MT040-11), replacing lang/typescript.py's previous
unconditional (None, None) placeholder.

Covers extraction/lang/typescript.py's resolve_entry_point() and
export_surface() directly, plus their integration into
extraction/api_surface.py's `reachable` field via _compute_reachable().

Fail-safe contract under test throughout: export_surface() must NEVER
manufacture a false "confirmed unreachable" -- every ambiguous or
unenumerable case must degrade to (None, None), never a partial name set.
"""
import json

# sys.path is set by tests/conftest.py -- no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface
from extraction.lang import typescript as ts


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestResolveEntryPoint:
    def test_main_field_direct_hit(self, tmp_path):
        """cells/typescript's real shape: main points straight at an
        existing .ts file, no mapping needed."""
        _write(tmp_path / "package.json", json.dumps({"main": "index.ts"}))
        _write(tmp_path / "index.ts", "export const A = 1;\n")
        entry = ts.resolve_entry_point(tmp_path, tmp_path)
        assert entry == tmp_path / "index.ts"

    def test_dist_to_src_and_js_to_ts_mapping(self, tmp_path):
        """pdf/typescript's real shape: main points at an unbuilt
        dist/index.js -- must map dist/ -> src/ and .js -> .ts."""
        _write(tmp_path / "package.json", json.dumps({
            "main": "dist/index.js", "types": "dist/index.d.ts",
        }))
        _write(tmp_path / "src" / "index.ts", "export const A = 1;\n")
        entry = ts.resolve_entry_point(tmp_path, tmp_path / "src")
        assert entry == tmp_path / "src" / "index.ts"

    def test_exports_dot_string_form(self, tmp_path):
        _write(tmp_path / "package.json", json.dumps({"exports": {".": "./lib/main.js"}}))
        _write(tmp_path / "src" / "main.ts", "export const A = 1;\n")
        entry = ts.resolve_entry_point(tmp_path, tmp_path / "src")
        assert entry == tmp_path / "src" / "main.ts"

    def test_exports_dot_dict_form(self, tmp_path):
        _write(tmp_path / "package.json", json.dumps(
            {"exports": {".": {"types": "./dist/index.d.ts", "default": "./dist/index.js"}}}
        ))
        _write(tmp_path / "src" / "index.ts", "export const A = 1;\n")
        entry = ts.resolve_entry_point(tmp_path, tmp_path / "src")
        assert entry == tmp_path / "src" / "index.ts"

    def test_no_package_json_falls_back_to_pkg_root_index(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export const A = 1;\n")
        entry = ts.resolve_entry_point(tmp_path, pkg_root)
        assert entry == pkg_root / "index.ts"

    def test_nothing_resolves_returns_none(self, tmp_path):
        """3d/typescript's real shape: no barrel file exists anywhere."""
        pkg_root = tmp_path / "src"
        pkg_root.mkdir(parents=True)
        entry = ts.resolve_entry_point(tmp_path, pkg_root)
        assert entry is None


class TestExportSurfaceBarrelParsing:
    def test_brace_form_with_alias_adds_both_names(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export { A, B as C } from './x';\n")
        _write(pkg_root / "x.ts", "export class A {}\nexport class B {}\n")
        names, entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"A", "B", "C"}
        assert entry == pkg_root / "index.ts"

    def test_bare_local_reexport_form(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "class A {}\nclass B {}\nexport { A, B as C };\n")
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"A", "B", "C"}

    def test_export_type_from_counts_as_reachable(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export type { CellValue, Style as StyleType } from './types';\n")
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"CellValue", "Style", "StyleType"}

    def test_star_from_recurses_into_relative_target(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * from './sub';\n")
        _write(pkg_root / "sub.ts", "export class Deep {}\n")
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"Deep"}

    def test_star_from_resolves_index_directory_form(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * from './sub';\n")
        _write(pkg_root / "sub" / "index.ts", "export class DeepDir {}\n")
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"DeepDir"}

    def test_star_from_cycle_does_not_infinite_loop(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * from './a';\nexport class Root {}\n")
        _write(pkg_root / "a.ts", "export * from './index';\nexport class A {}\n")
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"Root", "A"}

    def test_default_export_name(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export default Zed;\n")
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"Zed"}

    def test_bare_declared_names_in_entry_file(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", (
            "export abstract class Exporter {}\n"
            "export interface IThing {}\n"
            "export enum Color { Red }\n"
            "export function util() {}\n"
            "export const K = 1;\n"
            "export namespace NS {}\n"
        ))
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"Exporter", "IThing", "Color", "util", "K", "NS"}

    def test_inline_type_modifier_stripped(self, tmp_path):
        """TS 5+ per-specifier inline `type` modifier: `export { type Foo, Bar }`."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export { type Foo, Bar } from './x';\n")
        names, _entry = ts.export_surface(tmp_path, pkg_root)
        assert names == {"Foo", "Bar"}


class TestExportSurfaceFailSafeBailConditions:
    def test_nonrelative_star_from_bails_globally(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * from 'some-external-package';\n")
        names, entry = ts.export_surface(tmp_path, pkg_root)
        assert (names, entry) == (None, None)

    def test_unresolvable_relative_star_from_bails_globally(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * from './does-not-exist';\n")
        names, entry = ts.export_surface(tmp_path, pkg_root)
        assert (names, entry) == (None, None)

    def test_star_as_namespace_bails_globally(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * as NS from './x';\nexport class Extra {}\n")
        _write(pkg_root / "x.ts", "export class Q {}\n")
        names, entry = ts.export_surface(tmp_path, pkg_root)
        assert (names, entry) == (None, None)

    def test_export_equals_commonjs_bails_globally(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export = SomeThing;\n")
        names, entry = ts.export_surface(tmp_path, pkg_root)
        assert (names, entry) == (None, None)

    def test_no_exports_at_all_returns_none_not_empty_set(self, tmp_path):
        """cells/typescript's real repo-root index.ts shape: a demo/script
        entry point that only imports and runs code, exporting nothing.
        This must be (None, None) -- "cannot determine" -- NOT an empty set
        (which would mean "confirmed nothing is reachable", a different and
        much stronger claim)."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", (
            "import { Workbook } from './workbook';\n"
            "const wb = new Workbook();\n"
            "wb.save('out.xlsx');\n"
        ))
        names, entry = ts.export_surface(tmp_path, pkg_root)
        assert (names, entry) == (None, None)

    def test_no_barrel_file_at_all_returns_none_none(self, tmp_path):
        pkg_root = tmp_path / "src"
        pkg_root.mkdir(parents=True)
        names, entry = ts.export_surface(tmp_path, pkg_root)
        assert (names, entry) == (None, None)


class TestReachabilityIntegration:
    """extract_api_surface()'s `reachable` field, wired through
    lang.typescript.export_surface() via _compute_reachable()."""

    def test_barrel_exported_class_is_reachable(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export { Visible } from './visible';\n")
        _write(pkg_root / "visible.ts", "export class Visible {}\n")
        _write(pkg_root / "hidden.ts", "export class Hidden {}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        visible = next(c for c in classes if c["name"] == "Visible")
        hidden = next(c for c in classes if c["name"] == "Hidden")
        assert visible["reachable"] is True
        assert hidden["reachable"] is False

    def test_unresolvable_barrel_leaves_everyone_reachable_true(self, tmp_path):
        """Negative control: when the barrel can't be enumerated at all (no
        entry point resolves anywhere), every class must default to
        reachable=True -- the fail-safe default, never a fabricated False."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "onlyfile.ts", "export class Anything {}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Anything")
        assert entry["reachable"] is True

    def test_scout_report_ts_entry_point_populated(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export class Visible {}\n")
        parser = scout.get_parser("typescript")
        _classes, _claims, _files, _pkgs, report = extract_api_surface(
            parser, "typescript", pkg_root, tmp_path, "fake")
        assert report["ts_entry_point"] == "src/index.ts"

    def test_scout_report_ts_entry_point_empty_when_unresolvable(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "onlyfile.ts", "export class Anything {}\n")
        parser = scout.get_parser("typescript")
        _classes, _claims, _files, _pkgs, report = extract_api_surface(
            parser, "typescript", pkg_root, tmp_path, "fake")
        assert report["ts_entry_point"] == ""

    def test_other_languages_scout_report_has_no_ts_entry_point_key(self, tmp_path):
        """The key must be TS/JS-only, never an always-present field for
        every language -- confirmed the hard way: adding it unconditionally
        broke test_extraction_goldens.py's byte-for-byte python/rust report
        parity check."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "Foo.py", "class Foo:\n    pass\n")
        parser = scout.get_parser("python")
        _classes, _claims, _files, _pkgs, report = extract_api_surface(
            parser, "python", pkg_root, tmp_path, "fake")
        assert "ts_entry_point" not in report


class TestClearCache:
    def test_clear_cache_reflects_mutation(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export class A {}\n")
        names, _ = ts.export_surface(tmp_path, pkg_root)
        assert names == {"A"}

        _write(pkg_root / "index.ts", "export class A {}\nexport class B {}\n")
        stale_names, _ = ts.export_surface(tmp_path, pkg_root)
        assert stale_names == {"A"}, (
            "expected a STALE cached result before clear_cache()"
        )

        ts.clear_cache()
        fresh_names, _ = ts.export_surface(tmp_path, pkg_root)
        assert fresh_names == {"A", "B"}

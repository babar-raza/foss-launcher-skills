"""Tests for TypeScript export_groups() -- TC-MT040-43 / D-4 strategy (b):
best-effort {exported_name: group_label} map from `export * as Name from
'./relative'` barrel groupings.

This is an OPTIONAL, ADDITIVE adapter capability layered on top of the
shared export_surface() contract (see extraction/lang/__init__.py) -- it is
NOT part of that contract's return shape, so it is its own function that a
caller probes for with getattr(module, "export_groups", None).

Fail-safe-adjacent contract under test: a single unresolvable/non-relative
`export * as` target must only drop THAT one grouping (never a global
bail, unlike export_surface()'s all-or-nothing reachability contract); an
entry file with no such groupings at all -- the common case -- returns
None, not an empty dict, so callers can tell "no information" apart from
"confirmed zero groups".
"""
# sys.path is set by tests/conftest.py -- no manual insert needed here.
from extraction.lang import typescript as ts


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestExportGroupsBasic:
    def test_single_named_group(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * as Forms from './forms.js';\n")
        _write(pkg_root / "forms.ts", "export class FormField {}\nexport class AcroForm {}\n")
        groups = ts.export_groups(tmp_path, pkg_root)
        assert groups == {"FormField": "Forms", "AcroForm": "Forms"}

    def test_multiple_named_groups(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts",
               "export * as Forms from './forms.js';\n"
               "export * as Images from './images.js';\n")
        _write(pkg_root / "forms.ts", "export class FormField {}\n")
        _write(pkg_root / "images.ts", "export class ImageInfo {}\n")
        groups = ts.export_groups(tmp_path, pkg_root)
        assert groups == {"FormField": "Forms", "ImageInfo": "Images"}

    def test_no_grouped_reexports_returns_none(self, tmp_path):
        """Common case: a flat barrel with only plain `export { X } from`
        re-exports (no `export * as` at all) -- no grouping info available,
        distinct from "confirmed zero groups"."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export { A, B } from './x';\n")
        _write(pkg_root / "x.ts", "export class A {}\nexport class B {}\n")
        assert ts.export_groups(tmp_path, pkg_root) is None

    def test_no_entry_point_returns_none(self, tmp_path):
        assert ts.export_groups(tmp_path, tmp_path / "src") is None


class TestExportGroupsFailSafe:
    def test_nonrelative_star_as_target_skipped_not_global_bail(self, tmp_path):
        """A bare/unresolvable `export * as` target drops only that one
        grouping -- unlike export_surface()'s all-or-nothing bail, a
        SECOND, resolvable grouping in the same barrel still contributes."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts",
               "export * as Vendor from 'some-package';\n"
               "export * as Forms from './forms.js';\n")
        _write(pkg_root / "forms.ts", "export class FormField {}\n")
        groups = ts.export_groups(tmp_path, pkg_root)
        assert groups == {"FormField": "Forms"}

    def test_unresolvable_relative_target_skipped(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export * as Ghost from './missing.js';\n")
        assert ts.export_groups(tmp_path, pkg_root) is None

    def test_first_group_wins_on_duplicate_export(self, tmp_path):
        """A name re-exported under two different namespace groups keeps
        whichever group was encountered first (deterministic, not fatal)."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts",
               "export * as Forms from './forms.js';\n"
               "export * as Other from './other.js';\n")
        _write(pkg_root / "forms.ts", "export class Shared {}\n")
        _write(pkg_root / "other.ts", "export class Shared {}\n")
        groups = ts.export_groups(tmp_path, pkg_root)
        assert groups == {"Shared": "Forms"}


class TestExportGroupsAdapterCapabilityIsOptional:
    def test_typescript_module_implements_it(self):
        assert hasattr(ts, "export_groups")

    def test_probing_pattern_used_by_promote_py(self):
        """Mirrors how commands/knowledge/promote.py discovers this
        OPTIONAL capability -- getattr, never a hard import assumption."""
        from extraction import lang
        fn = getattr(lang.get("typescript"), "export_groups", None)
        assert fn is not None
        fn_missing = getattr(lang.get("python"), "export_groups", None)
        assert fn_missing is None

"""Tests for TypeScript namespace/module block handling (TC-MT040-15).

Root findings (verified via parse probe):
  - `namespace Foo {}` / `export namespace Foo {}` parses as an
    `internal_module` node; the legacy `module Foo {}` keyword form parses
    as a separate top-level `module` node -- tree_helpers._MODULE_TYPES
    ["typescript"] was an empty set before this card, so packages tracking
    never recognized either.
  - A dotted namespace name (`namespace Outer.Inner2 {}`) parses as a single
    `nested_identifier` name field whose own text already contains the dots.
  - is_public() already excludes a non-exported declaration nested inside a
    namespace block correctly (its parent is `statement_block`, not
    `export_statement`/`program`/`module`) -- confirmed via this file's own
    negative-control test, no change was needed there.
"""
# sys.path is set by tests/conftest.py -- no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface
from extraction.tree_helpers import _MODULE_TYPES


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestModuleTypesDeclared:
    def test_internal_module_and_module_recognized(self):
        assert "internal_module" in _MODULE_TYPES["typescript"]
        assert "module" in _MODULE_TYPES["typescript"]


class TestNamespaceMemberExtraction:
    def test_exported_class_inside_namespace_gets_prefixed_namespace(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "ns.ts", (
            "export namespace Outer {\n"
            "  export class Shown {}\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Shown")
        assert entry["canonical_namespace"].split(".")[0] == "Outer"
        assert entry["class_import"].startswith("Outer.")
        assert entry["class_import"].endswith(".Shown")

    def test_non_exported_class_inside_namespace_stays_excluded(self, tmp_path):
        """Negative control: a class declared without `export` inside a
        namespace block must still be excluded by the existing is_public()
        visibility logic, the same as any other non-exported TS
        declaration."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "ns.ts", (
            "export namespace Outer {\n"
            "  class Hidden {}\n"
            "  export class Shown {}\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        names = {c["name"] for c in classes}
        assert "Shown" in names
        assert "Hidden" not in names

    def test_dotted_namespace_chain(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "ns.ts", (
            "export namespace Outer.Inner2 {\n"
            "  export class Shown {}\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Shown")
        assert entry["canonical_namespace"].startswith("Outer.Inner2")
        assert entry["class_import"].startswith("Outer.Inner2.")

    def test_class_outside_any_namespace_unaffected(self, tmp_path):
        """Negative control: a plain top-level class must NOT get any
        namespace-chain prefix (chain is empty for it)."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "plain.ts", "export class Plain {}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Plain")
        assert entry["canonical_namespace"] == "plain"
        assert entry["class_import"] == "plain.Plain"

    def test_bare_module_keyword_form_also_recognized(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "ns.ts", (
            "module Legacy {\n"
            "  export class Old {}\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Old")
        assert entry["canonical_namespace"].split(".")[0] == "Legacy"


class TestPackagesSetTracksNamespaces:
    def test_namespace_name_added_to_packages(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "ns.ts", (
            "export namespace Outer {\n"
            "  export class Shown {}\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        _classes, _claims, _files, packages, _report = extract_api_surface(
            parser, "typescript", pkg_root, tmp_path, "fake")
        assert "Outer" in packages

    def test_dotted_namespace_added_whole_to_packages(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "ns.ts", (
            "export namespace Outer.Inner2 {\n"
            "  export class Shown {}\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        _classes, _claims, _files, packages, _report = extract_api_surface(
            parser, "typescript", pkg_root, tmp_path, "fake")
        assert "Outer.Inner2" in packages

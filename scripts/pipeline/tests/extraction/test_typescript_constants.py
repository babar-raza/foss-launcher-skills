"""Tests for TypeScript constant extraction (TC-MT040-13): class-member
static/readonly fields, and module-level `export const` declarations.

Root findings (verified via parse probe):
  - `static`/`readonly` are direct modifier-TOKEN children of a
    public_field_definition node (not bundled into a "modifiers" node the
    way C#/Java express class-member modifiers).
  - A module-level `export const X = ...;` is neither a class, a class
    member, nor a func_types node (lexical_declaration was never collected
    by the existing top-level-function loop) -- previously invisible to
    extraction entirely regardless of visibility/documentation.
  - Arrow functions carry the same `parameters`/`return_type` field shape as
    a regular function declaration, so an `export const f = (a, b) => ...`
    initializer reuses _extract_method_params/_extract_return_type directly.
"""
# sys.path is set by tests/conftest.py -- no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestClassMemberStaticReadonly:
    def test_static_readonly_field_is_constant(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "c.ts", (
            "export class Constants {\n"
            "    static readonly VERSION: string = \"1.0\";\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Constants")
        prop = next(p for p in entry["properties"] if p["name"] == "VERSION")
        assert prop["is_static"] is True
        assert prop["writable"] is False
        assert prop["kind"] == "constant"
        assert prop["value"] == '"1.0"'

    def test_static_literal_without_readonly_is_still_constant(self, tmp_path):
        """(static AND readonly) OR (static AND literal initializer) --
        this covers the second branch of that OR."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "c.ts", "export class Constants {\n    static MAX = 100;\n}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Constants")
        prop = next(p for p in entry["properties"] if p["name"] == "MAX")
        assert prop["is_static"] is True
        assert prop["kind"] == "constant"
        assert prop["value"] == "100"

    def test_static_non_literal_initializer_is_not_constant(self, tmp_path):
        """static + a `new Foo()` initializer is neither readonly nor
        literal-ish -- must NOT be tagged kind: "constant" (it's a mutable
        static instance field, not a constant)."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "c.ts", (
            "export class Registry {\n"
            "    static instance = new Registry();\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Registry")
        prop = next(p for p in entry["properties"] if p["name"] == "instance")
        assert prop["is_static"] is True
        assert "kind" not in prop

    def test_plain_mutable_field_is_writable_true(self, tmp_path):
        """Regression proof: previously EVERY TS field was hardcoded
        writable: False regardless of static/readonly status."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "c.ts", "export class Counter {\n    count = 0;\n}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Counter")
        prop = next(p for p in entry["properties"] if p["name"] == "count")
        assert prop["writable"] is True
        assert "is_static" not in prop
        assert "kind" not in prop

    def test_readonly_non_static_field_stays_not_writable_not_constant(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "c.ts", "export class Named {\n    readonly name: string = \"x\";\n}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Named")
        prop = next(p for p in entry["properties"] if p["name"] == "name")
        assert prop["writable"] is False
        assert "is_static" not in prop
        assert "kind" not in prop


class TestModuleLevelConstants:
    def test_typed_const_extracted(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", (
            "/** The maximum page size. */\n"
            "export const MAX_PAGE_SIZE: number = 100;\n"
        ))
        parser = scout.get_parser("typescript")
        classes, claims, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "MAX_PAGE_SIZE")
        assert entry["kind"] == "constant"
        assert entry["type"] == "number"
        assert entry["value"] == "100"
        assert entry["doc"] == "The maximum page size."
        assert entry["bases"] == []
        assert entry["methods"] == []
        assert entry["properties"] == []
        assert "reachable" in entry
        assert any("api_field" == c["kind"] for c in claims if "MAX_PAGE_SIZE" in c["text"])

    def test_inferred_type_string(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", 'export const NAME = "hello";\n')
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "NAME")
        assert entry["type"] == "string"

    def test_inferred_type_boolean(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", "export const FLAG = true;\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "FLAG")
        assert entry["type"] == "boolean"

    def test_inferred_type_array(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", 'export const NAMES = ["a", "b"];\n')
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "NAMES")
        assert entry["type"] == "array"

    def test_arrow_function_const_becomes_function_entry(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", (
            "export const add = (a: number, b: number): number => a + b;\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "add")
        assert entry["kind"] == "function"
        assert entry["return_type"] == "number"
        pnames = {p["name"] for p in entry["params"]}
        assert pnames == {"a", "b"}

    def test_function_expression_const_becomes_function_entry(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", "export const run = function(x: number): void {};\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "run")
        assert entry["kind"] == "function"

    def test_multi_declarator_const_statement(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", "export const A = 1, B = 2;\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        names = {c["name"] for c in classes if c.get("kind") == "constant"}
        assert {"A", "B"} <= names

    def test_let_declaration_produces_no_constant_entry(self, tmp_path):
        """Negative control: `let`/`var` are mutable, not constants -- must
        be skipped entirely."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", "export let mutable = 5;\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        assert not any(c["name"] == "mutable" for c in classes)

    def test_non_exported_const_produces_no_entry(self, tmp_path):
        """Negative control: a non-exported top-level const is never
        reachable from outside the module -- out of scope."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", "const INTERNAL_ONLY = 1;\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        assert not any(c["name"] == "INTERNAL_ONLY" for c in classes)

    def test_destructuring_pattern_declarator_skipped(self, tmp_path):
        """Negative control: `export const { a, b } = obj;` has no single
        meaningful name -- out of scope, must not crash or fabricate."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", "export const { a, b } = someObj;\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        assert not any(c.get("kind") == "constant" for c in classes)


class TestConstantsExcludedFromClassCounting:
    """index.py's _is_public_api_entry() gate is OUT OF SCOPE for this card
    (not in the taskcard's file scope) -- see completion report. This test
    only proves the api_surface.json SHAPE (kind: "constant", distinct from
    every class kind string), which is the fact any future gate would key
    off of.
    """

    def test_constant_kind_is_distinct_from_every_class_kind(self, tmp_path):
        from extraction.tree_helpers import _CLASS_TYPES

        pkg_root = tmp_path / "src"
        _write(pkg_root / "consts.ts", "export const K = 1;\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "K")
        assert entry["kind"] == "constant"
        assert entry["kind"] not in _CLASS_TYPES["typescript"]

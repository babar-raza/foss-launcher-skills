"""Tests for TypeScript abstract-class extraction (TC-MT040-10).

Root finding (verified live via a tree-sitter-typescript parse probe, and
against real source under runs/.clone_cache/aspose_3d_typescript/src/, e.g.
formats/Exporter.ts's `export abstract class Exporter`): `export abstract
class X {}` parses as a DISTINCT `abstract_class_declaration` node type, not
`class_declaration` -- before this card, tree_helpers._CLASS_TYPES["typescript"]
listed only `class_declaration`/`interface_declaration`/`type_alias_declaration`/
`enum_declaration`, so every abstract TS class was invisible to extraction
entirely (not merely missing an is_abstract flag). Abstract method
signatures (`abstract load(p: string): void;`, no body) inside such a class
similarly parse as their own `abstract_method_signature` node type, distinct
from `method_signature` (interface/ambient bodies).
"""
# sys.path is set by tests/conftest.py -- no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface
from extraction.tree_helpers import _CLASS_TYPES, _FUNC_TYPES
from lib.reference_filter import _CLASS_KINDS_BY_PLATFORM as REF_FILTER_KINDS


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestTreeHelpersDeclareAbstractKinds:
    def test_class_types_includes_abstract_class_declaration(self):
        assert "abstract_class_declaration" in _CLASS_TYPES["typescript"]

    def test_func_types_includes_abstract_method_signature(self):
        assert "abstract_method_signature" in _FUNC_TYPES["typescript"]

    def test_reference_filter_kinds_include_abstract_class_declaration(self):
        assert "abstract_class_declaration" in REF_FILTER_KINDS["typescript"]

    def test_batch_reference_kinds_include_abstract_class_declaration(self):
        import batch_reference as br
        assert "abstract_class_declaration" in br._CLASS_KINDS_BY_PLATFORM["typescript"]


class TestAbstractClassExtraction:
    def test_abstract_class_is_extracted_and_flagged(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "exporter.ts", (
            "export abstract class Exporter {\n"
            "    abstract doExport(path: string): void;\n"
            "    concreteHelper(): void {}\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Exporter")
        assert entry["kind"] == "abstract_class_declaration"
        assert entry["is_abstract"] is True
        method_names = {m["name"] for m in entry["methods"]}
        assert "doExport" in method_names
        assert "concreteHelper" in method_names

    def test_non_abstract_class_has_no_is_abstract_key(self, tmp_path):
        """Negative control: a plain class must NOT carry is_abstract."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "plain.ts", "export class Plain {\n    foo(): void {}\n}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Plain")
        assert "is_abstract" not in entry

    def test_abstract_class_extends_and_implements_extracted(self, tmp_path):
        """_extract_bases must find the class_heritage child of an
        abstract_class_declaration node the same way it does for a plain
        class_declaration -- the grammar shape (class_heritage child) is
        identical for both (verified via parse probe)."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "exporter.ts", (
            "export abstract class Exporter extends Base implements IExport {\n"
            "    abstract doExport(): void;\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Exporter")
        assert "Base" in entry["bases"]
        assert "IExport" in entry["bases"]

    def test_abstract_class_doc_comment_extracted(self, tmp_path):
        """TC-MT040-12 interaction check: the class's own JSDoc must be
        reachable through doc_anchor()'s export_statement redirection."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "exporter.ts", (
            "/**\n"
            " * Base exporter for all formats.\n"
            " */\n"
            "export abstract class Exporter {\n"
            "    abstract doExport(): void;\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Exporter")
        assert entry["doc"] == "Base exporter for all formats."

    def test_abstract_method_appears_in_reference_filter_output(self, tmp_path):
        """End-to-end regression proof for the filter-chain half of this
        card: an abstract class must survive lib/reference_filter.py's
        two-step filter, not just api_surface.json extraction."""
        from lib.reference_filter import filter_api_surface

        pkg_root = tmp_path / "src"
        _write(pkg_root / "exporter.ts", (
            "export abstract class Exporter {\n"
            "    abstract doExport(): void;\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        filtered = filter_api_surface(classes, "typescript")
        assert any(c["name"] == "Exporter" for c in filtered)

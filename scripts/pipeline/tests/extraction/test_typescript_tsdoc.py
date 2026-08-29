"""Tests for TypeScript doc_anchor() + the full TSDoc block-tag parser
(TC-MT040-12), and their wiring into api_surface.py's method/function/
module-constant entries.

Root finding (verified via a tree-sitter-typescript parse probe): for
`export class X {}` / `export function f() {}` / `export const X = ...`,
the JSDoc `/** ... */` block precedes the WRAPPING `export_statement` node,
not the inner declaration node -- the inner node has no preceding named
sibling of its OWN (it is export_statement's first/only named child), so
the pre-existing plain prev_named_sibling walk in
api_surface._extract_doc_comment found nothing for every exported TS
declaration. doc_anchor() is the seam that redirects through the wrapper.
"""
# sys.path is set by tests/conftest.py -- no manual insert needed here.
import scout
from extraction.api_surface import _extract_doc_comment, extract_api_surface
from extraction.lang import typescript as ts
from extraction.tree_helpers import deprecated_marker, get_parser


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestDocAnchorRedirect:
    def test_exported_class_redirects_to_export_statement(self):
        parser = get_parser("typescript")
        src = b"/** Does a thing. */\nexport class Foo {}\n"
        tree = parser.parse(src)
        root = tree.root_node
        exp = next(c for c in root.children if c.type == "export_statement")
        decl = exp.child_by_field_name("declaration")
        assert decl.type == "class_declaration"
        anchor = ts.doc_anchor(decl)
        assert anchor.type == "export_statement"
        assert anchor == exp

    def test_export_default_class_redirects_too(self):
        parser = get_parser("typescript")
        src = b"/** Default doc. */\nexport default class Foo {}\n"
        tree = parser.parse(src)
        root = tree.root_node
        exp = next(c for c in root.children if c.type == "export_statement")
        decl = exp.child_by_field_name("declaration")
        anchor = ts.doc_anchor(decl)
        assert anchor == exp

    def test_non_exported_declaration_is_identity(self):
        parser = get_parser("typescript")
        src = b"/** Not attached the same way. */\nclass Foo {}\n"
        tree = parser.parse(src)
        root = tree.root_node
        decl = next(c for c in root.children if c.type == "class_declaration")
        anchor = ts.doc_anchor(decl)
        assert anchor == decl

    def test_class_member_is_identity_no_wrapper(self):
        """A class MEMBER's own doc comment is a plain sibling inside
        class_body -- no export_statement wrapper involved at that depth."""
        parser = get_parser("typescript")
        src = b"export class Foo {\n  /** Method doc. */\n  bar(): void {}\n}\n"
        tree = parser.parse(src)
        root = tree.root_node
        exp = next(c for c in root.children if c.type == "export_statement")
        cls = exp.child_by_field_name("declaration")
        body = next(c for c in cls.children if c.type == "class_body")
        method = next(c for c in body.children if c.type == "method_definition")
        anchor = ts.doc_anchor(method)
        assert anchor == method


class TestExtractDocCommentIntegration:
    """End-to-end proof through api_surface._extract_doc_comment (which
    calls doc_anchor() internally) -- this is the actual bug that was fixed,
    not just the seam function in isolation."""

    def test_exported_function_doc_now_reachable(self):
        parser = get_parser("typescript")
        src = b"/** Loads a document. */\nexport function load(): void {}\n"
        tree = parser.parse(src)
        root = tree.root_node
        exp = next(c for c in root.children if c.type == "export_statement")
        decl = exp.child_by_field_name("declaration")
        assert _extract_doc_comment(decl, "typescript") == "Loads a document."

    def test_exported_abstract_class_doc_now_reachable(self):
        parser = get_parser("typescript")
        src = b"/** Base exporter. */\nexport abstract class Exporter {}\n"
        tree = parser.parse(src)
        root = tree.root_node
        exp = next(c for c in root.children if c.type == "export_statement")
        decl = exp.child_by_field_name("declaration")
        assert _extract_doc_comment(decl, "typescript") == "Base exporter."


class TestParseDocBackwardCompat:
    def test_plain_summary_only_matches_pre_existing_regression_exactly(self):
        """Must stay byte-for-byte {"summary": ...} with no other keys --
        the pre-existing TestParseDoc.test_typescript_jsdoc regression test
        in test_language_adapters.py asserts this exact equality."""
        assert ts.parse_doc("/** Does a thing. */") == {"summary": "Does a thing."}

    def test_non_jsdoc_input_returns_empty_summary_only(self):
        assert ts.parse_doc("// not jsdoc") == {"summary": ""}


class TestParseDocBlockTags:
    RAW = (
        "/**\n"
        " * Loads a document.\n"
        " * @param path - the path to load\n"
        " * @param {LoadOptions} options - load options\n"
        " * @returns the loaded document\n"
        " * @remarks This is a longer remark.\n"
        " * @example\n"
        " * ```ts\n"
        " * const d = load(\"a.pdf\");\n"
        " * ```\n"
        " * @deprecated use loadAsync instead\n"
        " */"
    )

    def test_summary_stops_before_first_tag(self):
        assert ts.parse_doc(self.RAW)["summary"] == "Loads a document."

    def test_params_both_forms_parsed(self):
        params = ts.parse_doc(self.RAW)["params"]
        assert params["path"] == "the path to load"
        assert params["options"] == "load options"

    def test_returns_captured(self):
        assert ts.parse_doc(self.RAW)["returns"] == "the loaded document"

    def test_remarks_captured(self):
        assert ts.parse_doc(self.RAW)["remarks"] == "This is a longer remark."

    def test_example_fence_stripped(self):
        examples = ts.parse_doc(self.RAW)["examples"]
        assert examples == ['const d = load("a.pdf");']

    def test_deprecated_with_text(self):
        assert ts.parse_doc(self.RAW)["deprecated"] == "use loadAsync instead"

    def test_bare_deprecated_is_true(self):
        raw = "/**\n * Old thing.\n * @deprecated\n */"
        assert ts.parse_doc(raw)["deprecated"] is True

    def test_ignored_tags_do_not_leak_into_output(self):
        raw = "/**\n * Thing.\n * @throws Error if bad\n * @see Other\n * @since 1.0\n */"
        parsed = ts.parse_doc(raw)
        assert parsed == {"summary": "Thing."}

    def test_inline_link_with_hash_reduces_to_member(self):
        raw = "/**\n * See {@link Document#save} for details.\n */"
        assert ts.parse_doc(raw)["summary"] == "See save for details."

    def test_inline_link_without_hash_keeps_dotted_form(self):
        raw = "/**\n * See {@link Document.save} for details.\n */"
        assert ts.parse_doc(raw)["summary"] == "See Document.save for details."

    def test_param_with_default_value_bracket_form(self):
        raw = "/**\n * Thing.\n * @param [name=foo] the name\n */"
        params = ts.parse_doc(raw)["params"]
        assert params["name"] == "the name"


class TestApiSurfaceEnrichmentAdditive:
    """Proves the enrichment is purely additive on the real extraction
    pipeline: existing "doc"/"params" shape is preserved, new fields are
    added alongside."""

    def test_method_gets_param_doc_and_return_doc(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "exporter.ts", (
            "export abstract class Exporter {\n"
            "    /**\n"
            "     * Exports the scene.\n"
            "     * @param path - target path\n"
            "     * @returns nothing useful\n"
            "     */\n"
            "    abstract doExport(path: string): void;\n"
            "}\n"
        ))
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Exporter")
        method = next(m for m in entry["methods"] if m["name"] == "doExport")
        assert method["doc"] == "Exports the scene."
        assert method["return_doc"] == "nothing useful"
        param = next(p for p in method["params"] if p["name"] == "path")
        assert param["doc"] == "target path"

    def test_method_without_jsdoc_has_no_enrichment_keys(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "plain.ts", "export class Plain {\n    foo(): void {}\n}\n")
        parser = scout.get_parser("typescript")
        classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Plain")
        method = next(m for m in entry["methods"] if m["name"] == "foo")
        assert "return_doc" not in method
        assert "remarks" not in method
        assert "doc_examples" not in method


class TestOtherLanguagesDocExtractionUnchanged:
    """Negative control: Java/C# doc-comment extraction must be
    byte-for-byte unchanged -- doc_anchor() for those languages stays the
    identity function (only Go/TypeScript specialize it), and
    _extract_doc_comment's own javadoc/xml_doc branches were not touched."""

    def test_java_javadoc_summary_unchanged(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "Foo.java", (
            "/**\n"
            " * Represents a document.\n"
            " * More detail.\n"
            " */\n"
            "public class Foo {\n"
            "}\n"
        ))
        parser = scout.get_parser("java")
        classes, *_ = extract_api_surface(parser, "java", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Foo")
        assert entry["doc"] == "Represents a document."

    def test_csharp_xml_doc_summary_unchanged(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "Foo.cs", (
            "/// <summary>\n"
            "/// Gets the value.\n"
            "/// </summary>\n"
            "public class Foo {\n"
            "}\n"
        ))
        parser = scout.get_parser("csharp")
        classes, *_ = extract_api_surface(parser, "csharp", pkg_root, tmp_path, "fake")
        entry = next(c for c in classes if c["name"] == "Foo")
        assert entry["doc"] == "Gets the value."

    def test_deprecated_marker_typescript_unaffected(self):
        """deprecated_marker() has no TypeScript-specific comment lookup at
        all (only java/csharp branches exist) -- confirms no change was
        needed there per this card's own investigation instructions."""
        parser = get_parser("typescript")
        src = b"export class Foo {}\n"
        tree = parser.parse(src)
        root = tree.root_node
        exp = next(c for c in root.children if c.type == "export_statement")
        decl = exp.child_by_field_name("declaration")
        assert deprecated_marker(decl, "typescript") == (False, "")

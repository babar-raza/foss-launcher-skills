"""Go struct/interface embedding detection in _extract_bases (cells/go launch
hardening).

Confirmed live before this fix, against pdf/go's real source
(runs/.clone_cache/aspose_pdf_go/annotation_caret.go): `_extract_bases`
special-cased only `rust`/`python`; Go fell through to the generic
Java/C#-shaped fallback loop, which inspects a type_spec's *direct* children
only. A struct's type_spec has exactly two children — `name` (the type's own
identifier) and `type` (a `struct_type`/`interface_type` node) — so the
fallback loop, which only matches `superclass`/`base_list`/bare
`type_identifier` node TYPES, never descends into the struct/interface body
where embedded fields and embedded interfaces actually live. Real embedding
(e.g. `CaretAnnotation struct { drawingAnnotationBase }`) therefore always
produced `bases: []`.

The ONE case that *did* work by accident before this fix is the type-alias
idiom (`type AnnotationType int`), because its type_spec's `type` field is a
bare `type_identifier` ("int") — exactly the node type the generic fallback
loop already matches directly (the type's own name, "AnnotationType", also
matches and is appended, but api_surface.py's self-referential-bases filter
removes it afterward). This file's `test_enum_alias_idiom_unaffected*` tests
are the regression guard proving this pre-existing behavior is unchanged.

Real tree-sitter-go node shapes verified by live probe before writing this
fix: an embedded (anonymous) struct field's `field_declaration` has a `type`
field but NO `name` field — that absence is the detection signal. An
interface's embedded-interface reference is a `type_elem` child of
`interface_type` (sibling to `method_elem`).
"""
from __future__ import annotations

import pytest

from extraction.tree_helpers import _extract_bases, child_by_field, collect_nodes, get_parser

_GO_SOURCE = """
package annotations

type drawingAnnotationBase struct {
	Color Color
}

type CaretAnnotation struct {
	drawingAnnotationBase
	Symbol string
}

type PointerEmbedAnnotation struct {
	*drawingAnnotationBase
	Symbol string
}

type NamedFieldOnly struct {
	Color Color
	Symbol string
}

type AnnotationType int

type Reader interface {
	Read() (int, error)
}

type Writer interface {
	Write() error
}

type ReadWriteCloser interface {
	Reader
	Writer
	Close() error
}

type Annotation interface {
	Rect() Rectangle
}
"""


def _type_spec_named(root, name: str):
    for ts in collect_nodes(root, {"type_spec"}):
        name_node = child_by_field(ts, "name")
        if name_node is not None and name_node.text.decode("utf-8") == name:
            return ts
    raise AssertionError(f"type_spec {name!r} not found in parsed fixture")


@pytest.fixture(scope="module")
def parsed_root():
    parser = get_parser("go")
    return parser.parse(_GO_SOURCE.encode("utf-8")).root_node


def test_anonymous_embedded_field_populates_bases(parsed_root):
    cnode = _type_spec_named(parsed_root, "CaretAnnotation")
    bases = _extract_bases(cnode, "go")
    assert bases == ["drawingAnnotationBase"]


def test_pointer_embedded_field_populates_bases(parsed_root):
    cnode = _type_spec_named(parsed_root, "PointerEmbedAnnotation")
    bases = _extract_bases(cnode, "go")
    assert bases == ["drawingAnnotationBase"]


def test_named_fields_only_yield_no_bases(parsed_root):
    cnode = _type_spec_named(parsed_root, "NamedFieldOnly")
    bases = _extract_bases(cnode, "go")
    assert bases == []


def test_interface_embedding_populates_bases(parsed_root):
    cnode = _type_spec_named(parsed_root, "ReadWriteCloser")
    bases = _extract_bases(cnode, "go")
    assert bases == ["Reader", "Writer"]


def test_interface_with_no_embedding_yields_no_bases(parsed_root):
    """Regression guard: a plain method-only interface must not have its
    method names mistaken for embedded-interface bases."""
    cnode = _type_spec_named(parsed_root, "Annotation")
    bases = _extract_bases(cnode, "go")
    assert bases == []


def test_enum_alias_idiom_unaffected_by_embedding_fix(parsed_root):
    """The pre-existing type-alias-to-primitive idiom must be byte-identical
    to its behavior before this fix — this is the fix's own explicit
    regression control, not just a documentation claim."""
    cnode = _type_spec_named(parsed_root, "AnnotationType")
    bases = _extract_bases(cnode, "go")
    # api_surface.py's self-referential filter (bases = [b for b in bases if
    # b != cname]) runs downstream of _extract_bases, not inside it — so at
    # this layer both the type's own name and its underlying type are
    # present, exactly as before this fix.
    assert bases == ["AnnotationType", "int"]

"""Go interface method-signature extraction (cells/go launch hardening).

Confirmed live before this fix, against pdf/go's real source
(runs/.clone_cache/aspose_pdf_go/annotation.go): a Go `interface` type's
method set was never extracted anywhere in the pipeline. `_CLASS_TYPES["go"]`
admits `type_spec` generically (covering both struct and interface bodies),
but only `_extract_go_struct_fields` populated a type's body — interface
method signatures live inside `interface_type -> method_elem*`, a node shape
`collect_nodes(cnode, func_types)` never visits (func_types for Go is
`{function_declaration, method_declaration}`, neither of which appears
inside an interface body). The result: every Go interface in api_surface.json
had `methods: []` regardless of its real method count.

Real tree-sitter-go node shapes verified by live probe before writing this
fix: `method_elem` has fields `name` (field_identifier), `parameters`
(parameter_list), and an optional `result` (return-type node) — the same
field names `_extract_method_params`/`_extract_return_type` already read for
ordinary Go functions, reused here directly rather than duplicated.
"""
from __future__ import annotations

import pytest

from extraction.api_surface import _extract_go_interface_methods
from extraction.tree_helpers import child_by_field, collect_nodes, get_parser

_GO_SOURCE = """
package annotations

// Annotation describes an annotation on a page.
type Annotation interface {
	// Rect returns the annotation's rectangle.
	Rect() Rectangle
	SetColor(c Color)
	Flatten() error
	noReturnUnexported()
	visible() bool
}

type EmptyInterface interface {
}

type Rectangle struct {
	LLX float64
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


def test_interface_methods_are_extracted(parsed_root):
    cnode = _type_spec_named(parsed_root, "Annotation")
    methods, claims = _extract_go_interface_methods(cnode, "Annotation", "annotation.go", "pdf")

    names = {m["name"] for m in methods}
    # Unexported methods (lowercase-first) are excluded — not part of the
    # public API contract, matching the exported-identifier convention
    # already used for Go struct fields.
    assert names == {"Rect", "SetColor", "Flatten"}
    assert len(claims) == 3


def test_interface_method_return_types_and_params(parsed_root):
    cnode = _type_spec_named(parsed_root, "Annotation")
    methods, _claims = _extract_go_interface_methods(cnode, "Annotation", "annotation.go", "pdf")

    by_name = {m["name"]: m for m in methods}
    assert by_name["Rect"]["return_type"] == "Rectangle"
    assert by_name["Rect"]["params"] == []
    assert by_name["SetColor"]["return_type"] == ""
    assert [p["name"] for p in by_name["SetColor"]["params"]] == ["c"]
    assert by_name["Flatten"]["return_type"] == "error"


def test_interface_method_doc_comment_captured(parsed_root):
    cnode = _type_spec_named(parsed_root, "Annotation")
    methods, _claims = _extract_go_interface_methods(cnode, "Annotation", "annotation.go", "pdf")
    by_name = {m["name"]: m for m in methods}
    assert "rectangle" in by_name["Rect"]["doc"].lower()


def test_empty_interface_yields_no_methods(parsed_root):
    cnode = _type_spec_named(parsed_root, "EmptyInterface")
    methods, claims = _extract_go_interface_methods(cnode, "EmptyInterface", "annotation.go", "pdf")
    assert methods == []
    assert claims == []


def test_struct_type_spec_yields_no_interface_methods(parsed_root):
    """Regression guard: calling the new interface-method extractor on a
    struct type_spec must be a clean no-op (struct receiver methods are
    handled by the pre-existing _associate_go_methods path, not this one)."""
    cnode = _type_spec_named(parsed_root, "Rectangle")
    methods, claims = _extract_go_interface_methods(cnode, "Rectangle", "annotation.go", "pdf")
    assert methods == []
    assert claims == []

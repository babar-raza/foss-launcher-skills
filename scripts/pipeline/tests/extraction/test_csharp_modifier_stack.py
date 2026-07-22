"""HARDEN-A11: C# modifier-order regression guard (ST-014 bug class, C# analog).

A dedicated audit for this hardening effort found that unlike Java (whose
grammar bundles every annotation/keyword for one declaration into a SINGLE
`modifiers` node), C#'s tree-sitter grammar emits each modifier keyword
(`public`, `static`, `virtual`, ...) as its OWN separate sibling node, in
whatever order the source wrote them. `tree_helpers.is_public()` used to
return on the FIRST modifier sibling it found — exactly the "only checks the
nearest sibling in a sequence" shape that caused ST-014 in Python's decorator
handling. Any C# member written with the access modifier not listed first
(`static public void Foo()`, `virtual public string Bar { get; }` — both
syntactically legal, just non-idiomatic ordering) was silently classified as
non-public and dropped from the extracted API surface entirely.

Reproduced live before the fix (verified during this hardening session):
    is_public=True   'public void NormalOrderMethod() {}'
    is_public=False  'static public void SwappedOrderMethod() {}'   <- BUG
    is_public=True   '[Obsolete]\\n public void AttrThenPublic() {}'
    is_public=False  '[Obsolete]\\n static public void AttrThenSwapped...'  <- BUG
"""
from __future__ import annotations

import pytest

from extraction.tree_helpers import collect_nodes, get_parser, is_public

_CS_SOURCE = """
using System;

namespace Aspose.Words {
    public class Document {
        public void NormalOrderMethod() {}

        static public void SwappedOrderMethod() {}

        [Obsolete]
        public void AttrThenPublicMethod() {}

        [Obsolete]
        static public void AttrThenSwappedMethod() {}

        public static void NormalStaticMethod() {}

        virtual public string SwappedVirtualProperty { get; set; }

        private void PrivateMethod() {}

        static private void SwappedPrivateMethod() {}
    }
}
"""


def _method_named(root, name: str):
    for node in collect_nodes(root, {"method_declaration", "property_declaration"}):
        for child in node.children:
            if child.type == "identifier" and child.text.decode("utf-8") == name:
                return node
    raise AssertionError(f"member {name!r} not found in parsed fixture")


@pytest.fixture(scope="module")
def parsed_root():
    parser = get_parser("csharp")
    return parser.parse(_CS_SOURCE.encode("utf-8")).root_node


@pytest.mark.parametrize("name,expected", [
    ("NormalOrderMethod", True),
    ("SwappedOrderMethod", True),  # <- was False before the A11 fix
    ("AttrThenPublicMethod", True),
    ("AttrThenSwappedMethod", True),  # <- was False before the A11 fix
    ("NormalStaticMethod", True),
    ("SwappedVirtualProperty", True),  # <- was False before the A11 fix
    ("PrivateMethod", False),
    ("SwappedPrivateMethod", False),
])
def test_is_public_independent_of_modifier_order(parsed_root, name, expected):
    node = _method_named(parsed_root, name)
    assert is_public(node, "csharp") is expected, (
        f"{name}: modifier keyword ORDER must not change public/private "
        f"classification — every modifier sibling must be inspected, not "
        f"just the nearest one (ST-014 bug class)"
    )


def test_java_modifiers_still_bundle_correctly_unaffected_by_fix():
    """Regression guard: Java's grammar already bundles all
    annotations/keywords into one 'modifiers' node — confirm the A11 fix
    (which generalizes to accumulate ALL modifier/modifiers siblings) didn't
    change Java's already-correct behavior."""
    java_source = """
    public class Foo {
        @Override
        @Deprecated
        public void bar() {}

        private void baz() {}
    }
    """
    parser = get_parser("java")
    root = parser.parse(java_source.encode("utf-8")).root_node
    methods = collect_nodes(root, {"method_declaration"})
    names_public = {}
    for m in methods:
        for child in m.children:
            if child.type == "identifier":
                names_public[child.text.decode("utf-8")] = is_public(m, "java")
    assert names_public.get("bar") is True
    assert names_public.get("baz") is False

"""TC-MT007-01 (backlog G-40): interface-contract member synthesis.

Covers `synthesize_interface_members()` in `extraction/tree_helpers.py` --
the fix for the scout extractor missing standard BCL interface-contract
members (Dispose, MoveNext/Reset/Current, GetEnumerator, CompareTo) on C#
classes that implement a known interface without an explicit same-file
override (found live: `NodeEnumerator : IEnumerator<Node>,
IDocumentPositionListener`, words/net).

Fixture-based, matching this codebase's existing convention (no
`hypothesis` dependency) -- see test_shared_reference_guard.py for the
sibling pattern this mirrors.
"""
from __future__ import annotations

from extraction.tree_helpers import synthesize_interface_members


def _method(name, return_type="void", line=1):
    return {"name": name, "params": [], "return_type": return_type, "doc": "",
            "line": line, "is_constructor": False}


def _prop(name, type_="String", line=1):
    return {"name": name, "type": type_, "doc": "", "line": line, "writable": False}


class TestNonCSharpLanguagesAreNoOp:
    def test_python_never_synthesizes(self):
        new_methods, new_properties = synthesize_interface_members(
            ["IDisposable"], [], [], "python")
        assert new_methods == []
        assert new_properties == []

    def test_java_never_synthesizes(self):
        # Java's own IDisposable-equivalent (AutoCloseable) is a different
        # contract and out of scope for this C#-only fix.
        new_methods, new_properties = synthesize_interface_members(
            ["IDisposable"], [], [], "java")
        assert new_methods == []
        assert new_properties == []


class TestIDisposable:
    def test_synthesizes_dispose(self):
        new_methods, _ = synthesize_interface_members(["IDisposable"], [], [], "csharp")
        assert len(new_methods) == 1
        m = new_methods[0]
        assert m["name"] == "Dispose"
        assert m["return_type"] == "void"
        assert m["line"] is None
        assert m["origin"] == "interface_synthesized"

    def test_explicit_override_is_not_shadowed(self):
        existing = [_method("Dispose", line=42)]
        new_methods, _ = synthesize_interface_members(["IDisposable"], existing, [], "csharp")
        assert new_methods == []  # the real, explicit declaration is left alone


class TestGenericIEnumerator:
    def test_synthesizes_movenext_reset_current_and_dispose(self):
        # This is the exact real-world case: NodeEnumerator : IEnumerator<Node>
        new_methods, new_properties = synthesize_interface_members(
            ["IEnumerator<Node>", "IDocumentPositionListener"], [], [], "csharp")
        method_names = {m["name"] for m in new_methods}
        assert method_names == {"MoveNext", "Reset", "Dispose"}
        assert all(m["origin"] == "interface_synthesized" for m in new_methods)
        assert all(m["line"] is None for m in new_methods)
        assert len(new_properties) == 1
        assert new_properties[0]["name"] == "Current"
        assert new_properties[0]["origin"] == "interface_synthesized"
        # Real generic argument ('Node') substituted, not a raw 'T' placeholder.
        assert new_properties[0]["type"] == "Node"

    def test_unrelated_second_base_is_ignored(self):
        # IDocumentPositionListener is not in the synthesizable set -- confirm
        # it contributes nothing (no over-synthesis on an unrelated interface).
        new_methods, new_properties = synthesize_interface_members(
            ["IDocumentPositionListener"], [], [], "csharp")
        assert new_methods == []
        assert new_properties == []


class TestNonGenericIEnumeratorHasNoDispose:
    def test_non_generic_does_not_imply_idisposable(self):
        # Real .NET contract: IEnumerator (non-generic) does NOT extend
        # IDisposable -- only IEnumerator<T> does. Getting this wrong would
        # be a fabrication in the opposite direction from G-40's original bug.
        new_methods, new_properties = synthesize_interface_members(
            ["IEnumerator"], [], [], "csharp")
        method_names = {m["name"] for m in new_methods}
        assert method_names == {"MoveNext", "Reset"}
        assert "Dispose" not in method_names
        assert new_properties[0]["type"] == "object"


class TestIEnumerable:
    def test_generic_get_enumerator_return_type(self):
        new_methods, _ = synthesize_interface_members(["IEnumerable<Node>"], [], [], "csharp")
        assert len(new_methods) == 1
        assert new_methods[0]["name"] == "GetEnumerator"
        # Real generic argument substituted into the return type.
        assert new_methods[0]["return_type"] == "IEnumerator<Node>"

    def test_non_generic_get_enumerator_return_type(self):
        new_methods, _ = synthesize_interface_members(["IEnumerable"], [], [], "csharp")
        assert new_methods[0]["return_type"] == "IEnumerator"


class TestIComparable:
    def test_generic_and_non_generic_both_synthesize_compareto(self):
        for base in ("IComparable", "IComparable<Node>"):
            new_methods, _ = synthesize_interface_members([base], [], [], "csharp")
            assert [m["name"] for m in new_methods] == ["CompareTo"]
            assert new_methods[0]["return_type"] == "int"


class TestNoDoubleSynthesisAcrossOverlappingBases:
    def test_ienumerator_and_generic_ienumerator_both_listed(self):
        # A pathological (but not impossible) bases list naming both forms
        # must not produce duplicate MoveNext/Reset/Current entries.
        new_methods, new_properties = synthesize_interface_members(
            ["IEnumerator<Node>", "IEnumerator"], [], [], "csharp")
        method_names = [m["name"] for m in new_methods]
        assert len(method_names) == len(set(method_names))
        assert len(new_properties) == 1


class TestExplicitPropertyOverrideIsNotShadowed:
    def test_current_already_declared(self):
        existing_props = [_prop("Current", type_="Node", line=10)]
        _, new_properties = synthesize_interface_members(
            ["IEnumerator<Node>"], [], existing_props, "csharp")
        assert new_properties == []  # explicit Current is left alone


class TestUnknownInterfacesAreIgnored:
    def test_arbitrary_project_interface_no_synthesis(self):
        new_methods, new_properties = synthesize_interface_members(
            ["ISomeProjectSpecificInterface", "Node"], [], [], "csharp")
        assert new_methods == []
        assert new_properties == []

    def test_no_substring_matching(self):
        # A hypothetical interface merely containing "IComparable" as a
        # substring must not match -- exact-name matching only.
        new_methods, _ = synthesize_interface_members(
            ["IComparableThingy"], [], [], "csharp")
        assert new_methods == []

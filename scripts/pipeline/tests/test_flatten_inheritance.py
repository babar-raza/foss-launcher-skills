"""Tests for _flatten_inheritance() — inherited-member copy isolation.

Regression coverage for ST-013: _flatten_inheritance() previously appended
the SAME dict object reference from a parent's methods/properties into every
inheriting child, instead of copying. Any later mutation of one class's copy
of an inherited member (e.g. a doc backfill pass) silently corrupted the
parent's own entry and every other class that inherited the same member,
since they all pointed at the identical object. Confirmed via the 3d/java
truth audit (2026-07-14): ~700 FAIL instances traced to this exact mechanism
— an identical wrong doc string appeared on ~37 unrelated reference pages
because they all rendered the same shared, mutated dict.
"""
from extraction.api_surface import _flatten_inheritance


def _cls(name, *, methods=None, properties=None, bases=None, file="a.java"):
    """Build a minimal class entry dict for testing."""
    return {
        "name": name,
        "kind": "class_declaration",
        "visibility": "public",
        "file": file,
        "methods": methods or [],
        "properties": properties or [],
        "bases": bases or [],
    }


def _method(name, doc="", return_type="void", line=1, file=None, params=None):
    entry = {"name": name, "params": params or [], "return_type": return_type,
             "doc": doc, "line": line, "is_constructor": False}
    if file is not None:
        entry["file"] = file
    return entry


def _prop(name, doc="", ptype="String", line=1):
    return {"name": name, "type": ptype, "doc": doc, "line": line}


# ---------------------------------------------------------------------------
# Core isolation guarantee
# ---------------------------------------------------------------------------


def test_inherited_method_is_a_distinct_object_not_shared_reference():
    parent = _cls("Entity", methods=[_method("getBoundingBox", doc="Original doc.")])
    child = _cls("Sphere", bases=["Entity"])
    classes = [parent, child]
    _flatten_inheritance(classes)

    parent_method = parent["methods"][0]
    child_method = next(m for m in child["methods"] if m["name"] == "getBoundingBox")
    assert child_method is not parent_method, (
        "inherited method dict must be a copy, not the same object as the parent's"
    )


def test_mutating_child_inherited_method_does_not_corrupt_parent():
    parent = _cls("Entity", methods=[_method("getBoundingBox", doc="Original doc.")])
    child = _cls("BooleanOperator", bases=["Entity"])
    classes = [parent, child]
    _flatten_inheritance(classes)

    child_method = next(m for m in child["methods"] if m["name"] == "getBoundingBox")
    child_method["doc"] = "The first operand of the Boolean operator."  # simulated bad mutation

    parent_method = parent["methods"][0]
    assert parent_method["doc"] == "Original doc.", (
        "mutating one class's inherited copy must not change the parent's own entry"
    )


def test_mutating_one_childs_inherited_method_does_not_corrupt_sibling():
    parent = _cls("Entity", methods=[_method("getBoundingBox", doc="Original doc.")])
    child_a = _cls("BooleanOperator", bases=["Entity"])
    child_b = _cls("Sphere", bases=["Entity"])
    classes = [parent, child_a, child_b]
    _flatten_inheritance(classes)

    method_a = next(m for m in child_a["methods"] if m["name"] == "getBoundingBox")
    method_a["doc"] = "Corrupted by an unrelated later pass."

    method_b = next(m for m in child_b["methods"] if m["name"] == "getBoundingBox")
    assert method_b["doc"] == "Original doc.", (
        "corrupting one sibling's inherited copy must not leak to another sibling"
    )


def test_mutating_inherited_property_does_not_corrupt_parent_or_sibling():
    parent = _cls("Entity", properties=[_prop("name", doc="Original property doc.")])
    child_a = _cls("Dish", bases=["Entity"])
    child_b = _cls("Cylinder", bases=["Entity"])
    classes = [parent, child_a, child_b]
    _flatten_inheritance(classes)

    prop_a = next(p for p in child_a["properties"] if p["name"] == "name")
    prop_a["doc"] = "Height of the dish."  # simulated bad mutation

    parent_prop = parent["properties"][0]
    prop_b = next(p for p in child_b["properties"] if p["name"] == "name")
    assert parent_prop["doc"] == "Original property doc."
    assert prop_b["doc"] == "Original property doc."


# ---------------------------------------------------------------------------
# Grandparent chains and other existing behavior must still hold
# ---------------------------------------------------------------------------


def test_transitive_inheritance_still_flattens_grandparent_members():
    grandparent = _cls("A3DObject", methods=[_method("getProperties", doc="GP doc.")])
    parent = _cls("SceneObject", bases=["A3DObject"])
    child = _cls("Entity", bases=["SceneObject"])
    classes = [grandparent, parent, child]
    _flatten_inheritance(classes)

    names = {m["name"] for m in child["methods"]}
    assert "getProperties" in names


def test_child_own_definition_takes_precedence_over_inherited():
    parent = _cls("Entity", methods=[_method("getName", doc="Parent doc.")])
    child = _cls("Sphere", bases=["Entity"],
                 methods=[_method("getName", doc="Child override doc.")])
    classes = [parent, child]
    _flatten_inheritance(classes)

    names = [m for m in child["methods"] if m["name"] == "getName"]
    assert len(names) == 1
    assert names[0]["doc"] == "Child override doc."


def test_circular_inheritance_does_not_infinite_loop():
    a = _cls("A", bases=["B"], methods=[_method("foo", doc="A.foo")])
    b = _cls("B", bases=["A"], methods=[_method("bar", doc="B.bar")])
    classes = [a, b]
    _flatten_inheritance(classes)  # must terminate, not hang

    a_names = {m["name"] for m in a["methods"]}
    b_names = {m["name"] for m in b["methods"]}
    assert "foo" in a_names
    assert "bar" in b_names


# ---------------------------------------------------------------------------
# G-21: inherited-member file/line provenance
#
# api_surface.py now backfills a per-member "file" key at extraction time
# (before _flatten_inheritance runs), so the deep-copy _flatten_inheritance
# already performs must PRESERVE that member's own declaring file, not let
# consumers fall back to the class-level "file" (which is the subclass's own
# file, not the base class's). Confirmed live on words/net: 94/617 classes
# (every direct Field subclass) previously produced a bogus
# (FieldCreateDate.cs, line-106-from-Field.cs) citation for an inherited
# GetFieldCode method.
# ---------------------------------------------------------------------------


def test_inherited_method_preserves_its_own_declaring_file():
    parent = _cls("Field", file="Field.cs",
                   methods=[_method("GetFieldCode", file="Field.cs", line=106)])
    child = _cls("FieldCreateDate", file="FieldCreateDate.cs", bases=["Field"])
    classes = [parent, child]
    _flatten_inheritance(classes)

    inherited = next(m for m in child["methods"] if m["name"] == "GetFieldCode")
    assert inherited["file"] == "Field.cs", (
        "an inherited member must carry its own declaring file, not silently "
        "default to (or lose) it in favor of the subclass's class-level file"
    )
    assert inherited["line"] == 106
    # The class-level file is still the subclass's own — unchanged, correct.
    assert child["file"] == "FieldCreateDate.cs"


def test_inherited_method_missing_file_key_does_not_crash():
    """Older/synthetic fixtures with no "file" key at all must not raise --
    _flatten_inheritance only needs to preserve whatever keys are present."""
    parent = _cls("Entity", methods=[_method("getName", doc="d")])
    child = _cls("Sphere", bases=["Entity"])
    classes = [parent, child]
    _flatten_inheritance(classes)  # must not raise

    inherited = next(m for m in child["methods"] if m["name"] == "getName")
    assert "file" not in inherited


# ---------------------------------------------------------------------------
# G-21 (compounding bug, same function): overload-preserving dedup
#
# Dedup was previously by name alone, silently dropping real overloads
# sharing a name with different parameter types. Confirmed live: Node.cs
# declares both ToString(SaveFormat) and ToString(SaveOptions); flattening
# kept only whichever the parent's own methods list happened to list first,
# for every one of dozens of Node subclasses.
# ---------------------------------------------------------------------------


def test_overloads_with_different_param_types_are_both_inherited():
    parent = _cls("Node", methods=[
        _method("ToString", line=974, params=[{"name": "format", "type": "SaveFormat"}]),
        _method("ToString", line=985, params=[{"name": "options", "type": "SaveOptions"}]),
    ])
    child = _cls("Run", bases=["Node"])
    classes = [parent, child]
    _flatten_inheritance(classes)

    to_string_overloads = [m for m in child["methods"] if m["name"] == "ToString"]
    assert len(to_string_overloads) == 2, (
        "both ToString(SaveFormat) and ToString(SaveOptions) must be inherited "
        "-- name-only dedup previously silently dropped one"
    )
    param_types = {tuple(p["type"] for p in m["params"]) for m in to_string_overloads}
    assert param_types == {("SaveFormat",), ("SaveOptions",)}


def test_genuine_duplicate_same_signature_is_still_deduped():
    """A method reached via two inheritance paths (diamond-shaped bases, or
    simply re-processed) with an IDENTICAL signature must still collapse to
    one entry -- the fix changes the dedup KEY, not whether dedup happens."""
    grandparent = _cls("Base", methods=[
        _method("Compute", line=10, params=[{"name": "x", "type": "int"}]),
    ])
    parent_a = _cls("MidA", bases=["Base"])
    parent_b = _cls("MidB", bases=["Base"])
    child = _cls("Combined", bases=["MidA", "MidB"])
    classes = [grandparent, parent_a, parent_b, child]
    _flatten_inheritance(classes)

    computes = [m for m in child["methods"] if m["name"] == "Compute"]
    assert len(computes) == 1, (
        "identical-signature method reached via two base paths must not duplicate"
    )


def test_child_own_overload_takes_precedence_but_other_overloads_still_inherit():
    parent = _cls("Node", methods=[
        _method("Foo", doc="parent int", params=[{"name": "x", "type": "int"}]),
        _method("Foo", doc="parent string", params=[{"name": "s", "type": "string"}]),
    ])
    child = _cls("Leaf", bases=["Node"], methods=[
        _method("Foo", doc="child override int", params=[{"name": "x", "type": "int"}]),
    ])
    classes = [parent, child]
    _flatten_inheritance(classes)

    foos = [m for m in child["methods"] if m["name"] == "Foo"]
    assert len(foos) == 2
    int_overload = next(m for m in foos if m["params"][0]["type"] == "int")
    string_overload = next(m for m in foos if m["params"][0]["type"] == "string")
    assert int_overload["doc"] == "child override int", (
        "child's own Foo(int) must win over the parent's Foo(int), unchanged behavior"
    )
    assert string_overload["doc"] == "parent string", (
        "parent's Foo(string) has no child override and must still be inherited"
    )

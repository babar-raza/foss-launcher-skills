"""Tests for consolidate_classes() — partial-class merge, stub discard,
namespace disambiguation, enum dedup, and fallback merge.

Covers the six consolidation categories defined in
extraction/api_surface.py:consolidate_classes().
"""
from pathlib import Path

import pytest

from extraction.api_surface import consolidate_classes, _merge_members


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cls(name, *, visibility="public", kind="class_declaration",
         methods=None, properties=None, bases=None, file="a.cs",
         namespace=None, is_partial=False, enum_members=None,
         class_import=None):
    """Build a minimal class entry dict for testing."""
    entry = {
        "name": name,
        "kind": kind,
        "visibility": visibility,
        "file": file,
        "methods": methods or [],
        "properties": properties or [],
        "bases": bases or [],
    }
    if namespace:
        entry["canonical_namespace"] = namespace
        entry["class_import"] = class_import or f"{namespace}.{name}"
    elif class_import:
        entry["class_import"] = class_import
    if is_partial:
        entry["is_partial"] = True
    if enum_members is not None:
        entry["enum_members"] = enum_members
    return entry


def _method(name, params=None):
    return {"name": name, "params": params or [], "return_type": "", "doc": "", "line": 1}


def _prop(name):
    return {"name": name, "type": "string", "doc": "", "line": 1}


# ---------------------------------------------------------------------------
# Category 1: True partial class merge
# ---------------------------------------------------------------------------

class TestPartialClassMerge:

    def test_two_partials_same_namespace_merge(self):
        classes = [
            _cls("Document", namespace="Aspose.Pdf", file="Document.cs",
                 is_partial=True,
                 methods=[_method("Save"), _method("Open")],
                 properties=[_prop("Pages")],
                 bases=["IDisposable"]),
            _cls("Document", namespace="Aspose.Pdf", file="Document.Hocr.cs",
                 is_partial=True,
                 methods=[_method("ConvertToHtml")],
                 properties=[_prop("HocrContent")]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1
        doc = result[0]
        method_names = {m["name"] for m in doc["methods"]}
        assert method_names == {"Save", "Open", "ConvertToHtml"}
        prop_names = {p["name"] for p in doc["properties"]}
        assert prop_names == {"Pages", "HocrContent"}
        assert doc["bases"] == ["IDisposable"]
        assert "_merged_files" in doc

    def test_three_way_partial_merge(self):
        classes = [
            _cls("Page", namespace="Aspose.Pdf", file="Page.cs",
                 is_partial=True,
                 methods=[_method("Save")],
                 properties=[_prop("Number")],
                 bases=["IDisposable"]),
            _cls("Page", namespace="Aspose.Pdf", file="Page.NewMembers.cs",
                 is_partial=True,
                 methods=[_method("AddStamp"), _method("AddImage")]),
            _cls("Page", namespace="Aspose.Pdf", file="Page.CalculateContentBBox.cs",
                 is_partial=True,
                 methods=[_method("CalculateContentBBox")]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1
        method_names = {m["name"] for m in result[0]["methods"]}
        assert method_names == {"Save", "AddStamp", "AddImage", "CalculateContentBBox"}
        assert result[0]["bases"] == ["IDisposable"]

    def test_dedup_overlapping_methods_in_partials(self):
        classes = [
            _cls("Widget", namespace="Ns", is_partial=True,
                 methods=[_method("Foo"), _method("Bar")]),
            _cls("Widget", namespace="Ns", is_partial=True, file="b.cs",
                 methods=[_method("Foo"), _method("Baz")]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1
        method_names = [m["name"] for m in result[0]["methods"]]
        assert sorted(method_names) == ["Bar", "Baz", "Foo"]

    def test_partial_prefers_doc_from_larger_fragment(self):
        classes = [
            _cls("Thing", namespace="Ns", is_partial=True, file="small.cs",
                 methods=[_method("A")]),
            _cls("Thing", namespace="Ns", is_partial=True, file="big.cs",
                 methods=[_method("B"), _method("C"), _method("D")]),
        ]
        classes[0]["doc"] = ""
        classes[1]["doc"] = "The main Thing class."
        result = consolidate_classes(classes, "csharp")
        assert result[0]["doc"] == "The main Thing class."


# ---------------------------------------------------------------------------
# Category 2: Stub vs full (discard stub)
# ---------------------------------------------------------------------------

class TestStubDiscard:

    def test_annotation_stub_discarded(self):
        """Stubs from AnnotationSelector.cs (no bases, 1 method) should be discarded."""
        classes = [
            _cls("CaretAnnotation", namespace="Aspose.Pdf.Annotations",
                 file="Annotation.cs",
                 methods=[_method("Accept"), _method("GetRectangle")],
                 properties=[_prop("Frame")],
                 bases=["MarkupAnnotation"]),
            _cls("CaretAnnotation", namespace="Aspose.Pdf.Annotations",
                 file="AnnotationSelector.cs",
                 methods=[_method("Accept")],
                 bases=[]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1
        assert result[0]["file"] == "Annotation.cs"
        assert result[0]["bases"] == ["MarkupAnnotation"]

    def test_stub_with_no_bases_discarded_over_full(self):
        classes = [
            _cls("Foo", namespace="Ns", bases=["BaseClass"],
                 methods=[_method("A"), _method("B")]),
            _cls("Foo", namespace="Ns", bases=[], file="stub.cs",
                 methods=[_method("A")]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1
        assert result[0]["bases"] == ["BaseClass"]


# ---------------------------------------------------------------------------
# Category 3: Compat shim discard
# ---------------------------------------------------------------------------

class TestCompatShimDiscard:

    def test_shim_inheriting_same_name_discarded(self):
        """Shim in SAME namespace whose bases reference the other by name."""
        classes = [
            _cls("Operator", namespace="Aspose.Pdf", file="Operator.cs",
                 methods=[_method("Execute")]),
            _cls("Operator", namespace="Aspose.Pdf", file="OperatorsAlias.cs",
                 bases=["Operator"]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1
        assert result[0]["file"] == "Operator.cs"

    def test_shim_different_namespace_kept(self):
        """Shim in DIFFERENT namespace kept (genuinely distinct types)."""
        classes = [
            _cls("Operator", namespace="Aspose.Pdf", file="Operator.cs",
                 methods=[_method("Execute")]),
            _cls("Operator", namespace="Aspose.Pdf.Content", file="OperatorsAlias.cs",
                 bases=["Aspose.Pdf.Operator"]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Category 4: Different namespace (keep both)
# ---------------------------------------------------------------------------

class TestDifferentNamespace:

    def test_same_name_different_namespace_kept(self):
        classes = [
            _cls("Color", namespace="Aspose.Pdf",
                 methods=[_method("FromRgb")],
                 properties=[_prop("R"), _prop("G"), _prop("B")]),
            _cls("Color", namespace="Aspose.Pdf.Drawing", file="Drawing/Graph.cs",
                 methods=[_method("Parse")],
                 properties=[_prop("Pattern")]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 2
        imports = {r.get("class_import") for r in result}
        assert imports == {"Aspose.Pdf.Color", "Aspose.Pdf.Drawing.Color"}

    def test_three_namespaces_all_kept(self):
        classes = [
            _cls("Stamp", namespace="Aspose.Pdf.Facades", file="Facades/Stamp.cs"),
            _cls("Stamp", namespace="Aspose.Pdf", file="Stamp.cs"),
            _cls("Stamp", namespace="Aspose.Pdf.Stamps", file="Stamps/Stamp.cs"),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Category 5: Identical enum dedup
# ---------------------------------------------------------------------------

class TestEnumDedup:

    def test_identical_enums_deduped(self):
        classes = [
            _cls("WordWrapMode", kind="enum_declaration", namespace="Aspose.Pdf.Text",
                 file="TextFormattingOptions.cs",
                 enum_members=[{"name": "NoWrap"}, {"name": "ByWords"}]),
            _cls("WordWrapMode", kind="enum_declaration", namespace="Aspose.Pdf.Text",
                 file="PdfFileMend.cs",
                 enum_members=[{"name": "NoWrap"}, {"name": "ByWords"}]),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1

    def test_triple_enum_deduped(self):
        classes = [
            _cls("NoCharAction", kind="enum_declaration", namespace="Ns"),
            _cls("NoCharAction", kind="enum_declaration", namespace="Ns", file="b.cs"),
            _cls("NoCharAction", kind="enum_declaration", namespace="Ns", file="c.cs"),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 1

    def test_enums_different_namespace_kept(self):
        classes = [
            _cls("FieldType", kind="enum_declaration", namespace="Aspose.Pdf.Facades"),
            _cls("FieldType", kind="enum_declaration", namespace="Aspose.Pdf.Forms",
                 file="Forms/FieldType.cs"),
        ]
        result = consolidate_classes(classes, "csharp")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Category 6: Fallback (no namespace, same visibility)
# ---------------------------------------------------------------------------

class TestFallbackMerge:

    def test_no_namespace_same_visibility_merges(self):
        classes = [
            _cls("Widget", methods=[_method("A")]),
            _cls("Widget", file="b.cs", methods=[_method("B")]),
        ]
        result = consolidate_classes(classes, "python")
        assert len(result) == 1
        method_names = {m["name"] for m in result[0]["methods"]}
        assert method_names == {"A", "B"}


# ---------------------------------------------------------------------------
# Cross-language: no-op for clean inputs
# ---------------------------------------------------------------------------

class TestCrossLanguageNoop:

    def test_no_duplicates_passthrough(self):
        classes = [
            _cls("Alpha", methods=[_method("X")]),
            _cls("Beta", methods=[_method("Y")]),
        ]
        result = consolidate_classes(classes, "python")
        assert len(result) == 2
        assert result[0]["name"] == "Alpha"
        assert result[1]["name"] == "Beta"

    def test_empty_list(self):
        result = consolidate_classes([], "csharp")
        assert result == []


# ---------------------------------------------------------------------------
# _merge_members unit tests
# ---------------------------------------------------------------------------

class TestMergeMembers:

    def test_merge_adds_new_methods(self):
        target = {"methods": [_method("A")], "properties": [], "bases": []}
        source = {"methods": [_method("B")], "properties": [_prop("X")], "bases": ["Base"]}
        _merge_members(target, source)
        assert len(target["methods"]) == 2
        assert len(target["properties"]) == 1
        assert target["bases"] == ["Base"]

    def test_merge_deduplicates_methods(self):
        target = {"methods": [_method("A")], "properties": [], "bases": []}
        source = {"methods": [_method("A")], "properties": [], "bases": []}
        _merge_members(target, source)
        assert len(target["methods"]) == 1

    def test_merge_tracks_provenance(self):
        target = {"methods": [], "properties": [], "bases": [], "file": "a.cs"}
        source = {"methods": [_method("X")], "properties": [], "bases": [], "file": "b.cs"}
        _merge_members(target, source)
        assert target["_merged_files"] == ["a.cs", "b.cs"]

    def test_merge_doc_preference(self):
        target = {"methods": [], "properties": [], "bases": [], "doc": ""}
        source = {"methods": [], "properties": [], "bases": [], "doc": "Good doc"}
        _merge_members(target, source)
        assert target["doc"] == "Good doc"

    def test_merge_unions_modifiers(self):
        target = {"methods": [], "properties": [], "bases": []}
        source = {"methods": [], "properties": [], "bases": [], "is_partial": True}
        _merge_members(target, source)
        assert target.get("is_partial") is True

"""Tests for batch_reference.py — platform scope rules, idempotency, and CLI.

Covers (S-62 Healing Sprint — F-1 + F-6):
  - Java kind filter: class_declaration / interface_declaration / enum_declaration
  - .NET kind filter: class_declaration / interface_declaration / enum_declaration / struct_declaration
  - C++ kind filter: class_specifier / enum_specifier
  - Python kind filter: class_definition (including enum subclasses via bases)
  - Idempotency: existing page → SKIP count increments
  - --limit N: only first N candidates processed
  - Hard stop: missing api_surface.json → SystemExit
  - I-prefix exclusion: IShape skipped for cpp, included for java/net
  - Java internal class filter: _JAVA_INTERNAL_CLASSES excluded from Java candidates (SEA-T3)
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import batch_reference as _br
from batch_reference import (_passes_platform_scope, _apply_kind_filter, _is_enum, run,
                              _build_erc_index, _build_page, check_member_doc_coverage,
                              _derive_group_key, _normalize_doc_for_index)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_api_surface(tmp_path: Path, entries: list[dict], family: str = "fake",
                      platform: str = "net") -> Path:
    """Write a synthetic api_surface.json and minimal model.yaml; return the path."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
    (merged / "model.yaml").write_text(
        yaml.safe_dump({"stale_since": None, "version": "1.0.0"}),
        encoding="utf-8",
    )
    return merged / "api_surface.json"


# ---------------------------------------------------------------------------
# Path isolation (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    _br.configure(repo_root=tmp_path)
    yield
    _br.configure()


# ---------------------------------------------------------------------------
# Kind filter tests (F-6 regression)
# ---------------------------------------------------------------------------

class TestKindFilterJava:
    ENTRIES = [
        {"name": "Foo", "kind": "class_declaration", "methods": [], "properties": []},
        {"name": "IBar", "kind": "interface_declaration", "methods": [], "properties": []},
        {"name": "MyEnum", "kind": "enum_declaration", "methods": [], "properties": []},
        {"name": "Annotation", "kind": "annotation_type_declaration", "methods": [], "properties": []},
        {"name": "BadClass", "kind": "class", "methods": [], "properties": []},  # old/wrong kind
    ]

    def test_class_declaration_passes(self):
        assert _passes_platform_scope({"name": "Foo", "kind": "class_declaration"}, "java")

    def test_interface_declaration_passes(self):
        assert _passes_platform_scope({"name": "IBar", "kind": "interface_declaration"}, "java")

    def test_enum_declaration_passes(self):
        assert _passes_platform_scope({"name": "MyEnum", "kind": "enum_declaration"}, "java")

    def test_simplified_kind_name_does_not_pass(self):
        """The old simplified name 'class' must NOT be treated as a valid kind."""
        assert not _passes_platform_scope({"name": "BadClass", "kind": "class"}, "java")

    def test_all_valid_java_kinds_included(self):
        valid = [e for e in self.ENTRIES if _passes_platform_scope(e, "java")]
        names = {e["name"] for e in valid}
        assert "Foo" in names
        assert "IBar" in names
        assert "MyEnum" in names
        assert "BadClass" not in names


class TestKindFilterNet:
    def test_class_declaration_passes(self):
        assert _passes_platform_scope({"name": "Foo", "kind": "class_declaration"}, "net")

    def test_struct_declaration_passes(self):
        assert _passes_platform_scope({"name": "Point", "kind": "struct_declaration"}, "net")

    def test_enum_declaration_passes(self):
        assert _passes_platform_scope({"name": "Color", "kind": "enum_declaration"}, "net")

    def test_interface_declaration_passes(self):
        assert _passes_platform_scope({"name": "IShape", "kind": "interface_declaration"}, "net")

    def test_simplified_enum_does_not_pass(self):
        assert not _passes_platform_scope({"name": "Color", "kind": "enum"}, "net")

    def test_simplified_struct_does_not_pass(self):
        assert not _passes_platform_scope({"name": "Point", "kind": "struct"}, "net")


class TestKindFilterCpp:
    def test_class_specifier_passes(self):
        assert _passes_platform_scope({"name": "Foo", "kind": "class_specifier"}, "cpp")

    def test_enum_specifier_passes(self):
        assert _passes_platform_scope({"name": "MyEnum", "kind": "enum_specifier"}, "cpp")

    def test_class_declaration_does_not_pass_for_cpp(self):
        assert not _passes_platform_scope({"name": "Foo", "kind": "class_declaration"}, "cpp")


class TestKindFilterPython:
    def test_class_definition_passes(self):
        assert _passes_platform_scope({"name": "Foo", "kind": "class_definition"}, "python")

    def test_class_definition_with_enum_base_passes(self):
        """Python enums are class_definition nodes — they should still pass the filter."""
        assert _passes_platform_scope(
            {"name": "MyEnum", "kind": "class_definition", "bases": ["IntEnum"]}, "python"
        )

    def test_simplified_class_kind_does_not_pass(self):
        assert not _passes_platform_scope({"name": "Foo", "kind": "class"}, "python")

    def test_is_enum_detected_via_base(self):
        assert _is_enum(
            {"name": "MyEnum", "kind": "class_definition", "bases": ["Enum"]}, "python"
        )

    def test_is_enum_not_detected_via_enum_members_alone(self):
        """FIX-09: enum_members heuristic removed — only base class or kind qualifies."""
        assert not _is_enum(
            {"name": "MyEnum", "kind": "class_definition", "enum_members": ["A", "B"]}, "python"
        )

    def test_regular_class_not_enum(self):
        assert not _is_enum({"name": "Foo", "kind": "class_definition"}, "python")


# ---------------------------------------------------------------------------
# I-prefix exclusion (F-1/F-6)
# ---------------------------------------------------------------------------

class TestIPrefixExclusion:
    def test_ishape_excluded_for_cpp(self):
        assert not _passes_platform_scope({"name": "IShape", "kind": "class_specifier"}, "cpp")

    def test_ishape_included_for_java(self):
        assert _passes_platform_scope({"name": "IShape", "kind": "interface_declaration"}, "java")

    def test_ishape_included_for_net(self):
        assert _passes_platform_scope({"name": "IShape", "kind": "interface_declaration"}, "net")

    def test_ishape_excluded_for_python(self):
        assert not _passes_platform_scope({"name": "IShape", "kind": "class_definition"}, "python")


# ---------------------------------------------------------------------------
# Idempotency (F-1)
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_existing_page_is_skipped(self, tmp_path):
        entries = [
            {"name": "Foo", "kind": "class_declaration", "methods": [], "properties": []},
            {"name": "Bar", "kind": "class_declaration", "methods": [], "properties": []},
        ]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")

        # Pre-create one page
        existing_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "slides" / "net"
        existing_dir.mkdir(parents=True)
        (existing_dir / "Foo.md").write_text("existing", encoding="utf-8")

        result = run("slides", "net")

        assert result["skipped"] == 1
        assert result["generated"] == 1
        # Existing file must not be overwritten
        assert (existing_dir / "Foo.md").read_text(encoding="utf-8") == "existing"

    def test_rerun_on_fully_populated_yields_zero_generated(self, tmp_path):
        entries = [
            {"name": "Alpha", "kind": "class_declaration", "methods": [], "properties": []},
        ]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")
        page_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "slides" / "net"
        page_dir.mkdir(parents=True)
        (page_dir / "Alpha.md").write_text("existing", encoding="utf-8")

        result = run("slides", "net")

        assert result["generated"] == 0
        assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# --limit (F-1)
# ---------------------------------------------------------------------------

class TestLimit:
    def test_limit_respected(self, tmp_path):
        entries = [
            {"name": f"Class{i}", "kind": "class_declaration", "methods": [], "properties": []}
            for i in range(10)
        ]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")

        result = run("slides", "net", limit=3)

        assert result["generated"] == 3

    def test_limit_zero_raises_system_exit(self, tmp_path):
        entries = [{"name": "Foo", "kind": "class_declaration", "methods": [], "properties": []}]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")

        with pytest.raises(SystemExit):
            run("slides", "net", limit=0)


# ---------------------------------------------------------------------------
# Hard stop: missing api_surface.json (F-1)
# ---------------------------------------------------------------------------

class TestHardStop:
    def test_missing_api_surface_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            run("nonexistent", "net")

    def test_stale_knowledge_exits(self, tmp_path):
        entries = [{"name": "Foo", "kind": "class_declaration", "methods": [], "properties": []}]
        merged = tmp_path / "knowledge" / "slides" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
        (merged / "model.yaml").write_text(
            yaml.safe_dump({"stale_since": "2026-03-01", "version": "1.0.0"}),
            encoding="utf-8",
        )

        with pytest.raises(SystemExit):
            run("slides", "net")


# ---------------------------------------------------------------------------
# --kind filter (F-1)
# ---------------------------------------------------------------------------

class TestKindArgFilter:
    def test_kind_enum_only_returns_enums(self, tmp_path):
        entries = [
            {"name": "MyClass", "kind": "class_declaration", "methods": [], "properties": []},
            {"name": "MyEnum", "kind": "enum_declaration", "methods": [], "properties": [], "members": []},
        ]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")

        result = run("slides", "net", kind_arg="enum")

        assert result["generated"] == 1

    def test_kind_class_excludes_enums(self, tmp_path):
        entries = [
            {"name": "MyClass", "kind": "class_declaration", "methods": [], "properties": []},
            {"name": "MyEnum", "kind": "enum_declaration", "methods": [], "properties": []},
        ]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")

        result = run("slides", "net", kind_arg="class")

        assert result["generated"] == 1


# ---------------------------------------------------------------------------
# ERC-* claim index and _build_page fallback (KC-04)
# ---------------------------------------------------------------------------

def _make_claims_file(tmp_path: Path, claims: list[dict], family: str = "test", platform: str = "net") -> Path:
    """Write claims.json to a temp knowledge/ dir. Returns the knowledge root Path."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    return tmp_path / "knowledge"


class TestBuildErcIndex:
    """_build_erc_index() returns a class_name → best ERC claim dict."""

    def test_extracts_class_from_the_prefix(self, tmp_path):
        claims = [{"claim_id": "ERC-001", "kind": "api", "text": "The AutoFilter class handles filtering.", "confidence": 0.95}]
        _make_claims_file(tmp_path, claims)
        index = _build_erc_index("test", "net")
        assert "AutoFilter" in index
        assert index["AutoFilter"]["claim_id"] == "ERC-001"

    def test_only_erc_claims_included(self, tmp_path):
        claims = [
            {"claim_id": "ERC-001", "kind": "api", "text": "The Widget class.", "confidence": 0.9},
            {"claim_id": "CLM-001", "kind": "api_method", "text": "Widget.do() -> void", "confidence": 1.0},
        ]
        _make_claims_file(tmp_path, claims)
        index = _build_erc_index("test", "net")
        assert "Widget" in index
        assert index["Widget"]["claim_id"] == "ERC-001"

    def test_highest_confidence_wins(self, tmp_path):
        claims = [
            {"claim_id": "ERC-001", "kind": "api", "text": "The Widget class.", "confidence": 0.7},
            {"claim_id": "ERC-002", "kind": "api", "text": "The Widget class provides more.", "confidence": 0.95},
        ]
        _make_claims_file(tmp_path, claims)
        index = _build_erc_index("test", "net")
        assert index["Widget"]["claim_id"] == "ERC-002"

    def test_empty_claims_returns_empty_index(self, tmp_path):
        _make_claims_file(tmp_path, [])
        index = _build_erc_index("test", "net")
        assert index == {}

    def test_missing_claims_file_returns_empty_index(self, tmp_path):
        _br.configure(knowledge_root=tmp_path / "no_such_dir")
        index = _build_erc_index("test", "net")
        assert index == {}


class TestBuildPageErcFallback:
    """_build_page() uses ERC claim text and ID when doc is empty."""

    def _entry(self, name: str, doc: str = "", methods: list | None = None) -> dict:
        return {"name": name, "kind": "class_declaration", "doc": doc,
                "methods": methods or [], "properties": [], "bases": []}

    def test_erc_text_used_when_doc_empty(self):
        entry = self._entry("AutoFilter", doc="")
        erc_index = {"AutoFilter": {"claim_id": "ERC-001", "kind": "api",
                                     "text": "The AutoFilter class handles worksheet filtering.",
                                     "confidence": 0.95}}
        page = _build_page(entry, "cells", "net", erc_index=erc_index)
        assert "AutoFilter class handles worksheet filtering" in page

    def test_erc_claim_id_in_frontmatter_claims(self):
        entry = self._entry("AutoFilter", doc="")
        erc_index = {"AutoFilter": {"claim_id": "ERC-001", "kind": "api",
                                     "text": "The AutoFilter class handles worksheet filtering.",
                                     "confidence": 0.95}}
        page = _build_page(entry, "cells", "net", erc_index=erc_index)
        # ERC-001 must appear before the second --- (end of frontmatter)
        parts = page.split("---")
        assert "ERC-001" in parts[1], "ERC claim ID not found in frontmatter"

    def test_docstring_wins_over_erc(self):
        entry = self._entry("AutoFilter", doc="Original docstring text.")
        erc_index = {"AutoFilter": {"claim_id": "ERC-001", "kind": "api",
                                     "text": "The AutoFilter class handles worksheet filtering.",
                                     "confidence": 0.95}}
        page = _build_page(entry, "cells", "net", erc_index=erc_index)
        assert "Original docstring text." in page
        assert "handles worksheet filtering" not in page

    def test_no_erc_match_no_claim_id_written(self):
        entry = self._entry("UnknownClass", doc="")
        erc_index = {"AutoFilter": {"claim_id": "ERC-001", "kind": "api",
                                     "text": "The AutoFilter class.", "confidence": 0.95}}
        page = _build_page(entry, "cells", "net", erc_index=erc_index)
        parts = page.split("---")
        assert "ERC-" not in parts[1], "Unexpected ERC ID in frontmatter for unmatched class"

    def test_no_erc_index_no_crash(self):
        entry = self._entry("SomeClass", doc="")
        page = _build_page(entry, "cells", "net", erc_index=None)
        assert "## Overview" in page


# ---------------------------------------------------------------------------
# Evidence apis: population from class metadata (WP-3 healing)
# ---------------------------------------------------------------------------

class TestBuildPageApiEvidence:
    """_build_page() must populate apis: from known class members (metadata-derived)."""

    def _entry_with_members(self, name: str, methods=None, properties=None) -> dict:
        return {
            "name": name,
            "kind": "class_declaration",
            "doc": "",
            "methods": methods or [],
            "properties": properties or [],
            "bases": [],
        }

    def test_methods_appear_in_apis_list(self):
        entry = self._entry_with_members(
            "AutoFilter",
            methods=[
                {"name": "Clear", "params": [], "return_type": "void", "doc": ""},
                {"name": "AddFilter", "params": [], "return_type": "void", "doc": ""},
            ],
        )
        page = _build_page(entry, "cells", "net")
        # Apis list must be non-empty in frontmatter
        fm = page.split("---")[1]
        assert "AutoFilter.Clear" in fm
        assert "AutoFilter.AddFilter" in fm

    def test_properties_appear_in_apis_list(self):
        entry = self._entry_with_members(
            "Worksheet",
            properties=[
                {"name": "Name", "type": "string", "writable": True, "doc": ""},
            ],
        )
        page = _build_page(entry, "cells", "net")
        fm = page.split("---")[1]
        assert "Worksheet.Name" in fm

    def test_empty_class_has_no_apis(self):
        entry = self._entry_with_members("EmptyClass")
        page = _build_page(entry, "cells", "net")
        fm = page.split("---")[1]
        assert "apis:\n  []" in fm or "apis: []\n" in fm or "apis:\n- " not in fm

    def test_model_sha_written_in_frontmatter(self):
        entry = self._entry_with_members("MyClass")
        sha = "abc123def456"
        page = _build_page(entry, "cells", "net", model_sha=sha)
        fm = page.split("---")[1]
        assert sha in fm

    def test_model_version_written_in_frontmatter(self):
        entry = self._entry_with_members("MyClass")
        page = _build_page(entry, "cells", "net", model_version="2.0.0")
        fm = page.split("---")[1]
        assert "2.0.0" in fm

    def test_apis_capped_at_20(self):
        """No more than 20 api entries should be emitted per page."""
        methods = [{"name": f"Method{i}", "params": [], "return_type": "void", "doc": ""} for i in range(25)]
        props = [{"name": f"Prop{i}", "type": "string", "writable": True, "doc": ""} for i in range(10)]
        entry = self._entry_with_members("BigClass", methods=methods, properties=props)
        page = _build_page(entry, "cells", "net")
        # Count api entries (lines matching '  - "BigClass.')
        import re
        api_lines = re.findall(r'"BigClass\.\w+"', page)
        assert len(api_lines) <= 20

    def test_method_count_consistent_with_overloads(self):
        """TC-SYS-016: description and overview prose must use the same method count.

        When a class has method overloads (same name, different params), the
        frontmatter description and overview prose must both report total
        method entries (including overloads), not unique names.
        """
        methods = [
            {"name": "Save", "params": [{"name": "path", "type": "string"}],
             "return_type": "void", "doc": ""},
            {"name": "Save", "params": [{"name": "path", "type": "string"},
                                         {"name": "opts", "type": "SaveOptions"}],
             "return_type": "void", "doc": ""},
            {"name": "Open", "params": [], "return_type": "Document", "doc": ""},
        ]
        entry = self._entry_with_members("Document", methods=methods)
        page = _build_page(entry, "pdf", "net")
        # Both the description and the overview prose should say "3 methods"
        assert "3 methods" in page
        # Should NOT say "2 methods" (which would be unique name count)
        assert "2 methods" not in page

    def test_run_writes_model_sha_in_generated_page(self, tmp_path):
        """run() reads model_sha from model.yaml and passes it to _build_page."""
        sha = "deadbeef1234567890"
        entries = [
            {"name": "Widget", "kind": "class_declaration",
             "methods": [{"name": "DoIt", "params": [], "return_type": "void", "doc": ""}],
             "properties": [], "doc": "", "bases": []},
        ]
        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
        import yaml as _yaml
        (merged / "model.yaml").write_text(
            _yaml.safe_dump({"stale_since": None, "version": "1.0.0", "repo_sha": sha}),
            encoding="utf-8",
        )

        result = run("test", "net")

        page_path = tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "net" / "Widget.md"
        assert page_path.exists()
        content = page_path.read_text(encoding="utf-8")
        assert sha in content
        assert "Widget.DoIt" in content


# ---------------------------------------------------------------------------
# Name collision deduplication (TM-02: Document class collision guard)
# ---------------------------------------------------------------------------

class TestNameCollisionDedup:
    """Name collisions are resolved upstream by consolidate_classes() at
    extraction time.  batch_reference handles remaining same-name entries
    (different namespaces) via disambiguated slugs.

    The old same-visibility merge is tested in test_consolidate_classes.py.
    """

    def test_prefers_exported_over_conventional(self, tmp_path):
        """When __all__ exports exist, conventional classes are filtered out."""
        entries = [
            {"name": "Document", "kind": "class_definition",
             "file": "internal/model.py", "visibility": "conventional",
             "methods": [{"name": "find_style", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
            {"name": "Document", "kind": "class_definition",
             "file": "document.py", "visibility": "exported",
             "methods": [{"name": "save", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
        ]
        _make_api_surface(tmp_path, entries, "words", "python")
        out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "words" / "python"
        out_dir.mkdir(parents=True)

        result = run("words", "python")

        page = out_dir / "Document.md"
        assert page.exists()
        content = page.read_text(encoding="utf-8")
        assert "save" in content
        assert result["generated"] == 1  # only 1 page, not 2

    def test_namespace_disambiguated_slugs(self, tmp_path):
        """Same-name classes with different namespaces get separate pages."""
        entries = [
            {"name": "Color", "kind": "class_declaration",
             "file": "Color.cs", "visibility": "public",
             "canonical_namespace": "Aspose.Pdf",
             "class_import": "Aspose.Pdf.Color",
             "methods": [{"name": "FromRgb", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
            {"name": "Color", "kind": "class_declaration",
             "file": "Drawing/Graph.cs", "visibility": "public",
             "canonical_namespace": "Aspose.Pdf.Drawing",
             "class_import": "Aspose.Pdf.Drawing.Color",
             "methods": [{"name": "Parse", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
        ]
        _make_api_surface(tmp_path, entries, "pdf", "net")
        out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "net"
        out_dir.mkdir(parents=True)

        result = run("pdf", "net")

        assert (out_dir / "Color-Pdf.md").exists()
        assert (out_dir / "Color-Drawing.md").exists()
        assert result["generated"] == 2

    def test_no_collision_passes_through(self, tmp_path):
        entries = [
            {"name": "Alpha", "kind": "class_definition",
             "file": "a.py", "visibility": "public",
             "methods": [], "properties": []},
            {"name": "Beta", "kind": "class_definition",
             "file": "b.py", "visibility": "public",
             "methods": [], "properties": []},
        ]
        _make_api_surface(tmp_path, entries, "words", "python")
        out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "words" / "python"
        out_dir.mkdir(parents=True)

        result = run("words", "python")

        assert (out_dir / "Alpha.md").exists()
        assert (out_dir / "Beta.md").exists()
        assert result["generated"] == 2


# ---------------------------------------------------------------------------
# Java internal class filter (SEA-T3 regression)
# ---------------------------------------------------------------------------

class TestJavaInternalClassFilter:
    """_JAVA_INTERNAL_CLASSES entries must be excluded from Java candidates only.

    Regression tests for SEA-T3: 31 internal implementation classes retired via
    draft: true must not be re-generated by batch-reference slides java.
    The filter must NOT affect any other platform (cpp, net, python, typescript).
    """

    # All 31 retired names
    _RETIRED = [
        "AppPropertiesPart", "AuthorData", "BaseCollection", "BulkTextFormat",
        "CommentAuthorsPart", "CommentData", "CommentsPart", "ContentTypesManager",
        "CorePropertiesPart", "CustomPropertiesPart", "ExporterBase", "ExporterRegistry",
        "ImageUtils", "LayoutSlidePart", "MasterReference", "MasterSlidePart",
        "NotesSlidePart", "Ns", "OpcPackage", "PptxConstants", "PptxExporter",
        "PptxExporterFactory", "PresentationPart", "RelationshipsManager", "RelsHelper",
        "ShapeFactory", "ShapeTypeMapping", "SlidePart", "SlideReference",
        "TableStyleMapping", "Template",
    ]

    def test_all_retired_classes_excluded_for_java(self):
        """Every name in _JAVA_INTERNAL_CLASSES must return False for java."""
        for name in self._RETIRED:
            entry = {"name": name, "kind": "class_declaration"}
            assert not _passes_platform_scope(entry, "java"), (
                f"{name} should be excluded for java but was included"
            )

    def test_public_presentation_class_still_passes_java(self):
        """A well-known public class must still be included."""
        assert _passes_platform_scope(
            {"name": "Presentation", "kind": "class_declaration"}, "java"
        )

    def test_public_ishape_interface_still_passes_java(self):
        """Interface entries with valid kind still pass the Java filter."""
        assert _passes_platform_scope(
            {"name": "IShape", "kind": "interface_declaration"}, "java"
        )

    def test_java_internal_name_passes_for_net(self):
        """Names in _JAVA_INTERNAL_CLASSES must not be blocked for .NET."""
        assert _passes_platform_scope(
            {"name": "AppPropertiesPart", "kind": "class_declaration"}, "net"
        )

    def test_java_internal_name_passes_for_python(self):
        """Names in _JAVA_INTERNAL_CLASSES must not be blocked for python."""
        assert _passes_platform_scope(
            {"name": "BaseCollection", "kind": "class_definition"}, "python"
        )

    def test_java_internal_name_passes_for_cpp(self):
        """Names in _JAVA_INTERNAL_CLASSES must not be blocked for cpp."""
        assert _passes_platform_scope(
            {"name": "Template", "kind": "class_specifier"}, "cpp"
        )

    def test_java_enum_not_blocked_if_not_internal(self):
        """A Java enum with a valid kind is included if not in the internal list."""
        assert _passes_platform_scope(
            {"name": "SaveFormat", "kind": "enum_declaration"}, "java"
        )

    def test_frozenset_has_exactly_31_entries(self):
        """The frozenset must contain exactly 31 entries — no more, no less."""
        assert len(_br._JAVA_INTERNAL_CLASSES) == 31


# ---------------------------------------------------------------------------
# Tests for the file-path-based internal package filter (Part X / Fix X-1)
# ---------------------------------------------------------------------------

class TestJavaInternalPathFilter:
    """_passes_platform_scope must reject Java entries whose `file` field
    contains an /internal/ path segment, regardless of class name."""

    _INTERNAL_FILE = "src/main/java/org/aspose/slides/foss/internal/pptx/AppPropertiesPart.java"
    _PUBLIC_FILE   = "src/main/java/org/aspose/slides/foss/Presentation.java"

    def test_internal_path_unix_sep_is_filtered(self):
        """Entry with /internal/ in file path must be excluded for java."""
        assert not _passes_platform_scope(
            {"name": "AppPropertiesPart", "kind": "class_declaration",
             "file": self._INTERNAL_FILE},
            "java",
        )

    def test_internal_path_windows_sep_is_filtered(self):
        r"""Entry with \internal\ (Windows separator) must also be excluded."""
        win_path = self._INTERNAL_FILE.replace("/", "\\")
        assert not _passes_platform_scope(
            {"name": "NewInternalClass", "kind": "class_declaration", "file": win_path},
            "java",
        )

    def test_public_file_path_passes(self):
        """Entry with a non-internal file path must still be included."""
        assert _passes_platform_scope(
            {"name": "Presentation", "kind": "class_declaration",
             "file": self._PUBLIC_FILE},
            "java",
        )

    def test_blocklist_fires_even_without_file_field(self):
        """_JAVA_INTERNAL_CLASSES name match must still reject entries with no file field."""
        assert not _passes_platform_scope(
            {"name": "AppPropertiesPart", "kind": "class_declaration"},
            "java",
        )

    def test_internal_path_also_affects_net(self):
        """FIX-01: universal /internal/ guard applies to ALL platforms."""
        assert not _passes_platform_scope(
            {"name": "SomeClass", "kind": "class_declaration",
             "file": "src/internal/SomeClass.cs"},
            "net",
        )

    def test_internal_path_also_affects_python(self):
        """FIX-01: universal /internal/ guard applies to ALL platforms."""
        assert not _passes_platform_scope(
            {"name": "SomeClass", "kind": "class_definition",
             "file": "src/internal/some_class.py"},
            "python",
        )

    def test_unknown_class_in_internal_package_filtered(self):
        """A brand-new class name (not in blocklist) from /internal/ must be filtered."""
        assert not _passes_platform_scope(
            {"name": "FutureInternalClass", "kind": "class_declaration",
             "file": "src/main/java/com/aspose/words/foss/internal/impl/FutureInternalClass.java"},
            "java",
        )


# ---------------------------------------------------------------------------
# TC-06 regression guard: ERC member index populates table description cells
# ---------------------------------------------------------------------------

class TestErcMemberIndexPopulatesTableCells:
    """_build_erc_member_index must return ClassName.MemberName → description
    entries when the claims.json contains ERC-* api-kind claims in the right format.

    Regression guard for RC-2 (member-doc enrichment never run). Verifies that
    the index-building logic correctly extracts member descriptions from properly
    formatted ERC claims.
    """

    def _write_claims(self, tmp_path: Path, claims: list) -> None:
        merged = tmp_path / "knowledge" / "test_fam" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")

    def test_erc_api_claim_indexed(self, tmp_path):
        """ERC-* claim with kind='api' and ClassName.Member prefix → entry in index."""
        self._write_claims(tmp_path, [
            {
                "claim_id": "ERC-test-0001",
                "kind": "api",
                "text": "Document.title returns the document title string.",
                "confidence": 0.85,
            }
        ])
        index = _br._build_erc_member_index("test_fam", "python")
        assert "Document.title" in index, "ERC api claim must be indexed under ClassName.MemberName"
        assert len(index["Document.title"]) >= 6, "Description must be non-trivial"

    def test_non_erc_claim_not_indexed(self, tmp_path):
        """Scout claim (CLM- prefix) must not appear in the member index."""
        self._write_claims(tmp_path, [
            {
                "claim_id": "CLM-test-abc123",
                "kind": "api_method",
                "text": "Document.save(path) -> None",
                "confidence": 1.0,
            }
        ])
        index = _br._build_erc_member_index("test_fam", "python")
        assert index == {}, "Scout claims (non-ERC) must not pollute the member index"

    def test_non_api_kind_erc_not_indexed(self, tmp_path):
        """ERC claim with kind='feature' (not 'api') must not appear in the index."""
        self._write_claims(tmp_path, [
            {
                "claim_id": "ERC-test-0002",
                "kind": "feature",
                "text": "Document supports import from PDF files.",
                "confidence": 0.90,
            }
        ])
        index = _br._build_erc_member_index("test_fam", "python")
        assert index == {}, "ERC feature claims must not appear in the member description index"

    def test_longest_description_wins(self, tmp_path):
        """When multiple ERC claims match the same member, the longest description wins."""
        self._write_claims(tmp_path, [
            {
                "claim_id": "ERC-test-0003",
                "kind": "api",
                "text": "Body.type short desc.",
                "confidence": 0.80,
            },
            {
                "claim_id": "ERC-test-0004",
                "kind": "api",
                "text": "Body.type is the content-model type string identifying the node kind.",
                "confidence": 0.85,
            },
        ])
        index = _br._build_erc_member_index("test_fam", "python")
        assert "Body.type" in index
        assert "content-model" in index["Body.type"] or len(index["Body.type"]) > len("short desc"), (
            "Longer description must win over shorter one"
        )

    def test_missing_claims_json_returns_empty(self, tmp_path):
        """Absent claims.json must return empty dict without error."""
        index = _br._build_erc_member_index("no_such_fam", "python")
        assert index == {}

    def test_snake_case_class_member_indexed(self, tmp_path):
        """SR-04: snake_case class name (e.g. cfb_document) is indexed when in api_surface.

        Regression guard for the _MEMBER_PREFIX_RE broadening from [A-Z] to [A-Za-z]
        combined with the class-name gate — ensures C++ snake_case class names are
        correctly matched when present in the known classes set.
        """
        self._write_claims(tmp_path, [
            {
                "claim_id": "ERC-cpp-0001",
                "kind": "api",
                "text": "cfb_document.major_version Returns the CFB container major version.",
                "confidence": 0.80,
            }
        ])
        api_surface = [{"name": "cfb_document", "properties": [], "methods": []}]
        index = _br._build_erc_member_index("test_fam", "python", api_surface=api_surface)
        assert "cfb_document.major_version" in index, (
            "snake_case class member must be indexed when class is in known api_surface"
        )

    def test_non_member_sentence_not_indexed(self, tmp_path):
        """SR-04: prose like 'it.seems' is NOT indexed even if it matches ClassName.word.

        The class-name gate must reject claims whose matched class name is not in
        the known classes set, preventing false-positive indexing of prose text.
        """
        self._write_claims(tmp_path, [
            {
                "claim_id": "ERC-prose-0001",
                "kind": "api",
                "text": "it.seems this is a method description",
                "confidence": 0.75,
            }
        ])
        api_surface = [{"name": "Document", "properties": [], "methods": []}]
        index = _br._build_erc_member_index("test_fam", "python", api_surface=api_surface)
        assert "it.seems" not in index, (
            "Prose sentence matching ClassName.word pattern must be rejected by class-name gate"
        )
        assert index == {}, "No valid member claims in input; index must be empty"

    def test_unknown_class_not_indexed(self, tmp_path):
        """SR-04: class not in api_surface is rejected even with correct ClassName.Member format.

        Ensures that claims referencing classes absent from api_surface (e.g. from
        a prior version of the API or a hallucinated class name) are not indexed.
        """
        self._write_claims(tmp_path, [
            {
                "claim_id": "ERC-unknown-0001",
                "kind": "api",
                "text": "UnknownClass.some_method does something useful.",
                "confidence": 0.82,
            }
        ])
        # api_surface contains Document, not UnknownClass
        api_surface = [{"name": "Document", "properties": [], "methods": []}]
        index = _br._build_erc_member_index("test_fam", "python", api_surface=api_surface)
        assert "UnknownClass.some_method" not in index, (
            "Class absent from api_surface must be rejected by class-name gate"
        )

    def test_class_name_gate_skipped_when_no_api_surface(self, tmp_path):
        """SR-04: when api_surface is None (backward-compat), class-name gate is skipped.

        Ensures that callers passing no api_surface still get the original behavior —
        any ClassName.MemberName claim is indexed regardless of known classes.
        """
        self._write_claims(tmp_path, [
            {
                "claim_id": "ERC-nosurf-0001",
                "kind": "api",
                "text": "AnyClass.any_member Returns something.",
                "confidence": 0.80,
            }
        ])
        # api_surface defaults to None → gate disabled → claim indexed
        index = _br._build_erc_member_index("test_fam", "python")
        assert "AnyClass.any_member" in index, (
            "Without api_surface, class-name gate must be skipped for backward compatibility"
        )


# ---------------------------------------------------------------------------
# TC-06 / TC-05 regression guard: pre-generation coverage check function
# ---------------------------------------------------------------------------

class TestMemberDocCoverageCheck:
    """check_member_doc_coverage must compute coverage rate correctly.

    Regression guard for TC-05 — verifies the pre-generation gate computes
    accurate coverage rates so the WARNING fires at the right threshold.
    """

    def _make_entry(self, name: str, props: list, methods: list) -> dict:
        return {"name": name, "properties": props, "methods": methods}

    def test_fully_covered_by_erc_index(self):
        """All members present in ERC index → 100% coverage."""
        api_surface = [self._make_entry("Doc", [
            {"name": "title", "doc": ""},
        ], [
            {"name": "save", "doc": "", "is_constructor": False},
        ])]
        erc_index = {"Doc.title": "The document title.", "Doc.save": "Saves the document."}
        rate, covered, total = check_member_doc_coverage(api_surface, erc_index)
        assert total == 2
        assert covered == 2
        assert rate == 1.0

    def test_no_coverage_returns_zero(self):
        """No members in ERC index and no source docstrings → 0% coverage."""
        api_surface = [self._make_entry("Doc", [
            {"name": "title", "doc": ""},
            {"name": "author", "doc": ""},
        ], [])]
        rate, covered, total = check_member_doc_coverage(api_surface, {})
        assert total == 2
        assert covered == 0
        assert rate == 0.0

    def test_source_docstring_counts_as_covered(self):
        """Member with non-empty 'doc' field from source counts as covered without ERC."""
        api_surface = [self._make_entry("Doc", [
            {"name": "title", "doc": "The document title."},
        ], [])]
        rate, covered, total = check_member_doc_coverage(api_surface, {})
        assert covered == 1
        assert total == 1
        assert rate == 1.0

    def test_constructors_excluded_from_count(self):
        """Constructor methods (is_constructor=True) must not inflate the total count."""
        api_surface = [self._make_entry("Doc", [], [
            {"name": "__init__", "doc": "", "is_constructor": True},
            {"name": "save", "doc": "", "is_constructor": False},
        ])]
        erc_index = {"Doc.save": "Saves to disk."}
        rate, covered, total = check_member_doc_coverage(api_surface, erc_index)
        assert total == 1  # __init__ excluded
        assert covered == 1
        assert rate == 1.0

    def test_empty_api_surface_returns_zero_rate(self):
        """Empty api_surface must return (0.0, 0, 0) without dividing by zero."""
        rate, covered, total = check_member_doc_coverage([], {})
        assert (rate, covered, total) == (0.0, 0, 0)


# ---------------------------------------------------------------------------
# SR-05: Pipe-escaping in type columns
# ---------------------------------------------------------------------------

class TestPipeEscapingInPropertyTypeColumn:
    """Property type strings containing | are escaped to \\| in the generated table.

    Regression guard for SR-05 Behavior 1: ensures that union types such as
    "int | None" do not break markdown table column alignment when written to
    the Properties table.
    """

    def test_pipe_escaped_in_property_type_column(self):
        """Type 'int | None' must appear as 'int \\| None' in the generated page."""
        entry = {
            "name": "MyClass",
            "kind": "class_declaration",
            "doc": "",
            "methods": [],
            "properties": [
                {"name": "count", "type": "int | None", "writable": False, "doc": "The count."},
            ],
            "bases": [],
        }
        page = _build_page(entry, "cells", "net")
        # Escaped form must be present
        assert r"int \| None" in page, "Pipe in type string was not escaped to \\|"
        # Raw unescaped form must not appear as a standalone table separator
        # (we check that the literal "| None |" pattern is absent as a cell boundary)
        lines = page.splitlines()
        for line in lines:
            if "int" in line and "None" in line and "|" in line:
                # The pipe between int and None must be backslash-escaped
                assert r"int \| None" in line, (
                    f"Found unescaped pipe in property type column: {line!r}"
                )


# ---------------------------------------------------------------------------
# SR-05: Enum ERC lookup populates cell when member has no doc
# ---------------------------------------------------------------------------

class TestEnumMemberErcLookup:
    """Enum table description cells are populated from member_erc_index when
    the enum member has no 'doc' field.

    Regression guard for SR-05 Behavior 2: verifies the ERC-index fallback path
    in the enum values table, mirroring the same fallback already tested for
    property/method rows.
    """

    def test_enum_member_erc_lookup_populates_cell(self):
        """When an enum member has no doc, member_erc_index supplies the description."""
        entry = {
            "name": "SaveFormat",
            "kind": "enum_declaration",
            "doc": "",
            "methods": [],
            "properties": [],
            "bases": [],
            "enum_members": [
                {"name": "PDF", "doc": ""},
                {"name": "DOCX", "doc": "Microsoft Word document format."},
            ],
        }
        member_erc_index = {
            "SaveFormat.PDF": "Portable Document Format output.",
        }
        page = _build_page(entry, "slides", "net", member_erc_index=member_erc_index)
        # ERC description must appear for the member with empty doc
        assert "Portable Document Format output." in page, (
            "ERC member description was not written into the enum values table"
        )
        # Existing doc must also be preserved
        assert "Microsoft Word document format." in page


# ---------------------------------------------------------------------------
# Fix D: _load_update_apis includes new + resurrected (healing sprint 2026-04-15)
# ---------------------------------------------------------------------------

class TestLoadUpdateApis:
    """Fix D: _load_update_apis returns modified + new + resurrected API sets."""

    def test_includes_all_three_fields(self, tmp_path):
        import json
        import batch_reference as br

        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text(json.dumps({
            "modified_apis": ["ClassA"],
            "new_apis": ["ClassB", "ClassC"],
            "resurrected_apis": ["ClassD"],
        }), encoding="utf-8")

        result = br._load_update_apis("test", "net")
        assert result == {"ClassA", "ClassB", "ClassC", "ClassD"}

    def test_missing_fields_use_empty_default(self, tmp_path):
        import json
        import batch_reference as br

        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "knowledge_delta.json").write_text(json.dumps({
            "modified_apis": ["ClassA"],
        }), encoding="utf-8")

        result = br._load_update_apis("test", "net")
        assert result == {"ClassA"}

    def test_missing_file_returns_none(self, tmp_path):
        import batch_reference as br
        result = br._load_update_apis("test", "net")
        assert result is None


# ---------------------------------------------------------------------------
# TC-S20-B08: --update delta chain behavior (2026-04-18)
# ---------------------------------------------------------------------------

class TestUpdateDeltaBehavior:
    """TC-S20-B08: --update produces a delta (subset of pages), not a full re-run.

    Verifies that when update=True and knowledge_delta.json lists only a subset
    of API classes as modified, only those pages are targeted for update while
    unmodified pages are skipped.  This is the core incremental-update guarantee.
    """

    def test_update_mode_targets_only_modified_apis(self, tmp_path):
        """With 3 existing pages and 1 in modified_apis, skipped == 2 (not 3).

        This proves the delta chain is incremental: pages not in knowledge_delta.json
        are skipped even though they already exist, so update is a strict subset of
        the full candidate list.
        """
        import json
        import yaml

        entries = [
            {"name": "Alpha", "kind": "class_definition", "methods": [], "properties": []},
            {"name": "Beta",  "kind": "class_definition", "methods": [], "properties": []},
            {"name": "Gamma", "kind": "class_definition", "methods": [], "properties": []},
        ]
        merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
        (merged / "model.yaml").write_text(
            yaml.safe_dump({"stale_since": None, "version": "1.0.0"}),
        )
        # Only Beta is modified — Alpha and Gamma are unchanged
        (merged / "knowledge_delta.json").write_text(json.dumps({
            "modified_apis": ["Beta"],
            "new_apis": [],
            "resurrected_apis": [],
        }), encoding="utf-8")

        # Pre-create all 3 pages (simulate committed content)
        page_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / "python"
        page_dir.mkdir(parents=True)
        for name in ("Alpha", "Beta", "Gamma"):
            (page_dir / f"{name}.md").write_text(
                f"---\nauto_updatable: true\n---\n# {name}\n", encoding="utf-8"
            )

        result = run("fake", "python", update=True, dry_run=True)

        # 2 pages skipped (Alpha + Gamma, not in modified_apis)
        assert result["skipped"] == 2, (
            f"Expected 2 pages skipped (not in modified_apis); got {result['skipped']}"
        )
        # dry_run means nothing was actually written
        assert result.get("dry_run") is True
        # The delta is strictly less than the total candidate count (3)
        assert result["skipped"] < 3, "skipped must be < total; --update is not a full re-run"


# ---------------------------------------------------------------------------
# S62-01: --rebuild-all mode tests
# ---------------------------------------------------------------------------

class TestRebuildAll:
    """Tests for the --rebuild-all flag added in S62-01.

    Verifies that existing auto-updatable pages are rebuilt from current
    merged/claims.json without requiring knowledge_delta.json, and that
    protection guardrails (auto_updatable=false, manually curated, confirm
    threshold, timestamp-only churn guard) all work correctly.
    """

    def _make_setup(self, tmp_path, names: list[str], platform: str = "net") -> tuple:
        """Create api_surface.json, model.yaml, and pre-existing page files.

        Returns (merged_dir, page_dir).
        """
        merged = tmp_path / "knowledge" / "fake" / platform / "merged"
        merged.mkdir(parents=True)
        import yaml as _yaml
        entries = [
            {"name": n, "kind": "class_declaration", "methods": [], "properties": []}
            for n in names
        ]
        (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
        (merged / "model.yaml").write_text(
            _yaml.safe_dump({"stale_since": None, "version": "1.0.0", "repo_sha": "abc123"}),
            encoding="utf-8",
        )
        page_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / platform
        page_dir.mkdir(parents=True)
        return merged, page_dir

    def test_rebuild_all_rebuilds_existing(self, tmp_path):
        """--rebuild-all + --confirm-rebuild rewrites existing auto-updatable pages."""
        merged, page_dir = self._make_setup(tmp_path, ["Alpha", "Beta"])
        # Create existing pages as auto-updatable (no manually-curated marker)
        for name in ("Alpha", "Beta"):
            (page_dir / f"{name}.md").write_text(
                "---\nprovenance:\n  content_origin: skill-generated\n"
                "  auto_updatable: true\n---\n# Original\n",
                encoding="utf-8",
            )
        result = run("fake", "net", rebuild_all=True, confirm_rebuild=True)
        assert result["updated"] == 2, f"Expected 2 rebuilt; got {result['updated']}"
        assert result["generated"] == 0
        assert result["skipped"] == 0

    def test_rebuild_all_requires_confirm_when_gt_threshold(self, tmp_path):
        """--rebuild-all without --confirm-rebuild raises SystemExit when >THRESHOLD pages."""
        from batch_reference import REBUILD_CONFIRM_THRESHOLD
        # Create THRESHOLD+1 pages
        n = REBUILD_CONFIRM_THRESHOLD + 1
        names = [f"Class{i:03d}" for i in range(n)]
        merged, page_dir = self._make_setup(tmp_path, names)
        for name in names:
            (page_dir / f"{name}.md").write_text(
                "---\nprovenance:\n  content_origin: skill-generated\n"
                "  auto_updatable: true\n---\n# Body\n",
                encoding="utf-8",
            )
        with pytest.raises(SystemExit, match="--confirm-rebuild"):
            run("fake", "net", rebuild_all=True, confirm_rebuild=False)

    def test_rebuild_all_no_confirm_required_at_threshold(self, tmp_path):
        """Exactly THRESHOLD pages does NOT require --confirm-rebuild."""
        from batch_reference import REBUILD_CONFIRM_THRESHOLD
        names = [f"Class{i:03d}" for i in range(REBUILD_CONFIRM_THRESHOLD)]
        merged, page_dir = self._make_setup(tmp_path, names)
        for name in names:
            (page_dir / f"{name}.md").write_text(
                "---\nprovenance:\n  content_origin: skill-generated\n"
                "  auto_updatable: true\n---\n# Body\n",
                encoding="utf-8",
            )
        # Should NOT raise — exactly at threshold
        result = run("fake", "net", rebuild_all=True, confirm_rebuild=False)
        assert result["updated"] == REBUILD_CONFIRM_THRESHOLD

    def test_rebuild_all_skips_non_auto_updatable(self, tmp_path):
        """--rebuild-all skips pages with auto_updatable: false."""
        merged, page_dir = self._make_setup(tmp_path, ["Safe", "Protected"])
        (page_dir / "Safe.md").write_text(
            "---\nprovenance:\n  content_origin: skill-generated\n"
            "  auto_updatable: true\n---\n# Safe\n",
            encoding="utf-8",
        )
        (page_dir / "Protected.md").write_text(
            "---\nprovenance:\n  content_origin: skill-generated\n"
            "  auto_updatable: false\n---\n# Protected\n",
            encoding="utf-8",
        )
        result = run("fake", "net", rebuild_all=True, confirm_rebuild=True)
        assert result["skipped"] == 1, f"Protected page should be skipped; got {result['skipped']}"
        assert result["updated"] == 1, f"Safe page should be rebuilt; got {result['updated']}"

    def test_rebuild_all_generates_missing_pages(self, tmp_path):
        """--rebuild-all generates pages that don't exist yet (same as default mode)."""
        merged, page_dir = self._make_setup(tmp_path, ["Existing", "New"])
        (page_dir / "Existing.md").write_text(
            "---\nprovenance:\n  content_origin: skill-generated\n"
            "  auto_updatable: true\n---\n# Existing\n",
            encoding="utf-8",
        )
        # "New" has no pre-existing file
        result = run("fake", "net", rebuild_all=True, confirm_rebuild=True)
        assert result["generated"] == 1, f"New page should be generated; got {result['generated']}"
        assert result["updated"] == 1, f"Existing page should be rebuilt; got {result['updated']}"
        assert (page_dir / "New.md").exists()

    def test_rebuild_all_dry_run(self, tmp_path):
        """--rebuild-all --dry-run reports candidates without writing."""
        merged, page_dir = self._make_setup(tmp_path, ["Alpha", "Beta"])
        for name in ("Alpha", "Beta"):
            (page_dir / f"{name}.md").write_text(
                "---\nprovenance:\n  content_origin: skill-generated\n"
                "  auto_updatable: true\n---\n# Original\n",
                encoding="utf-8",
            )
        original_mtime = (page_dir / "Alpha.md").stat().st_mtime
        result = run("fake", "net", rebuild_all=True, confirm_rebuild=True, dry_run=True)
        assert result.get("dry_run") is True
        assert result["updated"] == 0
        # Files must be unchanged
        assert (page_dir / "Alpha.md").stat().st_mtime == original_mtime

    def test_no_delta_update_still_skips_existing(self, tmp_path):
        """Regression: --update without knowledge_delta.json must skip existing pages.

        This verifies the corrected fallback behavior: 'skip-existing mode' not
        'full re-run'. The misleading warning text has been fixed; this test
        guards against future regressions to the old behavior.
        """
        merged, page_dir = self._make_setup(tmp_path, ["Alpha"])
        # No knowledge_delta.json — triggers fallback
        (page_dir / "Alpha.md").write_text(
            "---\nprovenance:\n  content_origin: skill-generated\n"
            "  auto_updatable: true\n---\n# Original\n",
            encoding="utf-8",
        )
        result = run("fake", "net", update=True)
        # Must skip the existing page, not regenerate it
        assert result["skipped"] == 1, f"Expected 1 skipped; got {result['skipped']}"
        assert result["updated"] == 0
        assert result["generated"] == 0

    def test_has_meaningful_change_detects_timestamp_only(self, tmp_path):
        """_has_meaningful_change returns False when only timestamp/grade metadata fields differ.

        Fields ignored: content_created_at, graded_at, grade, graded_content_hash,
        content_hash.  These are set by attach_evidence() / update_mechanism() and
        are absent in _build_page() output; comparing them against existing pages
        would always produce false positives.
        """
        from batch_reference import _has_meaningful_change
        existing = tmp_path / "page.md"
        existing.write_text(
            "---\ntitle: Foo\n"
            "  content_created_at: '2026-01-01T00:00:00+00:00'\n"
            "  content_hash: aabbccdd\n"
            "grade: A\n"
            "graded_at: '2026-01-01'\n"
            "graded_content_hash: \"deadbeef\"\n"
            "---\nbody\n",
            encoding="utf-8",
        )
        new_content = (
            "---\ntitle: Foo\n"
            "  content_created_at: '2026-05-01T12:00:00+00:00'\n"
            # grade/graded_at/graded_content_hash/content_hash absent in _build_page output
            "---\nbody\n"
        )
        assert not _has_meaningful_change(existing, new_content), (
            "Should detect metadata-only change (timestamps + grade fields) as not meaningful"
        )

    def test_has_meaningful_change_detects_body_change(self, tmp_path):
        """_has_meaningful_change returns True when body content differs."""
        from batch_reference import _has_meaningful_change
        existing = tmp_path / "page.md"
        existing.write_text(
            "---\ntitle: Foo\n---\nOld body\n",
            encoding="utf-8",
        )
        new_content = "---\ntitle: Foo\n---\nNew body\n"
        assert _has_meaningful_change(existing, new_content), (
            "Should detect body change as meaningful"
        )

    def test_rebuild_all_preserves_content_created_at(self, tmp_path):
        """--rebuild-all must not change content_created_at of existing pages."""
        merged, page_dir = self._make_setup(tmp_path, ["Alpha"])
        original_ts = "2026-01-01T00:00:00+00:00"
        (page_dir / "Alpha.md").write_text(
            f"---\nprovenance:\n  content_origin: skill-generated\n"
            f"  auto_updatable: true\n"
            f"  content_created_at: '{original_ts}'\n---\n# Alpha body text that will change\n",
            encoding="utf-8",
        )
        run("fake", "net", rebuild_all=True, confirm_rebuild=True)
        written = (page_dir / "Alpha.md").read_text(encoding="utf-8")
        assert original_ts in written, (
            f"content_created_at '{original_ts}' must be preserved after rebuild; "
            f"got:\n{written[:300]}"
        )


# ---------------------------------------------------------------------------
# configure() seam (MP-SR03 / TC-04)
# ---------------------------------------------------------------------------

class TestConfigureSeam:
    """Verify the configure() injection seam works without monkeypatching."""

    def test_configure_repo_root_overrides_globals(self, tmp_path):
        """configure(repo_root=tmp_path) must redirect KNOWLEDGE_ROOT and CONTENT_ROOT."""
        import batch_reference as _br_local
        _br_local.configure(repo_root=tmp_path)
        try:
            assert _br_local.KNOWLEDGE_ROOT == tmp_path / "knowledge"
            assert _br_local.CONTENT_ROOT == (
                tmp_path / "content" / "reference.aspose.org" / "en"
            )
        finally:
            _br_local.configure()  # reset to defaults

    def test_configure_knowledge_root_direct(self, tmp_path):
        """configure(knowledge_root=...) overrides KNOWLEDGE_ROOT independently."""
        import batch_reference as _br_local
        kr = tmp_path / "custom_knowledge"
        _br_local.configure(knowledge_root=kr)
        try:
            assert _br_local.KNOWLEDGE_ROOT == kr
        finally:
            _br_local.configure()

    def test_configure_reset_restores_defaults(self):
        """configure() with no args must restore the built-in defaults."""
        import batch_reference as _br_local
        from pathlib import Path as _Path
        default_root = _Path(__file__).resolve().parents[3]  # <repo>
        _br_local.configure(repo_root=_Path("/tmp/fake_root"))
        _br_local.configure()  # reset
        assert _br_local.KNOWLEDGE_ROOT == default_root / "knowledge"

    def test_configure_seam_enables_run_without_patching(self, tmp_path):
        """run() works correctly when roots are set via configure() instead of patch.object."""
        import batch_reference as _br_local
        entries = [
            {"name": "Foo", "kind": "class_declaration", "methods": [], "properties": []},
        ]
        _make_api_surface(tmp_path, entries, family="test_fam", platform="net")
        _br_local.configure(repo_root=tmp_path)
        try:
            result = _br_local.run("test_fam", "net")
        finally:
            _br_local.configure()
        assert result["generated"] == 1
        page = tmp_path / "content" / "reference.aspose.org" / "en" / "test_fam" / "net" / "Foo.md"
        assert page.exists()


# ---------------------------------------------------------------------------
# TC-BL-008: _get_family_display anchor text tests
# ---------------------------------------------------------------------------

class TestGetFamilyDisplay:
    """TC-BL-008: Verify anchor text respects target_type from resolve_backlink."""

    def test_family_rtype_omits_platform(self, tmp_path):
        """When target_type='family', anchor text must be family-only."""
        from batch_reference import _get_family_display
        result = _get_family_display("cells", "java", target_type="family")
        assert "for" not in result
        assert "Cells" in result

    def test_platform_rtype_includes_platform(self, tmp_path):
        """When target_type='platform', anchor text includes 'for Platform'."""
        from batch_reference import _get_family_display
        result = _get_family_display("cells", "java", target_type="platform")
        assert "for Java" in result

    def test_none_rtype_with_platform_includes_platform(self, tmp_path):
        """When target_type is None but platform is set, includes platform (defensive)."""
        from batch_reference import _get_family_display
        result = _get_family_display("cells", "java", target_type=None)
        assert "for Java" in result

    def test_no_platform_always_family_only(self, tmp_path):
        """When platform is empty/None, always family-only regardless of target_type."""
        from batch_reference import _get_family_display
        result = _get_family_display("cells", "", target_type="platform")
        assert "for" not in result
        assert "Cells" in result

    def test_platform_rtype_net_display(self, tmp_path):
        """Platform display correctly maps 'net' to '.NET'."""
        from batch_reference import _get_family_display
        result = _get_family_display("words", "net", target_type="platform")
        assert result.endswith("for .NET")

    def test_family_rtype_exception_fallback(self, tmp_path):
        """Family rtype with valid data returns family-only."""
        from batch_reference import _get_family_display
        result = _get_family_display("slides", "python", target_type="family")
        assert "for" not in result
        assert "Slides" in result

    def test_unknown_rtype_includes_platform(self, tmp_path):
        """Unknown rtype value with platform set falls through to platform branch."""
        from batch_reference import _get_family_display
        result = _get_family_display("pdf", "java", target_type="unknown_value")
        assert "for Java" in result


# ---------------------------------------------------------------------------
# TC-GATE4B: content_hash stability — generator output matches hook computation
# ---------------------------------------------------------------------------


class TestContentHashStability:
    """Verify _build_page includes content_hash that matches provenance.compute_content_hash.

    This prevents the RECONCILE_DRIFTED loop where the generator omits content_hash,
    the commit hook adds it, and the manifest output hash drifts from the generation
    snapshot — causing Gate 4B to fail after commit.
    """

    @staticmethod
    def _make_entry(**overrides):
        base = {
            "name": "StabilityTest",
            "kind": "class",
            "methods": [{"name": "run", "params": [], "returns": "void", "doc": ""}],
            "properties": [{"name": "val", "type": "int", "access": "Read", "doc": ""}],
            "bases": [],
            "doc": "",
        }
        base.update(overrides)
        return base

    def test_build_page_includes_content_hash(self):
        """_build_page output must contain a content_hash line."""
        import re
        result = _build_page(self._make_entry(), "cells", "java",
                             model_sha="abc", model_version="1.0")
        assert re.search(r"content_hash:\s+[0-9a-f]{32}", result), \
            "Generator must include content_hash in provenance block"

    def test_content_hash_matches_hook_computation(self, tmp_path):
        """Generator content_hash must equal provenance.compute_content_hash on the same text."""
        import re
        from lib.provenance import compute_content_hash

        result = _build_page(self._make_entry(), "cells", "java",
                             model_sha="abc", model_version="1.0")
        gen_hash = re.search(r"content_hash:\s+([0-9a-f]{32})", result).group(1)

        tmp_file = tmp_path / "test.md"
        tmp_file.write_text(result, encoding="utf-8")
        hook_hash = compute_content_hash(tmp_file)

        assert gen_hash == hook_hash, (
            f"Generator hash {gen_hash} != hook hash {hook_hash}. "
            "This will cause RECONCILE_DRIFTED after commit."
        )

    def test_content_hash_stable_across_categories(self, tmp_path):
        """content_hash is correct for class, enum, and interface pages."""
        import re
        from lib.provenance import compute_content_hash

        for kind, category in [("class", "Class"), ("enum", "Enum"), ("interface", "Interface")]:
            entry = self._make_entry(kind=kind)
            if kind == "enum":
                entry["enum_members"] = [{"name": "A"}, {"name": "B"}]
            result = _build_page(entry, "cells", "java",
                                 model_sha="abc", model_version="1.0")
            gen_hash = re.search(r"content_hash:\s+([0-9a-f]{32})", result).group(1)
            tmp_file = tmp_path / f"test_{kind}.md"
            tmp_file.write_text(result, encoding="utf-8")
            hook_hash = compute_content_hash(tmp_file)
            assert gen_hash == hook_hash, \
                f"{kind}: generator {gen_hash} != hook {hook_hash}"

    def test_hook_normalization_is_noop_after_generation(self, tmp_path):
        """After writing _build_page output, provenance_normalize_hash must not change the file."""
        from provenance_normalize_hash import normalize_file

        result = _build_page(self._make_entry(), "cells", "java",
                             model_sha="abc", model_version="1.0")
        tmp_file = tmp_path / "test.md"
        tmp_file.write_text(result, encoding="utf-8")
        original = tmp_file.read_text(encoding="utf-8")

        status = normalize_file(tmp_file, apply=True, auto_stage=False)
        assert status == "skipped", f"Expected 'skipped' (hash already correct), got '{status}'"

        after = tmp_file.read_text(encoding="utf-8")
        assert original == after, \
            "provenance_normalize_hash must be a no-op on freshly generated pages"


# ---------------------------------------------------------------------------
# RC-001 fallback description tests
# ---------------------------------------------------------------------------


class TestRC001FallbackDescriptions:
    """Verify that method/property cells never have empty description when doc and ERC are absent.

    RC-001 root cause: api_surface.json 'doc' field empty + no ERC claim → blank cell → DC FAIL.
    Fix: signature-based fallback in batch_reference.py inserted after ERC lookup block.
    """

    @staticmethod
    def _make_entry(name="Widget", props=None, methods=None):
        return {
            "name": name,
            "kind": "class",
            "doc": "",
            "bases": [],
            "properties": props or [],
            "methods": methods or [],
        }

    def test_method_with_no_doc_gets_fallback_description(self):
        """Method with empty 'doc' and no ERC entry must produce non-empty description cell."""
        entry = self._make_entry(
            name="Widget",
            methods=[{"name": "render", "doc": "", "params": [], "returns": "void",
                      "is_constructor": False}],
        )
        result = _build_page(entry, "cells", "java", model_sha="abc", model_version="1.0",
                             erc_index={})
        assert "Calls render on this Widget instance." in result, (
            "RC-001 fix: method with no doc and no ERC must produce fallback description"
        )

    def test_second_overload_of_same_method_has_empty_description(self):
        """Only the first overload of an undocumented method gets a fallback; the rest remain empty."""
        entry = self._make_entry(
            name="Widget",
            methods=[
                {"name": "render", "doc": "", "params": [], "returns": "void",
                 "is_constructor": False},
                {"name": "render", "doc": "", "params": [{"name": "opts", "type": "str"}],
                 "returns": "void", "is_constructor": False},
            ],
        )
        result = _build_page(entry, "cells", "java", model_sha="abc", model_version="1.0",
                             erc_index={})
        # Exactly one fallback description expected (not two)
        assert result.count("Calls render on this Widget instance.") == 1, (
            "RC-001 fix: only first overload of undocumented method should have fallback description"
        )

    def test_property_with_no_doc_gets_fallback_description(self):
        """Property with empty 'doc' and no ERC entry must produce non-empty description cell."""
        entry = self._make_entry(
            name="Widget",
            props=[{"name": "color", "type": "str", "access": "Read", "doc": ""}],
        )
        result = _build_page(entry, "cells", "java", model_sha="abc", model_version="1.0",
                             erc_index={})
        assert "The color property of Widget." in result, (
            "RC-001 fix: property with no doc and no ERC must produce fallback description"
        )

    def test_method_with_erc_description_uses_erc_not_fallback(self):
        """When member_erc_index provides a description, it must be used instead of the RC-001 fallback."""
        entry = self._make_entry(
            name="Widget",
            methods=[{"name": "render", "doc": "", "params": [], "returns": "void",
                      "is_constructor": False}],
        )
        member_erc_index = {"Widget.render": "Renders the widget to the output stream."}
        result = _build_page(entry, "cells", "java", model_sha="abc", model_version="1.0",
                             member_erc_index=member_erc_index)
        assert "Renders the widget to the output stream." in result, \
            "ERC description must take priority over RC-001 fallback"
        assert "Calls render on this Widget instance." not in result, \
            "RC-001 fallback must not appear when ERC description is present"

    def test_method_with_source_doc_uses_source_not_fallback(self):
        """When source 'doc' is non-empty, it must be used instead of the RC-001 fallback."""
        entry = self._make_entry(
            name="Widget",
            methods=[{"name": "render", "doc": "Draws the widget.", "params": [],
                      "returns": "void", "is_constructor": False}],
        )
        result = _build_page(entry, "cells", "java", model_sha="abc", model_version="1.0",
                             erc_index={})
        assert "Draws the widget." in result, \
            "Source doc must take priority over RC-001 fallback"
        assert "Calls render on this Widget instance." not in result, \
            "RC-001 fallback must not appear when source doc is present"


# ---------------------------------------------------------------------------
# _derive_group_key — path-pattern grouping
# ---------------------------------------------------------------------------

class TestDeriveGroupKey:
    """Tests for _derive_group_key — covers all platform path patterns.

    Regression guard: pdf/net was returning 'core' for every entry because
    _derive_group_key only searched for the family name as a directory segment
    (works for Java paths like org/aspose/pdf/annotations/Class.java) but
    .NET repos use src/{Namespace}/Class.cs with no family-name segment.
    """

    # --- .NET: src/{Namespace}/Class.cs layout (e.g. pdf/net) ---

    def test_net_namespace_directory(self):
        e = {"file": "src/Annotations/AnnotClass.cs", "name": "AnnotClass"}
        assert _derive_group_key(e, "pdf", "net") == "annotations"

    def test_net_namespace_nested(self):
        e = {"file": "src/Annotations/JavascriptExtensions/FieldFormatter.cs", "name": "FieldFormatter"}
        assert _derive_group_key(e, "pdf", "net") == "annotations"

    def test_net_drawing_namespace(self):
        e = {"file": "src/Drawing/ImageFormat.cs", "name": "ImageFormat"}
        assert _derive_group_key(e, "pdf", "net") == "drawing"

    def test_net_facades_namespace(self):
        e = {"file": "src/Facades/FormattedText.cs", "name": "FormattedText"}
        assert _derive_group_key(e, "pdf", "net") == "facades"

    def test_net_root_cs_file_returns_core(self):
        # Class file directly under src/ (no namespace subdirectory)
        e = {"file": "src/Document.cs", "name": "Document"}
        assert _derive_group_key(e, "pdf", "net") == "core"

    def test_net_vb_root_file_returns_core(self):
        e = {"file": "src/Helper.vb", "name": "Helper"}
        assert _derive_group_key(e, "pdf", "net") == "core"

    # --- Java: org/aspose/{family}/{namespace}/Class.java layout ---

    def test_java_namespace_after_family(self):
        e = {"file": "src/main/java/org/aspose/pdf/annotations/Annotation.java", "name": "Annotation"}
        assert _derive_group_key(e, "pdf", "java") == "annotations"

    def test_java_core_when_class_directly_under_family(self):
        e = {"file": "src/main/java/org/aspose/pdf/Document.java", "name": "Document"}
        assert _derive_group_key(e, "pdf", "java") == "core"

    def test_java_engine_namespace(self):
        e = {"file": "src/main/java/org/aspose/pdf/engine/Engine.java", "name": "Engine"}
        assert _derive_group_key(e, "pdf", "java") == "engine"

    # --- Python: src/aspose_{family}/{module}/class.py layout ---

    def test_python_submodule(self):
        e = {"file": "src/aspose_tex/presentation/device.py", "name": "Device"}
        assert _derive_group_key(e, "tex", "python") == "presentation"

    def test_python_core_when_no_submodule(self):
        e = {"file": "src/aspose_tex/__init__.py", "name": "TeXJob"}
        assert _derive_group_key(e, "tex", "python") == "core"

    # --- Edge cases ---

    def test_empty_file_returns_core(self):
        assert _derive_group_key({"file": "", "name": "X"}, "pdf", "net") == "core"

    def test_missing_file_key_returns_core(self):
        assert _derive_group_key({"name": "X"}, "pdf", "net") == "core"

    def test_unknown_platform_returns_core(self):
        e = {"file": "src/Foo/Bar.cs", "name": "Bar"}
        assert _derive_group_key(e, "pdf", "unknown") == "core"


# ---------------------------------------------------------------------------
# TC-RI: _normalize_doc_for_index regression tests
# ---------------------------------------------------------------------------


def test_normalize_strips_cr():
    assert "\r" not in _normalize_doc_for_index("foo\r bar\r baz")
    assert _normalize_doc_for_index("foo\r bar") == "foo bar"


def test_normalize_javadoc_code():
    assert _normalize_doc_for_index("use {@code Foo}") == "use `Foo`"
    assert _normalize_doc_for_index("use {@code  Foo }") == "use `Foo`"
    # No-space edge case (invalid javadoc but defensive)
    result = _normalize_doc_for_index("use {@codeFoo}")
    assert "{@code" not in result


def test_normalize_javadoc_link_simple():
    assert _normalize_doc_for_index("see {@link Bar}") == "see Bar"


def test_normalize_javadoc_link_qualified():
    # Qualified name: extract simple name
    result = _normalize_doc_for_index("see {@link org.aspose.pdf.devices.Margins}")
    assert result == "see Margins"


def test_normalize_javadoc_link_with_hash():
    # Method reference: extract method name
    result = _normalize_doc_for_index("see {@link Foo#bar}")
    assert result == "see bar"


def test_normalize_html_code_tag():
    assert _normalize_doc_for_index("a <code>X</code> b") == "a `X` b"
    assert _normalize_doc_for_index("a <CODE>X</CODE> b") == "a `X` b"


def test_normalize_margins_case():
    """Regression test for the known Margins defect in pdf/java."""
    raw = (
        "Page margins in printer/device units, used by the C# printing API\r"
        " (<code>Aspose.Pdf.Devices.Margins</code>) for {@code PageSettings.Margins}\r"
        " and {@code PrinterSettings.DefaultPageSettings.Margins}."
    )
    out = _normalize_doc_for_index(raw)
    assert "\r" not in out
    assert "{@code" not in out
    assert "<code>" not in out.lower()
    # Must be a single logical line (no embedded newlines)
    assert "\n" not in out
    # Backtick-wrapped code present
    assert "`PageSettings.Margins`" in out
    assert "`Aspose.Pdf.Devices.Margins`" in out


def test_normalize_empty_string():
    assert _normalize_doc_for_index("") == ""


def test_normalize_no_javadoc():
    """Strings without JavaDoc/HTML tokens must pass through unchanged (minus whitespace)."""
    plain = "Represents a PDF document."
    assert _normalize_doc_for_index(plain) == plain


# ---------------------------------------------------------------------------
# Phase A/B/C — Case-collision prevention (RC-001 / deferred fix)
# ---------------------------------------------------------------------------

def _make_case_collision_surface(tmp_path: Path, family: str = "fake",
                                 platform: str = "net") -> tuple[Path, Path]:
    """Create api_surface with Id (Aspose.Pdf) and ID (Aspose.Pdf.Operators).

    Returns (content_dir, api_surface_path).
    """
    entries = [
        {
            "name": "Id",
            "kind": "class_declaration",
            "visibility": "public",
            "canonical_namespace": "Aspose.Pdf",
            "description": "Pair of byte strings that make up the /ID array in the PDF trailer.",
            "methods": [],
            "properties": [],
        },
        {
            "name": "ID",
            "kind": "class_declaration",
            "visibility": "public",
            "canonical_namespace": "Aspose.Pdf.Operators",
            "description": "ID — Begin image data (after the inline-image dictionary).",
            "methods": [],
            "properties": [],
        },
    ]
    _make_api_surface(tmp_path, entries, family=family, platform=platform)
    content_dir = tmp_path / "content" / "reference.aspose.org" / "en" / family / platform
    content_dir.mkdir(parents=True, exist_ok=True)
    return content_dir, tmp_path / "knowledge" / family / platform / "merged" / "api_surface.json"


def test_case_collision_existing_wins(tmp_path):
    """Phase A: Id.md pre-exists → Id keeps slug, ID gets -Operators suffix.

    Expected: skipped=1 (Id), generated=1 (ID-Operators.md), no ID.md created.
    """
    content_dir, _ = _make_case_collision_surface(tmp_path)
    # Pre-create Id.md to simulate a committed reference page
    (content_dir / "Id.md").write_text("existing-id-page", encoding="utf-8")

    result = run("fake", "net")

    assert result["skipped"] == 1, f"Expected 1 skipped, got {result['skipped']}"
    assert result["generated"] == 1, f"Expected 1 generated, got {result['generated']}"
    assert result["errors"] == 0, f"Expected 0 errors, got {result['errors']}"
    # The generated file must be ID-Operators.md
    assert (content_dir / "ID-Operators.md").exists(), "ID-Operators.md should have been created"
    # Use case-sensitive directory listing: on Windows NTFS, Path.exists("ID.md") would match
    # Id.md (case-insensitive FS), so we enumerate actual stored names to check distinctness.
    actual_names = {f.name for f in content_dir.iterdir() if f.suffix == ".md"}
    assert "ID.md" not in actual_names, (
        f"ID.md must NOT appear as a separate file entry (would collide with Id.md on Windows). "
        f"Actual files: {sorted(actual_names)}"
    )
    # Id.md must be unchanged
    assert (content_dir / "Id.md").read_text(encoding="utf-8") == "existing-id-page"


def test_case_collision_fresh_both_disambiguated(tmp_path):
    """Phase A: No pre-existing files → both entries get namespace-suffix disambiguation.

    Expected: generated=2, Id-Pdf.md + ID-Operators.md created, Id.md does NOT exist.
    """
    content_dir, _ = _make_case_collision_surface(tmp_path)
    # No pre-existing files

    result = run("fake", "net")

    assert result["generated"] == 2, f"Expected 2 generated, got {result['generated']}"
    assert result["errors"] == 0, f"Expected 0 errors, got {result['errors']}"
    # Both entries should get namespace suffixes since neither pre-exists
    assert (content_dir / "Id-Pdf.md").exists(), "Id-Pdf.md should have been created"
    assert (content_dir / "ID-Operators.md").exists(), "ID-Operators.md should have been created"
    # Un-suffixed Id.md must NOT be created (would be a Windows NTFS collision hazard)
    assert not (content_dir / "Id.md").exists(), "Id.md must NOT exist when both entries are fresh"


def test_case_collision_update_mode(tmp_path):
    """Phase A + B: --update mode; Id.md + ID-Operators.md pre-exist; ID modified.

    Expected: Id skipped (unchanged), ID-Operators.md updated (in modified_apis).
    """
    content_dir, _ = _make_case_collision_surface(tmp_path)
    (content_dir / "Id.md").write_text("existing-id-page", encoding="utf-8")
    (content_dir / "ID-Operators.md").write_text("existing-id-operators-page", encoding="utf-8")

    # Write knowledge_delta.json with ID as a modified API
    merged_dir = tmp_path / "knowledge" / "fake" / "net" / "merged"
    (merged_dir / "knowledge_delta.json").write_text(
        '{"modified_apis": ["ID"], "new_apis": [], "resurrected_apis": []}',
        encoding="utf-8",
    )

    result = run("fake", "net", update=True)

    # Id is not in modified_apis and its page exists → skipped
    assert result["skipped"] >= 1, f"Expected at least 1 skipped, got {result['skipped']}"
    # ID (now slug ID-Operators) is in modified_apis and page exists → updated
    assert result["updated"] == 1, f"Expected 1 updated, got {result['updated']}"
    assert result["errors"] == 0, f"Expected 0 errors, got {result['errors']}"
    # Id.md must be untouched
    assert (content_dir / "Id.md").read_text(encoding="utf-8") == "existing-id-page"


def test_case_collision_rebuild_all_mode(tmp_path):
    """Phase A + B: --rebuild-all; both pre-existing pages rebuilt; no un-suffixed ID.md created.

    Expected: updated=2, no ID.md file at any point.
    """
    content_dir, _ = _make_case_collision_surface(tmp_path)
    (content_dir / "Id.md").write_text("existing-id-page", encoding="utf-8")
    (content_dir / "ID-Operators.md").write_text("existing-id-operators-page", encoding="utf-8")

    result = run("fake", "net", rebuild_all=True, confirm_rebuild=True)

    assert result["updated"] == 2, f"Expected 2 updated, got {result['updated']}"
    assert result["errors"] == 0, f"Expected 0 errors, got {result['errors']}"
    # Use case-sensitive listing to verify no un-suffixed ID.md was written as a distinct entry
    actual_names = {f.name for f in content_dir.iterdir() if f.suffix == ".md"}
    assert "ID.md" not in actual_names, (
        f"ID.md must NOT appear as a separate file entry after rebuild-all. "
        f"Actual files: {sorted(actual_names)}"
    )
    # Both expected pages must still exist
    assert "Id.md" in actual_names, "Id.md should still exist after rebuild-all"
    assert "ID-Operators.md" in actual_names, "ID-Operators.md should still exist after rebuild-all"


def test_within_batch_dedup_defensive(tmp_path, capsys):
    """Phase C backstop: two entries with empty namespace both reach write loop.

    Phase A cannot disambiguate (no canonical_namespace) → Phase C catches the second entry.
    Expected: errors=1, only one page written, WITHIN-BATCH-DEDUP in stdout.
    """
    # Two entries that produce identical lower-slugs, neither with a namespace
    entries = [
        {
            "name": "Foo",
            "kind": "class_declaration",
            "visibility": "public",
            "canonical_namespace": "",  # empty → Phase A cannot disambiguate
            "description": "First Foo.",
            "methods": [],
            "properties": [],
        },
        {
            "name": "FOO",
            "kind": "class_declaration",
            "visibility": "public",
            "canonical_namespace": "",  # empty → Phase A cannot disambiguate
            "description": "Second FOO.",
            "methods": [],
            "properties": [],
        },
    ]
    _make_api_surface(tmp_path, entries, family="fake", platform="net")

    result = run("fake", "net")

    captured = capsys.readouterr()
    assert result["errors"] == 1, f"Expected 1 error from Phase C dedup, got {result['errors']}"
    assert "WITHIN-BATCH-DEDUP" in captured.out, "Phase C log line missing from stdout"
    # Only ONE of the two pages should have been written
    content_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / "net"
    md_files = [f for f in content_dir.glob("*.md") if f.stem.lower() == "foo"]
    assert len(md_files) == 1, f"Expected exactly 1 foo*.md page, found {len(md_files)}: {md_files}"


def test_pdf_net_id_regression(tmp_path):
    """Regression: Id (Aspose.Pdf) + ID (Aspose.Pdf.Operators) with Id.md pre-existing.

    Reproduces the exact pdf/net case-collision scenario (Id.md committed, ID never got a page).
    After the fix: Id.md must be unchanged; ID-Operators.md must be generated; no errors.
    """
    content_dir, _ = _make_case_collision_surface(tmp_path)
    original_id_content = "---\ntitle: Id\n---\nId page content.\n"
    (content_dir / "Id.md").write_text(original_id_content, encoding="utf-8")

    result = run("fake", "net")

    # No errors — case-collision handled cleanly
    assert result["errors"] == 0, f"Expected 0 errors (regression), got {result['errors']}"
    # Id.md must be unchanged (pre-existing wins)
    assert (content_dir / "Id.md").read_text(encoding="utf-8") == original_id_content, \
        "Id.md content must not be modified"
    # ID-Operators.md must have been generated (the missing page from the original bug)
    assert (content_dir / "ID-Operators.md").exists(), \
        "ID-Operators.md must be generated — this was the missing page in the original bug"
    # Use case-sensitive listing: on Windows NTFS Path.exists("ID.md") matches Id.md,
    # so enumerate actual stored names to verify no un-suffixed ID.md was written.
    actual_names = {f.name for f in content_dir.iterdir() if f.suffix == ".md"}
    assert "ID.md" not in actual_names, (
        f"ID.md must NOT appear as a separate file entry — "
        f"creating it would silently overwrite Id.md on Windows NTFS. "
        f"Actual files: {sorted(actual_names)}"
    )


def test_generate_grouped_index_gi01_uses_entry_slug(tmp_path):
    """GI-01 fix: generate_grouped_index() must emit 'ID-Operators' slug, not bare 'ID'.

    Before the fix: _build_grouped_index_body() used e.get("name") -> produced | `ID` |
    which links to ID/ (a broken path; the page is at ID-Operators/).
    After the fix: Phase A disambiguation inside generate_grouped_index() sets _slug_suffix
    on the ID entry so _entry_slug() returns 'ID-Operators'.
    """
    # generate_grouped_index() requires >= 5 entries; add padding beyond Id/ID
    extra_entries = [
        {"name": "Document", "kind": "class_declaration", "visibility": "public",
         "canonical_namespace": "Aspose.Pdf", "description": "Represents a PDF document.",
         "methods": [], "properties": []},
        {"name": "Page", "kind": "class_declaration", "visibility": "public",
         "canonical_namespace": "Aspose.Pdf", "description": "Represents a PDF page.",
         "methods": [], "properties": []},
        {"name": "Cell", "kind": "class_declaration", "visibility": "public",
         "canonical_namespace": "Aspose.Pdf.Text", "description": "Represents a table cell.",
         "methods": [], "properties": []},
    ]
    entries = [
        {"name": "Id", "kind": "class_declaration", "visibility": "public",
         "canonical_namespace": "Aspose.Pdf",
         "description": "Pair of byte strings that make up the /ID array in the PDF trailer.",
         "methods": [], "properties": []},
        {"name": "ID", "kind": "class_declaration", "visibility": "public",
         "canonical_namespace": "Aspose.Pdf.Operators",
         "description": "ID — Begin image data (after the inline-image dictionary).",
         "methods": [], "properties": []},
    ] + extra_entries
    _make_api_surface(tmp_path, entries, family="fake", platform="net")
    content_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / "net"
    content_dir.mkdir(parents=True, exist_ok=True)
    # Pre-create Id.md — this is the "winning" committed page that keeps its slug
    (content_dir / "Id.md").write_text("---\ntitle: Id\n---\nId page.\n", encoding="utf-8")
    # Create a minimal valid _index.md so generate_grouped_index() can read/update frontmatter
    (content_dir / "_index.md").write_text(
        "---\ntitle: Fake NET Reference\ncategories: []\n"
        "provenance:\n  content_origin: skill-generated\n  last_mechanism: skill\n"
        "  auto_updatable: true\n---\n\nIndex.\n",
        encoding="utf-8",
    )

    result = _br.generate_grouped_index("fake", "net", dry_run=True)

    assert not result.get("skipped"), (
        f"generate_grouped_index should not be skipped. Reason: {result.get('reason')}"
    )
    body = result.get("body_preview", "")
    # The table must use the namespace-disambiguated slug, not the raw class name
    assert "ID-Operators" in body, (
        f"Expected 'ID-Operators' slug in index body — GI-01 root fix not applied.\n"
        f"Body preview:\n{body}"
    )
    # Verify the raw 'ID' slug does NOT appear as a table cell anchor
    # (it would create a link to /ID/ which doesn't exist — only /ID-Operators/ does)
    import re as _re
    assert not _re.search(r"\| `ID` \|", body), (
        f"Bare '| `ID` |' cell must NOT appear — would produce a broken link.\n"
        f"Body preview:\n{body}"
    )

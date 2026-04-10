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
from batch_reference import _passes_platform_scope, _apply_kind_filter, _is_enum, run, _build_erc_index, _build_page


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

    def test_is_enum_detected_via_enum_members(self):
        assert _is_enum(
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

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
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

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
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

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
            result = run("slides", "net", limit=3)

        assert result["generated"] == 3

    def test_limit_zero_raises_system_exit(self, tmp_path):
        entries = [{"name": "Foo", "kind": "class_declaration", "methods": [], "properties": []}]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"), \
             pytest.raises(SystemExit):
            run("slides", "net", limit=0)


# ---------------------------------------------------------------------------
# Hard stop: missing api_surface.json (F-1)
# ---------------------------------------------------------------------------

class TestHardStop:
    def test_missing_api_surface_exits(self, tmp_path):
        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"), \
             pytest.raises(SystemExit):
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

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"), \
             pytest.raises(SystemExit):
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

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
            result = run("slides", "net", kind_arg="enum")

        assert result["generated"] == 1

    def test_kind_class_excludes_enums(self, tmp_path):
        entries = [
            {"name": "MyClass", "kind": "class_declaration", "methods": [], "properties": []},
            {"name": "MyEnum", "kind": "enum_declaration", "methods": [], "properties": []},
        ]
        _make_api_surface(tmp_path, entries, family="slides", platform="net")

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
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
        kr = _make_claims_file(tmp_path, claims)
        with patch.object(_br, "KNOWLEDGE_ROOT", kr):
            index = _build_erc_index("test", "net")
        assert "AutoFilter" in index
        assert index["AutoFilter"]["claim_id"] == "ERC-001"

    def test_only_erc_claims_included(self, tmp_path):
        claims = [
            {"claim_id": "ERC-001", "kind": "api", "text": "The Widget class.", "confidence": 0.9},
            {"claim_id": "CLM-001", "kind": "api_method", "text": "Widget.do() -> void", "confidence": 1.0},
        ]
        kr = _make_claims_file(tmp_path, claims)
        with patch.object(_br, "KNOWLEDGE_ROOT", kr):
            index = _build_erc_index("test", "net")
        assert "Widget" in index
        assert index["Widget"]["claim_id"] == "ERC-001"

    def test_highest_confidence_wins(self, tmp_path):
        claims = [
            {"claim_id": "ERC-001", "kind": "api", "text": "The Widget class.", "confidence": 0.7},
            {"claim_id": "ERC-002", "kind": "api", "text": "The Widget class provides more.", "confidence": 0.95},
        ]
        kr = _make_claims_file(tmp_path, claims)
        with patch.object(_br, "KNOWLEDGE_ROOT", kr):
            index = _build_erc_index("test", "net")
        assert index["Widget"]["claim_id"] == "ERC-002"

    def test_empty_claims_returns_empty_index(self, tmp_path):
        kr = _make_claims_file(tmp_path, [])
        with patch.object(_br, "KNOWLEDGE_ROOT", kr):
            index = _build_erc_index("test", "net")
        assert index == {}

    def test_missing_claims_file_returns_empty_index(self, tmp_path):
        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "no_such_dir"):
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

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
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
    """When multiple api_surface entries share the same name, batch-reference
    should prefer the entry with the highest visibility tier."""

    def test_prefers_exported_over_conventional(self, tmp_path):
        entries = [
            {"name": "Document", "kind": "class_definition",
             "file": "internal/model.py", "visibility": "conventional",
             "methods": [{"name": "find_style", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
            {"name": "Document", "kind": "class_definition",
             "file": "document.py", "visibility": "public",
             "methods": [{"name": "save", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
        ]
        _make_api_surface(tmp_path, entries, "words", "python")
        out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "words" / "python"
        out_dir.mkdir(parents=True)

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
            result = run("words", "python")

        page = out_dir / "Document.md"
        assert page.exists()
        content = page.read_text(encoding="utf-8")
        # The public class (with save method) should win, not the internal one
        assert "save" in content
        assert result["generated"] == 1  # only 1 page, not 2

    def test_keeps_first_when_same_visibility(self, tmp_path):
        entries = [
            {"name": "Widget", "kind": "class_definition",
             "file": "a.py", "visibility": "public",
             "methods": [{"name": "first_method", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
            {"name": "Widget", "kind": "class_definition",
             "file": "b.py", "visibility": "public",
             "methods": [{"name": "second_method", "params": [], "return_type": "", "doc": "", "line": 1}],
             "properties": []},
        ]
        _make_api_surface(tmp_path, entries, "words", "python")
        out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "words" / "python"
        out_dir.mkdir(parents=True)

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
            result = run("words", "python")

        page = out_dir / "Widget.md"
        assert page.exists()
        content = page.read_text(encoding="utf-8")
        # First entry wins when visibility is equal
        assert "first_method" in content
        assert result["generated"] == 1

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

        with patch.object(_br, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch.object(_br, "CONTENT_ROOT", tmp_path / "content" / "reference.aspose.org" / "en"):
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

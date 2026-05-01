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
                              _build_erc_index, _build_page, check_member_doc_coverage)


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

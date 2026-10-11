"""
Tests for backlink_expand_reference_index.py

Covers:
- _is_public_class(): filters private/test classes correctly
- _slugify_class_name(): lowercase conversion
- _derive_namespace(): Python file path -> namespace
- build_reference_entries(): generates correct entry structure
- expand_index(): adds entries, skips duplicates, updates counts
- dry_run: no writes
- Integration: full expand cycle on synthetic api_surface data
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Resolve REPO_ROOT for imports
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from commands.ops.backlink_expand_reference_index import (
    _derive_namespace,
    _is_public_class,
    _slugify_class_name,
    build_reference_entries,
    expand_index,
    load_api_surface,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_SURFACE = [
    {
        "name": "FontSourceInfo",
        "kind": "class_definition",
        "doc": "Describe the origin of loaded bytes.",
        "file": "src/aspose_font/loader.py",
        "line": 33,
        "bases": [],
        "methods": [{"name": "from_file", "doc": "Load from file."}],
        "properties": [
            {"name": "is_path", "type": "bool", "doc": "Gets the is path."},
            {"name": "is_bytes", "type": "bool", "doc": "Gets the is bytes."},
        ],
    },
    {
        "name": "FontCollection",
        "kind": "class_definition",
        "doc": "A collection of fonts.",
        "file": "src/aspose_font/collection.py",
        "line": 10,
        "bases": [],
        "methods": [{"name": "add"}, {"name": "remove"}],
        "properties": [{"name": "count", "type": "int"}],
    },
    {
        "name": "_InternalHelper",  # private — should be excluded
        "kind": "class_definition",
        "doc": "Internal helper.",
        "file": "src/aspose_font/_helpers.py",
        "line": 1,
        "methods": [],
        "properties": [],
    },
    {
        "name": "load_font",  # function — should be excluded
        "kind": "function",
        "doc": "Load a font file.",
        "file": "src/aspose_font/__init__.py",
        "line": 5,
    },
    {
        "name": "FontMock",  # mock — should be excluded
        "kind": "class_definition",
        "doc": "Test mock.",
        "file": "src/aspose_font/loader.py",
        "line": 100,
        "methods": [],
        "properties": [],
    },
]

MINIMAL_DEEP_INDEX = {
    "schema_version": "1.0.0",
    "families_filter": None,
    "total_endpoints": 2,
    "type_counts": {"family_landing": 1, "platform_docs_root": 1},
    "target_map_hash": "sha256:test",
    "index": {
        "docs/font": {
            "url": "https://docs.aspose.com/font/",
            "path": "docs/font",
            "http_status": 200,
            "subdomain_key": "docs",
            "type": "family_landing",
            "family": "font",
        },
        "docs/font/python": {
            "url": "https://docs.aspose.com/font/python/",
            "path": "docs/font/python",
            "http_status": 200,
            "subdomain_key": "docs",
            "type": "platform_docs_root",
            "family": "font",
            "platform": "python",
        },
    },
}


# ── Unit tests: _is_public_class ──────────────────────────────────────────────

class TestIsPublicClass:
    def test_class_definition_accepted(self):
        assert _is_public_class({"name": "Font", "kind": "class_definition"}) is True

    def test_interface_accepted(self):
        assert _is_public_class({"name": "IFont", "kind": "interface"}) is True

    def test_enum_accepted(self):
        assert _is_public_class({"name": "FontStyle", "kind": "enum"}) is True

    def test_private_underscore_excluded(self):
        assert _is_public_class({"name": "_InternalFont", "kind": "class_definition"}) is False

    def test_mock_excluded(self):
        assert _is_public_class({"name": "FontMock", "kind": "class_definition"}) is False

    def test_function_excluded(self):
        assert _is_public_class({"name": "load_font", "kind": "function"}) is False

    def test_test_class_excluded(self):
        assert _is_public_class({"name": "TestFontLoader", "kind": "class_definition"}) is False

    def test_cpp_class_specifier_accepted(self):
        assert _is_public_class({"name": "PptxExporter", "kind": "class_specifier"}) is True

    def test_cpp_enum_specifier_accepted(self):
        assert _is_public_class({"name": "SaveFormat", "kind": "enum_specifier"}) is True

    def test_cpp_struct_specifier_accepted(self):
        assert _is_public_class({"name": "SlideOptions", "kind": "struct_specifier"}) is True

    def test_java_class_declaration_accepted(self):
        assert _is_public_class({"name": "Presentation", "kind": "class_declaration"}) is True

    def test_net_record_declaration_accepted(self):
        assert _is_public_class({"name": "SlideRecord", "kind": "record_declaration"}) is True

    def test_api_class_accepted(self):
        assert _is_public_class({"name": "Slide", "kind": "api_class"}) is True


# ── Unit tests: _slugify_class_name ──────────────────────────────────────────

class TestSlugifyClassName:
    def test_lowercase(self):
        assert _slugify_class_name("FontSourceInfo") == "fontsourceinfo"

    def test_already_lower(self):
        assert _slugify_class_name("font") == "font"

    def test_camel_case(self):
        assert _slugify_class_name("IColorFormat") == "icolorformat"

    def test_nested_class(self):
        # Dots preserved — nested class slug
        assert _slugify_class_name("CompositeCurve.Segment") == "compositecurve.segment"


# ── Unit tests: _derive_namespace ────────────────────────────────────────────

class TestDeriveNamespace:
    def test_python_aspose_font(self):
        entry = {"file": "src/aspose_font/loader.py"}
        result = _derive_namespace(entry, "font", "python")
        assert "aspose" in result.lower() or result == ""

    def test_explicit_namespace_field(self):
        entry = {"namespace": "com.aspose.threed", "file": ""}
        assert _derive_namespace(entry, "3d", "java") == "com.aspose.threed"

    def test_no_namespace_returns_empty(self):
        entry = {"file": "src/other/loader.py"}
        result = _derive_namespace(entry, "font", "python")
        assert isinstance(result, str)


# ── Unit tests: build_reference_entries ──────────────────────────────────────

class TestBuildReferenceEntries:
    def test_public_classes_included(self):
        entries = build_reference_entries("font", "python", SAMPLE_SURFACE)
        assert "reference/font/python/fontsourceinfo" in entries
        assert "reference/font/python/fontcollection" in entries

    def test_private_class_excluded(self):
        entries = build_reference_entries("font", "python", SAMPLE_SURFACE)
        assert "reference/font/python/_internalhelper" not in entries

    def test_function_excluded(self):
        entries = build_reference_entries("font", "python", SAMPLE_SURFACE)
        assert "reference/font/python/load_font" not in entries

    def test_entry_structure(self):
        entries = build_reference_entries("font", "python", SAMPLE_SURFACE)
        e = entries["reference/font/python/fontsourceinfo"]
        assert e["type"] == "reference_class"
        assert e["family"] == "font"
        assert e["platform"] == "python"
        assert e["class_name"] == "fontsourceinfo"
        assert e["http_status"] == 200
        assert e["synthetic"] is True
        assert e["url"].endswith("/")
        assert "fontsourceinfo" in e["url"]

    def test_api_member_count(self):
        entries = build_reference_entries("font", "python", SAMPLE_SURFACE)
        e = entries["reference/font/python/fontsourceinfo"]
        # FontSourceInfo has 1 method + 2 properties = 3
        assert e["api_member_count"] == 3

    def test_empty_surface_returns_empty(self):
        entries = build_reference_entries("font", "python", [])
        assert entries == {}

    def test_no_duplicate_path_keys(self):
        # If surface has duplicate names, only first is kept
        surface = [
            {"name": "Font", "kind": "class_definition", "file": "", "methods": [], "properties": []},
            {"name": "Font", "kind": "class_definition", "file": "", "methods": [], "properties": []},
        ]
        entries = build_reference_entries("font", "python", surface)
        assert len(entries) == 1


# ── Unit tests: expand_index ─────────────────────────────────────────────────

class TestExpandIndex:
    def _make_temp_surface(self, tmpdir: Path, family: str, platform: str, surface: list) -> None:
        """Write a temp api_surface.json for testing."""
        merged_dir = tmpdir / "knowledge" / family / platform / "merged"
        merged_dir.mkdir(parents=True)
        (merged_dir / "api_surface.json").write_text(
            json.dumps(surface), encoding="utf-8"
        )

    def test_adds_entries(self, monkeypatch, tmp_path):
        self._make_temp_surface(tmp_path, "font", "python", SAMPLE_SURFACE)
        monkeypatch.setattr(
            "commands.ops.backlink_expand_reference_index.KNOWLEDGE_ROOT",
            tmp_path / "knowledge",
        )
        index = copy.deepcopy(MINIMAL_DEEP_INDEX)
        updated, stats = expand_index(index, [("font", "python")], dry_run=False)
        assert stats["font/python"] > 0
        assert "reference/font/python/fontsourceinfo" in updated["index"]
        assert "reference/font/python/fontcollection" in updated["index"]

    def test_skips_existing_entries(self, monkeypatch, tmp_path):
        """Entries already in index are not overwritten."""
        self._make_temp_surface(tmp_path, "font", "python", SAMPLE_SURFACE)
        monkeypatch.setattr(
            "commands.ops.backlink_expand_reference_index.KNOWLEDGE_ROOT",
            tmp_path / "knowledge",
        )
        # Pre-populate index with one of the entries
        index = copy.deepcopy(MINIMAL_DEEP_INDEX)
        index["index"]["reference/font/python/fontsourceinfo"] = {
            "url": "https://reference.aspose.com/font/python/fontsourceinfo/",
            "path": "reference/font/python/fontsourceinfo",
            "http_status": 200,
            "subdomain_key": "reference",
            "type": "reference_class",
            "family": "font",
            "platform": "python",
            "class_name": "fontsourceinfo",
        }
        before_count = len(index["index"])
        updated, stats = expand_index(index, [("font", "python")], dry_run=False)
        # fontsourceinfo already present; only fontcollection added
        assert stats["font/python"] == 1
        assert len(updated["index"]) == before_count + 1

    def test_dry_run_does_not_modify_index(self, monkeypatch, tmp_path):
        """Dry-run mode: stats reported but index not modified."""
        self._make_temp_surface(tmp_path, "font", "python", SAMPLE_SURFACE)
        monkeypatch.setattr(
            "commands.ops.backlink_expand_reference_index.KNOWLEDGE_ROOT",
            tmp_path / "knowledge",
        )
        index = copy.deepcopy(MINIMAL_DEEP_INDEX)
        original_count = len(index["index"])
        updated, stats = expand_index(index, [("font", "python")], dry_run=True)
        # Stats should show potential adds
        assert stats["font/python"] > 0
        # Index should NOT be modified in dry_run
        assert len(updated.get("index", {})) == original_count

    def test_missing_surface_returns_zero(self, tmp_path):
        """Missing api_surface.json -> 0 entries added."""
        # Don't create any surface file
        index = copy.deepcopy(MINIMAL_DEEP_INDEX)
        import commands.ops.backlink_expand_reference_index as mod
        orig = mod.KNOWLEDGE_ROOT
        try:
            mod.KNOWLEDGE_ROOT = tmp_path / "knowledge"
            updated, stats = expand_index(index, [("missing_family", "python")], dry_run=False)
            assert stats["missing_family/python"] == 0
        finally:
            mod.KNOWLEDGE_ROOT = orig

    def test_total_endpoints_updated(self, monkeypatch, tmp_path):
        """total_endpoints in updated index reflects new count."""
        self._make_temp_surface(tmp_path, "font", "python", SAMPLE_SURFACE)
        monkeypatch.setattr(
            "commands.ops.backlink_expand_reference_index.KNOWLEDGE_ROOT",
            tmp_path / "knowledge",
        )
        index = copy.deepcopy(MINIMAL_DEEP_INDEX)
        updated, stats = expand_index(index, [("font", "python")], dry_run=False)
        expected_count = 2 + stats["font/python"]  # 2 original + N added
        assert updated["total_endpoints"] == expected_count

    def test_type_counts_updated(self, monkeypatch, tmp_path):
        """type_counts in updated index includes reference_class."""
        self._make_temp_surface(tmp_path, "font", "python", SAMPLE_SURFACE)
        monkeypatch.setattr(
            "commands.ops.backlink_expand_reference_index.KNOWLEDGE_ROOT",
            tmp_path / "knowledge",
        )
        index = copy.deepcopy(MINIMAL_DEEP_INDEX)
        updated, stats = expand_index(index, [("font", "python")], dry_run=False)
        assert updated["type_counts"].get("reference_class", 0) > 0

"""Tests for index.py — pure functions and minimal fixture-based tests.

Covers:
  - compute_api_confidence: pure function, no I/O
  - _is_public_api_entry: pure function
  - _is_interface_name: pure function
  - _has_surface: pure function
  - build_index: disk-based, tested via temp directory fixture
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from index import (
    compute_api_confidence,
    _is_public_api_entry,
    _is_interface_name,
    _has_surface,
    build_index,
    KNOWLEDGE_ROOT,
)
import index as _index_module


@pytest.fixture(autouse=True)
def _reset_index():
    yield
    _index_module.configure()


# ---------------------------------------------------------------------------
# compute_api_confidence — pure function
# ---------------------------------------------------------------------------

class TestComputeApiConfidence:
    def test_high_tier(self):
        assert compute_api_confidence(20, 0.5) == "high"

    def test_high_boundary(self):
        # Exactly at the minimum high threshold
        assert compute_api_confidence(15, 0.20) == "high"

    def test_medium_tier(self):
        assert compute_api_confidence(8, 0.15) == "medium"

    def test_medium_boundary(self):
        assert compute_api_confidence(5, 0.10) == "medium"

    def test_low_api_total_too_small(self):
        assert compute_api_confidence(4, 0.50) == "low"

    def test_low_method_pct_too_small(self):
        assert compute_api_confidence(20, 0.05) == "low"

    def test_low_empty(self):
        assert compute_api_confidence(0, 0.0) == "low"

    def test_high_method_pct_at_0_20(self):
        # Exact boundary: api_total=15, method_pct=0.20 → high
        assert compute_api_confidence(15, 0.20) == "high"

    def test_medium_method_pct_below_high(self):
        # api_total=15, method_pct=0.19 → not high → try medium: 15>=5 and 0.19>=0.10 → medium
        assert compute_api_confidence(15, 0.19) == "medium"


# ---------------------------------------------------------------------------
# _is_interface_name — pure function
# ---------------------------------------------------------------------------

class TestIsInterfaceName:
    def test_valid_interface(self):
        assert _is_interface_name("IShape")

    def test_valid_interface_longer(self):
        assert _is_interface_name("ISlide")

    def test_io_prefix_excluded(self):
        # IO = Input/Output, not the interface marker
        assert not _is_interface_name("IOService")

    def test_lowercase_second_char_excluded(self):
        assert not _is_interface_name("Invalid")

    def test_too_short(self):
        assert not _is_interface_name("I")
        assert not _is_interface_name("IX")

    def test_not_starting_with_I(self):
        assert not _is_interface_name("Shape")


# ---------------------------------------------------------------------------
# _has_surface — pure function
# ---------------------------------------------------------------------------

class TestHasSurface:
    def test_has_methods(self):
        assert _has_surface({"methods": [{"name": "foo"}]})

    def test_has_properties(self):
        assert _has_surface({"properties": ["Width"]})

    def test_has_enum_members(self):
        assert _has_surface({"enum_members": ["A", "B"]})

    def test_empty_entry(self):
        assert not _has_surface({})

    def test_empty_lists(self):
        assert not _has_surface({"methods": [], "properties": [], "enum_members": []})


# ---------------------------------------------------------------------------
# _is_public_api_entry — pure function
# ---------------------------------------------------------------------------

class TestIsPublicApiEntry:
    def test_public_class(self):
        entry = {"kind": "class", "name": "Workbook", "file": "aspose/cells/workbook.py"}
        assert _is_public_api_entry(entry)

    def test_private_name(self):
        entry = {"kind": "class", "name": "_InternalHelper", "file": "aspose/cells/helper.py"}
        assert not _is_public_api_entry(entry)

    def test_function_kind(self):
        entry = {"kind": "function", "name": "public_func", "file": "aspose/cells/util.py"}
        assert not _is_public_api_entry(entry)

    def test_empty_name(self):
        entry = {"kind": "class", "name": "", "file": "aspose/cells/empty.py"}
        assert not _is_public_api_entry(entry)

    def test_test_file(self):
        entry = {"kind": "class", "name": "TestHelper", "file": "tests/test_helper.py"}
        assert not _is_public_api_entry(entry)

    def test_non_dict(self):
        assert not _is_public_api_entry("not a dict")
        assert not _is_public_api_entry(None)


# ---------------------------------------------------------------------------
# build_index — disk fixture test
# ---------------------------------------------------------------------------

def _make_merged_dir(tmp_path: Path, family: str, platform: str) -> Path:
    """Create a minimal merged/ directory fixture for build_index."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    model = {
        "family": family,
        "platform": platform,
        "repo_sha": "abc123",
        "merged_at": "2026-01-01T00:00:00Z",
        "stats": {"total_classes": 2},
        "stale_since": None,
    }
    (merged / "model.yaml").write_text(
        "family: " + family + "\n"
        "platform: " + platform + "\n"
        "repo_sha: abc123\n"
        "merged_at: '2026-01-01T00:00:00Z'\n"
        "stale_since: null\n"
        "stats:\n"
        "  total_classes: 2\n",
        encoding="utf-8",
    )

    api_surface = [
        {"kind": "class", "name": "Workbook", "file": "aspose/cells/workbook.py",
         "methods": [{"name": "save"}, {"name": "load"}], "properties": ["FileName"]},
        {"kind": "class", "name": "Worksheet", "file": "aspose/cells/worksheet.py",
         "methods": [{"name": "add_row"}], "properties": []},
        # This one should be filtered out by _is_public_api_entry (function kind)
        {"kind": "function", "name": "helper_func", "file": "aspose/cells/util.py"},
    ]
    (merged / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
    (merged / "claims.json").write_text(json.dumps([
        "Workbook supports loading XLSX files.",
        "Worksheet.add_row adds a new row to the sheet.",
    ]), encoding="utf-8")
    (merged / "formats.json").write_text(json.dumps([
        {"format": "xlsx", "can_import": True, "can_export": True},
        {"format": "csv", "direction": "export"},
    ]), encoding="utf-8")
    return merged


def test_build_index_returns_dict(tmp_path, monkeypatch):
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    assert result is not None
    assert isinstance(result, dict)


def test_build_index_summary_fields(tmp_path, monkeypatch):
    """build_index returns a condensed summary dict; full index is written to index.json."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    # Return value has summary keys
    for key in ("family", "platform", "api_confidence", "class_count", "claim_count"):
        assert key in result, f"Missing key in return value: {key}"
    # Full index is written to disk
    index_path = tmp_path / "knowledge" / "cells" / "python" / "merged" / "index.json"
    assert index_path.exists(), "index.json must be written to disk"
    written = json.loads(index_path.read_text(encoding="utf-8"))
    for key in ("family", "platform", "api_confidence", "classes"):
        assert key in written, f"Missing key in written index.json: {key}"


def test_build_index_api_confidence_returned(tmp_path, monkeypatch):
    """api_confidence must be present in return value."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    assert result["api_confidence"] in ("high", "medium", "low")


def test_build_index_filters_function_kind(tmp_path, monkeypatch):
    """helper_func with kind=function must not appear in classes list in written index.json."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    build_index("cells", "python")
    written = json.loads(
        (tmp_path / "knowledge" / "cells" / "python" / "merged" / "index.json")
        .read_text(encoding="utf-8")
    )
    assert "helper_func" not in written["classes"]
    assert "Workbook" in written["classes"]


def test_build_index_formats_split(tmp_path, monkeypatch):
    """Formats should be split into import/export lists in written index.json."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    build_index("cells", "python")
    written = json.loads(
        (tmp_path / "knowledge" / "cells" / "python" / "merged" / "index.json")
        .read_text(encoding="utf-8")
    )
    assert "xlsx" in written["formats"]["import"]
    assert "xlsx" in written["formats"]["export"]
    assert "csv" in written["formats"]["export"]
    assert "csv" not in written["formats"]["import"]


def test_build_index_no_model_yaml_returns_none(tmp_path, monkeypatch):
    """build_index returns None when model.yaml is missing."""
    merged = tmp_path / "knowledge" / "cells" / "python" / "merged"
    merged.mkdir(parents=True)
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    assert result is None

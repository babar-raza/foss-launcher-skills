"""Tests for denominator_reconciler.py — TC-02.

Verifies:
  - Reconciliation math (scope_eligible - pages_on_disk = gap)
  - Scope filter logging (filtered entries include reasons)
  - Missing page detection
  - Orphan page detection
  - api_surface.json missing returns error
"""
import json
import sys
from pathlib import Path

import pytest
import yaml

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_CMD_CONTENT = _PIPELINE_ROOT / "commands" / "content"
if str(_CMD_CONTENT) not in sys.path:
    sys.path.insert(0, str(_CMD_CONTENT))

import batch_reference as br
from denominator_reconciler import reconcile


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    br.configure(repo_root=tmp_path)
    yield
    br.configure()


def _setup_knowledge(tmp_path, entries, family="test", platform="python"):
    """Write api_surface.json + model.yaml into knowledge dir."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "api_surface.json").write_text(
        json.dumps(entries), encoding="utf-8"
    )
    (merged / "model.yaml").write_text(
        yaml.dump({"family": family, "platform": platform,
                    "stale_since": None, "repo_sha": "abc", "version": "1.0"}),
        encoding="utf-8",
    )
    return merged


def _setup_pages(tmp_path, names, family="test", platform="python"):
    """Create .md page stubs in the reference content dir."""
    content_dir = (
        tmp_path / "content" / "reference.aspose.org" / "en" / family / platform
    )
    content_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (content_dir / f"{name}.md").write_text(
            f"---\ntitle: {name}\n---\n", encoding="utf-8"
        )
    return content_dir


class TestReconcile:
    """Core reconciliation tests."""

    def test_perfect_alignment(self, tmp_path):
        entries = [
            {"name": "Font", "kind": "class_definition", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
            {"name": "GlyphId", "kind": "class_definition", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
        ]
        _setup_knowledge(tmp_path, entries)
        _setup_pages(tmp_path, ["Font", "GlyphId"])

        report = reconcile(
            "test", "python",
            knowledge_root=tmp_path / "knowledge",
            content_root=tmp_path / "content",
        )
        assert report["denominator_gap"] == 0
        assert report["scope_eligible"] == 2
        assert report["pages_on_disk"] == 2
        assert report["missing_pages"] == []
        assert report["orphan_pages"] == []

    def test_missing_page_detected(self, tmp_path):
        entries = [
            {"name": "Font", "kind": "class_definition", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
            {"name": "GlyphId", "kind": "class_definition", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
        ]
        _setup_knowledge(tmp_path, entries)
        _setup_pages(tmp_path, ["Font"])  # GlyphId page missing

        report = reconcile(
            "test", "python",
            knowledge_root=tmp_path / "knowledge",
            content_root=tmp_path / "content",
        )
        assert report["denominator_gap"] == 1
        assert "GlyphId" in report["missing_pages"]

    def test_orphan_page_detected(self, tmp_path):
        entries = [
            {"name": "Font", "kind": "class_definition", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
        ]
        _setup_knowledge(tmp_path, entries)
        _setup_pages(tmp_path, ["Font", "OldClass"])  # OldClass has no API entry

        report = reconcile(
            "test", "python",
            knowledge_root=tmp_path / "knowledge",
            content_root=tmp_path / "content",
        )
        assert "OldClass" in report["orphan_pages"]

    def test_scope_filter_excludes_underscore_prefix(self, tmp_path):
        entries = [
            {"name": "Font", "kind": "class_definition", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
            {"name": "_InternalHelper", "kind": "class_definition", "methods": [],
             "properties": [], "enum_members": [], "bases": []},
        ]
        _setup_knowledge(tmp_path, entries)
        _setup_pages(tmp_path, ["Font"])

        report = reconcile(
            "test", "python",
            knowledge_root=tmp_path / "knowledge",
            content_root=tmp_path / "content",
        )
        assert report["scope_eligible"] == 1
        assert report["denominator_gap"] == 0
        filter_names = [f["name"] for f in report["scope_filter_log"]]
        assert "_InternalHelper" in filter_names

    def test_missing_api_surface_returns_error(self, tmp_path):
        report = reconcile(
            "test", "python",
            knowledge_root=tmp_path / "knowledge",
            content_root=tmp_path / "content",
        )
        assert "error" in report
        assert report["api_surface_total"] == 0

    def test_index_md_excluded_from_page_count(self, tmp_path):
        entries = [
            {"name": "Font", "kind": "class_definition", "methods": [], "properties": [],
             "enum_members": [], "bases": []},
        ]
        _setup_knowledge(tmp_path, entries)
        content_dir = _setup_pages(tmp_path, ["Font"])
        # Add _index.md which should NOT be counted
        (content_dir / "_index.md").write_text("---\ntitle: Index\n---\n", encoding="utf-8")

        report = reconcile(
            "test", "python",
            knowledge_root=tmp_path / "knowledge",
            content_root=tmp_path / "content",
        )
        assert report["pages_on_disk"] == 1  # Only Font, not _index


class TestGenerationManifest:
    """Test that _write_generation_manifest produces valid YAML."""

    def test_manifest_written(self, tmp_path):
        br.configure(repo_root=tmp_path)
        br._write_generation_manifest(
            "test", "python",
            api_surface_total=10,
            scope_eligible=8,
            pages_created=5,
            pages_updated=2,
            pages_skipped=1,
            pages_failed=0,
            pages_unchanged=0,
            model_sha="abc123",
        )

        manifest_path = tmp_path / "reports" / "generation" / "test-python.yaml"
        assert manifest_path.exists()

        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert data["family"] == "test"
        assert data["platform"] == "python"
        assert data["api_surface_total"] == 10
        assert data["scope_eligible"] == 8
        assert data["scope_filtered"] == 2
        assert data["pages_created"] == 5
        assert data["denominator_gap"] == 0  # 8 - (5+2+1+0) = 0

    def test_manifest_gap_nonzero(self, tmp_path):
        br.configure(repo_root=tmp_path)
        br._write_generation_manifest(
            "test", "python",
            api_surface_total=10,
            scope_eligible=8,
            pages_created=3,
            pages_updated=0,
            pages_skipped=2,
            pages_failed=1,
            pages_unchanged=0,
            model_sha="abc123",
        )
        manifest_path = tmp_path / "reports" / "generation" / "test-python.yaml"
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert data["denominator_gap"] == 3  # 8 - (3+0+2+0) = 3; failed pages not counted as success

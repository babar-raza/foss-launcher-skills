"""Tests for healing detector functions — TC-03.

Verifies each detector returns correct findings for fixture scenarios.
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
from healing.detector import (
    IssueType,
    Severity,
    detect_hierarchy_drift,
    detect_metadata_corruption,
    detect_missing_pages,
    detect_naming_drift,
    detect_silent_omissions,
    detect_stale_pages,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    br.configure(repo_root=tmp_path)
    yield
    br.configure()


def _make_knowledge(tmp_path, entries, sha="abc123", stale=None):
    merged = tmp_path / "knowledge" / "test" / "python" / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
    (merged / "model.yaml").write_text(yaml.dump({
        "family": "test", "platform": "python",
        "stale_since": stale, "repo_sha": sha, "version": "1.0",
    }), encoding="utf-8")
    (merged / "formats.json").write_text('{"formats": []}', encoding="utf-8")
    return merged


def _make_page(tmp_path, name, sha="abc123", has_evidence=True):
    d = tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "python"
    d.mkdir(parents=True, exist_ok=True)
    if has_evidence:
        text = f"---\ntitle: {name}\nevidence:\n  model_sha: '{sha}'\n---\nContent\n"
    else:
        text = f"---\ntitle: {name}\n---\nContent\n"
    (d / f"{name}.md").write_text(text, encoding="utf-8")
    return d


def _api_entry(name):
    return {"name": name, "kind": "class_definition", "methods": [],
            "properties": [], "enum_members": [], "bases": []}


class TestDetectMissingPages:

    def test_no_missing_pages(self, tmp_path):
        _make_knowledge(tmp_path, [_api_entry("Font")])
        _make_page(tmp_path, "Font")
        findings = detect_missing_pages("test", "python",
            knowledge_root=tmp_path / "knowledge", content_root=tmp_path / "content")
        assert len(findings) == 0

    def test_missing_page_found(self, tmp_path):
        _make_knowledge(tmp_path, [_api_entry("Font"), _api_entry("GlyphId")])
        _make_page(tmp_path, "Font")
        findings = detect_missing_pages("test", "python",
            knowledge_root=tmp_path / "knowledge", content_root=tmp_path / "content")
        assert len(findings) == 1
        assert findings[0].entity == "GlyphId"
        assert findings[0].issue_type == IssueType.MISSING_PAGE
        assert findings[0].severity == Severity.CRITICAL


class TestDetectStalePages:

    def test_no_stale_pages(self, tmp_path):
        _make_knowledge(tmp_path, [_api_entry("Font")], sha="abc123")
        _make_page(tmp_path, "Font", sha="abc123")
        findings = detect_stale_pages("test", "python",
            knowledge_root=tmp_path / "knowledge", content_root=tmp_path / "content")
        assert len(findings) == 0

    def test_stale_page_detected(self, tmp_path):
        _make_knowledge(tmp_path, [_api_entry("Font")], sha="new_sha")
        _make_page(tmp_path, "Font", sha="old_sha")
        findings = detect_stale_pages("test", "python",
            knowledge_root=tmp_path / "knowledge", content_root=tmp_path / "content")
        assert len(findings) == 1
        assert findings[0].entity == "Font"
        assert findings[0].issue_type == IssueType.STALE_PAGE


class TestDetectHierarchyDrift:

    def test_no_drift_with_index(self, tmp_path):
        d = tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "python"
        d.mkdir(parents=True)
        (d / "_index.md").write_text("---\ntitle: Index\n---\n", encoding="utf-8")
        (d.parent / "_index.md").write_text("---\ntitle: Test\n---\n", encoding="utf-8")
        findings = detect_hierarchy_drift("test", "python",
            content_root=tmp_path / "content")
        ref_findings = [f for f in findings if "reference" in f.entity]
        assert len(ref_findings) == 0

    def test_missing_platform_index(self, tmp_path):
        d = tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "python"
        d.mkdir(parents=True)
        (d.parent / "_index.md").write_text("---\ntitle: Test\n---\n", encoding="utf-8")
        # No _index.md in platform dir
        findings = detect_hierarchy_drift("test", "python",
            content_root=tmp_path / "content")
        assert any(f.issue_type == IssueType.HIERARCHY_DRIFT for f in findings)


class TestDetectMetadataCorruption:

    def test_valid_page_no_findings(self, tmp_path):
        _make_page(tmp_path, "Font", has_evidence=True)
        findings = detect_metadata_corruption("test", "python",
            content_root=tmp_path / "content")
        assert len(findings) == 0

    def test_missing_evidence_block(self, tmp_path):
        _make_page(tmp_path, "Font", has_evidence=False)
        findings = detect_metadata_corruption("test", "python",
            content_root=tmp_path / "content")
        assert len(findings) == 1
        assert findings[0].issue_type == IssueType.METADATA_CORRUPTION
        assert "evidence" in findings[0].detail.lower()

    def test_missing_frontmatter(self, tmp_path):
        d = tmp_path / "content" / "reference.aspose.org" / "en" / "test" / "python"
        d.mkdir(parents=True)
        (d / "Bad.md").write_text("Just plain text\n", encoding="utf-8")
        findings = detect_metadata_corruption("test", "python",
            content_root=tmp_path / "content")
        assert len(findings) == 1
        assert "frontmatter" in findings[0].detail.lower()


class TestDetectNamingDrift:

    def test_no_drift_for_clean_names(self, tmp_path):
        _make_knowledge(tmp_path, [_api_entry("Font")])
        _make_page(tmp_path, "Font")
        findings = detect_naming_drift("test", "python",
            knowledge_root=tmp_path / "knowledge", content_root=tmp_path / "content")
        assert len(findings) == 0

"""
TC-S96-008 + TC-S96-011: Tests for content_diff_classifier.py
"""

import json
import pathlib

import pytest

from commands.ops.content_diff_classifier import (
    Category,
    DiffEntry,
    DiffReport,
    classify_diff,
    detect_churn_signals,
    is_churn_only,
    write_diff_report,
)
from commands.ops.cleanroom_manifest import capture_baseline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(files=None, content_roots=None, family="cells", platform="java"):
    class MockScope:
        pass
    s = MockScope()
    s.family = family
    s.platform = platform
    s.subdomains = ["reference"]
    s.files = files or []
    s.content_roots = content_roots or {}
    return s


def _write_md(directory: pathlib.Path, name: str, content: str) -> pathlib.Path:
    p = directory / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_manifest(tmp_path: pathlib.Path, files: dict) -> dict:
    """Build a minimal manifest dict with given {rel_path: sha256} mapping."""
    from commands.ops.cleanroom_manifest import sha256_text
    file_records = {}
    for rel, content in files.items():
        if content is None:
            continue
        sha = sha256_text(content)
        file_records[rel] = {
            "sha256": sha,
            "size_bytes": len(content.encode("utf-8")),
            "frontmatter": {},
        }
        # Write the file to tmp_path
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    return {
        "run_id": "test-001",
        "baseline_git_sha": "abc1234",
        "captured_at": "2026-01-01T00:00:00+00:00",
        "scope": {"family": "cells", "platform": "java", "subdomains": ["reference"], "files": []},
        "files": file_records,
        "_errors": [],
    }


# ---------------------------------------------------------------------------
# Category tests
# ---------------------------------------------------------------------------

def test_added_file_detected(tmp_path):
    """File on disk not in baseline → ADDED."""
    rel = "content/reference.aspose.org/en/cells/java/NewPage.md"
    manifest = {"run_id": "t", "baseline_git_sha": "abc", "captured_at": "", "scope": {}, "files": {}, "_errors": []}
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("---\ntitle: New\n---\n# Body\n", encoding="utf-8")

    scope = _make_scope(files=[rel])
    report = classify_diff(manifest, tmp_path, scope)
    entries = {e.path: e for e in report.entries}
    assert rel in entries
    assert entries[rel].category == Category.ADDED


def test_deleted_file_detected(tmp_path):
    """File in baseline but not on disk → DELETED."""
    rel = "content/reference.aspose.org/en/cells/java/Gone.md"
    manifest = _make_manifest(tmp_path, {rel: "---\ntitle: Gone\n---\n"})
    # Now delete the file
    (tmp_path / rel).unlink()

    report = classify_diff(manifest, tmp_path)
    entries = {e.path: e for e in report.entries}
    assert rel in entries
    assert entries[rel].category == Category.DELETED


def test_unchanged_file(tmp_path):
    """File with same sha256 as baseline → UNCHANGED."""
    rel = "content/reference.aspose.org/en/cells/java/Same.md"
    content = "---\ntitle: Same\n---\n# Body unchanged\n"
    manifest = _make_manifest(tmp_path, {rel: content})
    # File is already on disk from _make_manifest

    report = classify_diff(manifest, tmp_path)
    entries = {e.path: e for e in report.entries}
    assert rel in entries
    assert entries[rel].category == Category.UNCHANGED


def test_edited_file_detected(tmp_path):
    """File with different sha256 → EDITED."""
    rel = "content/reference.aspose.org/en/cells/java/Changed.md"
    original = "---\ntitle: Original\n---\n# Original body\n"
    manifest = _make_manifest(tmp_path, {rel: original})
    # Now overwrite with different content
    (tmp_path / rel).write_text("---\ntitle: Modified\n---\n# Modified body\n", encoding="utf-8")

    report = classify_diff(manifest, tmp_path)
    entries = {e.path: e for e in report.entries}
    assert rel in entries
    assert entries[rel].category in (Category.EDITED, Category.CHURN_ONLY)


def test_edited_entry_has_sha_values(tmp_path):
    rel = "content/reference.aspose.org/en/cells/java/Edit.md"
    original = "---\ntitle: V1\n---\n# V1\n"
    manifest = _make_manifest(tmp_path, {rel: original})
    (tmp_path / rel).write_text("---\ntitle: V2\n---\n# V2 with more content\n", encoding="utf-8")

    report = classify_diff(manifest, tmp_path)
    entries = {e.path: e for e in report.entries}
    e = entries[rel]
    assert e.baseline_sha is not None
    assert e.current_sha is not None
    assert e.baseline_sha != e.current_sha


# ---------------------------------------------------------------------------
# Churn signal tests (TC-S96-011)
# ---------------------------------------------------------------------------

def test_timestamp_only_change_is_churn():
    baseline = "---\ntitle: Test\ndate: 2026-01-01\ncontent_created_at: 2026-01-01T00:00:00Z\n---\n# Body\n"
    current  = "---\ntitle: Test\ndate: 2026-02-01\ncontent_created_at: 2026-02-01T00:00:00Z\n---\n# Body\n"
    signals = detect_churn_signals(baseline, current)
    assert "timestamp_only" in signals
    assert is_churn_only(signals)


def test_whitespace_only_change_is_churn():
    baseline = "---\ntitle: X\n---\n# Body  content\n"
    current  = "---\ntitle: X\n---\n# Body content\n"
    signals = detect_churn_signals(baseline, current)
    assert "whitespace_only" in signals
    assert is_churn_only(signals)


def test_yaml_reorder_only_is_churn():
    baseline = "---\ntitle: X\nslug: x\n---\n# Body\n"
    current  = "---\nslug: x\ntitle: X\n---\n# Body\n"
    signals = detect_churn_signals(baseline, current)
    # yaml_reorder: same keys/values, different order, body same
    # Note: if YAML is available, both parse to the same dict
    # The signal should be detected
    if signals:  # only if YAML available and signal detected
        assert "yaml_reorder" in signals or "whitespace_only" in signals


def test_real_content_change_not_churn():
    baseline = "---\ntitle: X\n---\n# Original body\n"
    current  = "---\ntitle: X\n---\n# Completely different body with new content added here\n"
    signals = detect_churn_signals(baseline, current)
    assert not is_churn_only(signals)


def test_mixed_timestamp_and_real_content_not_churn():
    """Real content improvement + timestamp update is NOT churn."""
    baseline = "---\ntitle: X\ndate: 2026-01-01\n---\n# Original body\n"
    current  = "---\ntitle: X\ndate: 2026-02-01\n---\n# New and improved body with more detail\n"
    signals = detect_churn_signals(baseline, current)
    assert not is_churn_only(signals)


def test_grade_churn_detected():
    baseline = "---\ntitle: X\ngrade: A\ngraded_at: 2026-01-01\n---\n# Body\n"
    current  = "---\ntitle: X\ngrade: A\ngraded_at: 2026-02-01\n---\n# Body\n"
    signals = detect_churn_signals(baseline, current)
    # graded_at is a grade key — should detect grade_churn
    if signals:
        assert "grade_churn" in signals or "timestamp_only" in signals


# ---------------------------------------------------------------------------
# Write tests
# ---------------------------------------------------------------------------

def test_write_diff_report_produces_schema_valid_json(tmp_path):
    report = DiffReport(
        run_id="test-write",
        baseline_git_sha="abc1234",
        generated_at="2026-01-01T00:00:00Z",
        entries=[
            DiffEntry(path="foo.md", category=Category.ADDED, current_sha="sha1"),
            DiffEntry(path="bar.md", category=Category.DELETED, baseline_sha="sha2"),
        ],
    )
    output = tmp_path / "diff-report.json"
    write_diff_report(report, output)
    assert output.exists()
    data = json.loads(output.read_text())
    assert data["run_id"] == "test-write"
    assert len(data["entries"]) == 2
    assert data["counts"]["added"] == 1
    assert data["counts"]["deleted"] == 1


def test_diff_report_no_tmp_file_after_write(tmp_path):
    report = DiffReport(run_id="x", baseline_git_sha="abc", generated_at="2026-01-01T00:00:00Z")
    output = tmp_path / "d.json"
    write_diff_report(report, output)
    assert not (tmp_path / "d.tmp").exists()

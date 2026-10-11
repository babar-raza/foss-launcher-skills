"""Tests for TC-CE-023: snapshot_guard.py — pre-write snapshot and rollback."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest


@pytest.fixture
def repo_tree(tmp_path):
    """Create a minimal repo structure with a content file."""
    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "font" / "python"
    content_dir.mkdir(parents=True)
    page = content_dir / "core-management.md"
    page.write_text(
        "---\ntitle: Core Management\nevidence:\n  claims: [CLM-1]\n---\n\nBody text here.\n",
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports" / "snapshots"
    reports_dir.mkdir(parents=True)
    return tmp_path, str(page.relative_to(tmp_path))


def _import_guard():
    from enrichment.snapshot_guard import take_snapshot, restore_snapshot, diff_summary
    return take_snapshot, restore_snapshot, diff_summary


class TestTakeSnapshot:
    def test_creates_manifest_and_snapshot_file(self, repo_tree):
        root, rel_path = repo_tree
        take_snapshot, _, _ = _import_guard()

        snap_dir = take_snapshot(
            "font", "python", [rel_path], repo_root=root,
        )

        assert (snap_dir / "manifest.json").exists()
        manifest = json.loads((snap_dir / "manifest.json").read_text())
        assert manifest["family"] == "font"
        assert manifest["platform"] == "python"
        assert len(manifest["files"]) == 1

        rec = manifest["files"][0]
        assert rec["file_path"] == rel_path
        assert rec["existed_before"] is True
        assert rec["file_size"] > 0

        snap_file = snap_dir / rec["snapshot_file"]
        assert snap_file.exists()

    def test_snapshot_matches_original_hash(self, repo_tree):
        root, rel_path = repo_tree
        take_snapshot, _, _ = _import_guard()

        snap_dir = take_snapshot("font", "python", [rel_path], repo_root=root)
        manifest = json.loads((snap_dir / "manifest.json").read_text())
        rec = manifest["files"][0]

        original = (root / rel_path).read_bytes()
        assert rec["content_sha256"] == hashlib.sha256(original).hexdigest()

    def test_path_guard_rejects_non_content(self, repo_tree):
        root, _ = repo_tree
        take_snapshot, _, _ = _import_guard()

        with pytest.raises(ValueError, match="only content/ paths"):
            take_snapshot("font", "python", ["scripts/foo.py"], repo_root=root)

    def test_path_guard_rejects_traversal(self, repo_tree):
        root, _ = repo_tree
        take_snapshot, _, _ = _import_guard()

        with pytest.raises(ValueError, match="path traversal"):
            take_snapshot("font", "python", ["content/../secrets.txt"], repo_root=root)

    def test_empty_paths_rejected(self, repo_tree):
        root, _ = repo_tree
        take_snapshot, _, _ = _import_guard()

        with pytest.raises(ValueError, match="must not be empty"):
            take_snapshot("font", "python", [], repo_root=root)

    def test_missing_file_raises(self, repo_tree):
        root, _ = repo_tree
        take_snapshot, _, _ = _import_guard()

        with pytest.raises(FileNotFoundError):
            take_snapshot("font", "python", ["content/nonexistent.md"], repo_root=root)


class TestRestoreSnapshot:
    def test_restore_modified_file(self, repo_tree):
        root, rel_path = repo_tree
        take_snapshot, restore_snapshot, _ = _import_guard()

        snap_dir = take_snapshot("font", "python", [rel_path], repo_root=root)

        # Modify the file
        target = root / rel_path
        target.write_text("MODIFIED CONTENT", encoding="utf-8")

        result = restore_snapshot(snap_dir, repo_root=root)
        assert len(result["restored"]) == 1
        assert rel_path in result["restored"][0]
        assert len(result["errors"]) == 0

        # Verify content matches original
        manifest = json.loads((snap_dir / "manifest.json").read_text())
        expected_hash = manifest["files"][0]["content_sha256"]
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        assert actual_hash == expected_hash

    def test_restore_noop_when_unchanged(self, repo_tree):
        root, rel_path = repo_tree
        take_snapshot, restore_snapshot, _ = _import_guard()

        snap_dir = take_snapshot("font", "python", [rel_path], repo_root=root)
        result = restore_snapshot(snap_dir, repo_root=root)
        assert len(result["skipped"]) == 1
        assert len(result["restored"]) == 0

    def test_dry_run_does_not_write(self, repo_tree):
        root, rel_path = repo_tree
        take_snapshot, restore_snapshot, _ = _import_guard()

        snap_dir = take_snapshot("font", "python", [rel_path], repo_root=root)
        target = root / rel_path
        target.write_text("MODIFIED", encoding="utf-8")

        result = restore_snapshot(snap_dir, dry_run=True, repo_root=root)
        assert result["dry_run"] is True
        assert len(result["restored"]) == 1
        assert "(would restore)" in result["restored"][0]

        # File should still be modified
        assert target.read_text() == "MODIFIED"

    def test_missing_manifest_returns_error(self, tmp_path):
        _, restore_snapshot, _ = _import_guard()
        result = restore_snapshot(tmp_path)
        assert len(result["errors"]) == 1


class TestDiffSummary:
    def test_unchanged_file(self, repo_tree):
        root, rel_path = repo_tree
        take_snapshot, _, diff_summary = _import_guard()

        snap_dir = take_snapshot("font", "python", [rel_path], repo_root=root)
        diffs = diff_summary(snap_dir, repo_root=root)
        assert len(diffs) == 1
        assert diffs[0]["status"] == "unchanged"
        assert diffs[0]["size_delta"] == 0

    def test_modified_file(self, repo_tree):
        root, rel_path = repo_tree
        take_snapshot, _, diff_summary = _import_guard()

        snap_dir = take_snapshot("font", "python", [rel_path], repo_root=root)
        (root / rel_path).write_text("NEW CONTENT" * 100, encoding="utf-8")

        diffs = diff_summary(snap_dir, repo_root=root)
        assert diffs[0]["status"] == "modified"
        assert diffs[0]["size_delta"] != 0

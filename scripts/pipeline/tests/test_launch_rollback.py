"""Tests for launch_rollback.py — content rollback after flawed launch.

Coverage:
- _is_content_path(): content/ accepted, non-content/ rejected
- _is_protected(): protected prefixes excluded; content/ not protected
- _classify_files(): correct classification of revert/skip/protected
- protected-file guard: _is_protected() prevents deletion of protected file
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import launch_rollback


# ---------------------------------------------------------------------------
# _is_content_path
# ---------------------------------------------------------------------------

class TestIsContentPath:
    @pytest.mark.parametrize("path", [
        "content/docs.aspose.org/en/3d/python/getting-started.md",
        "content/reference.aspose.org/en/3d/python/SomeClass.md",
        "content/blog.aspose.org/3d/python/post.md",
    ])
    def test_content_paths_accepted(self, path):
        assert launch_rollback._is_content_path(path) is True

    @pytest.mark.parametrize("path", [
        "scripts/pipeline/something.py",
        "knowledge/3d/python/model.json",
        "reports/plans/3d/python/site_plan.yaml",
        ".agents/skills/commit/SKILL.md",
    ])
    def test_non_content_paths_rejected(self, path):
        assert launch_rollback._is_content_path(path) is False


# ---------------------------------------------------------------------------
# _is_protected
# ---------------------------------------------------------------------------

class TestIsProtected:
    @pytest.mark.parametrize("path", [
        "scripts/pipeline/audit.py",
        ".agents/skills/commit/SKILL.md",
        ".claude/commands/commit.md",
        ".kilocode/skills/commit/SKILL.md",
        "reports/plans/3d/python/site_plan.yaml",
        "knowledge/3d/python/model.json",
        "configs/docs.aspose.org.toml",
        "layouts/partials/head.html",
        "static/img/logo.png",
        "themes/aspose/layouts/index.html",
    ])
    def test_protected_paths_detected(self, path):
        assert launch_rollback._is_protected(path) is True

    @pytest.mark.parametrize("path", [
        "content/docs.aspose.org/en/3d/python/index.md",
        "content/reference.aspose.org/en/3d/python/Cls.md",
    ])
    def test_content_paths_not_protected(self, path):
        assert launch_rollback._is_protected(path) is False


# ---------------------------------------------------------------------------
# _classify_files — with tmp_path content tree
# ---------------------------------------------------------------------------

class TestClassifyFiles:
    def test_protected_path_goes_to_protected(self):
        """Protected prefix path must appear in protected list, never revert/delete."""
        with patch.object(launch_rollback, "_git_in_index", return_value=True):
            to_revert, to_delete, to_skip, protected = launch_rollback._classify_files([
                "scripts/pipeline/something.py",
            ])
        assert "scripts/pipeline/something.py" in protected
        assert len(to_revert) == 0
        assert len(to_delete) == 0

    def test_missing_content_file_goes_to_skip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launch_rollback, "REPO_ROOT", tmp_path)
        # file does not exist
        to_revert, to_delete, to_skip, protected = launch_rollback._classify_files([
            "content/docs.aspose.org/en/3d/python/missing.md",
        ])
        assert "content/docs.aspose.org/en/3d/python/missing.md" in to_skip
        assert len(to_revert) == 0
        assert len(to_delete) == 0

    def test_tracked_content_file_goes_to_revert(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launch_rollback, "REPO_ROOT", tmp_path)
        page = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python" / "page.md"
        page.parent.mkdir(parents=True)
        page.write_text("---\ntitle: Test\n---\n")

        with patch.object(launch_rollback, "_git_in_index", return_value=True):
            to_revert, to_delete, to_skip, protected = launch_rollback._classify_files([
                "content/docs.aspose.org/en/3d/python/page.md",
            ])
        assert "content/docs.aspose.org/en/3d/python/page.md" in to_revert
        assert len(to_delete) == 0

    def test_untracked_content_file_goes_to_delete(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launch_rollback, "REPO_ROOT", tmp_path)
        page = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python" / "new.md"
        page.parent.mkdir(parents=True)
        page.write_text("---\ntitle: New\n---\n")

        with patch.object(launch_rollback, "_git_in_index", return_value=False):
            to_revert, to_delete, to_skip, protected = launch_rollback._classify_files([
                "content/docs.aspose.org/en/3d/python/new.md",
            ])
        assert "content/docs.aspose.org/en/3d/python/new.md" in to_delete
        assert len(to_revert) == 0

    def test_mixed_paths_classified_correctly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launch_rollback, "REPO_ROOT", tmp_path)
        page = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python" / "page.md"
        page.parent.mkdir(parents=True)
        page.write_text("---\ntitle: Test\n---\n")

        paths = [
            "content/docs.aspose.org/en/3d/python/page.md",  # → revert
            "content/docs.aspose.org/en/3d/python/missing.md",  # → skip
            "scripts/pipeline/audit.py",  # → protected
        ]

        with patch.object(launch_rollback, "_git_in_index", return_value=True):
            to_revert, to_delete, to_skip, protected = launch_rollback._classify_files(paths)

        assert len(to_revert) == 1
        assert len(to_skip) == 1
        assert len(protected) == 1
        assert "scripts/pipeline/audit.py" in protected


# ---------------------------------------------------------------------------
# Safety guard: protected files must never be reverted
# ---------------------------------------------------------------------------

class TestProtectedFileGuard:
    def test_run_aborts_on_protected_paths(self, tmp_path, monkeypatch, capsys):
        """When protected paths appear in the plan, run() exits 2 without reverting."""
        monkeypatch.setattr(launch_rollback, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(launch_rollback, "PLANS_DIR", tmp_path / "plans")
        monkeypatch.setattr(launch_rollback, "ROLLBACK_DIR", tmp_path / "rollback")

        # Write a site plan that includes a protected path (should never happen in practice)
        plan_dir = tmp_path / "plans" / "3d" / "python"
        plan_dir.mkdir(parents=True)
        (plan_dir / "site_plan.yaml").write_text(
            "plan:\n  sections:\n    docs:\n      pages:\n"
            "        - path: scripts/pipeline/audit.py\n",
            encoding="utf-8",
        )

        rc = launch_rollback.run("3d", "python", dry_run=False, no_manifest=True)
        assert rc == 2  # protected paths → abort

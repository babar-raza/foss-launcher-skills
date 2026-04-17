"""Tests for check_graded_at_only.py.

Each test creates a temporary git repository, makes commits, and stages
specific diffs so the script can be called as a subprocess against real git state.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit_file(repo: Path, name: str, content: str, message: str = "init") -> Path:
    p = repo / name
    p.write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", message)
    return p


def _run_checker(repo: Path, paths: list) -> subprocess.CompletedProcess:
    """Run check_graded_at_only.py --files-from against a list of paths in the given repo."""
    tmpf = repo / "_file_list.txt"
    tmpf.write_text("\n".join(paths) + "\n", encoding="utf-8")

    checker = Path(__file__).resolve().parents[1] / "check_graded_at_only.py"
    result = subprocess.run(
        [sys.executable, str(checker), "--files-from", str(tmpf)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(checker.parent)},
    )
    tmpf.unlink(missing_ok=True)
    return result


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

FRONTMATTER_WITH_GRADE = """\
---
title: Test
grade: A
graded_at: "2026-01-01T00:00:00Z"
graded_model_sha: sha1
graded_evaluators: full
graded_logic_version: 5
graded_content_hash: "abcdef1234567890"
---

Body text here.
"""

FRONTMATTER_WITH_GRADE_UPDATED_AT = """\
---
title: Test
grade: A
graded_at: "2026-04-17T12:00:00Z"
graded_model_sha: sha1
graded_evaluators: full
graded_logic_version: 5
graded_content_hash: "abcdef1234567890"
---

Body text here.
"""

FRONTMATTER_WITH_GRADE_B = """\
---
title: Test
grade: B
graded_at: "2026-04-17T12:00:00Z"
graded_model_sha: sha2
graded_evaluators: full
graded_logic_version: 5
graded_content_hash: "abcdef1234567890"
---

Body text here.
"""

FRONTMATTER_BODY_CHANGED = """\
---
title: Test
grade: A
graded_at: "2026-01-01T00:00:00Z"
graded_model_sha: sha1
graded_evaluators: full
graded_logic_version: 5
graded_content_hash: "abcdef1234567890"
---

Body text here, now with extra content.
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDetectsGradedAtOnlyDiff:
    """Case A: only graded_at changed -> path printed to stdout."""

    def test_detects_graded_at_only_diff(self, tmp_path):
        repo = _init_repo(tmp_path)
        p = _commit_file(repo, "page.md", FRONTMATTER_WITH_GRADE)

        # Stage a change where only graded_at differs
        p.write_text(FRONTMATTER_WITH_GRADE_UPDATED_AT, encoding="utf-8")
        _git(repo, "add", "page.md")

        result = _run_checker(repo, ["page.md"])
        assert result.returncode == 0
        assert "page.md" in result.stdout
        assert "PARSE_FAILURE" not in result.stderr


class TestIgnoresGradeFieldChange:
    """Case B: grade AND graded_at changed -> nothing in stdout."""

    def test_ignores_grade_field_change(self, tmp_path):
        repo = _init_repo(tmp_path)
        p = _commit_file(repo, "page.md", FRONTMATTER_WITH_GRADE)

        # Stage a change where grade letter and graded_at both differ
        p.write_text(FRONTMATTER_WITH_GRADE_B, encoding="utf-8")
        _git(repo, "add", "page.md")

        result = _run_checker(repo, ["page.md"])
        assert result.returncode == 0
        assert "page.md" not in result.stdout
        assert "PARSE_FAILURE" not in result.stderr


class TestIgnoresBodyChange:
    """Case C: body changed, no graded_at in diff -> nothing in stdout."""

    def test_ignores_body_change(self, tmp_path):
        repo = _init_repo(tmp_path)
        p = _commit_file(repo, "page.md", FRONTMATTER_WITH_GRADE)

        # Stage a change where only the body changed (graded_at same)
        p.write_text(FRONTMATTER_BODY_CHANGED, encoding="utf-8")
        _git(repo, "add", "page.md")

        result = _run_checker(repo, ["page.md"])
        assert result.returncode == 0
        assert "page.md" not in result.stdout
        assert "PARSE_FAILURE" not in result.stderr


class TestIgnoresNewFile:
    """Case C (new file, no HEAD): diff is empty -> not printed."""

    def test_ignores_new_file(self, tmp_path):
        repo = _init_repo(tmp_path)
        # Create initial commit with a different file so repo has a HEAD
        _commit_file(repo, "other.md", "---\ntitle: Other\n---\nBody.\n")

        # Add new file (no HEAD for this path)
        new_p = repo / "new_page.md"
        new_p.write_text(FRONTMATTER_WITH_GRADE, encoding="utf-8")
        _git(repo, "add", "new_page.md")

        result = _run_checker(repo, ["new_page.md"])
        assert result.returncode == 0
        assert "new_page.md" not in result.stdout
        assert "PARSE_FAILURE" not in result.stderr


class TestUnstaggedFileIsIgnored:
    """Case C (no staged diff for file): diff is empty -> not printed."""

    def test_unstaged_file_not_printed(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit_file(repo, "other.md", "---\ntitle: Other\n---\nBody.\n")

        # Write file but do NOT stage it (unstaged worktree change)
        orphan = repo / "orphan.md"
        orphan.write_text(FRONTMATTER_WITH_GRADE, encoding="utf-8")
        # No git add -- staged diff is empty -> Case C

        result = _run_checker(repo, ["orphan.md"])
        assert result.returncode == 0
        assert "orphan.md" not in result.stdout


class TestParseFailureExitsNonzero:
    """Case D: git failure in non-repo directory -> PARSE_FAILURE in stderr, exit 2."""

    def test_parse_failure_exits_nonzero(self, tmp_path):
        """Checker run from a non-git directory: git diff fails -> Case D."""
        import os

        # non_repo is a plain directory with no git init -- git will error
        non_repo = tmp_path / "non_repo"
        non_repo.mkdir()

        # File list pointing at a local path (file doesn't need to exist)
        tmpf = non_repo / "_files.txt"
        tmpf.write_text("page.md\n", encoding="utf-8")

        checker = Path(__file__).resolve().parents[1] / "check_graded_at_only.py"
        result = subprocess.run(
            [sys.executable, str(checker), "--files-from", str(tmpf)],
            cwd=str(non_repo),   # <-- not a git repo; git diff will fail
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(checker.parent)},
        )
        tmpf.unlink(missing_ok=True)

        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
        assert "PARSE_FAILURE" in result.stderr, (
            f"Expected PARSE_FAILURE in stderr; got: {result.stderr!r}"
        )

"""Tests for check_grade_downgrade.py: the --files-from/positional merge added
to fix the "Argument list too long" ceiling (~450-500 staged files on this
repo's Windows/MSYS setup), and the downgrade-detection gate itself.

Real temp git repo, subprocess-invoked script (no mocking) -- mirrors
test_check_graded_at_only.py's pattern. `git show origin/main:<path>` is
satisfied by creating a local branch literally named "origin/main" (git's ref
resolution matches refs/heads/origin/main the same way it would a real
remote-tracking ref), avoiding the need for an actual remote in tests.

Note on scope: this file proves the BLOCK path (a genuine downgrade is still
detected and written to --blocked-files-out) survives the argv -> --files-from
rewrite. It does not re-test override-token acceptance -- that logic lives
entirely in scripts/pre-commit-audit.sh's own bash loop (calling
override_manager.py), which this change does not touch; it is exercised by
the plan's separate isolated `bash scripts/pre-commit-audit.sh` verification
step, not at this script's unit level.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "commands" / "governance" / "check_grade_downgrade.py"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, check=False)


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


def _mark_as_origin_main(repo: Path) -> None:
    _git(repo, "branch", "origin/main", "HEAD")


def _run_checker(repo: Path, positional: list[str] | None = None,
                  files_from: list[str] | None = None,
                  extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(CHECKER)]
    tmpf = None
    if files_from is not None:
        tmpf = repo / "_file_list.txt"
        tmpf.write_text("\n".join(files_from) + "\n", encoding="utf-8")
        cmd += ["--files-from", str(tmpf)]
    if positional:
        cmd += positional
    if extra_args:
        cmd += extra_args
    result = subprocess.run(
        cmd, cwd=str(repo), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(CHECKER.parents[1])},
    )
    if tmpf is not None:
        tmpf.unlink(missing_ok=True)
    return result


FRONTMATTER_GRADE_A = """\
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

FRONTMATTER_GRADE_F = """\
---
title: Test
grade: F
graded_at: "2026-04-17T12:00:00Z"
graded_model_sha: sha2
graded_evaluators: full
graded_logic_version: 5
graded_content_hash: "1234567890abcdef"
---

Body text here, much worse now.
"""


class TestPositionalFilesStillWork:
    def test_positional_only(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit_file(repo, "page.md", FRONTMATTER_GRADE_A)
        _mark_as_origin_main(repo)

        result = _run_checker(repo, positional=["page.md"])
        assert result.returncode == 0, result.stderr
        assert "1 file(s) checked" in result.stdout


class TestFilesFromAlone:
    def test_files_from_only(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit_file(repo, "page.md", FRONTMATTER_GRADE_A)
        _mark_as_origin_main(repo)

        result = _run_checker(repo, files_from=["page.md"])
        assert result.returncode == 0, result.stderr
        assert "1 file(s) checked" in result.stdout


class TestPositionalAndFilesFromMerge:
    def test_both_sources_merged(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit_file(repo, "a.md", FRONTMATTER_GRADE_A)
        _commit_file(repo, "b.md", FRONTMATTER_GRADE_A)
        _mark_as_origin_main(repo)

        result = _run_checker(repo, positional=["a.md"], files_from=["b.md"])
        assert result.returncode == 0, result.stderr
        assert "2 file(s) checked" in result.stdout


class TestFilesFromMissingFile:
    def test_missing_files_from_path_errors_cleanly(self, tmp_path):
        repo = _init_repo(tmp_path)

        cmd = [sys.executable, str(CHECKER), "--files-from", str(repo / "does_not_exist.txt")]
        result = subprocess.run(
            cmd, cwd=str(repo), capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(CHECKER.parents[1])},
        )
        assert result.returncode == 1
        assert "cannot read --files-from" in result.stderr
        assert "Traceback" not in result.stderr


class TestGenuineDowngradeStillBlocks:
    """G4: the argv -> --files-from rewrite must not silently stop blocking
    real downgrades. A->F must BLOCK per no_downgrade_guard._decision (A/B
    existing + D/F predicted -> DECISION_BLOCK)."""

    def test_downgrade_blocked_via_files_from(self, tmp_path):
        repo = _init_repo(tmp_path)
        p = _commit_file(repo, "page.md", FRONTMATTER_GRADE_A)
        _mark_as_origin_main(repo)

        # Working-copy edit downgrades the grade (not committed -- check_grade_downgrade.py
        # compares origin/main's committed grade against the on-disk working copy).
        p.write_text(FRONTMATTER_GRADE_F, encoding="utf-8")

        blocked_out = repo / "_blocked.txt"
        result = _run_checker(
            repo, files_from=["page.md"],
            extra_args=["--blocked-files-out", str(blocked_out)],
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "BLOCKED" in result.stderr
        assert blocked_out.exists()
        assert "page.md" in blocked_out.read_text(encoding="utf-8")


class TestNoDowngradePasses:
    def test_same_grade_passes(self, tmp_path):
        repo = _init_repo(tmp_path)
        p = _commit_file(repo, "page.md", FRONTMATTER_GRADE_A)
        _mark_as_origin_main(repo)

        p.write_text(FRONTMATTER_GRADE_A, encoding="utf-8")

        result = _run_checker(repo, files_from=["page.md"])
        assert result.returncode == 0, result.stderr


class TestBlockedFilesOutHasNoCarriageReturns:
    """Found live 2026-08-30 (MT040 Phase I): --blocked-files-out was written
    via Path.write_text() with no `newline=` pin, so Windows Python's default
    universal-newlines translation turned every "\\n" into "\\r\\n". The file
    is consumed by pre-commit-audit.sh's `while IFS= read -r _gd_f` loop,
    which -- unlike Python's text-mode readers -- does NOT strip a trailing
    \\r, so `_gd_f` carried a trailing carriage return into
    `override_manager.py validate-for-path "$_gd_f"`. That exact-string path
    match then always failed against a token created for the clean path,
    silently defeating every override for this gate on Windows. Must never
    regress: the file must contain LF-only line endings regardless of the
    platform running the check."""

    def test_blocked_files_out_uses_lf_only(self, tmp_path):
        repo = _init_repo(tmp_path)
        p = _commit_file(repo, "page.md", FRONTMATTER_GRADE_A)
        _mark_as_origin_main(repo)

        p.write_text(FRONTMATTER_GRADE_F, encoding="utf-8")

        blocked_out = repo / "_blocked.txt"
        result = _run_checker(
            repo, files_from=["page.md"],
            extra_args=["--blocked-files-out", str(blocked_out)],
        )
        assert result.returncode == 2, result.stdout + result.stderr
        raw = blocked_out.read_bytes()
        assert b"\r" not in raw, f"blocked-files-out contains a carriage return: {raw!r}"
        assert raw == b"page.md\n"

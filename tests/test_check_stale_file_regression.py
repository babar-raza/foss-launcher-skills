"""Tests for scripts/ci/checks/check_stale_file_regression.py (ported 2026-08-29)."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))

import check_stale_file_regression as sfr  # noqa: E402


# --- Pure-function tests (detect_regression takes no I/O) -----------------

def test_detect_regression_true_when_matches_parent_not_intervening():
    assert sfr.detect_regression(
        proposed_content="old value",
        parent_content="old value",
        intervening_content="new value",
    ) is True


def test_detect_regression_false_when_matches_intervening():
    assert sfr.detect_regression(
        proposed_content="new value",
        parent_content="old value",
        intervening_content="new value",
    ) is False


def test_detect_regression_false_when_matches_neither():
    assert sfr.detect_regression(
        proposed_content="something else entirely",
        parent_content="old value",
        intervening_content="new value",
    ) is False


def test_detect_regression_false_when_intervening_content_missing():
    assert sfr.detect_regression(
        proposed_content="old value",
        parent_content="old value",
        intervening_content=None,
    ) is False


def test_detect_regression_false_when_parent_content_missing():
    assert sfr.detect_regression(
        proposed_content="new value",
        parent_content=None,
        intervening_content="new value",
    ) is False


# --- End-to-end test against a real, disposable git repo ------------------

def _git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout


@pytest.fixture
def tiny_repo(tmp_path):
    repo = tmp_path / "tiny-repo"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)

    target_file = repo / "shared.txt"
    target_file.write_text("v1 -- original\n", encoding="utf-8")
    _git(["add", "shared.txt"], repo)
    _git(["commit", "-q", "-m", "initial"], repo)
    base_sha = _git(["rev-parse", "HEAD"], repo).strip()

    # Simulate "another session" committing a fix after our base_sha.
    target_file.write_text("v2 -- corrected by another session\n", encoding="utf-8")
    _git(["add", "shared.txt"], repo)
    _git(["commit", "-q", "-m", "unrelated fix by another session"], repo)

    return repo, base_sha


def test_end_to_end_detects_silent_revert(tiny_repo):
    repo, base_sha = tiny_repo
    # Our session, unaware of the intervening commit, stages the OLD value again.
    (repo / "shared.txt").write_text("v1 -- original\n", encoding="utf-8")
    _git(["add", "shared.txt"], repo)

    result = sfr.check_file("shared.txt", base_sha, repo_root=repo, use_staged=True)
    assert result is not None
    assert result["file"] == "shared.txt"


def test_end_to_end_allows_legitimate_further_edit(tiny_repo):
    repo, base_sha = tiny_repo
    # Our session builds ON TOP of the intervening commit's content -- not a revert.
    (repo / "shared.txt").write_text("v2 -- corrected by another session\nplus our addition\n", encoding="utf-8")
    _git(["add", "shared.txt"], repo)

    result = sfr.check_file("shared.txt", base_sha, repo_root=repo, use_staged=True)
    assert result is None


def test_end_to_end_no_intervening_commit_is_silent(tiny_repo):
    repo, base_sha = tiny_repo
    # A DIFFERENT file with no intervening commit at all -- nothing to flag.
    other = repo / "untouched.txt"
    other.write_text("brand new file\n", encoding="utf-8")
    _git(["add", "untouched.txt"], repo)

    result = sfr.check_file("untouched.txt", base_sha, repo_root=repo, use_staged=True)
    assert result is None


def test_main_skips_advisory_when_no_base_sha_given(capsys):
    code = sfr.main(["--files", "some_file.py"])
    assert code == 0
    assert "skipping" in capsys.readouterr().err.lower()


def test_main_returns_zero_for_empty_file_list():
    assert sfr.main(["--files", "--base-sha", "deadbeef"]) == 0

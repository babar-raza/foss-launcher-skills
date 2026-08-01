"""Tests for check_stale_file_regression.py.

Each test creates a temporary git repository, makes real commits, and calls
the module's functions against real git state -- this check is fundamentally
git-plumbing-based, and mocking git commands would exercise far less than the
real thing. Includes a regression test reproducing the actual incident this
check exists to prevent (TC-MT018-06's commit d2dce37de5 silently reverting
an unrelated fix to fetch_aspose_com_targets.py hours after it landed).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_stale_file_regression as sfr  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (mirrors scripts/pipeline/tests/test_check_graded_at_only.py)
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit_file(repo: Path, name: str, content: str, message: str = "commit") -> str:
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _stage(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)


# ---------------------------------------------------------------------------
# find_intervening_commit
# ---------------------------------------------------------------------------

def test_no_intervening_commit_when_file_untouched_since_base(tmp_path):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "v1", "base")
    _commit_file(repo, "other.txt", "unrelated", "unrelated change")
    assert sfr.find_intervening_commit("f.txt", base_sha, repo_root=repo) is None


def test_base_sha_equals_last_touch_no_intervening(tmp_path):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "v1", "base")
    assert sfr.find_intervening_commit("f.txt", base_sha, repo_root=repo) is None


def test_intervening_commit_found_when_file_changed_since_base(tmp_path):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "v1", "base")
    second_sha = _commit_file(repo, "f.txt", "v2", "fix by another session")
    assert sfr.find_intervening_commit("f.txt", base_sha, repo_root=repo) == second_sha


def test_no_intervening_commit_when_base_not_ancestor(tmp_path):
    """Defensive: base_sha not actually an ancestor of the file's last-touch
    commit (unrelated/rewritten history) must not crash or false-positive."""
    repo = _init_repo(tmp_path)
    _commit_file(repo, "f.txt", "v1", "base")
    fake_sha = "0" * 40
    assert sfr.find_intervening_commit("f.txt", fake_sha, repo_root=repo) is None


# ---------------------------------------------------------------------------
# get_blob_at / get_staged_content
# ---------------------------------------------------------------------------

def test_get_blob_at_returns_content(tmp_path):
    repo = _init_repo(tmp_path)
    sha = _commit_file(repo, "f.txt", "hello", "c1")
    assert sfr.get_blob_at(sha, "f.txt", repo_root=repo) == "hello"


def test_get_blob_at_returns_none_for_nonexistent_path(tmp_path):
    repo = _init_repo(tmp_path)
    sha = _commit_file(repo, "f.txt", "hello", "c1")
    assert sfr.get_blob_at(sha, "does_not_exist.txt", repo_root=repo) is None


def test_get_blob_at_parent_returns_none_for_newly_created_file(tmp_path):
    repo = _init_repo(tmp_path)
    sha = _commit_file(repo, "f.txt", "hello", "c1")
    assert sfr.get_blob_at(f"{sha}^", "f.txt", repo_root=repo) is None


def test_get_staged_content_returns_index_content(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_file(repo, "f.txt", "v1", "c1")
    _stage(repo, "f.txt", "v2-staged")
    assert sfr.get_staged_content("f.txt", repo_root=repo) == "v2-staged"


# ---------------------------------------------------------------------------
# detect_regression (pure)
# ---------------------------------------------------------------------------

def test_detect_regression_true_when_proposed_matches_parent_not_intervening():
    assert sfr.detect_regression(
        proposed_content="old-wrong-value",
        parent_content="old-wrong-value",
        intervening_content="new-correct-value",
    ) is True


def test_detect_regression_false_when_proposed_incorporates_intervening():
    assert sfr.detect_regression(
        proposed_content="new-correct-value",
        parent_content="old-wrong-value",
        intervening_content="new-correct-value",
    ) is False


def test_detect_regression_false_when_proposed_is_independent_edit():
    """A genuinely independent further edit -- neither matching the old nor
    the intervening state -- must not be flagged (avoids false positives on
    legitimate concurrent work)."""
    assert sfr.detect_regression(
        proposed_content="yet-another-value",
        parent_content="old-wrong-value",
        intervening_content="new-correct-value",
    ) is False


def test_detect_regression_false_when_no_parent_content():
    """Intervening commit CREATED the file -- nothing older to revert to."""
    assert sfr.detect_regression(
        proposed_content="anything", parent_content=None, intervening_content="new",
    ) is False


def test_detect_regression_false_when_no_intervening_content():
    assert sfr.detect_regression(
        proposed_content="anything", parent_content="old", intervening_content=None,
    ) is False


# ---------------------------------------------------------------------------
# check_file (integration of the above against a real repo)
# ---------------------------------------------------------------------------

def test_check_file_detects_real_revert(tmp_path):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "wrong-value", "base (before fix)")
    _commit_file(repo, "f.txt", "correct-value", "fix by another session")
    # This session's own change: stale content reverting the fix, staged now.
    _stage(repo, "f.txt", "wrong-value")

    finding = sfr.check_file("f.txt", base_sha, repo_root=repo)
    assert finding is not None
    assert finding["file"] == "f.txt"


def test_check_file_no_finding_when_fix_incorporated(tmp_path):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "wrong-value", "base")
    _commit_file(repo, "f.txt", "correct-value", "fix by another session")
    _stage(repo, "f.txt", "correct-value-plus-more")  # builds on the fix

    assert sfr.check_file("f.txt", base_sha, repo_root=repo) is None


def test_check_file_no_finding_when_no_intervening_commit(tmp_path):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "v1", "base")
    _stage(repo, "f.txt", "v2-my-own-edit")

    assert sfr.check_file("f.txt", base_sha, repo_root=repo) is None


# ---------------------------------------------------------------------------
# Regression test reproducing the actual incident
# ---------------------------------------------------------------------------

def test_reproduces_actual_mt018_incident(tmp_path):
    """Structural replay of the real 2026-08-01 incident: a fix commit
    corrects a URL field; hours later, an unrelated commit's stale content
    reverts it back to the known-wrong value. Confirms this check would have
    caught it."""
    repo = _init_repo(tmp_path)
    pre_fix = '{"pdf/go": {"url": "https://products.aspose.com/pdf/go/", "http_status": 404}}'
    post_fix = '{"pdf/go": {"url": "https://products.aspose.com/pdf/go-cpp/", "http_status": 200}}'

    base_sha = _commit_file(repo, "data/aspose_com_targets.json", pre_fix,
                             "chore: seed data")
    _commit_file(repo, "data/aspose_com_targets.json", post_fix,
                 "fix: fetch_aspose_com_targets.py silently accepted path-changing redirects")

    # The OTHER session's own unrelated commit, staging a stale snapshot that
    # predates the fix -- exactly what happened live.
    _stage(repo, "data/aspose_com_targets.json", pre_fix)

    finding = sfr.check_file("data/aspose_com_targets.json", base_sha, repo_root=repo)
    assert finding is not None, "this check must catch the exact incident it was built for"


# ---------------------------------------------------------------------------
# CLI (main())
# ---------------------------------------------------------------------------

def test_main_exits_zero_when_clean(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "v1", "base")
    _stage(repo, "f.txt", "v2")

    monkeypatch.chdir(repo)
    rc = sfr.main(["--files", "f.txt", "--base-sha", base_sha])
    assert rc == 0


def test_main_exits_one_and_reports_on_regression(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "wrong", "base")
    _commit_file(repo, "f.txt", "right", "fix")
    _stage(repo, "f.txt", "wrong")

    monkeypatch.chdir(repo)
    rc = sfr.main(["--files", "f.txt", "--base-sha", base_sha])
    out = capsys.readouterr().out
    assert rc == 1
    assert "f.txt" in out


def test_main_reads_files_from_stdin_when_no_files_flag(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    base_sha = _commit_file(repo, "f.txt", "wrong", "base")
    _commit_file(repo, "f.txt", "right", "fix")
    _stage(repo, "f.txt", "wrong")

    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("f.txt\n"))
    rc = sfr.main(["--base-sha", base_sha])
    assert rc == 1


def test_main_no_files_is_a_noop(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(""))
    assert sfr.main([]) == 0


def test_main_advisory_pass_when_base_sha_unresolvable(tmp_path, monkeypatch, capsys):
    """Infrastructure unavailable (no session ledger, no base sha) must never
    itself block an unrelated commit -- fails OPEN, advisory.

    resolve_base_sha itself is monkeypatched rather than relying on the
    REAL repo's absence of an active session_ledger session: this test
    suite runs inside the actual aspose.org checkout, where other live
    sessions frequently ARE active, so falling through to the real
    session_ledger module here would make this test non-deterministic."""
    repo = _init_repo(tmp_path)
    _commit_file(repo, "f.txt", "v1", "base")
    monkeypatch.setattr(sfr, "resolve_base_sha", lambda explicit, session_id: None)

    monkeypatch.chdir(repo)
    rc = sfr.main(["--files", "f.txt"])  # no --base-sha, no --session-id
    assert rc == 0
    assert "advisory" in capsys.readouterr().err.lower()

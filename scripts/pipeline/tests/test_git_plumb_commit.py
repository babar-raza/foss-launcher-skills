"""Tests for git_plumb_commit.py (production concurrency redesign,
2026-08-01, Step 8 follow-up: MT019's own convergence audit, TC-MT019-03).

Uses a REAL local bare repo as the push destination -- no network
dependency, no mocking of git itself -- matching this session's established
preference for exercising real git behavior rather than simulating it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import git_plumb_commit as gpc
from commands.governance import override_manager


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False,
    )


def _init_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare 'origin' repo and a working repo cloned from it, with
    one initial commit already pushed. Returns (working_repo, bare_repo)."""
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-q")

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "test@test.com")
    _git(work, "config", "user.name", "Test")
    (work / "seed.txt").write_text("seed", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "seed")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", "main")
    return work, bare


@pytest.fixture(autouse=True)
def _isolate_override_manager(tmp_path):
    """override_manager.find_valid_token_for_path reads module-level
    repo_root/pending-dir defaults (the REAL repo's own paths) unless
    reconfigured -- isolate both for every test in this file. repo_root
    matters even though pending_dir is overridden separately: cmd_create's
    own success message computes out_path.relative_to(_REPO_ROOT), which
    raises if _REPO_ROOT doesn't actually contain pending_dir."""
    override_manager.configure(repo_root=tmp_path, pending_dir=tmp_path / "overrides_pending")
    yield
    override_manager.configure()


@pytest.fixture(autouse=True)
def _reset_gpc_config():
    yield
    gpc.configure()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_commits_and_pushes_real_new_file(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "new_file.txt").write_text("hello", encoding="utf-8")

    result = gpc.plumb_commit(
        ["new_file.txt"], "add new_file.txt",
        repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True,
    )

    assert result["pushed"] is True
    assert result["commit_sha"]

    # Verify the push actually landed on the bare "remote" -- real proof, not
    # an assumption based on a zero exit code.
    show = _git(bare, "show", f"{result['commit_sha']}:new_file.txt")
    assert show.stdout == "hello"

    # Local refs synced.
    local_head = _git(work, "rev-parse", "refs/heads/main").stdout.strip()
    assert local_head == result["commit_sha"]
    remote_tracking = _git(work, "rev-parse", "refs/remotes/origin/main").stdout.strip()
    assert remote_tracking == result["commit_sha"]


def test_does_not_touch_real_index_or_other_staged_files(tmp_path):
    """The core safety property: another file staged in the real index
    (simulating another session's in-flight work) must survive untouched.

    Verifies via `git ls-files --stage` (the real index's own content),
    not `git diff --cached` -- after a successful plumb_commit, `update-ref`
    moves the local branch pointer forward past the real (untouched, now
    stale-relative-to-new-HEAD) index, so `git diff --cached` naturally
    shows the newly-committed file as a spurious "D" (deleted) entry -- an
    already-documented, expected artifact of this exact technique (see this
    session's other commits' own "post-commit index staleness" notes), not
    evidence of a bug. `git ls-files --stage` reports the index's actual
    entries directly, unaffected by which commit HEAD happens to point at.
    """
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "mine.txt").write_text("mine", encoding="utf-8")
    (work / "someone_elses.txt").write_text("their staged content", encoding="utf-8")
    _git(work, "add", "someone_elses.txt")  # staged in the REAL index, not by us

    gpc.plumb_commit(
        ["mine.txt"], "add mine.txt", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True,
    )

    # The real index must still show exactly someone_elses.txt -- mine.txt
    # was never added to it.
    real_index = _git(work, "ls-files", "--stage").stdout
    assert "someone_elses.txt" in real_index
    assert "mine.txt" not in real_index

    head_files = _git(work, "show", "--stat", "--format=", "HEAD").stdout
    assert "mine.txt" in head_files
    assert "someone_elses.txt" not in head_files


def test_commit_message_preserved_verbatim(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    msg = "fix(pipeline): a real multi-line message\n\n- detail one\n- detail two\n"

    result = gpc.plumb_commit(
        ["f.txt"], msg, repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True,
    )

    actual_msg = _git(work, "log", "-1", "--format=%B", result["commit_sha"]).stdout
    assert actual_msg.strip() == msg.strip()


def test_no_push_mode_creates_commit_without_pushing(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["f.txt"], "no push test", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, push=False,
    )

    assert result["pushed"] is False
    # Not reachable on the bare repo.
    show = _git(bare, "cat-file", "-e", result["commit_sha"])
    assert show.returncode != 0


# ---------------------------------------------------------------------------
# .gitignore warnings (TC-H04, found live 2026-08-06: this tool force-tracked
# 8 gitignored /.supervisor/state/ files with zero feedback)
# ---------------------------------------------------------------------------

def test_warns_on_gitignored_file_but_still_commits(tmp_path, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "add gitignore")
    (work / "ignored").mkdir()
    (work / "ignored" / "secret.txt").write_text("s", encoding="utf-8")

    result = gpc.plumb_commit(
        ["ignored/secret.txt"], "force-track a gitignored file",
        repo_root=work, branch="main", remote=str(bare), skip_stale_check=True,
    )

    assert result["gitignore_warnings"] == ["ignored/secret.txt"]
    assert "WARNING" in capsys.readouterr().err
    assert result["pushed"] is True  # non-fatal -- commit still proceeds
    show = _git(bare, "show", f"{result['commit_sha']}:ignored/secret.txt")
    assert show.stdout == "s"


def test_ack_gitignored_silences_the_warning(tmp_path, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "add gitignore")
    (work / "ignored").mkdir()
    (work / "ignored" / "secret.txt").write_text("s", encoding="utf-8")

    result = gpc.plumb_commit(
        ["ignored/secret.txt"], "intentionally force-track",
        repo_root=work, branch="main", remote=str(bare), skip_stale_check=True,
        ack_gitignored=["ignored/secret.txt"],
    )

    assert result["gitignore_warnings"] == []
    assert "WARNING" not in capsys.readouterr().err
    assert result["pushed"] is True


def test_no_warning_for_a_normal_tracked_path(tmp_path, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "normal.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["normal.txt"], "normal commit", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True,
    )

    assert result["gitignore_warnings"] == []
    assert "WARNING" not in capsys.readouterr().err


def test_cli_ack_gitignored_flag_silences_warning(tmp_path, monkeypatch, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "add gitignore")
    (work / "ignored").mkdir()
    (work / "ignored" / "secret.txt").write_text("s", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("chore: cli ack test", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files", "ignored/secret.txt",
        "--message-file", str(msg_file),
        "--skills", "S-99", "--plan", "cli ack test",
        "--branch", "main", "--remote", str(bare),
        "--skip-stale-check", "--no-push",
        "--ack-gitignored", "ignored/secret.txt",
    ])

    assert rc == 0
    assert "WARNING" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Stale-file regression blocking
# ---------------------------------------------------------------------------

def test_blocks_a_real_regression_with_no_override(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed data.txt as wrong")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("correct-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix by another session")
    _git(work, "push", "-q", "origin", "main")

    # This session's own proposed content reverts the fix.
    (work / "data.txt").write_text("wrong-value", encoding="utf-8")

    with pytest.raises(gpc.PlumbCommitBlocked) as exc_info:
        gpc.plumb_commit(
            ["data.txt"], "accidental revert", repo_root=work, branch="main",
            remote=str(bare), base_sha=base_sha,
        )
    assert "data.txt" in str(exc_info.value)

    # Nothing pushed.
    remote_tip = _git(bare, "rev-parse", "main").stdout.strip()
    local_tip = _git(work, "rev-parse", "HEAD").stdout.strip()
    assert remote_tip == local_tip  # bare repo unchanged, no new commit landed


def test_allows_a_regression_covered_by_a_valid_override_token(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed data.txt as wrong")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("correct-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix by another session")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")  # intentional revert

    class Args:
        paths = ["data.txt"]
        reason = "intentional revert for this test"
        plan = "test-plan"
        scope = ""
        operation = "edit"
        retroactive = False

    override_manager.cmd_create(Args())

    result = gpc.plumb_commit(
        ["data.txt"], "intentional revert, governed", repo_root=work, branch="main",
        remote=str(bare), base_sha=base_sha,
    )
    assert result["pushed"] is True


def test_skip_stale_check_bypasses_the_check_entirely(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed data.txt as wrong")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("correct-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix by another session")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")

    result = gpc.plumb_commit(
        ["data.txt"], "explicit skip", repo_root=work, branch="main",
        remote=str(bare), base_sha=base_sha, skip_stale_check=True,
    )
    assert result["pushed"] is True


def test_no_base_sha_and_no_skip_is_advisory_pass(tmp_path):
    """No base_sha resolvable (and not explicitly skipped) -- same fail-open
    policy as check_stale_file_regression.py itself: never block on missing
    infrastructure."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["f.txt"], "no base sha", repo_root=work, branch="main", remote=str(bare),
        base_sha=None, session_id="no-such-session-anywhere",
    )
    assert result["pushed"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_end_to_end(tmp_path, monkeypatch):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("chore: cli test commit", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files", "f.txt",
        "--message-file", str(msg_file),
        "--skills", "S-99",
        "--plan", "cli test",
        "--branch", "main",
        "--remote", str(bare),
        "--skip-stale-check",
        "--no-push",  # avoid needing a real skill_run_manager.py invocation in this test
    ])
    assert rc == 0


def test_cli_requires_exactly_one_message_source(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    rc = gpc.main([
        "--files", "f.txt", "--skills", "S-99", "--plan", "x",
    ])
    assert rc == 2

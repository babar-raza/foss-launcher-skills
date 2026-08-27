"""Tests for git_plumb_commit.py's reconcile() capability and
plumb_commit()'s automatic non-fast-forward retry (2026-08-26 pipeline
reliability hardening pass,
reports/skill-gaps/2026-08-26-pipeline-reliability-hardening.md).

Found live 2026-08-26: `plumb_commit()` had no divergence handling at all --
a push against a `HEAD` already stale relative to `origin/<branch>` (a
routine occurrence under real concurrent-session load, hit twice in one
session) required an agent to hand-build a two-parent merge commit via raw
git plumbing under live push pressure. These tests exercise `reconcile()`
and the auto-retry it enables against REAL local bare repos (no mocking of
git itself), mirroring the existing test file's established convention.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import git_plumb_commit as gpc


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False,
    )


def _init_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
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


def _clone(bare: Path, dest: Path) -> Path:
    """A second independent working clone of `bare`, simulating another
    concurrent session's own checkout. `bare`'s HEAD symref may still point
    at whatever `init.defaultBranch` was (e.g. "master") even though only
    "main" has ever actually been pushed -- explicitly check out a local
    "main" tracking origin/main rather than relying on clone's default
    checkout, which would otherwise leave `dest` on a nonexistent branch."""
    _git(dest.parent, "clone", "-q", str(bare), str(dest))
    _git(dest, "config", "user.email", "other@test.com")
    _git(dest, "config", "user.name", "Other")
    _git(dest, "checkout", "-B", "main", "--track", "origin/main")
    return dest


@pytest.fixture(autouse=True)
def _reset_gpc_config():
    yield
    gpc.configure()


def test_reconcile_merges_disjoint_files_after_a_real_divergence(tmp_path):
    """The core regression scenario: two independent working trees push
    disjoint-file commits to the same bare origin. The second push, built
    against a now-stale local HEAD, is rejected non-fast-forward.
    reconcile() must produce a merge commit containing BOTH sets of files.
    """
    work, bare = _init_repo_with_remote(tmp_path)
    other = _clone(bare, tmp_path / "other")

    # "Other session" commits and pushes first, advancing origin/main.
    (other / "other_file.txt").write_text("from the other session", encoding="utf-8")
    _git(other, "add", "other_file.txt")
    _git(other, "commit", "-q", "-m", "other session's commit")
    push = _git(other, "push", "origin", "main")
    assert push.returncode == 0

    # "This session" built its own commit against the now-stale local HEAD
    # (it never fetched -- exactly plumb_commit()'s own behavior: it reads
    # HEAD once at the start and never re-checks before pushing).
    (work / "mine.txt").write_text("mine", encoding="utf-8")
    stale_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    _git(work, "add", "mine.txt")
    _git(work, "commit", "-q", "-m", "my commit")
    my_commit_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    result = gpc.reconcile(
        my_commit_sha, ["mine.txt"], repo_root=work, branch="main",
        remote=str(bare), old_parent_sha=stale_head,
    )

    assert result["fast_forward"] is False
    merge_sha = result["commit_sha"]

    # The merge commit's tree must contain BOTH files.
    tree_files = _git(work, "ls-tree", "-r", "--name-only", merge_sha).stdout
    assert "mine.txt" in tree_files
    assert "other_file.txt" in tree_files
    assert "seed.txt" in tree_files

    # Both parents recorded.
    parents = _git(work, "log", "-1", "--format=%P", merge_sha).stdout.strip().split()
    assert len(parents) == 2

    # Pushed and landed on the bare remote for real.
    assert result["pushed"] is True
    remote_tip = _git(bare, "rev-parse", "main").stdout.strip()
    assert remote_tip == merge_sha

    # Real content proof, not just presence in the tree listing.
    assert _git(bare, "show", f"{merge_sha}:mine.txt").stdout == "mine"
    assert _git(bare, "show", f"{merge_sha}:other_file.txt").stdout == "from the other session"


def test_plumb_commit_auto_reconciles_on_non_fast_forward_push(tmp_path):
    """End-to-end: plumb_commit() itself, with auto_reconcile=True (the
    default), must recover transparently from exactly this scenario without
    the caller invoking reconcile() by hand."""
    work, bare = _init_repo_with_remote(tmp_path)
    other = _clone(bare, tmp_path / "other")

    (other / "other_file.txt").write_text("from the other session", encoding="utf-8")
    _git(other, "add", "other_file.txt")
    _git(other, "commit", "-q", "-m", "other session's commit")
    assert _git(other, "push", "origin", "main").returncode == 0

    (work / "mine.txt").write_text("mine", encoding="utf-8")

    result = gpc.plumb_commit(
        ["mine.txt"], "my commit", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True,
    )

    assert result["pushed"] is True
    assert result["reconciled_against"]

    tree_files = _git(bare, "ls-tree", "-r", "--name-only", result["commit_sha"]).stdout
    assert "mine.txt" in tree_files
    assert "other_file.txt" in tree_files


def test_plumb_commit_raises_when_auto_reconcile_disabled(tmp_path):
    """auto_reconcile=False must preserve the pre-hardening behavior: raise
    on a rejected push rather than silently attempting reconciliation --
    for callers that deliberately want to handle divergence themselves."""
    work, bare = _init_repo_with_remote(tmp_path)
    other = _clone(bare, tmp_path / "other")

    (other / "other_file.txt").write_text("from the other session", encoding="utf-8")
    _git(other, "add", "other_file.txt")
    _git(other, "commit", "-q", "-m", "other session's commit")
    assert _git(other, "push", "origin", "main").returncode == 0

    (work / "mine.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(gpc.PlumbCommitPushRejected) as exc_info:
        gpc.plumb_commit(
            ["mine.txt"], "my commit", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True, auto_reconcile=False,
        )

    # The already-built commit's identity must be recoverable from the
    # exception -- nothing locally built is lost even though the push failed.
    assert exc_info.value.commit_sha
    assert exc_info.value.files == ["mine.txt"]

    # And the commit really does exist locally, ready for a manual reconcile().
    show = _git(work, "cat-file", "-t", exc_info.value.commit_sha)
    assert show.stdout.strip() == "commit"

    # Nothing pushed to the remote.
    remote_tip = _git(bare, "rev-parse", "main").stdout.strip()
    other_tip = _git(other, "rev-parse", "HEAD").stdout.strip()
    assert remote_tip == other_tip


def test_reconcile_refuses_a_real_content_conflict(tmp_path):
    """If the remote's new tip ALSO touched a file this commit touches,
    reconcile() must refuse rather than silently discarding the remote's
    change -- exactly the silent-revert failure mode PlumbCommitBlocked's
    stale-file-regression check exists to prevent elsewhere in this tool."""
    work, bare = _init_repo_with_remote(tmp_path)
    other = _clone(bare, tmp_path / "other")

    # Other session edits seed.txt (a file this session will ALSO touch).
    (other / "seed.txt").write_text("other session's edit", encoding="utf-8")
    _git(other, "add", "seed.txt")
    _git(other, "commit", "-q", "-m", "other session edits seed.txt")
    assert _git(other, "push", "origin", "main").returncode == 0

    stale_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "seed.txt").write_text("my conflicting edit", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "my edit to seed.txt")
    my_commit_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    with pytest.raises(gpc.PlumbCommitReconcileConflict) as exc_info:
        gpc.reconcile(
            my_commit_sha, ["seed.txt"], repo_root=work, branch="main",
            remote=str(bare), old_parent_sha=stale_head,
        )
    assert "seed.txt" in exc_info.value.files

    # Nothing was pushed -- the remote's own content must be untouched.
    remote_seed = _git(bare, "show", "main:seed.txt").stdout
    assert remote_seed == "other session's edit"


def test_reconcile_is_a_clean_fast_forward_when_nothing_further_diverged(tmp_path):
    """If old_parent_sha already matches the remote tip by the time
    reconcile() runs (the race window closed on its own), it must do a
    plain fast-forward push -- no unnecessary merge commit."""
    work, bare = _init_repo_with_remote(tmp_path)
    head = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "mine.txt").write_text("mine", encoding="utf-8")
    _git(work, "add", "mine.txt")
    _git(work, "commit", "-q", "-m", "my commit")
    my_commit_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    result = gpc.reconcile(
        my_commit_sha, ["mine.txt"], repo_root=work, branch="main",
        remote=str(bare), old_parent_sha=head,
    )

    assert result["fast_forward"] is True
    assert result["commit_sha"] == my_commit_sha  # no new merge commit built
    remote_tip = _git(bare, "rev-parse", "main").stdout.strip()
    assert remote_tip == my_commit_sha


def test_reconcile_handles_a_deleted_file_correctly(tmp_path):
    """A commit that DELETES a file (present in old_parent_sha's tree,
    absent from commit_sha's tree) must have that deletion correctly
    replayed onto the new remote tip's tree, not silently dropped."""
    work, bare = _init_repo_with_remote(tmp_path)
    other = _clone(bare, tmp_path / "other")

    (other / "unrelated.txt").write_text("unrelated", encoding="utf-8")
    _git(other, "add", "unrelated.txt")
    _git(other, "commit", "-q", "-m", "other session's unrelated commit")
    assert _git(other, "push", "origin", "main").returncode == 0

    stale_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    _git(work, "rm", "-q", "seed.txt")
    _git(work, "commit", "-q", "-m", "delete seed.txt")
    my_commit_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    result = gpc.reconcile(
        my_commit_sha, ["seed.txt"], repo_root=work, branch="main",
        remote=str(bare), old_parent_sha=stale_head,
    )

    tree_files = _git(bare, "ls-tree", "-r", "--name-only", result["commit_sha"]).stdout
    assert "seed.txt" not in tree_files
    assert "unrelated.txt" in tree_files


def test_reconcile_retried_with_a_stale_parent_after_it_already_landed_fails_safe(tmp_path):
    """Recovery/idempotency boundary: if a caller retries reconcile() for
    the SAME (commit_sha, old_parent_sha) pair after the first call already
    landed a merge on the remote, it must never silently corrupt or
    duplicate that state. commit_sha (an ancestor of the already-pushed
    merge) is no longer a valid fast-forward target, and old_parent_sha no
    longer reflects the remote's real history for mine.txt -- reconcile()
    must fail closed (a conflict or a git-level rejection), never silently
    "succeed" a second time with different results.
    """
    work, bare = _init_repo_with_remote(tmp_path)
    other = _clone(bare, tmp_path / "other")

    (other / "other_file.txt").write_text("from the other session", encoding="utf-8")
    _git(other, "add", "other_file.txt")
    _git(other, "commit", "-q", "-m", "other session's commit")
    assert _git(other, "push", "origin", "main").returncode == 0

    stale_head = _git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "mine.txt").write_text("mine", encoding="utf-8")
    _git(work, "add", "mine.txt")
    _git(work, "commit", "-q", "-m", "my commit")
    my_commit_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    first = gpc.reconcile(
        my_commit_sha, ["mine.txt"], repo_root=work, branch="main",
        remote=str(bare), old_parent_sha=stale_head,
    )
    assert first["fast_forward"] is False
    remote_after_first = _git(bare, "rev-parse", "main").stdout.strip()
    assert remote_after_first == first["commit_sha"]

    # Retry with the exact same (now-stale) arguments a well-behaved caller
    # would only send by mistake (e.g. re-derived old_parent_sha from a
    # cached value instead of a fresh `git rev-parse`). This must not
    # silently re-succeed and must not alter what's already on the remote.
    with pytest.raises(gpc.PlumbCommitError):
        gpc.reconcile(
            my_commit_sha, ["mine.txt"], repo_root=work, branch="main",
            remote=str(bare), old_parent_sha=stale_head,
        )

    remote_after_retry = _git(bare, "rev-parse", "main").stdout.strip()
    assert remote_after_retry == remote_after_first, (
        "a failed/rejected retry must never alter what the first, "
        "successful reconcile() already landed"
    )

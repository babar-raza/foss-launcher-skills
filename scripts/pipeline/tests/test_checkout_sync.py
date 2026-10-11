"""Tests for lib/checkout_sync.py + its git_plumb_commit.py integration
(2026-08-29 stale-guard plan, T11 / TC-SG-03 -- the RC-1 source fix).

The class under test, reproduced live before the fix: any commit built via an
isolated temp index + `update-ref` (git_plumb_commit.py, the manual plumbing
recipe, object-level merges) leaves the REAL index holding the pre-commit blob
for each committed path. The next porcelain commit by ANY session -- which
commits the whole index -- then silently reverts those paths byte-exactly.
Porcelain commits are emulated here exactly as git performs them
(`write-tree` on the real index + `commit-tree` + `update-ref`), which is also
why no test in this file shells out to the porcelain command itself.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _TESTS_DIR.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_OPS_DIR = _PIPELINE_DIR / "commands" / "ops"
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

from lib import checkout_sync as cs  # noqa: E402
import git_plumb_commit as gpc  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configs():
    yield
    cs.configure()
    gpc.configure()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )


def _seed_repo(tmp_path: Path, *, autocrlf: bool = False) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.autocrlf", "true" if autocrlf else "false")
    (repo / "a.txt").write_bytes(b"v1\r\n" if autocrlf else b"v1\n")
    (repo / "other.txt").write_bytes(b"x\n")
    _git(repo, "add", "a.txt", "other.txt")
    _porcelain_commit(repo, "base", parent=None)
    return repo


def _porcelain_commit(repo: Path, message: str, *, parent: "str | None" = "HEAD") -> str:
    """Exactly what the porcelain commit command does: commit the REAL index."""
    tree = _git(repo, "write-tree").stdout.strip()
    args = ["commit-tree", tree, "-m", message]
    if parent:
        args[2:2] = ["-p", parent]
    sha = _git(repo, *args).stdout.strip()
    _git(repo, "update-ref", "refs/heads/main", sha)
    return sha


def _plumb_change(repo: Path, path: str, content: bytes) -> "tuple[str, str]":
    """git_plumb_commit.py's exact sequence: isolated temp index, worktree
    content, commit-tree, update-ref. Returns (old_head, new_head)."""
    old_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / path).write_bytes(content)
    tmp_index = repo.parent / f"tmp_index_{path.replace('/', '_')}"
    if tmp_index.exists():
        tmp_index.unlink()
    env_args = ["-c", "core.autocrlf=true"] if False else []
    import os
    env = {**os.environ, "GIT_INDEX_FILE": str(tmp_index)}
    subprocess.run(["git", "read-tree", "HEAD"], cwd=str(repo), env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "add", "-f", path], cwd=str(repo), env=env,
                   capture_output=True, check=True)
    tree = subprocess.run(["git", "write-tree"], cwd=str(repo), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()
    new_head = _git(repo, "commit-tree", tree, "-p", old_head, "-m", f"plumbed {path}").stdout.strip()
    _git(repo, "update-ref", "refs/heads/main", new_head)
    tmp_index.unlink(missing_ok=True)
    return old_head, new_head


def _plumb_delete(repo: Path, path: str) -> "tuple[str, str]":
    old_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    import os
    tmp_index = repo.parent / "tmp_index_del"
    if tmp_index.exists():
        tmp_index.unlink()
    env = {**os.environ, "GIT_INDEX_FILE": str(tmp_index)}
    subprocess.run(["git", "read-tree", "HEAD"], cwd=str(repo), env=env,
                   capture_output=True, check=True)
    subprocess.run(["git", "update-index", "--force-remove", path], cwd=str(repo),
                   env=env, capture_output=True, check=True)
    tree = subprocess.run(["git", "write-tree"], cwd=str(repo), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()
    new_head = _git(repo, "commit-tree", tree, "-p", old_head, "-m", f"plumb-delete {path}").stdout.strip()
    _git(repo, "update-ref", "refs/heads/main", new_head)
    tmp_index.unlink(missing_ok=True)
    return old_head, new_head


def _status(repo: Path, path: str) -> str:
    return _git(repo, "status", "--porcelain", "--", path).stdout.strip()


def _index_oid(repo: Path, path: str) -> str:
    out = _git(repo, "ls-files", "-s", "--", path).stdout.strip()
    return out.split()[1] if out else ""


# ---------------------------------------------------------------------------
# The class itself, and the fix
# ---------------------------------------------------------------------------

def test_without_sync_next_porcelain_commit_reverts_the_plumbed_change(tmp_path):
    """Negative control documenting the RC-1 class: this is the exact
    mechanism that reverted the MT018 fixes and the 2026-08-07 keyword files."""
    repo = _seed_repo(tmp_path)
    _old, _new = _plumb_change(repo, "a.txt", b"v2\n")
    assert _status(repo, "a.txt") == "MM a.txt"  # index=v1(stale), worktree=v2, HEAD=v2

    (repo / "other.txt").write_bytes(b"y\n")
    _git(repo, "add", "other.txt")
    _porcelain_commit(repo, "other session: only other.txt")

    assert _git(repo, "show", "HEAD:a.txt").stdout == "v1\n"  # silently reverted


def test_synced_residue_survives_the_next_porcelain_commit(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _plumb_change(repo, "a.txt", b"v2\n")

    report = cs.sync_after_ref_advance(old, new, paths=["a.txt"], repo_root=repo)

    assert report.synced_index == ["a.txt"]
    assert _status(repo, "a.txt") == ""  # residue gone

    (repo / "other.txt").write_bytes(b"y\n")
    _git(repo, "add", "other.txt")
    _porcelain_commit(repo, "other session: only other.txt")
    assert _git(repo, "show", "HEAD:a.txt").stdout == "v2\n"  # preserved


def test_default_paths_come_from_the_advance_diff(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _plumb_change(repo, "a.txt", b"v2\n")
    report = cs.sync_after_ref_advance(old, new, repo_root=repo)  # no explicit paths
    assert report.synced_index == ["a.txt"]


def test_skips_entry_someone_else_staged_and_preserves_it_byte_identically(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _plumb_change(repo, "a.txt", b"v2\n")
    # A concurrent session stages ITS OWN content for the same path.
    (repo / "a.txt").write_bytes(b"their-work\n")
    _git(repo, "add", "a.txt")
    their_oid = _index_oid(repo, "a.txt")

    report = cs.sync_after_ref_advance(old, new, paths=["a.txt"], repo_root=repo)

    assert report.synced_index == []
    assert report.skipped_dirty == ["a.txt"]
    assert _index_oid(repo, "a.txt") == their_oid  # untouched


def test_removes_index_entry_for_path_deleted_by_the_advance(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _plumb_delete(repo, "a.txt")
    assert _index_oid(repo, "a.txt")  # residue entry still present

    report = cs.sync_after_ref_advance(old, new, repo_root=repo)

    assert report.removed_index == ["a.txt"]
    assert _index_oid(repo, "a.txt") == ""
    assert (repo / "a.txt").exists()  # index mode NEVER touches the worktree


def test_idempotent_second_run_touches_nothing(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _plumb_change(repo, "a.txt", b"v2\n")
    first = cs.sync_after_ref_advance(old, new, paths=["a.txt"], repo_root=repo)
    assert first.touched == 1
    second = cs.sync_after_ref_advance(old, new, paths=["a.txt"], repo_root=repo)
    assert second.touched == 0
    assert second.skipped_dirty == []


def test_index_lock_aborts_without_touching_anything(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _plumb_change(repo, "a.txt", b"v2\n")
    lock = repo / ".git" / "index.lock"
    lock.write_bytes(b"")
    try:
        report = cs.sync_after_ref_advance(old, new, paths=["a.txt"], repo_root=repo)
    finally:
        lock.unlink()
    assert report.index_locked is True
    assert report.synced_index == []
    assert _status(repo, "a.txt") == "MM a.txt"  # residue untouched (never wait/steal)


# ---------------------------------------------------------------------------
# The remote-advance / reconcile trap (index+worktree mode)
# ---------------------------------------------------------------------------

def _remote_advance(tmp_path: Path, repo: Path, content: bytes) -> "tuple[str, str]":
    """A remote commit arrives via fetch + update-ref (the object-level-merge
    recipe / reconcile() shape): index AND worktree keep the old content."""
    clone = tmp_path / "r2"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)],
                   capture_output=True, check=True)
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    (clone / "a.txt").write_bytes(content)
    _git(clone, "add", "a.txt")
    remote_sha = _porcelain_commit(clone, "remote change")
    old_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "fetch", "-q", str(clone), "main")
    _git(repo, "update-ref", "refs/heads/main", remote_sha)
    return old_head, remote_sha


def test_worktree_mode_syncs_a_remote_advance(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _remote_advance(tmp_path, repo, b"remote-v3\n")
    assert _status(repo, "a.txt") == "M  a.txt"  # old content posing as staged work

    report = cs.sync_after_ref_advance(old, new, repo_root=repo, mode="index+worktree")

    assert "a.txt" in report.synced_worktree
    assert (repo / "a.txt").read_bytes() == b"remote-v3\n"
    assert _status(repo, "a.txt") == ""


def test_worktree_mode_never_overwrites_a_local_modification(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _remote_advance(tmp_path, repo, b"remote-v3\n")
    (repo / "a.txt").write_bytes(b"my uncommitted local work\n")

    report = cs.sync_after_ref_advance(old, new, repo_root=repo, mode="index+worktree")

    assert report.synced_worktree == []
    assert "a.txt" in report.skipped_dirty
    assert (repo / "a.txt").read_bytes() == b"my uncommitted local work\n"


def test_worktree_gating_respects_the_clean_filter_under_autocrlf(tmp_path):
    """core.autocrlf=true: on-disk CRLF bytes differ from the LF blob, so a
    raw-bytes comparison would wrongly classify a pristine file as modified.
    hash-object applies the clean filter, so the sync still recognises it."""
    repo = _seed_repo(tmp_path, autocrlf=True)
    assert b"\r\n" in (repo / "a.txt").read_bytes()  # fixture really is CRLF on disk
    old, new = _remote_advance(tmp_path, repo, b"remote-v3\n")

    report = cs.sync_after_ref_advance(old, new, repo_root=repo, mode="index+worktree")

    assert "a.txt" in report.synced_worktree
    assert _status(repo, "a.txt") == ""


# ---------------------------------------------------------------------------
# Residue report (read-only)
# ---------------------------------------------------------------------------

def test_residue_report_lists_exactly_the_trap_then_clears(tmp_path):
    repo = _seed_repo(tmp_path)
    old, new = _plumb_change(repo, "a.txt", b"v2\n")

    rows = cs.residue_report(repo_root=repo)
    assert [r["path"] for r in rows] == ["a.txt"]
    assert rows[0]["reverts_commit"] == new

    cs.sync_after_ref_advance(old, new, paths=["a.txt"], repo_root=repo)
    assert cs.residue_report(repo_root=repo) == []


# ---------------------------------------------------------------------------
# git_plumb_commit.py integration (automatic post-commit sync)
# ---------------------------------------------------------------------------

def _init_repo_with_remote(tmp_path: Path) -> "tuple[Path, Path]":
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
    _porcelain_commit(work, "seed", parent=None)
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", "main")
    return work, bare


def test_plumb_commit_leaves_no_residue_for_its_own_files(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["f.txt"], "auto-synced", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, skip_ledger_check=True, skip_tier1_checks=True,
    )

    assert result["pushed"] is True
    assert _status(work, "f.txt") == ""  # no MM residue -- the RC-1 trap is gone


def test_plumb_commit_no_sync_flag_leaves_the_documented_residue(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    gpc.plumb_commit(
        ["f.txt"], "unsynced", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, skip_ledger_check=True, skip_tier1_checks=True,
        sync_state=False,
    )

    # f.txt is new: with sync off, the index has NO entry while HEAD does ->
    # a porcelain commit of the untouched index would delete it (the residue
    # class, deletion flavour).
    assert _index_oid(work, "f.txt") == ""


def test_plumb_commit_sync_preserves_other_sessions_staged_entry(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "mine.txt").write_text("mine", encoding="utf-8")
    (work / "someone_elses.txt").write_text("their staged content", encoding="utf-8")
    _git(work, "add", "someone_elses.txt")
    their_entry_before = _git(work, "ls-files", "-s", "--", "someone_elses.txt").stdout

    gpc.plumb_commit(
        ["mine.txt"], "add mine.txt", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, skip_ledger_check=True, skip_tier1_checks=True,
    )

    their_entry_after = _git(work, "ls-files", "-s", "--", "someone_elses.txt").stdout
    assert their_entry_after == their_entry_before  # byte-identical
    assert _status(work, "mine.txt") == ""  # and my own path carries no trap

"""Tests for scripts/pipeline/core/clone_cache.py — update_clone() function.

Uses a local temporary git repo as the remote to avoid any network calls.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Ensure pipeline directory is on sys.path
_PIPELINE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from core.clone_cache import (  # noqa: E402
    clone_exists,
    clone_head_sha,
    clone_path,
    update_clone,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _make_bare_remote(tmp_path: Path) -> Path:
    """Create a minimal bare git repo to act as the upstream remote."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git("init", "--bare", cwd=remote)
    # Seed with one commit so the remote has a HEAD
    work = tmp_path / "work"
    work.mkdir()
    _git("init", cwd=work)
    _git("config", "user.email", "test@test.com", cwd=work)
    _git("config", "user.name", "Test", cwd=work)
    (work / "README.md").write_text("init")
    _git("add", ".", cwd=work)
    _git("commit", "-m", "init", cwd=work)
    _git("remote", "add", "origin", str(remote), cwd=work)
    _git("push", "origin", "HEAD:main", cwd=work)
    _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)
    return remote


def _shallow_clone(remote: Path, dest: Path) -> None:
    """Create a shallow clone of `remote` at `dest`."""
    subprocess.run(
        ["git", "clone", "--depth", "1", str(remote), str(dest)],
        capture_output=True,
        check=True,
    )


# ---------------------------------------------------------------------------
# Happy path: update_clone on existing clone returns new HEAD SHA string
# ---------------------------------------------------------------------------

def test_update_clone_returns_sha(tmp_path, monkeypatch):
    """update_clone() fetches upstream and returns the new HEAD SHA."""
    remote = _make_bare_remote(tmp_path)

    # Point the cache root at tmp_path
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "cache"))

    family, platform = "testfamily", "testplatform"
    cache = tmp_path / "cache"
    dest = cache / f"aspose_{family}_{platform}"
    cache.mkdir(parents=True, exist_ok=True)
    _shallow_clone(remote, dest)

    # Confirm clone exists before calling update_clone
    assert clone_exists(family, platform)
    initial_sha = clone_head_sha(family, platform)
    assert initial_sha is not None

    # Push a new commit to remote
    work = tmp_path / "work2"
    work.mkdir()
    _git("init", cwd=work)
    _git("config", "user.email", "test@test.com", cwd=work)
    _git("config", "user.name", "Test", cwd=work)
    (work / "README.md").write_text("updated")
    _git("add", ".", cwd=work)
    _git("commit", "--allow-empty", "-m", "second commit", cwd=work)
    # Push directly to bare remote as a new commit on top of existing
    subprocess.run(
        ["git", "push", str(remote), "HEAD:main"],
        cwd=str(work),
        capture_output=True,
        check=False,
    )
    # A simpler approach: add a commit in a fresh clone of the remote
    work2 = tmp_path / "contributor"
    _shallow_clone(remote, work2)
    _git("config", "user.email", "c@c.com", cwd=work2)
    _git("config", "user.name", "Contributor", cwd=work2)
    (work2 / "NEW.md").write_text("new file")
    _git("add", ".", cwd=work2)
    _git("commit", "-m", "add new file", cwd=work2)
    _git("push", "origin", "HEAD:main", cwd=work2)

    # update_clone should fetch and return a non-None SHA
    result_sha = update_clone(family, platform)
    assert result_sha is not None
    assert isinstance(result_sha, str)
    assert len(result_sha) == 40  # full git SHA

    # The SHA should now reflect the new commit
    assert result_sha == clone_head_sha(family, platform)


# ---------------------------------------------------------------------------
# Happy path: update_clone when clone does not exist returns None
# ---------------------------------------------------------------------------

def test_update_clone_missing_clone_returns_none(tmp_path, monkeypatch):
    """update_clone() returns None (without raising) when no clone exists."""
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "empty_cache"))
    result = update_clone("nonexistent", "family")
    assert result is None


# ---------------------------------------------------------------------------
# Failing path: update_clone when git fetch fails returns None without raising
# ---------------------------------------------------------------------------

def test_update_clone_bad_remote_returns_none(tmp_path, monkeypatch):
    """update_clone() returns None when git fetch fails (bad remote URL)."""
    # Create a shallow clone, then break the remote URL
    remote = _make_bare_remote(tmp_path)
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "cache"))

    family, platform = "breaktest", "net"
    cache = tmp_path / "cache"
    dest = cache / f"aspose_{family}_{platform}"
    cache.mkdir(parents=True, exist_ok=True)
    _shallow_clone(remote, dest)

    # Break the origin remote by pointing it at a non-existent path
    subprocess.run(
        ["git", "remote", "set-url", "origin", "/no/such/path/repo.git"],
        cwd=str(dest),
        capture_output=True,
        check=True,
    )

    # update_clone must return None without raising
    result = update_clone(family, platform)
    assert result is None

"""Regression test for the "Harness <harness@test.local>" identity incident
(2026-08-31): a test fixture's bare `git config user.*` inside a `git
worktree add` of the real repo silently corrupted the SHARED .git/config
(per git's own documented worktree semantics -- an unscoped `git config`
write inside any linked worktree resolves to $GIT_COMMON_DIR/config, the
exact same file the main checkout and every other worktree use), going
undetected for 9 consecutive commits.

Two independent regression controls exist for this:
  1. precommit_full_run_harness.py no longer touches git config at all --
     identity is supplied via env vars scoped to one subprocess call.
  2. conftest.py's `_guard_shared_git_identity` (session-scoped, autouse)
     detects and self-heals any test that reintroduces this class of leak.

This file tests control #2's own detect/restore mechanism directly. It
deliberately does NOT exercise it against the real repo's .git/config --
even briefly corrupting the real shared identity would risk misattributing
a genuine commit from one of this repo's other concurrently active sessions
during the test's own window, which is exactly the incident being guarded
against. Instead it uses a disposable, isolated `git init` repo (the same
safe pattern already used by every other git-config-touching fixture in
this test suite except the one that caused this incident).
"""
from __future__ import annotations

import subprocess

from conftest import _snapshot_local_git_identity


def _git(*args: str, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )


def test_snapshot_and_restore_detect_and_revert_a_local_identity_override(tmp_path):
    """Mirrors exactly the two operations `_guard_shared_git_identity`
    performs: snapshot before/after, and -- on a diff -- restore. Proves the
    mechanism actually works, isolated from the real repo entirely."""
    repo = tmp_path / "isolated_repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)

    before = _snapshot_local_git_identity(repo_root=repo)
    assert before == (None, None), (
        f"a fresh `git init` repo should have no local user.* override, got {before}"
    )

    # Simulate the incident: something sets a local override directly (the
    # exact mistake precommit_full_run_harness.py used to make).
    _git("config", "user.name", "Harness", cwd=repo)
    _git("config", "user.email", "harness@test.local", cwd=repo)

    leaked = _snapshot_local_git_identity(repo_root=repo)
    assert leaked == ("Harness", "harness@test.local"), (
        "the snapshot function failed to detect a real local git config override -- "
        "this is the exact detection _guard_shared_git_identity relies on"
    )

    # The restore path `_guard_shared_git_identity` takes when the pre-session
    # value was (None, None): unset back to falling through to global/unset.
    _git("config", "--unset", "user.name", cwd=repo)
    _git("config", "--unset", "user.email", cwd=repo)

    after = _snapshot_local_git_identity(repo_root=repo)
    assert after == before, (
        f"restore failed to return the repo to its clean pre-incident state, got {after}"
    )


def test_snapshot_and_restore_revert_to_a_prior_explicit_value(tmp_path):
    """The restore path when the pre-session value was NOT (None, None) --
    e.g. a repo that legitimately has its own local override already set --
    must restore that value, not blank it out."""
    repo = tmp_path / "isolated_repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.name", "Legitimate Owner", cwd=repo)
    _git("config", "user.email", "owner@example.com", cwd=repo)

    before = _snapshot_local_git_identity(repo_root=repo)
    assert before == ("Legitimate Owner", "owner@example.com")

    _git("config", "user.name", "Harness", cwd=repo)
    _git("config", "user.email", "harness@test.local", cwd=repo)
    assert _snapshot_local_git_identity(repo_root=repo) == ("Harness", "harness@test.local")

    # Restore path when `before` values are not None: set explicitly, not unset.
    _git("config", "user.name", before[0], cwd=repo)
    _git("config", "user.email", before[1], cwd=repo)

    assert _snapshot_local_git_identity(repo_root=repo) == before

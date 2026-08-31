"""Tests for scripts/ci/sync_remotes.py.

Every scenario runs against local, throwaway bare git repositories standing
in for "github" and "gitlab" -- never against the real github.com or
gitlab.recruitize.ai, per GHGL-1's do-no-harm constraint.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import sync_remotes  # noqa: E402


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


def _init_bare(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(["init", "--bare", "-b", "main"], path)
    return path


def _init_worktree_with_commit(path: Path, message: str = "initial") -> Path:
    path.mkdir(parents=True)
    _git(["init", "-b", "main"], path)
    _git(["config", "user.email", "test@example.com"], path)
    _git(["config", "user.name", "Test"], path)
    (path / "README.md").write_text(f"{message}\n")
    _git(["add", "README.md"], path)
    _git(["commit", "-m", message], path)
    return path


def _commit(path: Path, message: str) -> str:
    (path / f"{message}.txt").write_text(message)
    _git(["add", f"{message}.txt"], path)
    _git(["commit", "-m", message], path)
    return _git(["rev-parse", "HEAD"], path).stdout.strip()


def _push(source: Path, target_url: str, branch: str = "main") -> None:
    _git(["push", target_url, f"HEAD:{branch}"], source)


def _clone(url: str, dest: Path) -> Path:
    _git(["clone", url, str(dest)], dest.parent)
    _git(["config", "user.email", "test@example.com"], dest)
    _git(["config", "user.name", "Test"], dest)
    return dest


def _diverged_worktrees(tmp_path: Path, patch_urls: dict) -> tuple[Path, Path, str, str]:
    """Push a common ancestor to both bares, then commit a DIFFERENT change in
    two independent clones and push each back to its own bare -- a genuine,
    independently-created divergence (not a single worktree's linear history)."""
    ancestor = _init_worktree_with_commit(tmp_path / "ancestor")
    _push(ancestor, patch_urls["gitlab"].as_uri())
    _push(ancestor, patch_urls["github"].as_uri())

    work_gitlab = _clone(patch_urls["gitlab"].as_uri(), tmp_path / "work-gitlab")
    gitlab_sha = _commit(work_gitlab, "gitlab-side-commit")
    _push(work_gitlab, patch_urls["gitlab"].as_uri())

    work_github = _clone(patch_urls["github"].as_uri(), tmp_path / "work-github")
    github_sha = _commit(work_github, "github-side-commit")
    _push(work_github, patch_urls["github"].as_uri())

    return work_gitlab, work_github, gitlab_sha, github_sha


@pytest.fixture
def env():
    return {"gitlab_token": "dummy-gitlab-token", "github_token": "dummy-github-token"}


@pytest.fixture(autouse=True)
def patch_urls(monkeypatch, tmp_path):
    """Point TARGET_URL at local bare repos instead of real remotes for every test."""
    github_bare = _init_bare(tmp_path / "github-bare.git")
    gitlab_bare = _init_bare(tmp_path / "gitlab-bare.git")
    monkeypatch.setattr(sync_remotes, "TARGET_URL", {
        "github": github_bare.as_uri(),
        "gitlab": gitlab_bare.as_uri(),
    })
    return {"github": github_bare, "gitlab": gitlab_bare}


def _bare_head(bare: Path) -> str:
    result = _git(["rev-parse", "main"], bare)
    return result.stdout.strip()


def test_already_in_sync(monkeypatch, tmp_path, env, patch_urls):
    work = _init_worktree_with_commit(tmp_path / "work")
    _push(work, patch_urls["gitlab"].as_uri())

    monkeypatch.chdir(work)
    code = sync_remotes.sync("github", "main", dry_run=False, env=env)

    assert code == sync_remotes.EXIT_SYNCED


def test_clean_fast_forward_push(monkeypatch, tmp_path, env, patch_urls):
    work = _init_worktree_with_commit(tmp_path / "work")
    _push(work, patch_urls["gitlab"].as_uri())
    new_sha = _commit(work, "second")

    monkeypatch.chdir(work)
    code = sync_remotes.sync("github", "main", dry_run=False, env=env)

    assert code == sync_remotes.EXIT_SYNCED
    assert _bare_head(patch_urls["gitlab"]) == new_sha


def test_dry_run_makes_no_change(monkeypatch, tmp_path, env, patch_urls):
    work = _init_worktree_with_commit(tmp_path / "work")
    _push(work, patch_urls["gitlab"].as_uri())
    old_target_sha = _bare_head(patch_urls["gitlab"])
    _commit(work, "second")

    monkeypatch.chdir(work)
    code = sync_remotes.sync("github", "main", dry_run=True, env=env)

    assert code == sync_remotes.EXIT_SYNCED
    assert _bare_head(patch_urls["gitlab"]) == old_target_sha  # unchanged


def test_divergence_is_rejected_not_overwritten(monkeypatch, tmp_path, env, patch_urls):
    work_gitlab, _work_github, gitlab_sha, github_sha = _diverged_worktrees(tmp_path, patch_urls)

    monkeypatch.chdir(work_gitlab)
    code = sync_remotes.sync("gitlab", "main", dry_run=False, env=env)

    assert code == sync_remotes.EXIT_DIVERGENCE
    # Neither remote's history was altered by the failed push.
    assert _bare_head(patch_urls["github"]) == github_sha
    assert _bare_head(patch_urls["gitlab"]) == gitlab_sha


def test_divergence_on_github_files_issue(monkeypatch, tmp_path, env, patch_urls):
    _work_gitlab, work_github, _gitlab_sha, _github_sha = _diverged_worktrees(tmp_path, patch_urls)

    calls = []
    monkeypatch.setattr(
        sync_remotes, "file_divergence_issue",
        lambda *a, **kw: calls.append((a, kw)),
    )

    monkeypatch.chdir(work_github)
    code = sync_remotes.sync("github", "main", dry_run=False, env=env)

    assert code == sync_remotes.EXIT_DIVERGENCE
    assert len(calls) == 1


def test_divergence_on_gitlab_does_not_file_issue(monkeypatch, tmp_path, env, patch_urls):
    work_gitlab, _work_github, _gitlab_sha, _github_sha = _diverged_worktrees(tmp_path, patch_urls)

    calls = []
    monkeypatch.setattr(
        sync_remotes, "file_divergence_issue",
        lambda *a, **kw: calls.append((a, kw)),
    )

    monkeypatch.chdir(work_gitlab)
    code = sync_remotes.sync("gitlab", "main", dry_run=False, env=env)

    assert code == sync_remotes.EXIT_DIVERGENCE
    assert calls == []  # gitlab-side job never files a GitHub issue


def test_missing_credential(monkeypatch, tmp_path, patch_urls):
    work = _init_worktree_with_commit(tmp_path / "work")
    monkeypatch.chdir(work)

    code = sync_remotes.sync("github", "main", dry_run=False, env={})

    assert code == sync_remotes.EXIT_INFRA_ERROR


def test_wrong_credential_name_is_reported(monkeypatch, tmp_path, patch_urls, capsys):
    work = _init_worktree_with_commit(tmp_path / "work")
    monkeypatch.chdir(work)

    code = sync_remotes.sync("github", "main", dry_run=False, env={"GITLAB_TOKEN": "wrong-name"})

    assert code == sync_remotes.EXIT_INFRA_ERROR
    captured = capsys.readouterr()
    assert "GITLAB_TOKEN" in captured.err
    assert "gitlab_token" in captured.err


def test_rerun_after_success_is_idempotent_noop(monkeypatch, tmp_path, env, patch_urls):
    work = _init_worktree_with_commit(tmp_path / "work")
    _push(work, patch_urls["gitlab"].as_uri())
    _commit(work, "second")

    monkeypatch.chdir(work)
    first = sync_remotes.sync("github", "main", dry_run=False, env=env)
    second = sync_remotes.sync("github", "main", dry_run=False, env=env)

    assert first == sync_remotes.EXIT_SYNCED
    assert second == sync_remotes.EXIT_SYNCED


def test_dry_run_reports_divergence_not_false_success(monkeypatch, tmp_path, env, patch_urls):
    """A dry-run must never imply a push would succeed when it would actually
    be rejected as non-fast-forward -- caught live against the real repos
    during GHGL-1's own bootstrap step, where the naive count-only dry-run
    said 'would push... No push performed' for a case that would have been
    rejected had it been attempted for real."""
    work_gitlab, _work_github, _gitlab_sha, _github_sha = _diverged_worktrees(tmp_path, patch_urls)
    old_target_sha = _bare_head(patch_urls["github"])

    monkeypatch.chdir(work_gitlab)
    code = sync_remotes.sync("gitlab", "main", dry_run=True, env=env)

    assert code == sync_remotes.EXIT_DIVERGENCE
    assert _bare_head(patch_urls["github"]) == old_target_sha  # dry-run never pushes


def test_infra_error_on_unreachable_target(monkeypatch, tmp_path, env):
    work = _init_worktree_with_commit(tmp_path / "work")
    monkeypatch.setattr(sync_remotes, "TARGET_URL", {
        "github": (tmp_path / "does-not-exist.git").as_uri(),
        "gitlab": (tmp_path / "does-not-exist-2.git").as_uri(),
    })
    monkeypatch.chdir(work)

    code = sync_remotes.sync("github", "main", dry_run=False, env=env)

    assert code == sync_remotes.EXIT_INFRA_ERROR

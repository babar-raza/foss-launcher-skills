"""Tests for scripts/pipeline/commands/ops/compute_source_delta.py (new 2026-08-29).

Uses tiny SYNTHETIC fixture git repos, never the real aspose.org checkout --
this regression-tests the tool's own correctness independent of aspose.org's
actual current state, per the sync plan's explicit testing requirement.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"))

import compute_source_delta as csd  # noqa: E402


def _git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout


@pytest.fixture
def fake_source_repo(tmp_path):
    repo = tmp_path / "fake-source"
    (repo / "skills").mkdir(parents=True)
    (repo / "scripts" / "pipeline" / "lib").mkdir(parents=True)
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "T"], repo)

    (repo / "skills" / "existing-skill.md").write_text("# existing\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "baseline"], repo)
    since_sha = _git(["rev-parse", "HEAD"], repo).strip()

    # New skill, clean.
    (repo / "skills" / "new-skill.md").write_text("# new\n", encoding="utf-8")
    # Modified existing skill.
    (repo / "skills" / "existing-skill.md").write_text("# existing, updated\n", encoding="utf-8")
    # New infra module with a hardcoded absolute path (should be flagged).
    (repo / "scripts" / "pipeline" / "lib" / "new_lib.py").write_text(
        'ROOT = "D:/onedrive/Documents/GitHub/aspose.org/content"\n', encoding="utf-8",
    )
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "add new skill, update existing, add infra module"], repo)

    return repo, since_sha


def test_collect_changed_files_reports_correct_statuses(fake_source_repo):
    repo, since_sha = fake_source_repo
    changed = csd.collect_changed_files(repo, since_sha, ["skills/", "scripts/pipeline/lib/"])
    assert changed["skills/new-skill.md"] == "A"
    assert changed["skills/existing-skill.md"] == "M"
    assert changed["scripts/pipeline/lib/new_lib.py"] == "A"


def test_classify_file_new_skill_with_no_target_counterpart(fake_source_repo, tmp_path):
    repo, _ = fake_source_repo
    empty_target = tmp_path / "empty-target"
    empty_target.mkdir()
    entry = csd.classify_file(repo, "skills/new-skill.md", "A", empty_target)
    assert entry["bucket"] == "NEW_SKILL_CANDIDATE"
    assert entry["target_already_exists"] is False


def test_classify_file_modified_skill_with_target_counterpart(fake_source_repo, tmp_path):
    repo, _ = fake_source_repo
    target = tmp_path / "target-with-skill"
    (target / "skills").mkdir(parents=True)
    (target / "skills" / "existing-skill.md").write_text("# already here\n", encoding="utf-8")
    entry = csd.classify_file(repo, "skills/existing-skill.md", "M", target)
    assert entry["bucket"] == "MODIFIED_EXISTING"
    assert entry["target_already_exists"] is True


def test_classify_file_flags_hardcoded_path_in_new_infra_module(fake_source_repo, tmp_path):
    repo, _ = fake_source_repo
    empty_target = tmp_path / "empty-target"
    empty_target.mkdir()
    entry = csd.classify_file(repo, "scripts/pipeline/lib/new_lib.py", "A", empty_target)
    assert entry["bucket"] == "NEW_INFRA_MODULE"
    assert "hardcoded_absolute_path_in_source" in entry["heuristic_flags"]


def test_classify_file_removed_upstream_bucket(fake_source_repo, tmp_path):
    repo, _ = fake_source_repo
    empty_target = tmp_path / "empty-target"
    empty_target.mkdir()
    entry = csd.classify_file(repo, "skills/some-retired-skill.md", "D", empty_target)
    assert entry["bucket"] == "REMOVED_UPSTREAM"


def test_compute_delta_end_to_end(fake_source_repo, tmp_path):
    repo, since_sha = fake_source_repo
    # A REALISTIC target: it already has existing-skill.md (hence "modified",
    # not "new"), but has never seen new-skill.md or new_lib.py.
    target = tmp_path / "realistic-target"
    (target / "skills").mkdir(parents=True)
    (target / "skills" / "existing-skill.md").write_text("# already ported" + chr(10), encoding="utf-8")
    delta = csd.compute_delta(repo, since_sha, ["skills/", "scripts/pipeline/lib/"], target)
    assert delta["total_changed_files"] == 3
    assert delta["counts_by_bucket"]["NEW_SKILL_CANDIDATE"] == 1
    assert delta["counts_by_bucket"]["MODIFIED_EXISTING"] == 1
    assert delta["counts_by_bucket"]["NEW_INFRA_MODULE"] == 1


def test_resolve_source_repo_raises_when_unset(monkeypatch):
    monkeypatch.delenv(csd.ENV_SOURCE_REPO_PATH, raising=False)
    with pytest.raises(ValueError, match="not set"):
        csd.resolve_source_repo()


def test_resolve_source_repo_raises_when_not_a_git_repo(monkeypatch, tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.setenv(csd.ENV_SOURCE_REPO_PATH, str(not_a_repo))
    with pytest.raises(ValueError, match="not a git working tree"):
        csd.resolve_source_repo()


def test_main_returns_2_when_source_repo_path_unset(monkeypatch, capsys):
    monkeypatch.delenv(csd.ENV_SOURCE_REPO_PATH, raising=False)
    code = csd.main(["--since-sha", "deadbeef"])
    assert code == 2

"""Tests for tools/capability_sync/detect_source_drift.py (new 2026-08-29).

Uses tiny SYNTHETIC fixture git repos, never the real aspose.org checkout.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "capability_sync"))

import detect_source_drift as dsd  # noqa: E402


def _git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout


@pytest.fixture
def fake_source_repo(tmp_path):
    repo = tmp_path / "fake-source"
    (repo / "scripts").mkdir(parents=True)
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "T"], repo)

    (repo / "scripts" / "stable.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "scripts" / "will_change.py").write_text("y = 1\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "anchor point"], repo)
    anchor_sha = _git(["rev-parse", "HEAD"], repo).strip()

    (repo / "scripts" / "will_change.py").write_text("y = 2  # changed upstream\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "upstream change"], repo)

    return repo, anchor_sha


def test_resolve_source_repo_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv(dsd.ENV_SOURCE_REPO_PATH, raising=False)
    assert dsd.resolve_source_repo() is None


def test_resolve_source_repo_raises_for_non_git_dir(monkeypatch, tmp_path):
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.setenv(dsd.ENV_SOURCE_REPO_PATH, str(not_a_repo))
    with pytest.raises(ValueError):
        dsd.resolve_source_repo()


def test_check_anchor_no_drift_for_unchanged_file(fake_source_repo):
    repo, anchor_sha = fake_source_repo
    anchor = {"target_path": "scripts/stable.py", "source_path": "scripts/stable.py", "commit_sha": anchor_sha}
    assert dsd.check_anchor(anchor, source_repo=repo) is None


def test_check_anchor_detects_drift_for_changed_file(fake_source_repo):
    repo, anchor_sha = fake_source_repo
    anchor = {"target_path": "scripts/will_change.py", "source_path": "scripts/will_change.py", "commit_sha": anchor_sha}
    result = dsd.check_anchor(anchor, source_repo=repo)
    assert result is not None
    assert result["drift_detected"] is True
    assert "changed since" in result["reason"]


def test_check_anchor_detects_deleted_file(fake_source_repo):
    repo, anchor_sha = fake_source_repo
    _git(["rm", "-q", "scripts/will_change.py"], repo)
    _git(["commit", "-q", "-m", "remove file"], repo)
    anchor = {"target_path": "scripts/will_change.py", "source_path": "scripts/will_change.py", "commit_sha": anchor_sha}
    result = dsd.check_anchor(anchor, source_repo=repo)
    assert result is not None
    assert "no longer exists" in result["reason"]


def test_check_anchor_skips_incomplete_anchor(fake_source_repo):
    repo, _ = fake_source_repo
    assert dsd.check_anchor({"target_path": "x"}, source_repo=repo) is None


def test_detect_drift_mixed_results(fake_source_repo, tmp_path, monkeypatch):
    repo, anchor_sha = fake_source_repo
    anchors_file = tmp_path / 'source-anchors.yaml'
    rows = [
        {'target_path': 'a', 'source_path': 'scripts/stable.py', 'commit_sha': anchor_sha},
        {'target_path': 'b', 'source_path': 'scripts/will_change.py', 'commit_sha': anchor_sha},
    ]
    lines = ['schema_version: 1', 'anchors:']
    for row in rows:
        lines.append('  - target_path: ' + row['target_path'])
        lines.append('    source_path: ' + row['source_path'])
        lines.append("    capability_id: null")
        lines.append('    commit_sha: ' + row['commit_sha'])
    anchors_file.write_text(chr(10).join(lines) + chr(10), encoding='utf-8')
    monkeypatch.setattr(dsd, '_ANCHORS_FILE', anchors_file)
    entries, total = dsd.detect_drift(repo)
    assert total == 2
    assert len(entries) == 1
    assert entries[0]['target_path'] == 'b'


def test_main_check_returns_1_on_drift(fake_source_repo, tmp_path, monkeypatch):
    repo, anchor_sha = fake_source_repo
    anchors_file = tmp_path / 'source-anchors.yaml'
    lines = [
        'schema_version: 1',
        'anchors:',
        '  - target_path: b',
        '    source_path: scripts/will_change.py',
        '    capability_id: null',
        '    commit_sha: ' + anchor_sha,
    ]
    anchors_file.write_text(chr(10).join(lines) + chr(10), encoding='utf-8')
    monkeypatch.setattr(dsd, '_ANCHORS_FILE', anchors_file)
    monkeypatch.setenv(dsd.ENV_SOURCE_REPO_PATH, str(repo))
    assert dsd.main(['--check']) == 1


def test_main_returns_0_when_source_repo_path_unset(monkeypatch, capsys):
    monkeypatch.delenv(dsd.ENV_SOURCE_REPO_PATH, raising=False)
    code = dsd.main(['--check'])
    assert code == 0
    assert 'SKIPPED' in capsys.readouterr().err

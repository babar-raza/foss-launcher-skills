"""Tests for scripts/pipeline/lib/input_manifest.py (TC-13 slice,
readme-refresh-trackb-and-followon-2026-09-01).

Real regression input: tex/python's own documented BLOCKER (this mission's TC-27a
canary) -- data/aspose_com_targets.json corrected 4 days after the candidate was
composed, undetected because nothing recorded what the candidate was built against.
"""

import json
import subprocess
from pathlib import Path

import pytest

from lib import input_manifest as im


@pytest.fixture(autouse=True)
def _reset():
    yield
    im.configure()


def _init_real_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(path), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=str(path), check=True)


def _write_targets(repo_root: Path, platforms: dict) -> None:
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    (repo_root / "data" / "aspose_com_targets.json").write_text(
        json.dumps({"targets": {"products.aspose.com": {"platforms": platforms}}}), encoding="utf-8",
    )


def test_resolve_manifest_real_clone_cache_and_ee_target(tmp_path):
    repo_root = tmp_path / "repo"
    clone_cache = repo_root / "clone"
    _init_real_git_repo(clone_cache)
    _write_targets(repo_root, {"tex/python": {"url": "https://products.aspose.com/tex/python/", "http_status": 200}})
    im.configure(repo_root=repo_root)

    manifest = im.resolve_input_manifest("tex", "python", clone_cache)
    assert manifest["clone_cache"]["commit"] is not None
    assert manifest["clone_cache"]["tree"] is not None
    assert manifest["enterprise_edition_target"]["entry"]["url"] == "https://products.aspose.com/tex/python/"
    assert manifest["manifest_hash"]


def test_resolve_manifest_handles_missing_clone_cache_and_registry(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    im.configure(repo_root=repo_root)

    manifest = im.resolve_input_manifest("nope", "nope", repo_root / "no-such-clone")
    assert manifest["clone_cache"]["commit"] is None
    assert manifest["clone_cache"]["tree"] is None
    assert manifest["enterprise_edition_target"]["entry"] is None
    assert manifest["manifest_hash"]  # still hashes cleanly, never raises


def test_diff_manifests_empty_when_identical():
    m = {"clone_cache": {"commit": "abc", "tree": "def"},
         "enterprise_edition_target": {"entry_sha256": "xyz"}}
    assert im.diff_manifests(m, m) == []


def test_diff_manifests_real_tex_python_regression_ee_target_changed_after_compose():
    """The exact real incident: the EE target entry changes underneath an already-composed
    candidate. Must be named specifically, not just 'something changed'."""
    pinned = {"clone_cache": {"commit": "abc", "tree": "def"},
              "enterprise_edition_target": {"entry_sha256": "old-hash"}}
    current = {"clone_cache": {"commit": "abc", "tree": "def"},
               "enterprise_edition_target": {"entry_sha256": "new-hash"}}
    diffs = im.diff_manifests(pinned, current)
    assert len(diffs) == 1
    assert "aspose_com_targets.json" in diffs[0]


def test_diff_manifests_detects_clone_cache_drift_separately_from_registry_drift():
    pinned = {"clone_cache": {"commit": "abc", "tree": "tree1"},
              "enterprise_edition_target": {"entry_sha256": "same"}}
    current = {"clone_cache": {"commit": "xyz", "tree": "tree2"},
               "enterprise_edition_target": {"entry_sha256": "same"}}
    diffs = im.diff_manifests(pinned, current)
    assert len(diffs) == 2
    assert any("commit" in d for d in diffs)
    assert any("tree" in d for d in diffs)


def test_manifest_hash_changes_when_ee_target_entry_changes(tmp_path):
    repo_root = tmp_path / "repo"
    clone_cache = repo_root / "clone"
    _init_real_git_repo(clone_cache)
    im.configure(repo_root=repo_root)

    _write_targets(repo_root, {"tex/python": {"url": "https://products.aspose.com/tex/python/", "http_status": 200}})
    before = im.resolve_input_manifest("tex", "python", clone_cache)

    _write_targets(repo_root, {"tex/python": {"url": "https://products.aspose.com/tex/python-corrected/", "http_status": 200}})
    after = im.resolve_input_manifest("tex", "python", clone_cache)

    assert before["manifest_hash"] != after["manifest_hash"]
    diffs = im.diff_manifests(before, after)
    assert len(diffs) == 1
    assert "aspose_com_targets.json" in diffs[0]

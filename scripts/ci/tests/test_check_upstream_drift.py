"""Tests for check_upstream_drift.py — FRESH-001 rewrite.

Covers:
  - check_drift() classification (unchanged, current, no baseline, fetch failure)
  - Issue dedup: find_existing_issue() label-pair search
  - file_or_update_issue(): create vs comment, against a mocked `gh` runner
  - Drift state persistence (data/upstream_drift_state.json shape, consecutive
    weeks counter, reset-to-zero when a product stops being flagged)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))

import check_upstream_drift as cud  # noqa: E402


@pytest.fixture(autouse=True)
def _configure(tmp_path):
    cud.configure(repo_root=tmp_path)
    yield
    cud.configure(repo_root=None)


def _write_products(tmp_path, entries):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "products.json").write_text(json.dumps(entries), encoding="utf-8")


def _write_baselines(tmp_path, entries):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "upstream_baselines.json").write_text(json.dumps(entries), encoding="utf-8")


def _cp(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestCheckDrift:
    def test_unchanged_when_sha_matches(self, tmp_path):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": True,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {"cells/net": "sha1"})
        runner = MagicMock(return_value=_cp(stdout="sha1"))
        result = cud.check_drift(runner=runner)
        assert result["findings"] == []
        assert result["no_drift_count"] == 1

    def test_no_baseline_is_high(self, tmp_path):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": True,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {})
        runner = MagicMock(return_value=_cp(stdout="sha1"))
        result = cud.check_drift(runner=runner)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["level"] == "HIGH"
        assert result["findings"][0]["reason"] == "NO_BASELINE"

    def test_fetch_failure_is_medium_error(self, tmp_path):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": True,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {"cells/net": "sha1"})
        runner = MagicMock(return_value=_cp(returncode=1))
        result = cud.check_drift(runner=runner)
        assert result["findings"][0]["level"] == "MEDIUM"
        assert result["error_count"] == 1

    def test_sha_drift_classified_via_compare(self, tmp_path):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": True,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {"cells/net": "old_sha"})

        def _side_effect(cmd, **kw):
            if "commits/HEAD" in cmd[2]:
                return _cp(stdout="new_sha")
            if "compare" in cmd[2]:
                return _cp(stdout="src/Program.cs")
            return _cp(returncode=1)

        runner = MagicMock(side_effect=_side_effect)
        result = cud.check_drift(runner=runner)
        assert result["findings"][0]["level"] == "HIGH"

    def test_inactive_products_skipped(self, tmp_path):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": False,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {})
        runner = MagicMock(return_value=_cp(stdout="sha1"))
        result = cud.check_drift(runner=runner)
        assert result["findings"] == []
        runner.assert_not_called()


class TestFindExistingIssue:
    def test_returns_number_when_found(self, tmp_path):
        runner = MagicMock(return_value=_cp(stdout=json.dumps([{"number": 42}])))
        num = cud.find_existing_issue("cells", "net", repo="org/repo", runner=runner)
        assert num == 42
        args = runner.call_args[0][0]
        assert "upstream-drift" in args
        assert "product:cells-net" in args

    def test_returns_none_when_not_found(self, tmp_path):
        runner = MagicMock(return_value=_cp(stdout="[]"))
        num = cud.find_existing_issue("cells", "net", repo="org/repo", runner=runner)
        assert num is None

    def test_returns_none_on_gh_failure(self, tmp_path):
        runner = MagicMock(return_value=_cp(returncode=1))
        num = cud.find_existing_issue("cells", "net", repo="org/repo", runner=runner)
        assert num is None


class TestFileOrUpdateIssue:
    FINDING = {"family": "cells", "platform": "net", "level": "HIGH", "reason": "SHA_DRIFT",
               "stored": "455b1c37a5a9", "head": "c0176f510f13"}

    def test_creates_new_issue_when_none_exists(self, tmp_path):
        def _side_effect(cmd, **kw):
            if cmd[1] == "issue" and cmd[2] == "list":
                return _cp(stdout="[]")
            if cmd[1] == "issue" and cmd[2] == "create":
                return _cp(stdout="https://github.com/org/repo/issues/99")
            return _cp(returncode=1)

        runner = MagicMock(side_effect=_side_effect)
        result = cud.file_or_update_issue(self.FINDING, repo="org/repo", runner=runner)
        assert result == {"action": "created", "issue_number": 99}

    def test_comments_on_existing_issue_instead_of_duplicating(self, tmp_path):
        def _side_effect(cmd, **kw):
            if cmd[1] == "issue" and cmd[2] == "list":
                return _cp(stdout=json.dumps([{"number": 42}]))
            if cmd[1] == "issue" and cmd[2] == "comment":
                return _cp(returncode=0)
            return _cp(returncode=1)

        runner = MagicMock(side_effect=_side_effect)
        result = cud.file_or_update_issue(self.FINDING, repo="org/repo", runner=runner)
        assert result == {"action": "commented", "issue_number": 42}
        # never called "gh issue create"
        create_calls = [c for c in runner.call_args_list if "create" in c[0][0]]
        assert create_calls == []

    def test_new_issue_names_product_and_shas_in_body(self, tmp_path):
        captured = {}

        def _side_effect(cmd, **kw):
            if cmd[1] == "issue" and cmd[2] == "list":
                return _cp(stdout="[]")
            if cmd[1] == "issue" and cmd[2] == "create":
                captured["body"] = cmd[cmd.index("--body") + 1]
                captured["title"] = cmd[cmd.index("--title") + 1]
                return _cp(stdout="https://github.com/org/repo/issues/1")
            return _cp(returncode=1)

        runner = MagicMock(side_effect=_side_effect)
        cud.file_or_update_issue(self.FINDING, repo="org/repo", runner=runner)
        assert "cells/net" in captured["title"]
        assert "cells/net" in captured["body"]
        assert "455b1c37a5a9" in captured["body"]
        assert "c0176f510f13" in captured["body"]

    def test_dedup_labels_applied_on_create(self, tmp_path):
        def _side_effect(cmd, **kw):
            if cmd[1] == "issue" and cmd[2] == "list":
                return _cp(stdout="[]")
            if cmd[1] == "issue" and cmd[2] == "create":
                return _cp(stdout="https://github.com/org/repo/issues/1")
            return _cp(returncode=1)

        runner = MagicMock(side_effect=_side_effect)
        cud.file_or_update_issue(self.FINDING, repo="org/repo", runner=runner)
        create_cmd = [
            c[0][0] for c in runner.call_args_list
            if c[0][0][1] == "issue" and c[0][0][2] == "create"
        ][0]
        assert "upstream-drift" in create_cmd
        assert "product:cells-net" in create_cmd

    def test_ensures_product_label_exists_before_create(self, tmp_path):
        """The label-creation call must happen, and must precede `gh issue
        create` -- this is the fix for the confirmed live bug where `gh
        issue create --label product:{family}-{platform}` failed silently
        because that label had never been provisioned in the repo."""
        def _side_effect(cmd, **kw):
            if cmd[1] == "issue" and cmd[2] == "list":
                return _cp(stdout="[]")
            if cmd[1] == "issue" and cmd[2] == "create":
                return _cp(stdout="https://github.com/org/repo/issues/1")
            return _cp(returncode=1)

        runner = MagicMock(side_effect=_side_effect)
        cud.file_or_update_issue(self.FINDING, repo="org/repo", runner=runner)
        calls = [c[0][0] for c in runner.call_args_list]
        label_create_calls = [
            c for c in calls if c[1] == "label" and c[2] == "create"
        ]
        assert len(label_create_calls) == 1
        assert "product:cells-net" in label_create_calls[0]
        issue_create_idx = next(
            i for i, c in enumerate(calls) if c[1] == "issue" and c[2] == "create"
        )
        label_create_idx = next(
            i for i, c in enumerate(calls) if c[1] == "label" and c[2] == "create"
        )
        assert label_create_idx < issue_create_idx


class TestDriftStatePersistence:
    def test_update_and_save_roundtrip(self, tmp_path):
        finding = {"family": "cells", "platform": "net", "level": "HIGH",
                   "stored": "old", "head": "new"}
        state = cud.update_drift_state({}, finding, checked_at="2026-08-14T00:00:00Z", issue_number=42)
        cud.save_drift_state(state)
        reloaded = cud.load_drift_state()
        assert reloaded["cells/net"]["level"] == "HIGH"
        assert reloaded["cells/net"]["last_issue_number"] == 42
        assert reloaded["cells/net"]["consecutive_weeks_flagged"] == 1

    def test_consecutive_weeks_increments(self, tmp_path):
        finding = {"family": "cells", "platform": "net", "level": "HIGH",
                   "stored": "old", "head": "new"}
        state = cud.update_drift_state({}, finding, checked_at="2026-08-07T00:00:00Z", issue_number=1)
        state = cud.update_drift_state(state, finding, checked_at="2026-08-14T00:00:00Z", issue_number=1)
        assert state["cells/net"]["consecutive_weeks_flagged"] == 2

    def test_issue_number_preserved_when_not_refiled(self, tmp_path):
        finding = {"family": "cells", "platform": "net", "level": "HIGH",
                   "stored": "old", "head": "new"}
        state = cud.update_drift_state({}, finding, checked_at="2026-08-07T00:00:00Z", issue_number=42)
        # a later update without a fresh issue_number (e.g. --file-issues not passed)
        state = cud.update_drift_state(state, finding, checked_at="2026-08-14T00:00:00Z", issue_number=None)
        assert state["cells/net"]["last_issue_number"] == 42


class TestMainResetsResolvedProducts:
    def test_reset_to_zero_when_no_longer_flagged(self, tmp_path, monkeypatch):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": True,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {"cells/net": "current_sha"})
        cud.save_drift_state({"cells/net": {"level": "HIGH", "consecutive_weeks_flagged": 3,
                                             "checked_at": "2026-08-07T00:00:00Z",
                                             "last_issue_number": 42}})
        monkeypatch.setenv("GH_TOKEN", "fake-token")
        monkeypatch.setattr(cud.subprocess, "run", lambda *a, **kw: _cp(stdout="current_sha"))
        rc = cud.main([])
        assert rc == 0
        state = cud.load_drift_state()
        assert state["cells/net"]["consecutive_weeks_flagged"] == 0
        assert state["cells/net"]["level"] == "NONE"


class TestMainExitCodes:
    def test_exit_2_when_no_gh_token(self, tmp_path, monkeypatch):
        _write_products(tmp_path, [])
        _write_baselines(tmp_path, {})
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert cud.main([]) == 2

    def test_exit_1_when_drift_found(self, tmp_path, monkeypatch):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": True,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {})
        monkeypatch.setenv("GH_TOKEN", "fake-token")
        monkeypatch.setattr(cud.subprocess, "run", lambda *a, **kw: _cp(stdout="sha1"))
        assert cud.main([]) == 1

    def test_exit_0_when_no_drift(self, tmp_path, monkeypatch):
        _write_products(tmp_path, [{"family": "cells", "platform": "net", "active": True,
                                     "repo_url": "https://github.com/org/repo"}])
        _write_baselines(tmp_path, {"cells/net": "sha1"})
        monkeypatch.setenv("GH_TOKEN", "fake-token")
        monkeypatch.setattr(cud.subprocess, "run", lambda *a, **kw: _cp(stdout="sha1"))
        assert cud.main([]) == 0

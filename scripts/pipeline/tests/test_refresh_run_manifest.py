"""Tests for containment of the retired partial-manifest writer."""
from __future__ import annotations

import pytest

import refresh_run_manifest as rrm


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    rrm.configure(repo_root=tmp_path)
    yield
    rrm.configure()


class TestCaptureBaseCommitSha:
    def test_writer_is_disabled_and_creates_nothing(self, tmp_path):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "abc123def456")
        with pytest.raises(RuntimeError, match="deprecated"):
            rrm.capture_base_commit_sha("pdf", "net")
        assert not (tmp_path / "reports").exists()


class TestCLI:
    def test_capture_base_flag_exits_2_without_writing(self, tmp_path, capsys):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "abc123")
        exit_code = rrm.main(["pdf", "net", "--capture-base"])
        assert exit_code == 2
        assert "partial refresh manifests are disabled" in capsys.readouterr().err
        assert not (tmp_path / "reports").exists()

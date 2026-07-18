"""Tests for refresh_run_manifest.py — ST-034 base_commit_sha capture."""
from __future__ import annotations

import json

import pytest

import refresh_run_manifest as rrm


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    rrm.configure(repo_root=tmp_path)
    yield
    rrm.configure()


class TestCaptureBaseCommitSha:
    def test_writes_manifest_with_head_sha(self, tmp_path):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "abc123def456")
        path = rrm.capture_base_commit_sha("pdf", "net")
        assert path is not None
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["base_commit_sha"] == "abc123def456"
        assert data["family"] == "pdf"
        assert data["platform"] == "net"
        assert data["status"] == "in_progress"

    def test_written_path_matches_reports_refresh_runs_convention(self, tmp_path):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "abc123")
        path = rrm.capture_base_commit_sha("pdf", "net")
        rel = path.relative_to(tmp_path)
        assert str(rel).replace("\\", "/").startswith("reports/refresh_runs/pdf/net/")
        assert rel.name.endswith(".manifest.json")

    def test_returns_none_when_head_unresolvable(self, tmp_path):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: None)
        path = rrm.capture_base_commit_sha("pdf", "net")
        assert path is None

    def test_explicit_run_id_used_verbatim(self, tmp_path):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "abc123")
        path = rrm.capture_base_commit_sha("pdf", "net", run_id="RUN-001")
        assert path.name == "RUN-001.manifest.json"

    def test_all_schema_5e_required_keys_present_even_if_placeholder(self, tmp_path):
        """The manifest is intentionally partial (base_commit_sha capture only,
        see module docstring) but must still be well-formed JSON with the
        keys a downstream reader might reasonably expect to exist."""
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "abc123")
        path = rrm.capture_base_commit_sha("pdf", "net")
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("run_id", "family", "platform", "started_at", "base_commit_sha",
                    "status", "baseline_ledger_ref", "product_change_refs",
                    "page_coverage_ledger_ref", "patch_receipt_refs"):
            assert key in data, f"missing key: {key}"

    def test_second_capture_produces_newer_lexicographic_run_id(self, tmp_path):
        """RPR-J-17's _load_base_commit_sha picks the lexicographically-last
        manifest as "newest" -- the timestamp-prefixed run_id must sort
        correctly so a later capture is correctly seen as more recent."""
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "first-sha")
        path1 = rrm.capture_base_commit_sha("pdf", "net")
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "second-sha")
        path2 = rrm.capture_base_commit_sha("pdf", "net")
        assert path1 != path2
        assert sorted([path1.name, path2.name])[-1] == path2.name


class TestIntegrationWithPostRefreshVerify:
    """End-to-end: a manifest this module writes must be correctly picked up
    by post_refresh_verify.py's _load_base_commit_sha() / verify()'s
    base_ref resolution (RPR-J-17) -- proves the writer and reader actually
    agree on file layout and field names, not just each side's own tests."""

    def test_captured_manifest_is_read_back_by_post_refresh_verify(self, tmp_path):
        import post_refresh_verify

        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "deadbeef1234")
        rrm.capture_base_commit_sha("pdf", "net")

        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        try:
            sha = post_refresh_verify._load_base_commit_sha("pdf", "net")
            assert sha == "deadbeef1234"
        finally:
            post_refresh_verify.configure()


class TestCLI:
    def test_capture_base_flag_exits_0_on_success(self, tmp_path, capsys):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: "abc123")
        exit_code = rrm.main(["pdf", "net", "--capture-base"])
        assert exit_code == 0
        assert "base_commit_sha captured" in capsys.readouterr().out

    def test_capture_base_flag_exits_1_when_head_unresolvable(self, tmp_path, capsys):
        rrm.configure(repo_root=tmp_path, git_rev_parse=lambda: None)
        exit_code = rrm.main(["pdf", "net", "--capture-base"])
        assert exit_code == 1
        assert "ERROR" in capsys.readouterr().err

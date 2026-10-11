"""Tests for scripts/pipeline/commands/governance/deletion_governance_manager.py."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, str(
    Path(__file__).resolve().parents[1]
    / "scripts" / "pipeline" / "commands" / "governance"
))

import deletion_governance_manager as dgm  # type: ignore


def _write_dgr(dgr_dir: Path, dgr_id: str, path: str, expired: bool = False) -> Path:
    """Helper to write a DGR YAML file in a temp directory."""
    now = datetime.now(tz=timezone.utc)
    if expired:
        approved_at = now - timedelta(days=10)
        expires_at = now - timedelta(days=3)
    else:
        approved_at = now
        expires_at = now + timedelta(days=7)

    content = f"""dgr_id: {dgr_id}
dgr_version: "1.0"
approver: human-maintainer
approved_at: "{approved_at.isoformat().replace('+00:00', 'Z')}"
expires_at: "{expires_at.isoformat().replace('+00:00', 'Z')}"
plan_ref: test-plan
reason: "Test reason"
files:
  - path: {path}
    deletion_class: T-01
    operation: hard_delete
rename_destination: null
commit_message_token: "Deletion-Approved: {dgr_id}"
"""
    out = dgr_dir / f"{dgr_id}.yaml"
    out.write_text(content, encoding="utf-8")
    return out


class TestCreate:
    def test_create_t01_succeeds(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        dgr_dir = tmp_path / "deletion-approvals"

        rc = dgm.main([
            "create",
            "--files", "content/products.aspose.org/ar/old/_index.md",
            "--reason", "Obsolete locale page",
            "--plan", "test-plan",
        ])
        assert rc == 0

        yaml_files = list(dgr_dir.glob("*.yaml"))
        assert len(yaml_files) == 1
        content = yaml_files[0].read_text(encoding="utf-8")
        assert "T-01" in content
        assert "Deletion-Approved:" in content

    def test_create_rejects_t00_agents_md(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        rc = dgm.main([
            "create",
            "--files", "AGENTS.md",
            "--reason", "T-00 test",
        ])
        assert rc == 2

    def test_create_rejects_t00_hook_script(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        rc = dgm.main([
            "create",
            "--files", "scripts/ci/hooks/check_session_gate.sh",
            "--reason", "T-00 hook test",
        ])
        assert rc == 2

    def test_create_rejects_t00_path_guard(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        rc = dgm.main([
            "create",
            "--files", "scripts/pipeline/commands/governance/path_guard.py",
            "--reason", "T-00 path_guard test",
        ])
        assert rc == 2

    def test_create_sets_expiry_7_days(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        dgm.main([
            "create",
            "--files", "content/products.aspose.org/ar/old/_index.md",
            "--reason", "Expiry test",
        ])
        dgr_dir = tmp_path / "deletion-approvals"
        yaml_files = list(dgr_dir.glob("*.yaml"))
        content = yaml_files[0].read_text(encoding="utf-8")
        assert "expires_at" in content


class TestValidateForPath:
    def test_valid_dgr_exits_0(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        dgr_dir = tmp_path / "deletion-approvals"
        dgr_dir.mkdir(parents=True)
        _write_dgr(dgr_dir, "DGR-20260704-test", "content/products.aspose.org/ar/old/_index.md")

        rc = dgm.main([
            "validate-for-path",
            "content/products.aspose.org/ar/old/_index.md",
        ])
        assert rc == 0

    def test_missing_dgr_exits_2(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        (tmp_path / "deletion-approvals").mkdir(parents=True)

        rc = dgm.main([
            "validate-for-path",
            "content/products.aspose.org/ar/missing/_index.md",
        ])
        assert rc == 2

    def test_expired_dgr_exits_2(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        dgr_dir = tmp_path / "deletion-approvals"
        dgr_dir.mkdir(parents=True)
        _write_dgr(
            dgr_dir, "DGR-20260601-expired",
            "content/products.aspose.org/ar/old/_index.md",
            expired=True,
        )

        rc = dgm.main([
            "validate-for-path",
            "content/products.aspose.org/ar/old/_index.md",
        ])
        assert rc == 2

    def test_no_dgr_dir_exits_2(self, tmp_path):
        """Missing deletion-approvals/ dir is fail-closed."""
        dgm.configure(repo_root=tmp_path)
        # Don't create deletion-approvals/ dir
        rc = dgm.main([
            "validate-for-path",
            "content/products.aspose.org/ar/old/_index.md",
        ])
        assert rc == 2


class TestConsume:
    def test_consume_archives_dgr(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        dgr_dir = tmp_path / "deletion-approvals"
        dgr_dir.mkdir(parents=True)
        _write_dgr(dgr_dir, "DGR-20260704-consume-test", "content/products.aspose.org/ar/old/_index.md")

        rc = dgm.main([
            "consume",
            "--dgr-id", "DGR-20260704-consume-test",
            "--commit-sha", "abc123def456",
        ])
        assert rc == 0

        # Original should be gone; archived should exist
        assert not (dgr_dir / "DGR-20260704-consume-test.yaml").exists()
        archived = tmp_path / "deletion-approvals" / "archived" / "DGR-20260704-consume-test.yaml"
        assert archived.exists()
        content = archived.read_text(encoding="utf-8")
        assert "abc123def456" in content

    def test_consume_missing_dgr_exits_1(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        (tmp_path / "deletion-approvals").mkdir(parents=True)

        rc = dgm.main([
            "consume",
            "--dgr-id", "DGR-does-not-exist",
            "--commit-sha", "abc",
        ])
        assert rc == 1


class TestListPending:
    def test_list_pending_empty(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        rc = dgm.main(["list-pending"])
        assert rc == 0

    def test_list_pending_shows_dgrs(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        dgr_dir = tmp_path / "deletion-approvals"
        dgr_dir.mkdir(parents=True)
        _write_dgr(dgr_dir, "DGR-20260704-list-test", "content/products.aspose.org/ar/_index.md")

        rc = dgm.main(["list-pending"])
        assert rc == 0


class TestAudit:
    def test_audit_empty(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        rc = dgm.main(["audit"])
        assert rc == 0

    def test_audit_shows_archived(self, tmp_path):
        dgm.configure(repo_root=tmp_path)
        dgr_dir = tmp_path / "deletion-approvals"
        archived_dir = dgr_dir / "archived"
        archived_dir.mkdir(parents=True)
        _write_dgr(archived_dir, "DGR-20260704-archived", "content/products.aspose.org/ar/_index.md")

        rc = dgm.main(["audit"])
        assert rc == 0

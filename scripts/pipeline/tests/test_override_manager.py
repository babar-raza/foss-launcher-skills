"""Tests for override_manager.py — override token lifecycle.

Coverage:
- create: token file written to pending/
- validate-for-path: matching path passes; non-matching rejected
- expired token: explicitly rejected
- consume: token moves from pending/ to archived/
- non-existent token: rejected
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import override_manager


@pytest.fixture(autouse=True)
def _reset_om():
    yield
    override_manager.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_token(pending_dir: Path, token: dict) -> Path:
    """Write a token dict to pending_dir/{id}.json and return the path."""
    pending_dir.mkdir(parents=True, exist_ok=True)
    token_id = token["override_id"]
    p = pending_dir / f"{token_id}.json"
    p.write_text(json.dumps(token, indent=2), encoding="utf-8")
    return p


def _make_token(
    token_id: str,
    paths: list[str],
    *,
    days_ago: int = 0,
    retroactive: bool = False,
) -> dict:
    authorized_at = (
        datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    ).isoformat().replace("+00:00", "Z")
    return {
        "override_id": token_id,
        "paths": paths,
        "operation": "edit",
        "reason": "test reason",
        "plan_reference": "",
        "scope_description": "",
        "authorized_at": authorized_at,
        "retroactive": retroactive,
        "consumed_by_commit": None,
    }


# ---------------------------------------------------------------------------
# TASK-05 tests
# ---------------------------------------------------------------------------

class TestCreate:
    def test_token_file_written_to_pending(self, tmp_path, monkeypatch):
        pending = tmp_path / "pending"
        archived = tmp_path / "archived"
        override_manager.configure(repo_root=tmp_path, pending_dir=pending, archived_dir=archived)

        class Args:
            paths = ["AGENTS.md"]
            reason = "test reason"
            plan = "my-plan.md"
            scope = ""
            operation = "edit"
            retroactive = False

        rc = override_manager.cmd_create(Args())

        assert rc == 0
        token_files = list(pending.glob("*.json"))
        assert len(token_files) == 1

        token = json.loads(token_files[0].read_text())
        assert token["paths"] == ["AGENTS.md"]
        assert token["reason"] == "test reason"
        assert token["consumed_by_commit"] is None

    def test_dotdir_path_leading_dot_preserved(self, tmp_path, monkeypatch):
        """Found live, production concurrency redesign (2026-08-01), Step 6:
        the old `.lstrip("./")` normalization silently ate the leading '.'
        from any dotdir path (.supervisor/, .claude/, .agents/, .kilocode/ --
        all real protected paths this repo issues override tokens for),
        since lstrip strips a character SET, not a prefix string."""
        pending = tmp_path / "pending"
        archived = tmp_path / "archived"
        override_manager.configure(repo_root=tmp_path, pending_dir=pending, archived_dir=archived)

        class Args:
            paths = [".supervisor/prompts/prompt4-close-task.md"]
            reason = "test reason"
            plan = "my-plan.md"
            scope = ""
            operation = "edit"
            retroactive = False

        rc = override_manager.cmd_create(Args())
        assert rc == 0

        token_files = list(pending.glob("*.json"))
        token = json.loads(token_files[0].read_text())
        assert token["paths"] == [".supervisor/prompts/prompt4-close-task.md"]

    def test_relative_prefix_still_stripped(self, tmp_path, monkeypatch):
        """The fix must still strip a genuine './' relative-path prefix
        (including a repeated one) -- only the dotdir-eating side effect was
        the bug."""
        pending = tmp_path / "pending"
        archived = tmp_path / "archived"
        override_manager.configure(repo_root=tmp_path, pending_dir=pending, archived_dir=archived)

        class Args:
            paths = ["./AGENTS.md", "././scripts/foo.py"]
            reason = "test reason"
            plan = "my-plan.md"
            scope = ""
            operation = "edit"
            retroactive = False

        rc = override_manager.cmd_create(Args())
        assert rc == 0

        token_files = list(pending.glob("*.json"))
        token = json.loads(token_files[0].read_text())
        assert token["paths"] == ["AGENTS.md", "scripts/foo.py"]


class TestValidateForPath:
    def test_matching_path_passes(self, tmp_path, monkeypatch):
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        token = _make_token("20260401-123000-agents-md", ["AGENTS.md"], days_ago=1)
        _write_token(pending, token)

        class Args:
            path = "AGENTS.md"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 0

    def test_non_matching_path_rejected(self, tmp_path, monkeypatch):
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        token = _make_token("20260401-123000-agents-md", ["AGENTS.md"], days_ago=1)
        _write_token(pending, token)

        class Args:
            path = "scripts/pipeline/somefile.py"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 2

    def test_expired_token_rejected(self, tmp_path, monkeypatch):
        """Expired token (>7 days) must be rejected — the core safety property."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        # Token created 10 days ago — past the 7-day TTL
        token = _make_token("20260401-123000-agents-md", ["AGENTS.md"], days_ago=10)
        _write_token(pending, token)

        class Args:
            path = "AGENTS.md"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 2  # expired → rejected

    def test_expired_retroactive_token_passes(self, tmp_path, monkeypatch):
        """Retroactive tokens bypass the TTL check."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        token = _make_token(
            "20260401-123000-agents-md", ["AGENTS.md"], days_ago=10, retroactive=True
        )
        _write_token(pending, token)

        class Args:
            path = "AGENTS.md"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 0

    def test_no_token_returns_2(self, tmp_path, monkeypatch):
        """No pending token → exit 2."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        class Args:
            path = "AGENTS.md"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 2


class TestFindValidTokenForPath:
    """Direct, importable API -- production concurrency redesign (2026-08-01),
    Step 8 follow-up: git_plumb_commit.py calls this directly instead of
    shelling out to the CLI."""

    def test_returns_token_dict_when_covered(self, tmp_path):
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)
        token = _make_token("20260401-123000-agents-md", ["AGENTS.md"], days_ago=1)
        _write_token(pending, token)

        found = override_manager.find_valid_token_for_path("AGENTS.md")
        assert found is not None
        assert found["override_id"] == "20260401-123000-agents-md"

    def test_returns_none_when_not_covered(self, tmp_path):
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)
        token = _make_token("20260401-123000-agents-md", ["AGENTS.md"], days_ago=1)
        _write_token(pending, token)

        assert override_manager.find_valid_token_for_path("scripts/foo.py") is None

    def test_returns_none_when_only_expired_token_covers(self, tmp_path):
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)
        token = _make_token("20260401-123000-agents-md", ["AGENTS.md"], days_ago=10)
        _write_token(pending, token)

        assert override_manager.find_valid_token_for_path("AGENTS.md") is None

    def test_skips_expired_token_and_finds_a_later_valid_one(self, tmp_path):
        """If an expired token and a fresh token both cover the same path,
        the fresh one must still be found -- not masked by the expired one
        being enumerated first."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)
        expired = _make_token("20260401-000000-agents-md-old", ["AGENTS.md"], days_ago=10)
        fresh = _make_token("20260410-000000-agents-md-new", ["AGENTS.md"], days_ago=1)
        _write_token(pending, expired)
        _write_token(pending, fresh)

        found = override_manager.find_valid_token_for_path("AGENTS.md")
        assert found is not None
        assert found["override_id"] == "20260410-000000-agents-md-new"

    def test_retroactive_expired_token_still_counts_as_valid(self, tmp_path):
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)
        token = _make_token(
            "20260401-123000-agents-md", ["AGENTS.md"], days_ago=10, retroactive=True,
        )
        _write_token(pending, token)

        found = override_manager.find_valid_token_for_path("AGENTS.md")
        assert found is not None


class TestConsume:
    def test_consume_moves_to_archived(self, tmp_path, monkeypatch):
        pending = tmp_path / "pending"
        archived = tmp_path / "archived"
        override_manager.configure(pending_dir=pending, archived_dir=archived)

        token_id = "20260401-123000-agents-md"
        token = _make_token(token_id, ["AGENTS.md"], days_ago=1)
        _write_token(pending, token)

        class Args:
            token_id = "20260401-123000-agents-md"
            commit_sha = "abc123def456"

        rc = override_manager.cmd_consume(Args())

        assert rc == 0
        assert not (pending / f"{token_id}.json").exists()
        archived_file = archived / f"{token_id}.json"
        assert archived_file.exists()

        consumed = json.loads(archived_file.read_text())
        assert consumed["consumed_by_commit"] == "abc123def456"

    def test_consume_nonexistent_token_returns_1(self, tmp_path, monkeypatch):
        pending = tmp_path / "pending"
        archived = tmp_path / "archived"
        override_manager.configure(pending_dir=pending, archived_dir=archived)

        class Args:
            token_id = "nonexistent-token"
            commit_sha = "abc123"

        rc = override_manager.cmd_consume(Args())
        assert rc == 1

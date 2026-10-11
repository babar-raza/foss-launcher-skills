"""Tests for PreToolUse token-aware governance behavior.

Covers:
- Forbidden path blocked without token (baseline)
- Forbidden path behavior with pending override token
- ROOT_WRITE_AUTHORIZED behavior with forbidden paths
- Allowed path passes without token
- override_manager.py validate-for-path: expired, wrong-path, missing token

Sprint 1 GOV-LIGHT tests — follows subprocess pattern from test_check_write_path_hook.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK_PATH = "scripts/ci/hooks/check_write_path_hook.sh"

# Override manager for token lifecycle tests
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline" / "commands" / "governance"))
import override_manager  # noqa: E402


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run_hook(file_path: str, env_overrides: dict | None = None) -> int:
    """Invoke check_write_path_hook.sh with the given file_path; return exit code."""
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": "test"},
    })
    env = dict(os.environ)
    env["CLAUDE_TOOL_INPUT"] = payload
    env.pop("ROOT_WRITE_AUTHORIZED", None)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [_BASH, _HOOK_PATH],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode


@pytest.fixture(autouse=True)
def _reset_override_manager():
    """Reset override_manager module paths after each test."""
    yield
    override_manager.configure()


# ---------------------------------------------------------------------------
# T1: Forbidden path without token is BLOCKED
# ---------------------------------------------------------------------------

def test_forbidden_path_blocked_without_token():
    """Forbidden path (themes/) without any token -> exit 2."""
    rc = _run_hook("themes/test-forbidden.html")
    assert rc == 2, f"Expected exit 2 (blocked), got {rc}"


def test_forbidden_exact_blocked_without_token():
    """FORBIDDEN_EXACT file (AGENTS.md) without token -> exit 2."""
    rc = _run_hook("AGENTS.md")
    assert rc == 2, f"Expected exit 2 (blocked), got {rc}"


# ---------------------------------------------------------------------------
# T2: ROOT_WRITE_AUTHORIZED allows forbidden paths (documents current broad behavior)
# ---------------------------------------------------------------------------

def test_root_write_authorized_allows_forbidden_path():
    """ROOT_WRITE_AUTHORIZED=1 bypasses ALL path_guard DENYs including forbidden."""
    rc = _run_hook("themes/test-forbidden.html", {"ROOT_WRITE_AUTHORIZED": "1"})
    assert rc == 0, f"Expected exit 0 (allowed via ROOT_WRITE_AUTHORIZED), got {rc}"


def test_root_write_authorized_allows_forbidden_exact():
    """ROOT_WRITE_AUTHORIZED=1 bypasses FORBIDDEN_EXACT too."""
    rc = _run_hook("AGENTS.md", {"ROOT_WRITE_AUTHORIZED": "1"})
    assert rc == 0, f"Expected exit 0 (allowed via ROOT_WRITE_AUTHORIZED), got {rc}"


# ---------------------------------------------------------------------------
# T3: Allowed path passes without token
# ---------------------------------------------------------------------------

def test_allowed_path_passes():
    """Allowed path (reports/) passes without any token."""
    rc = _run_hook("reports/test-file.txt")
    assert rc == 0, f"Expected exit 0 (allowed path), got {rc}"


# ---------------------------------------------------------------------------
# T4: override_manager.py validate-for-path behavior (unit tests)
# ---------------------------------------------------------------------------

class TestValidateForPathUnit:
    """Unit tests for override_manager validate-for-path logic."""

    def test_expired_token_rejected(self, tmp_path):
        """Expired token (>7 days old, non-retroactive) -> exit 2."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        authorized_at = (
            datetime.now(tz=timezone.utc) - timedelta(days=10)
        ).isoformat().replace("+00:00", "Z")
        token = {
            "override_id": "test-expired",
            "paths": ["themes/test.html"],
            "operation": "edit",
            "reason": "test",
            "plan_reference": "",
            "scope_description": "",
            "authorized_at": authorized_at,
            "retroactive": False,
            "consumed_by_commit": None,
        }
        pending.mkdir(parents=True, exist_ok=True)
        (pending / "test-expired.json").write_text(
            json.dumps(token), encoding="utf-8"
        )

        class Args:
            path = "themes/test.html"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 2, "Expired token should be rejected"

    def test_wrong_path_token_rejected(self, tmp_path):
        """Token for AGENTS.md does NOT cover themes/test.html -> exit 2."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        authorized_at = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        token = {
            "override_id": "test-wrong-path",
            "paths": ["AGENTS.md"],
            "operation": "edit",
            "reason": "test",
            "plan_reference": "",
            "scope_description": "",
            "authorized_at": authorized_at,
            "retroactive": False,
            "consumed_by_commit": None,
        }
        pending.mkdir(parents=True, exist_ok=True)
        (pending / "test-wrong-path.json").write_text(
            json.dumps(token), encoding="utf-8"
        )

        class Args:
            path = "themes/test.html"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 2, "Wrong-path token should be rejected"

    def test_valid_token_accepted(self, tmp_path):
        """Valid, non-expired token covering exact path -> exit 0."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        authorized_at = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
        token = {
            "override_id": "test-valid",
            "paths": ["themes/test.html"],
            "operation": "edit",
            "reason": "test",
            "plan_reference": "",
            "scope_description": "",
            "authorized_at": authorized_at,
            "retroactive": False,
            "consumed_by_commit": None,
        }
        pending.mkdir(parents=True, exist_ok=True)
        (pending / "test-valid.json").write_text(
            json.dumps(token), encoding="utf-8"
        )

        class Args:
            path = "themes/test.html"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 0, "Valid token should be accepted"

    def test_missing_token_rejected(self, tmp_path):
        """No token at all -> exit 2."""
        pending = tmp_path / "pending"
        override_manager.configure(pending_dir=pending)

        class Args:
            path = "themes/test.html"

        rc = override_manager.cmd_validate_for_path(Args())
        assert rc == 2, "Missing token should be rejected"

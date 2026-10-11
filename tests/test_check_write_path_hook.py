"""
Tests for scripts/ci/check_write_path_hook.sh boundary logic.

Covers:
- In-repo ALLOW path → exit 0, no log
- In-repo DENY path (root-level) → exit 2
- Out-of-repo absolute POSIX path → exit 0 + log line
- Out-of-repo Windows forward-slash path → exit 0 + log line
- Empty stdin → exit 2 (fail-closed)
- Malformed JSON → exit 2 (fail-closed)
- CLAUDE_TOOL_INPUT env var path (alternative to stdin) → same result as stdin
- ROOT_WRITE_AUTHORIZED=1 bypass on DENY path → exit 0
- Forbidden path (themes/) ALLOWED when valid pending override token exists (GOV-LIGHT-001)

Note on Windows: WSL bash (the default `bash` on Windows PATH) rejects CRLF line endings,
whereas Git Bash handles them transparently.  We normalise the hook script to LF in a
temporary file so the tests work under either bash implementation.
"""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
_HOOK_SRC = REPO_ROOT / "scripts" / "ci" / "hooks" / "check_write_path_hook.sh"

# Prefer Git Bash over WSL bash — WSL bash cannot resolve Windows-style paths.
_GIT_BASH_CANDIDATES = [
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
]
BASH = next(
    (c for c in _GIT_BASH_CANDIDATES if Path(c).exists()),
    "bash",  # fallback (Unix / CI environments where bash is already POSIX)
)

# LF-normalised hook written at module import time inside the repo so bash can resolve it
# via a repo-relative path when subprocess is called with cwd=REPO_ROOT.
_LF_HOOK_REL = "scripts/ci/hooks/.tmp_hook_test.sh"
_LF_HOOK_ABS = REPO_ROOT / _LF_HOOK_REL
_content = _HOOK_SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
_LF_HOOK_ABS.write_bytes(_content)


@pytest.fixture(scope="module")
def hook_path() -> str:
    """Relative path to LF-normalised hook (relative to REPO_ROOT — usable with cwd)."""
    yield _LF_HOOK_REL
    _LF_HOOK_ABS.unlink(missing_ok=True)


def _run_hook(
    file_path: str,
    hook_path: str,
    *,
    use_env_var: bool = False,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Invoke the hook with file_path supplied via stdin JSON or CLAUDE_TOOL_INPUT env var."""
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    if use_env_var:
        env["CLAUDE_TOOL_INPUT"] = payload
        stdin_data = None
    else:
        stdin_data = payload.encode()

    return subprocess.run(
        [BASH, hook_path],
        input=stdin_data,
        capture_output=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# Happy-path: in-repo ALLOW
# ---------------------------------------------------------------------------

def test_allow_in_repo_content_path(hook_path):
    """content/ prefix is in ALLOWED_PREFIXES → exit 0, no stderr output."""
    result = _run_hook("content/docs.aspose.org/en/3d/python/test.md", hook_path)
    assert result.returncode == 0
    assert b"blocked" not in result.stderr.lower()
    assert b"out-of-repo" not in result.stderr


def test_allow_in_repo_reports_path(hook_path):
    """reports/ prefix is also ALLOW."""
    result = _run_hook("reports/some/report.json", hook_path)
    assert result.returncode == 0


def test_allow_in_repo_knowledge_path(hook_path):
    """knowledge/ prefix is ALLOW."""
    result = _run_hook("knowledge/cells/python/merged/model.yaml", hook_path)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# DENY: root-level and forbidden paths
# ---------------------------------------------------------------------------

def test_deny_root_level_file(hook_path):
    """Root-level files like RUNBOOK.md are DENY → exit 2."""
    result = _run_hook("RUNBOOK.md", hook_path)
    assert result.returncode == 2
    assert b"blocked" in result.stderr.lower()


def test_deny_forbidden_prefix_themes(hook_path):
    """themes/ is in FORBIDDEN_PREFIXES → exit 2."""
    result = _run_hook("themes/default/style.css", hook_path)
    assert result.returncode == 2


def test_deny_root_config(hook_path):
    """Root-level config files are DENY → exit 2."""
    result = _run_hook("config.json", hook_path)
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Out-of-repo absolute paths → ALLOW + log line
# ---------------------------------------------------------------------------

def test_allow_out_of_repo_posix_absolute(hook_path):
    """/c/Users/... is outside the repo root → exit 0 + log line."""
    result = _run_hook("/c/Users/prora/.claude/plans/test.md", hook_path)
    assert result.returncode == 0


def test_allow_out_of_repo_windows_forward_slash(hook_path):
    """C:/Users/... (forward slash, how Claude Code sends on Windows) → exit 0 + log."""
    result = _run_hook("C:/Users/prora/.claude/plans/test.md", hook_path)
    assert result.returncode == 0


def test_deny_out_of_repo_different_drive(hook_path):
    """/e/some/other/path — different drive, outside repo → exit 0 + log."""
    result = _run_hook("/e/some/other/path/file.md", hook_path)
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Fail-closed: bad input
# ---------------------------------------------------------------------------

def test_fail_closed_empty_input(hook_path):
    """Empty stdin with no CLAUDE_TOOL_INPUT → fail-closed, exit 2."""
    result = subprocess.run(
        [BASH, hook_path],
        input=b"",
        capture_output=True,
        env=os.environ.copy(),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 2
    assert b"blocked" in result.stderr.lower()


def test_fail_closed_malformed_json(hook_path):
    """Malformed JSON on stdin → fail-closed, exit 2."""
    result = subprocess.run(
        [BASH, hook_path],
        input=b"{not valid json",
        capture_output=True,
        env=os.environ.copy(),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 2


def test_fail_closed_missing_file_path_key(hook_path):
    """Valid JSON but file_path key absent → fail-closed, exit 2."""
    result = subprocess.run(
        [BASH, hook_path],
        input=json.dumps({"tool_input": {"other_key": "value"}}).encode(),
        capture_output=True,
        env=os.environ.copy(),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# CLAUDE_TOOL_INPUT env var path
# ---------------------------------------------------------------------------

def test_claude_tool_input_env_var_allow(hook_path):
    """CLAUDE_TOOL_INPUT env var with ALLOW path → exit 0 (no stdin provided)."""
    result = _run_hook("content/docs.aspose.org/en/test.md", hook_path, use_env_var=True)
    assert result.returncode == 0


def test_claude_tool_input_env_var_deny(hook_path):
    """CLAUDE_TOOL_INPUT env var with DENY path → exit 2."""
    result = _run_hook("RUNBOOK.md", hook_path, use_env_var=True)
    assert result.returncode == 2


def test_claude_tool_input_env_var_out_of_repo(hook_path):
    """CLAUDE_TOOL_INPUT env var with out-of-repo path → exit 0 + log."""
    result = _run_hook("/c/Users/prora/.claude/plans/x.md", hook_path, use_env_var=True)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# ROOT_WRITE_AUTHORIZED bypass
# ---------------------------------------------------------------------------

def test_root_write_authorized_bypass(hook_path):
    """ROOT_WRITE_AUTHORIZED=1 on a DENY path → exit 0 (operator bypass)."""
    result = _run_hook("RUNBOOK.md", hook_path, extra_env={"ROOT_WRITE_AUTHORIZED": "1"})
    assert result.returncode == 0
    # Bypass should emit a warning, not a block message
    assert b"bypass" in result.stderr.lower() or b"authorized" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Override token integration: GOV-LIGHT-001
# ---------------------------------------------------------------------------

def test_forbidden_path_allowed_with_valid_override_token(hook_path):
    """themes/ path is ALLOWED by the hook when a valid pending override token exists.

    GOV-LIGHT-001: check_write_path_hook.sh calls override_manager.py validate-for-path
    when path_guard returns DENY.  A valid pending token covering the exact path must
    result in exit 0 (write allowed) and a pretooluse-audit.log entry.
    """
    pending_dir = REPO_ROOT / "reports" / "overrides" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    token_id = "test-pretooluse-integration-allow"
    target_path = "themes/default/style.css"
    token = {
        "override_id": token_id,
        "paths": [target_path],
        "operation": "edit",
        "reason": "integration test: verify PreToolUse allows write when valid token exists",
        "plan_reference": "GOV-LIGHT-001-test",
        "scope_description": "",
        "authorized_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "retroactive": False,
        "consumed_by_commit": None,
    }
    token_path = pending_dir / f"{token_id}.json"
    try:
        token_path.write_text(json.dumps(token, indent=2), encoding="utf-8")
        result = _run_hook(target_path, hook_path)
        assert result.returncode == 0, (
            f"Expected exit 0 (token allows write), got {result.returncode}. "
            f"stderr: {result.stderr.decode(errors='replace')}"
        )
    finally:
        token_path.unlink(missing_ok=True)


def test_forbidden_path_still_blocked_with_wrong_path_token(hook_path):
    """themes/ path is BLOCKED if pending token covers a different path.

    A token for AGENTS.md must NOT allow a write to themes/default/style.css.
    """
    pending_dir = REPO_ROOT / "reports" / "overrides" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    token_id = "test-pretooluse-integration-wrong-path"
    token = {
        "override_id": token_id,
        "paths": ["AGENTS.md"],
        "operation": "edit",
        "reason": "integration test: wrong-path token must not grant access to other paths",
        "plan_reference": "GOV-LIGHT-001-test",
        "scope_description": "",
        "authorized_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "retroactive": False,
        "consumed_by_commit": None,
    }
    token_path = pending_dir / f"{token_id}.json"
    try:
        token_path.write_text(json.dumps(token, indent=2), encoding="utf-8")
        result = _run_hook("themes/default/style.css", hook_path)
        assert result.returncode == 2, (
            f"Expected exit 2 (wrong-path token must not grant access), got {result.returncode}. "
            f"stderr: {result.stderr.decode(errors='replace')}"
        )
    finally:
        token_path.unlink(missing_ok=True)

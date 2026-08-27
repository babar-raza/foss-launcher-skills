"""Tests for scripts/ci/hooks/check_add_bash_hook.sh.

The hook receives a JSON payload via CLAUDE_TOOL_INPUT and NEVER blocks
(always exits 0) -- it prints a WARN-level message to stderr when the
command contains `git add` and no live skill context exists for the
resolving session identity.

Warned: git add (all forms) with no live skill context anywhere.
Not warned: git add with at least one live skill context (ANY skill, not
    just S-76 -- unlike check_commit_bash_hook.sh); non-add commands;
    empty/unparseable input; operator bypass (SKIP_ADD_BASH_CHECK=1).

Every test runs against an ISOLATED root via the hook's
CHECK_ADD_HOOK_ROOT_OVERRIDE seam (PYTEST_CURRENT_TEST-gated, mirrors
check_commit_bash_hook.sh's CHECK_COMMIT_HOOK_ROOT_OVERRIDE exactly) --
tests never read or mutate the live repo's reports/skill-context/ state.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK_REL = "scripts/ci/hooks/check_add_bash_hook.sh"
_SENTINEL = object()


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _now_iso(hours_ago: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.isoformat().replace("+00:00", "Z")


def _run(
    command: str,
    *,
    skip: bool = False,
    active_skill=_SENTINEL,
    session_ctxs: tuple = (),
) -> subprocess.CompletedProcess:
    """Invoke the hook against an isolated root; return the full result
    (exit code AND stderr, since this hook communicates via stderr, not
    exit code -- it always exits 0)."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx_dir = root / "reports" / "skill-context"
        ctx_dir.mkdir(parents=True)

        if active_skill not in (_SENTINEL, None):
            (ctx_dir / "ACTIVE.json").write_text(json.dumps({
                "skill_id": active_skill, "scope_patterns": ["*"],
                "started_at": _now_iso(0.0),
            }), encoding="utf-8")

        if session_ctxs:
            active_dir = ctx_dir / "active"
            active_dir.mkdir()
            for session_id, skill_id, stale in session_ctxs:
                (active_dir / f"{session_id}.json").write_text(json.dumps({
                    "skill_id": skill_id, "scope_patterns": ["*"],
                    "session_id": session_id,
                    "started_at": _now_iso(3.0 if stale else 0.0),
                }), encoding="utf-8")

        env = dict(os.environ)
        env["CLAUDE_TOOL_INPUT"] = payload
        env["CHECK_ADD_HOOK_ROOT_OVERRIDE"] = str(root)
        env.pop("AGENT_SESSION_ID", None)
        env.pop("CODEX_THREAD_ID", None)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        if skip:
            env["SKIP_ADD_BASH_CHECK"] = "1"
        else:
            env.pop("SKIP_ADD_BASH_CHECK", None)

        return subprocess.run(
            [_BASH, _HOOK_REL], env=env, cwd=str(_REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8",
        )


def _run_empty() -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env.pop("SKIP_ADD_BASH_CHECK", None)
    with tempfile.TemporaryDirectory() as tmp:
        env["CHECK_ADD_HOOK_ROOT_OVERRIDE"] = tmp
        return subprocess.run(
            [_BASH, _HOOK_REL], env=env, cwd=str(_REPO_ROOT),
            input="", capture_output=True, text=True,
        )


# ---------------------------------------------------------------------------
# Never blocks — the core safety property of this hook
# ---------------------------------------------------------------------------

def test_never_blocks_even_with_git_add_and_no_context():
    result = _run("git add somefile.txt")
    assert result.returncode == 0


def test_never_blocks_git_add_dash_capital_a_with_no_context():
    result = _run("git add -A")
    assert result.returncode == 0


def test_never_blocks_chained_git_add_with_no_context():
    result = _run("cd repo && git add file.txt && echo done")
    assert result.returncode == 0


def test_never_blocks_env_prefixed_git_add_with_no_context():
    result = _run("AGENT_SESSION_ID=someone git add file.txt")
    assert result.returncode == 0


def test_never_blocks_unparseable_input():
    result = _run("this is not json handled by the caller")
    assert result.returncode == 0


def test_never_blocks_empty_input():
    assert _run_empty().returncode == 0


# ---------------------------------------------------------------------------
# Warns (stderr, still exit 0) — git add with no live skill context
# ---------------------------------------------------------------------------

def test_warns_on_bare_git_add_with_no_context():
    result = _run("git add somefile.txt")
    assert "WARN" in result.stderr
    assert "git add" in result.stderr


def test_warns_on_git_add_dash_capital_a():
    result = _run("git add -A")
    assert "WARN" in result.stderr


def test_warns_on_git_add_dot():
    result = _run("git add .")
    assert "WARN" in result.stderr


def test_warns_on_chained_git_add():
    result = _run("cd repo && git add file.txt")
    assert "WARN" in result.stderr


def test_warns_on_env_prefixed_git_add():
    result = _run("AGENT_SESSION_ID=whoever git add file.txt")
    assert "WARN" in result.stderr


def test_warns_on_git_add_with_global_options():
    result = _run("git -c user.email=x add file.txt")
    assert "WARN" in result.stderr


# ---------------------------------------------------------------------------
# Does NOT warn — a live skill context exists (any skill, unlike the
# commit hook's S-76-specific requirement)
# ---------------------------------------------------------------------------

def test_no_warning_with_live_legacy_active_context():
    result = _run("git add somefile.txt", active_skill="S-73")
    assert "WARN" not in result.stderr


def test_no_warning_with_live_per_session_context():
    result = _run(
        "git add somefile.txt",
        session_ctxs=(("some-session", "S-99", False),),
    )
    assert "WARN" not in result.stderr


def test_no_warning_when_any_of_multiple_sessions_is_live():
    result = _run(
        "git add somefile.txt",
        session_ctxs=(
            ("session-a", "S-73", True),   # stale
            ("session-b", "S-84", False),  # live
        ),
    )
    assert "WARN" not in result.stderr


def test_still_warns_when_only_stale_contexts_exist():
    result = _run(
        "git add somefile.txt",
        session_ctxs=(("session-a", "S-73", True),),
    )
    assert "WARN" in result.stderr


# ---------------------------------------------------------------------------
# Does NOT warn — command doesn't contain `git add` at all
# ---------------------------------------------------------------------------

def test_no_warning_for_unrelated_command():
    result = _run("git status")
    assert "WARN" not in result.stderr
    assert result.returncode == 0


def test_no_warning_for_git_commit_alone():
    """git commit is check_commit_bash_hook.sh's job, not this one's."""
    result = _run("git commit -m 'msg'")
    assert "WARN" not in result.stderr


def test_no_warning_for_add_as_a_non_git_word():
    """'add' appearing as an unrelated word/argument must not false-positive."""
    result = _run("echo add something")
    assert "WARN" not in result.stderr


# ---------------------------------------------------------------------------
# Operator bypass
# ---------------------------------------------------------------------------

def test_bypass_suppresses_the_warning():
    result = _run("git add somefile.txt", skip=True)
    assert result.returncode == 0
    assert "WARN" not in result.stderr

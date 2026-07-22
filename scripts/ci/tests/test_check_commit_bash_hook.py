"""Tests for scripts/ci/hooks/check_commit_bash_hook.sh.

The hook receives a JSON payload via CLAUDE_TOOL_INPUT and exits 2 (block)
when the command contains `git commit` without a live S-76 skill context.

Blocked: git commit (all forms) without S-76 context; identity naming a session
         without S-76; two live S-76 contexts with no identity (ambiguous);
         stale/timestamp-less S-76 contexts.
Allowed: git commit with exactly one live S-76 context, identity naming the
         holder session, git commit-tree/commit-graph (plumbing),
         empty/unparseable input (fail-open), operator bypass.

HARDEN-A3/F8: every test runs against an ISOLATED root via the hook's
CHECK_COMMIT_HOOK_ROOT_OVERRIDE seam — tests never read or mutate the live
repo's reports/skill-context/ state (which could transiently yank a concurrent
session's commit authorization or make these tests flaky).
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
_HOOK_REL = "scripts/ci/hooks/check_commit_bash_hook.sh"
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
    active_started_hours_ago: float = 0.0,
    active_omit_started_at: bool = False,
    session_ctxs: tuple = (),
) -> int:
    """Invoke the hook against an isolated root; return exit code.

    active_skill: _SENTINEL/None = no legacy ACTIVE.json; "S-76" etc. writes one.
    session_ctxs: iterable of (session_id, skill_id, stale: bool) tuples written
        as per-session context files under reports/skill-context/active/.
    """
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx_dir = root / "reports" / "skill-context"
        ctx_dir.mkdir(parents=True)

        if active_skill not in (_SENTINEL, None):
            record: dict = {"skill_id": active_skill, "scope_patterns": ["*"]}
            if not active_omit_started_at:
                record["started_at"] = _now_iso(active_started_hours_ago)
            (ctx_dir / "ACTIVE.json").write_text(json.dumps(record), encoding="utf-8")

        if session_ctxs:
            active_dir = ctx_dir / "active"
            active_dir.mkdir()
            for session_id, skill_id, stale in session_ctxs:
                (active_dir / f"{session_id}.json").write_text(json.dumps({
                    "skill_id": skill_id,
                    "scope_patterns": ["*"],
                    "session_id": session_id,
                    "started_at": _now_iso(3.0 if stale else 0.0),
                }), encoding="utf-8")

        env = dict(os.environ)
        env["CLAUDE_TOOL_INPUT"] = payload
        env["CHECK_COMMIT_HOOK_ROOT_OVERRIDE"] = str(root)
        # Keep hermetic against a live agent shell's exported identity
        env.pop("AGENT_SESSION_ID", None)
        if skip:
            env["SKIP_COMMIT_BASH_CHECK"] = "1"
        else:
            env.pop("SKIP_COMMIT_BASH_CHECK", None)

        result = subprocess.run(
            [_BASH, _HOOK_REL],
            env=env,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        return result.returncode


def _run_empty() -> int:
    """Invoke hook with empty input (simulates no CLAUDE_TOOL_INPUT)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env.pop("SKIP_COMMIT_BASH_CHECK", None)
    with tempfile.TemporaryDirectory() as tmp:
        env["CHECK_COMMIT_HOOK_ROOT_OVERRIDE"] = tmp
        result = subprocess.run(
            [_BASH, _HOOK_REL],
            env=env,
            cwd=str(_REPO_ROOT),
            input="",
            capture_output=True,
            text=True,
        )
        return result.returncode


# ---------------------------------------------------------------------------
# Blocked operations (exit 2) — git commit without S-76 context
# ---------------------------------------------------------------------------

def test_cb_01_git_commit_bare_blocked():
    """CB-01: git commit → exit 2."""
    assert _run("git commit") == 2


def test_cb_02_git_commit_m_blocked():
    """CB-02: git commit -m "msg" → exit 2."""
    assert _run('git commit -m "test message"') == 2


def test_cb_03_git_commit_amend_blocked():
    """CB-03: git commit --amend → exit 2."""
    assert _run("git commit --amend") == 2


def test_cb_04_chained_git_commit_blocked():
    """CB-04: git add . && git commit -m "msg" → exit 2."""
    assert _run('git add . && git commit -m "test"') == 2


def test_cb_05_semicolon_chained_blocked():
    """CB-05: echo foo; git commit -m "msg" → exit 2."""
    assert _run('echo foo; git commit -m "test"') == 2


def test_cb_06_pipe_chained_blocked():
    """CB-06: echo msg | git commit -F - → exit 2."""
    assert _run("echo msg | git commit -F -") == 2


# ---------------------------------------------------------------------------
# HARDEN-A3/F2: prefix forms that used to bypass detection entirely
# ---------------------------------------------------------------------------

def test_cb_f2_env_prefix_blocked():
    """F2: VAR=1 git commit → exit 2 (was a full bypass pre-A3)."""
    assert _run("VAR=1 git commit -m x") == 2


def test_cb_f2_quoted_env_value_blocked():
    """F2: GIT_AUTHOR_NAME="John Doe" git commit → exit 2 (quoted-value bypass)."""
    assert _run('GIT_AUTHOR_NAME="John Doe" git commit -m x') == 2


def test_cb_f2_single_quoted_env_value_blocked():
    """F2: VAR='a b' git commit → exit 2."""
    assert _run("VAR='a b' git commit -m x") == 2


def test_cb_f2_subshell_blocked():
    """F2: (git commit -m x) → exit 2 (subshell bypass)."""
    assert _run("(git commit -m x)") == 2


def test_cb_f2_command_prefix_blocked():
    """F2: command git commit → exit 2 (builtin-prefix bypass)."""
    assert _run("command git commit -m x") == 2


def test_cb_f2_env_word_prefix_blocked():
    """F2: env git commit → exit 2."""
    assert _run("env git commit -m x") == 2


def test_cb_f2_plumbing_with_env_prefix_still_allowed():
    """F2: VAR=1 git commit-tree stays allowed (plumbing exclusion intact)."""
    assert _run("VAR=1 git commit-tree abc1234 -m msg") == 0


def test_cb_f2r2_env_with_options_blocked():
    """F2 round 2: env -i git commit → exit 2."""
    assert _run("env -i git commit -m a") == 2


def test_cb_f2r2_command_with_options_blocked():
    """F2 round 2: command -p git commit → exit 2."""
    assert _run("command -p git commit -m a") == 2


def test_cb_f2r2_assignment_then_command_word_blocked():
    """F2 round 2: VAR=1 command git commit (interleaved prefixes) → exit 2."""
    assert _run("VAR=1 command git commit -m a") == 2


def test_cb_f2r2_git_global_options_blocked():
    """F2 round 2: git -c user.email=x commit → exit 2 (infix options)."""
    assert _run("git -c user.email=x commit -m a") == 2
    assert _run("git --no-pager commit -m a") == 2
    assert _run("git -C somedir commit -m a") == 2
    assert _run("git --git-dir /tmp/x commit -m a") == 2


def test_cb_f2r2_backslash_escaped_git_blocked():
    """F2 round 2: \\git commit → exit 2 (alias-escape bypass)."""
    assert _run("\\git commit -m a") == 2


def test_cb_f2r2_line_continuation_blocked():
    """F2 round 2: git \\<newline>commit → exit 2 (continuation bypass)."""
    assert _run("git \\\n  commit -m a") == 2


def test_cb_f2r2_git_options_plumbing_still_allowed():
    """F2 round 2: git -c x=y commit-tree stays allowed (plumbing exclusion)."""
    assert _run("git -c user.email=x commit-tree abc1234 -m msg") == 0


# ---------------------------------------------------------------------------
# Allowed operations (exit 0) — S-76 context active
# ---------------------------------------------------------------------------

def test_cb_10_git_commit_with_s76_allowed():
    """CB-10: git commit with S-76 context → exit 0."""
    assert _run('git commit -m "test"', active_skill="S-76") == 0


def test_cb_11_git_commit_amend_with_s76_allowed():
    """CB-11: git commit --amend with S-76 context → exit 0."""
    assert _run("git commit --amend", active_skill="S-76") == 0


# ---------------------------------------------------------------------------
# HARDEN-A3: session-identity awareness
# ---------------------------------------------------------------------------

def test_cb_a3_stale_s76_context_blocked():
    """A3: an expired S-76 ACTIVE.json no longer authorizes commits."""
    assert _run('git commit -m "x"', active_skill="S-76",
                active_started_hours_ago=3.0) == 2


def test_cb_a3_timestampless_s76_context_blocked():
    """A3: an S-76 ACTIVE.json with no started_at is not live."""
    assert _run('git commit -m "x"', active_skill="S-76",
                active_omit_started_at=True) == 2


def test_cb_a3_two_live_s76_contexts_ambiguous_blocked():
    """A3: two live S-76 contexts + no identity = fail-closed, not first-wins."""
    assert _run('git commit -m "x"',
                session_ctxs=(("sess-a", "S-76", False), ("sess-b", "S-76", False))) == 2


def test_cb_a3_identity_prefix_allows_own_session():
    """A3: AGENT_SESSION_ID=<id> git commit passes when THAT session holds S-76."""
    assert _run('AGENT_SESSION_ID=sess-a git commit -m "x"',
                session_ctxs=(("sess-a", "S-76", False), ("sess-b", "S-76", False))) == 0


def test_cb_a3_identity_prefix_blocks_wrong_session():
    """A3: naming a session that does NOT hold S-76 blocks, even if another does."""
    assert _run('AGENT_SESSION_ID=sess-nope git commit -m "x"',
                session_ctxs=(("sess-a", "S-76", False),)) == 2


def test_cb_a3_single_session_context_allows_without_identity():
    """A3: exactly one live per-session S-76 context resolves unambiguously."""
    assert _run('git commit -m "x"',
                session_ctxs=(("sess-solo", "S-76", False),)) == 0


def test_cb_a3_stale_session_context_not_counted():
    """A3: a stale per-session S-76 context neither authorizes nor disambiguates."""
    # stale sess-old doesn't count: sess-live is the single live holder → allow
    assert _run('git commit -m "x"',
                session_ctxs=(("sess-old", "S-76", True), ("sess-live", "S-76", False))) == 0
    # only a stale context exists → block
    assert _run('git commit -m "x"',
                session_ctxs=(("sess-old", "S-76", True),)) == 2


# ---------------------------------------------------------------------------
# Allowed operations (exit 0) — non-commit commands
# ---------------------------------------------------------------------------

def test_cb_20_git_add_allowed():
    """CB-20: git add → exit 0 (not a commit)."""
    assert _run("git add .") == 0


def test_cb_21_git_status_allowed():
    """CB-21: git status → exit 0."""
    assert _run("git status") == 0


def test_cb_22_git_diff_allowed():
    """CB-22: git diff → exit 0."""
    assert _run("git diff --cached --stat") == 0


def test_cb_23_git_log_allowed():
    """CB-23: git log → exit 0."""
    assert _run("git log --oneline -5") == 0


def test_cb_24_git_push_allowed():
    """CB-24: git push → exit 0 (handled by destructive hook, not this one)."""
    assert _run("git push origin main") == 0


# ---------------------------------------------------------------------------
# Allowed operations (exit 0) — plumbing commands
# ---------------------------------------------------------------------------

def test_cb_30_git_commit_tree_allowed():
    """CB-30: git commit-tree → exit 0 (plumbing, not porcelain)."""
    assert _run("git commit-tree abc1234 -m msg") == 0


def test_cb_31_git_commit_graph_allowed():
    """CB-31: git commit-graph → exit 0 (plumbing, not porcelain)."""
    assert _run("git commit-graph write") == 0


# ---------------------------------------------------------------------------
# Fail-open + bypass
# ---------------------------------------------------------------------------

def test_cb_40_empty_input_allowed():
    """CB-40: empty/missing CLAUDE_TOOL_INPUT → exit 0 (fail-open)."""
    assert _run_empty() == 0


def test_cb_41_unparseable_json_allowed():
    """CB-41: malformed JSON input → exit 0 (fail-open)."""
    env = dict(os.environ)
    env["CLAUDE_TOOL_INPUT"] = "{not json"
    env.pop("SKIP_COMMIT_BASH_CHECK", None)
    with tempfile.TemporaryDirectory() as tmp:
        env["CHECK_COMMIT_HOOK_ROOT_OVERRIDE"] = tmp
        result = subprocess.run(
            [_BASH, _HOOK_REL], env=env, cwd=str(_REPO_ROOT),
            capture_output=True, text=True,
        )
    assert result.returncode == 0


def test_cb_42_operator_bypass():
    """CB-42: SKIP_COMMIT_BASH_CHECK=1 → exit 0 (operator bypass)."""
    assert _run("git commit -m x", skip=True) == 0


def test_cb_43_non_bash_payload_allowed():
    """CB-43: payload with no command field → exit 0 (fail-open)."""
    env = dict(os.environ)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"tool_name": "Bash", "tool_input": {}})
    env.pop("SKIP_COMMIT_BASH_CHECK", None)
    with tempfile.TemporaryDirectory() as tmp:
        env["CHECK_COMMIT_HOOK_ROOT_OVERRIDE"] = tmp
        result = subprocess.run(
            [_BASH, _HOOK_REL], env=env, cwd=str(_REPO_ROOT),
            capture_output=True, text=True,
        )
    assert result.returncode == 0

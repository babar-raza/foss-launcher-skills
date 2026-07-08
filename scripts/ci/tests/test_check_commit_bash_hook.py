"""Tests for scripts/ci/hooks/check_commit_bash_hook.sh.

The hook receives a JSON payload via CLAUDE_TOOL_INPUT and exits 2 (block)
when the command contains `git commit` without an active S-76 skill context.

Blocked: git commit (all forms) without S-76 context
Allowed: git commit with S-76 context, git commit-tree/commit-graph (plumbing),
         empty/unparseable input (fail-open), operator bypass
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK_REL = "scripts/ci/hooks/check_commit_bash_hook.sh"
_ACTIVE_FILE = _REPO_ROOT / "reports" / "skill-context" / "ACTIVE.json"
_SENTINEL = object()


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run(command: str, skip: bool = False, active_skill: str | None = _SENTINEL) -> int:
    """Invoke the hook with the given Bash command string; return exit code.

    active_skill controls ACTIVE.json state during the test:
      - _SENTINEL (default): remove ACTIVE.json to ensure isolation from live state
      - None: explicitly no skill (same effect as _SENTINEL, but semantically distinct)
      - "S-76": write ACTIVE.json with that skill_id
    """
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = dict(os.environ)
    env["CLAUDE_TOOL_INPUT"] = payload
    if skip:
        env["SKIP_COMMIT_BASH_CHECK"] = "1"
    else:
        env.pop("SKIP_COMMIT_BASH_CHECK", None)

    # Save existing ACTIVE.json state
    _ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing_active = None
    if _ACTIVE_FILE.exists():
        existing_active = _ACTIVE_FILE.read_text(encoding="utf-8")

    # Set up test state
    if active_skill is _SENTINEL or active_skill is None:
        # Remove ACTIVE.json to isolate from live skill context
        if _ACTIVE_FILE.exists():
            _ACTIVE_FILE.unlink()
    else:
        _ACTIVE_FILE.write_text(
            json.dumps({"skill_id": active_skill, "scope": ["*"]}),
            encoding="utf-8",
        )

    try:
        result = subprocess.run(
            [_BASH, _HOOK_REL],
            env=env,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        return result.returncode
    finally:
        # Restore previous ACTIVE.json state
        if existing_active is not None:
            _ACTIVE_FILE.write_text(existing_active, encoding="utf-8")
        elif _ACTIVE_FILE.exists():
            _ACTIVE_FILE.unlink()


def _run_empty() -> int:
    """Invoke hook with empty input (simulates no CLAUDE_TOOL_INPUT)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env.pop("SKIP_COMMIT_BASH_CHECK", None)
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
# Allowed operations (exit 0) — S-76 context active
# ---------------------------------------------------------------------------

def test_cb_10_git_commit_with_s76_allowed():
    """CB-10: git commit with S-76 context → exit 0."""
    assert _run('git commit -m "test"', active_skill="S-76") == 0


def test_cb_11_git_commit_amend_with_s76_allowed():
    """CB-11: git commit --amend with S-76 context → exit 0."""
    assert _run("git commit --amend", active_skill="S-76") == 0


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
# Allowed operations (exit 0) — edge cases
# ---------------------------------------------------------------------------

def test_cb_40_empty_input_allowed():
    """CB-40: Empty input → fail-open (exit 0)."""
    assert _run_empty() == 0


def test_cb_41_skip_flag_bypasses():
    """CB-41: SKIP_COMMIT_BASH_CHECK=1 → exit 0 regardless of command."""
    assert _run('git commit -m "test"', skip=True) == 0


def test_cb_42_comment_line_allowed():
    """CB-42: # git commit in comment → exit 0."""
    assert _run("# git commit -m 'test'") == 0


def test_cb_43_non_s76_skill_blocked():
    """CB-43: git commit with non-S-76 skill context → exit 2."""
    assert _run('git commit -m "test"', active_skill="S-73") == 2

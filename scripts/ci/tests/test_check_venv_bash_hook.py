"""Tests for check_venv_bash_hook.sh.

The hook receives a JSON payload via CLAUDE_TOOL_INPUT and exits 2 (block)
if the command contains a bare interpreter invocation not prefixed with the
repo venv path.

Test strategy: invoke the shell script as a subprocess with CLAUDE_TOOL_INPUT
set per case, assert on exit code. Stderr is captured but not asserted on.

Known gaps (deferred per plan rosy-wandering-haven TC-D):
- Subshell invocations: hook does not parse subshell syntax.
- Heredoc multi-line commands: hook reads line by line; heredoc bodies may miss.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Use a relative path from the repo root (where pytest is invoked from).
# Path.resolve() returns a Windows path on Windows; bash expects POSIX paths
# or a relative path. Using a repo-relative string avoids the conversion issue.
_HOOK_REL = "scripts/ci/check_venv_bash_hook.sh"

# Repo root: the directory two levels above this test file's location.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Bare interpreter names referenced only as string values so they are never
# the leading token on a line (which would trigger this very hook during
# execution of tests that write files containing these strings).
_PY = "python"
_PY3 = "python3"
_PIP = "pip"
_PIP3 = "pip3"


def _find_bash() -> str:
    """Return bash executable for subprocess invocation.

    On Windows the default 'bash' resolves to WSL bash, which does not
    forward environment variables (including CLAUDE_TOOL_INPUT) across the
    Windows->WSL boundary. Git Bash handles env vars correctly.
    """
    if sys.platform == "win32":
        git_bash = os.path.join(
            "C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe"
        )
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run(command: str) -> int:
    """Invoke the hook with the given command string; return exit code."""
    payload = json.dumps({"command": command})
    env = {**os.environ, "CLAUDE_TOOL_INPUT": payload}
    result = subprocess.run(
        [_BASH, _HOOK_REL],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode


# ---------------------------------------------------------------------------
# TC-D-01: Bare interpreter invocations are blocked
# ---------------------------------------------------------------------------

def test_bare_python_script_is_blocked():
    assert _run(f"{_PY} scripts/pipeline/audit.py") == 2


def test_bare_python3_script_is_blocked():
    assert _run(f"{_PY3} scripts/pipeline/audit.py") == 2


def test_bare_python_module_flag_is_blocked():
    assert _run(f"{_PY} -m pytest tests/") == 2


# ---------------------------------------------------------------------------
# TC-D-02: Compliant .venv paths are allowed
# ---------------------------------------------------------------------------

def test_venv_scripts_python_is_allowed():
    assert _run(".venv/Scripts/python scripts/pipeline/audit.py") == 0


def test_venv_bin_python_is_allowed():
    assert _run(".venv/bin/python scripts/pipeline/audit.py") == 0


def test_venv_scripts_python_module_is_allowed():
    assert _run(".venv/Scripts/python -m pytest tests/") == 0


# ---------------------------------------------------------------------------
# TC-D-03: Exemptions are allowed
# ---------------------------------------------------------------------------

def test_venv_bootstrap_is_exempt():
    # python -m venv must use system interpreter -- exempt from the rule
    assert _run(f"{_PY} -m venv .venv") == 0


def test_python_version_flag_is_exempt():
    assert _run(f"{_PY} --version") == 0


def test_python_version_short_flag_is_exempt():
    assert _run(f"{_PY} -V") == 0


# ---------------------------------------------------------------------------
# TC-D-04: Bare pip invocations are blocked
# ---------------------------------------------------------------------------

def test_bare_pip_install_is_blocked():
    assert _run(f"{_PIP} install requests") == 2


def test_bare_pip3_install_is_blocked():
    assert _run(f"{_PIP3} install requests") == 2


def test_bare_pip_freeze_is_blocked():
    assert _run(f"{_PIP} freeze > requirements.txt") == 2


# ---------------------------------------------------------------------------
# TC-D-05: Env-var prefix stripping
# ---------------------------------------------------------------------------

def test_env_var_prefixed_bare_invocation_is_blocked():
    # PYTHONPATH=foo sets env var; the next token after stripping is bare interpreter
    assert _run(f"PYTHONPATH=scripts/pipeline {_PY} scripts/pipeline/audit.py") == 2


def test_multiple_env_var_prefixes_stripped():
    assert _run(f"PYTHONPATH=a DEBUG=1 {_PY} script.py") == 2


def test_env_var_prefixed_venv_invocation_is_allowed():
    assert _run("PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/audit.py") == 0


# ---------------------------------------------------------------------------
# TC-D-06: Pipeline segment scanning
# ---------------------------------------------------------------------------

def test_bare_python_after_and_operator_is_blocked():
    assert _run(f"mkdir -p out && {_PY} scripts/audit.py") == 2


def test_bare_python_after_semicolon_is_blocked():
    assert _run(f"echo start; {_PY} scripts/audit.py") == 2


def test_non_python_pipeline_is_allowed():
    assert _run("git status && git diff") == 0


# ---------------------------------------------------------------------------
# TC-D-07: Fail-open for missing or unparseable input
# ---------------------------------------------------------------------------

def test_empty_claude_tool_input_is_allowed():
    # No CLAUDE_TOOL_INPUT and no stdin -- hook must fail-open (exit 0)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    result = subprocess.run(
        [_BASH, _HOOK_REL],
        env=env,
        cwd=str(_REPO_ROOT),
        input="",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_empty_json_object_is_allowed():
    # JSON {} has no command key -- hook must fail-open
    assert _run("") == 0

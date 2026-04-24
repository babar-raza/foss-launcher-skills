"""Tests for check_session_gate.sh.

The hook receives a JSON payload via CLAUDE_TOOL_INPUT and exits 2 (block)
when the session has not been bootstrapped (.claude/.agents_read absent),
except for exempted cases (Read tool, exact bootstrap Bash command).

Input handling policy:
- Empty/missing input: fall through to gate-file check
- Malformed JSON: fail-closed (exit 2) regardless of gate state
- Read tool: always allowed (exit 0)
- Exact bootstrap command: always allowed (exit 0)
- All other tools: gate-file check

Bootstrap command matching (exact regex):
  bash scripts/ci/bootstrap_session_gate.sh
  bash ./scripts/ci/bootstrap_session_gate.sh
  (with optional leading/trailing whitespace)
Rejected: compound commands, quoted paths, path traversal.

Test strategy: invoke the shell script as a subprocess (absolute path) with
CLAUDE_TOOL_INPUT set per case. Gate state is controlled by temporarily
saving/restoring the real .claude/.agents_read in the repo root. The hook
finds the gate file via its own SCRIPT_DIR-derived REPO_ROOT, not via cwd.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

# Repo root: three levels up from this test file (scripts/ci/tests/)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Hook uses absolute path — cwd does not need to be the repo root
_HOOK_ABS = str(_REPO_ROOT / "scripts" / "ci" / "check_session_gate.sh")

# Real gate file location (the hook always checks here via SCRIPT_DIR-derived REPO_ROOT)
_GATE_FILE = _REPO_ROOT / ".claude" / ".agents_read"
_GATE_BACKUP = _REPO_ROOT / ".claude" / ".agents_read.test_backup"


def _find_bash() -> str:
    """Return bash executable. On Windows prefer Git Bash for env-var forwarding."""
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


@contextmanager
def _gate_state(present: bool):
    """Context manager: temporarily set gate file state, restore on exit."""
    was_present = _GATE_FILE.exists()
    backup_taken = False

    if was_present and not present:
        # Need gate absent: back up and remove
        shutil.copy2(str(_GATE_FILE), str(_GATE_BACKUP))
        _GATE_FILE.unlink()
        backup_taken = True
    elif not was_present and present:
        # Need gate present: create it
        _GATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _GATE_FILE.write_text("1")

    try:
        yield
    finally:
        # Restore original state
        if was_present and not present:
            if backup_taken and _GATE_BACKUP.exists():
                shutil.copy2(str(_GATE_BACKUP), str(_GATE_FILE))
                _GATE_BACKUP.unlink()
            elif not _GATE_FILE.exists():
                # Backup was lost — recreate from scratch (safe default)
                _GATE_FILE.write_text("1")
        elif not was_present and present:
            if _GATE_FILE.exists():
                _GATE_FILE.unlink()


def _run(
    tool_name: str,
    tool_input: dict | None = None,
    *,
    gate_present: bool,
    raw_payload: str | None = None,
    skip_flag: bool = False,
) -> int:
    """Invoke the hook and return exit code."""
    if raw_payload is not None:
        payload = raw_payload
    else:
        data: dict = {"tool_name": tool_name}
        if tool_input is not None:
            data["tool_input"] = tool_input
        payload = json.dumps(data)

    env = {**os.environ, "CLAUDE_TOOL_INPUT": payload}
    if skip_flag:
        env["SKIP_SESSION_GATE_CHECK"] = "1"
    else:
        env.pop("SKIP_SESSION_GATE_CHECK", None)

    with _gate_state(gate_present):
        result = subprocess.run(
            [_BASH, _HOOK_ABS],
            env=env,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
    return result.returncode


# ---------------------------------------------------------------------------
# TC-SG-01 through TC-SG-10: gate ABSENT
# ---------------------------------------------------------------------------

def test_tc_sg_01_read_tool_exempt_when_gate_absent():
    """TC-SG-01: Read tool always allowed even when gate absent."""
    assert _run("Read", {"file_path": "AGENTS.md"}, gate_present=False) == 0


def test_tc_sg_02_bootstrap_bash_exempt_when_gate_absent():
    """TC-SG-02: Exact bootstrap command allowed when gate absent."""
    assert _run("Bash", {"command": "bash scripts/ci/bootstrap_session_gate.sh"}, gate_present=False) == 0


def test_tc_sg_03_bootstrap_bash_relative_path_exempt():
    """TC-SG-03: ./scripts/ci/bootstrap_session_gate.sh variant allowed."""
    assert _run("Bash", {"command": "bash ./scripts/ci/bootstrap_session_gate.sh"}, gate_present=False) == 0


def test_tc_sg_04_bootstrap_bash_leading_whitespace_exempt():
    """TC-SG-04: Bootstrap command with leading whitespace allowed."""
    assert _run("Bash", {"command": "  bash scripts/ci/bootstrap_session_gate.sh  "}, gate_present=False) == 0


def test_tc_sg_05_other_bash_blocked_when_gate_absent():
    """TC-SG-05: Arbitrary Bash blocked when gate absent."""
    assert _run("Bash", {"command": "cat AGENTS.md"}, gate_present=False) == 2


def test_tc_sg_06_compound_injection_blocked():
    """TC-SG-06: Bootstrap command with appended compound injection blocked."""
    assert _run("Bash", {"command": "bash scripts/ci/bootstrap_session_gate.sh; cat /etc/passwd"}, gate_present=False) == 2


def test_tc_sg_07_quoted_bootstrap_path_blocked():
    """TC-SG-07: Quoted bootstrap path rejected (conservative)."""
    assert _run("Bash", {"command": 'bash "scripts/ci/bootstrap_session_gate.sh"'}, gate_present=False) == 2


def test_tc_sg_08_edit_blocked_when_gate_absent():
    """TC-SG-08: Edit tool blocked when gate absent."""
    assert _run("Edit", {"file_path": "content/foo.md"}, gate_present=False) == 2


def test_tc_sg_09_write_blocked_when_gate_absent():
    """TC-SG-09: Write tool blocked when gate absent."""
    assert _run("Write", {"file_path": "content/foo.md"}, gate_present=False) == 2


def test_tc_sg_10_unknown_tool_blocked_when_gate_absent():
    """TC-SG-10: tool_name present but unknown falls through to gate check — blocked."""
    assert _run("UnknownTool", {}, gate_present=False) == 2


# ---------------------------------------------------------------------------
# TC-SG-11 through TC-SG-13: gate PRESENT
# ---------------------------------------------------------------------------

def test_tc_sg_11_bash_allowed_when_gate_present():
    """TC-SG-11: Arbitrary Bash allowed when gate present."""
    assert _run("Bash", {"command": "cat AGENTS.md"}, gate_present=True) == 0


def test_tc_sg_12_edit_allowed_when_gate_present():
    """TC-SG-12: Edit allowed when gate present."""
    assert _run("Edit", {"file_path": "content/foo.md"}, gate_present=True) == 0


def test_tc_sg_13_write_allowed_when_gate_present():
    """TC-SG-13: Write allowed when gate present."""
    assert _run("Write", {"file_path": "content/foo.md"}, gate_present=True) == 0


# ---------------------------------------------------------------------------
# TC-SG-14 through TC-SG-18: input edge cases
# ---------------------------------------------------------------------------

def test_tc_sg_14_empty_input_gate_absent_blocked():
    """TC-SG-14: Empty CLAUDE_TOOL_INPUT with gate absent — blocked (falls to gate check)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env.pop("SKIP_SESSION_GATE_CHECK", None)
    with _gate_state(False):
        result = subprocess.run(
            [_BASH, _HOOK_ABS],
            env=env,
            cwd=str(_REPO_ROOT),
            input="",
            capture_output=True,
            text=True,
        )
    assert result.returncode == 2


def test_tc_sg_15_empty_input_gate_present_allowed():
    """TC-SG-15: Empty CLAUDE_TOOL_INPUT with gate present — allowed (falls to gate check)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env.pop("SKIP_SESSION_GATE_CHECK", None)
    with _gate_state(True):
        result = subprocess.run(
            [_BASH, _HOOK_ABS],
            env=env,
            cwd=str(_REPO_ROOT),
            input="",
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0


def test_tc_sg_16_malformed_json_gate_absent_blocked():
    """TC-SG-16: Malformed JSON with gate absent — fail-closed (exit 2)."""
    assert _run("", gate_present=False, raw_payload="{not valid json}") == 2


def test_tc_sg_17_malformed_json_gate_present_blocked():
    """TC-SG-17: Malformed JSON with gate present — fail-closed regardless of gate state."""
    assert _run("", gate_present=True, raw_payload="{not valid json}") == 2


def test_tc_sg_18_skip_flag_bypasses_all():
    """TC-SG-18: SKIP_SESSION_GATE_CHECK=1 exits 0 regardless of gate state or tool."""
    assert _run("Edit", {"file_path": "content/foo.md"}, gate_present=False, skip_flag=True) == 0

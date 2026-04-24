"""End-to-end tests for the session gate bootstrap fix.

Proves the full recovery sequence:
1. Gate absent → non-bootstrap non-Read tool blocked
2. Gate absent → Read tool allowed (bootstrap read path)
3. Gate absent → bootstrap Bash command allowed by gate hook
4. Bootstrap script creates gate file
5. Gate present → normal tool calls allowed
6. Compound injection blocked even with gate absent
7. Downstream skill-context hook still enforces its own rules after bootstrap

Gate state is controlled by temporarily saving/restoring the real
.claude/.agents_read in the repo root. The hook finds the gate file via
its own SCRIPT_DIR-derived REPO_ROOT, not via cwd.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_GATE_HOOK_ABS = str(_REPO_ROOT / "scripts" / "ci" / "check_session_gate.sh")
_SKILL_HOOK_ABS = str(_REPO_ROOT / "scripts" / "ci" / "check_skill_context_hook.sh")
_BOOTSTRAP_SCRIPT_ABS = str(_REPO_ROOT / "scripts" / "ci" / "bootstrap_session_gate.sh")
_GATE_FILE = _REPO_ROOT / ".claude" / ".agents_read"
_GATE_BACKUP = _REPO_ROOT / ".claude" / ".agents_read.e2e_backup"


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


@contextmanager
def _gate_state(present: bool):
    """Temporarily set gate file state, restore on exit."""
    was_present = _GATE_FILE.exists()
    backup_taken = False

    if was_present and not present:
        shutil.copy2(str(_GATE_FILE), str(_GATE_BACKUP))
        _GATE_FILE.unlink()
        backup_taken = True
    elif not was_present and present:
        _GATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _GATE_FILE.write_text("1")

    try:
        yield
    finally:
        if was_present and not present:
            if backup_taken and _GATE_BACKUP.exists():
                shutil.copy2(str(_GATE_BACKUP), str(_GATE_FILE))
                _GATE_BACKUP.unlink()
            elif not _GATE_FILE.exists():
                _GATE_FILE.write_text("1")
        elif not was_present and present:
            if _GATE_FILE.exists():
                _GATE_FILE.unlink()


def _run_gate_hook(tool_name: str, tool_input: dict) -> int:
    """Run check_session_gate.sh with a JSON payload. Gate state must be set by caller."""
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    env = {**os.environ, "CLAUDE_TOOL_INPUT": payload}
    env.pop("SKIP_SESSION_GATE_CHECK", None)
    result = subprocess.run(
        [_BASH, _GATE_HOOK_ABS],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode


def test_e2e_01_gate_absent_edit_blocked():
    """E2E-01: Gate absent → Edit tool blocked."""
    with _gate_state(False):
        code = _run_gate_hook("Edit", {"file_path": "content/foo.md"})
    assert code == 2, f"Expected exit 2 (blocked), got {code}"


def test_e2e_02_gate_absent_read_allowed():
    """E2E-02: Gate absent → Read tool allowed (needed for AGENTS.md)."""
    with _gate_state(False):
        code = _run_gate_hook("Read", {"file_path": "AGENTS.md"})
    assert code == 0, f"Expected exit 0 (allowed), got {code}"


def test_e2e_03_gate_absent_bootstrap_command_allowed():
    """E2E-03: Gate absent → bootstrap Bash command passes gate hook."""
    with _gate_state(False):
        code = _run_gate_hook("Bash", {"command": "bash scripts/ci/bootstrap_session_gate.sh"})
    assert code == 0, f"Expected exit 0 (bootstrap exempt), got {code}"


def test_e2e_04_bootstrap_script_creates_gate():
    """E2E-04: Running bootstrap_session_gate.sh creates .claude/.agents_read."""
    with _gate_state(False):
        assert not _GATE_FILE.exists()
        result = subprocess.run(
            [_BASH, _BOOTSTRAP_SCRIPT_ABS],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        created = _GATE_FILE.exists()
    # After context manager restores state, just check it was created during the run
    assert result.returncode == 0, f"Bootstrap script failed: {result.stderr}"
    assert created, ".claude/.agents_read was not created by bootstrap script"


def test_e2e_05_gate_present_edit_allowed():
    """E2E-05: After bootstrap, Edit tool is allowed by gate hook."""
    with _gate_state(True):
        code = _run_gate_hook("Edit", {"file_path": "content/foo.md"})
    assert code == 0, f"Expected exit 0 (gate present), got {code}"


def test_e2e_06_compound_injection_blocked():
    """E2E-06: Compound bootstrap injection blocked even when gate absent."""
    with _gate_state(False):
        code = _run_gate_hook(
            "Bash",
            {"command": "bash scripts/ci/bootstrap_session_gate.sh; cat /etc/passwd"},
        )
    assert code == 2, f"Compound injection should be rejected (exit 2), got {code}"


def test_e2e_07_skill_context_hook_still_enforces_after_bootstrap():
    """E2E-07: check_skill_context_hook still blocks governed edits without ACTIVE.json.

    This proves downstream governance enforcement is unchanged by the bootstrap fix.
    """
    active_json = _REPO_ROOT / "reports" / "skill-context" / "ACTIVE.json"
    active_existed = active_json.exists()
    active_backup = _REPO_ROOT / "reports" / "skill-context" / "ACTIVE.json.e2e_backup"

    if active_existed:
        shutil.copy2(str(active_json), str(active_backup))
        active_json.unlink()

    try:
        payload = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": str(_REPO_ROOT / "content" / "foo.md")},
        })
        env = {
            **os.environ,
            "CLAUDE_TOOL_INPUT": payload,
        }
        env.pop("SKIP_SKILL_CONTEXT_CHECK", None)
        result = subprocess.run(
            [_BASH, _SKILL_HOOK_ABS],
            env=env,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, (
            f"skill_context hook should block without ACTIVE.json (exit 2), "
            f"got {result.returncode}. stderr: {result.stderr}"
        )
    finally:
        if active_existed and active_backup.exists():
            shutil.copy2(str(active_backup), str(active_json))
            active_backup.unlink()

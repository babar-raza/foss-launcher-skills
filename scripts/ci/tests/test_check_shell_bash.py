"""Tests for scripts/ci/check_shell_bash.sh — Git Bash enforcement utility.

Test strategy: invoke the shell script as a subprocess with environment variables
set per case, assert on exit code and stderr content.

Note: Tests simulate env vars via subprocess. Cannot test from a real PowerShell
or cmd.exe process in CI (CI runs on ubuntu-latest). Shell environment simulation
is the accepted approach for this test suite.

Test naming follows plan taskcards (TC-01 through TC-10).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Script under test — use repo-relative path to avoid Windows/POSIX conversion issues.
_SCRIPT_REL = "scripts/ci/hooks/check_shell_bash.sh"

# Repo root: four levels above this test file's location.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _find_bash() -> str:
    """Return bash executable for subprocess invocation.

    On Windows the default 'bash' resolves to WSL bash, which does not
    forward environment variables across the Windows->WSL boundary.
    Git Bash handles env vars correctly.
    """
    if sys.platform == "win32":
        git_bash = os.path.join(
            "C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe"
        )
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run(
    env_overrides: dict[str, str],
    mode: str = "warn",
) -> subprocess.CompletedProcess[str]:
    """Run check_shell_bash.sh with the given environment overrides."""
    env = os.environ.copy()
    # Remove vars that would indicate Git Bash by default on the test runner,
    # so each test controls exactly which signals are present.
    for key in ("MSYSTEM", "WSL_DISTRO_NAME", "WSL_INTEROP"):
        env.pop(key, None)
    # Do NOT remove OSTYPE — bash sets it automatically; tests that need cygwin
    # override it explicitly (the override wins for the child process).
    env.update(env_overrides)
    env["_SHELL_CHECK_MODE"] = mode
    return subprocess.run(
        [_BASH, _SCRIPT_REL],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(_REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# TC-01, TC-02: Positive tests — Git Bash on Windows must pass
# ---------------------------------------------------------------------------

def test_TC01_git_bash_mingw64_passes():
    """Git Bash (MSYSTEM=MINGW64) is the expected environment — must pass."""
    result = _run({"OS": "Windows_NT", "MSYSTEM": "MINGW64"})
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "VIOLATION" not in result.stderr


def test_TC02_git_bash_mingw32_passes():
    """Git Bash (MSYSTEM=MINGW32) is also acceptable — must pass."""
    result = _run({"OS": "Windows_NT", "MSYSTEM": "MINGW32"})
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "VIOLATION" not in result.stderr


# ---------------------------------------------------------------------------
# TC-03: WSL detection via WSL_DISTRO_NAME — warn and block modes
# ---------------------------------------------------------------------------

def test_TC03_wsl_distro_name_warn_mode():
    """WSL detected via WSL_DISTRO_NAME — warn mode exits 0 but prints warning."""
    result = _run(
        {"OS": "Windows_NT", "WSL_DISTRO_NAME": "Ubuntu"},
        mode="warn",
    )
    assert result.returncode == 0
    assert "WSL" in result.stderr
    assert "WARN MODE" in result.stderr


def test_TC03_wsl_distro_name_block_mode():
    """WSL detected via WSL_DISTRO_NAME — block mode exits 1."""
    result = _run(
        {"OS": "Windows_NT", "WSL_DISTRO_NAME": "Ubuntu"},
        mode="block",
    )
    assert result.returncode == 1
    assert "WSL" in result.stderr
    assert "WARN MODE" not in result.stderr


# ---------------------------------------------------------------------------
# TC-04: WSL detection via WSL_INTEROP — block mode
# ---------------------------------------------------------------------------

def test_TC04_wsl_interop_block_mode():
    """WSL detected via WSL_INTEROP — block mode exits 1."""
    result = _run(
        {"OS": "Windows_NT", "WSL_INTEROP": "/run/WSL/12345_interop"},
        mode="block",
    )
    assert result.returncode == 1
    assert "WSL" in result.stderr


# ---------------------------------------------------------------------------
# TC-05: Cygwin detection — block mode
# ---------------------------------------------------------------------------

def test_TC05_cygwin_block_mode():
    """Cygwin detected via OSTYPE=cygwin — block mode exits 1."""
    result = _run(
        {"OS": "Windows_NT", "OSTYPE": "cygwin"},
        mode="block",
    )
    assert result.returncode == 1
    assert "Cygwin" in result.stderr


# ---------------------------------------------------------------------------
# TC-06: Unknown bash on Windows (BASH_VERSION set but no MSYSTEM) — block mode
# ---------------------------------------------------------------------------

def test_TC06_unknown_bash_no_msystem_block_mode():
    """Bash on Windows but no MSYSTEM — not Git Bash — block mode exits 1."""
    result = _run(
        {"OS": "Windows_NT"},
        mode="block",
    )
    assert result.returncode == 1
    assert "MSYSTEM" in result.stderr


# ---------------------------------------------------------------------------
# TC-07, TC-08: Non-Windows environments skip unconditionally
# ---------------------------------------------------------------------------

def test_TC07_linux_skipped():
    """On Linux (OS != Windows_NT), the check skips unconditionally."""
    result = _run({"OS": "Linux"}, mode="block")
    assert result.returncode == 0
    assert "VIOLATION" not in result.stderr


def test_TC08_no_os_var_skipped():
    """When OS is absent (macOS, CI), check skips."""
    env = os.environ.copy()
    for key in ("MSYSTEM", "WSL_DISTRO_NAME", "WSL_INTEROP"):
        env.pop(key, None)
    env.pop("OS", None)
    env["_SHELL_CHECK_MODE"] = "block"
    result = subprocess.run(
        [_BASH, _SCRIPT_REL],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0
    assert "VIOLATION" not in result.stderr


# ---------------------------------------------------------------------------
# TC-09, TC-10: Violation message content checks
# ---------------------------------------------------------------------------

def test_TC09_violation_messages_link_to_quickstart():
    """All violation messages must reference docs/QUICKSTART.md."""
    result = _run(
        {"OS": "Windows_NT", "WSL_DISTRO_NAME": "Ubuntu"},
        mode="warn",
    )
    assert "QUICKSTART.md" in result.stderr


def test_TC10_wsl_violation_links_to_status_doc():
    """WSL violation must reference docs/STATUS-venv-closure.md."""
    result = _run(
        {"OS": "Windows_NT", "WSL_DISTRO_NAME": "Ubuntu"},
        mode="warn",
    )
    assert "STATUS-venv-closure.md" in result.stderr

"""Tests for scripts/ci/find_python.sh.

Test strategy: source find_python.sh in a bash subprocess and check the
resulting PYTHON variable. For healthy-venv cases, use the real repo venv.
For broken/absent venv cases, create a temp directory tree that mimics the
repo structure (scripts/ci/find_python.sh above a fake .venv/) so
find_python.sh computes the wrong repo root and cannot find a real Python.

Policy (DR-01): find_python.sh must NEVER fall back to python3 or bare python.
If .venv is absent or broken, PYTHON must be empty and exit code must be 1.

Notes on MSYS2/Git Bash behaviour:
- Running an empty .exe file on MSYS2 treats it as an empty shell script (exit 0).
  Use a stub that explicitly exits 1 instead of an empty file.
- The source return code is not automatically propagated as the subprocess exit
  code when followed by other commands. Capture _SRC_RC explicitly and exit with it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FIND_PYTHON_SH = _REPO_ROOT / "scripts" / "ci" / "find_python.sh"


def _find_bash() -> str:
    """Return Git Bash on Windows; plain bash elsewhere."""
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _source_and_check(script_path: Path) -> tuple[str, int]:
    """Source the find_python.sh at script_path; return (PYTHON value, exit code of source).

    Propagates the source return code as the subprocess exit code by capturing
    it in _SRC_RC and passing it to `exit`. This avoids the MSYS2 behaviour
    where the final `echo` command masks the source return code.
    """
    cmd = (
        f'source "{script_path}" 2>/dev/null; _SRC_RC=$?; '
        f'echo "PYTHON=${{PYTHON:-}}"; exit "$_SRC_RC"'
    )
    result = subprocess.run(
        [_BASH, "-c", cmd],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    python_val = ""
    for line in result.stdout.splitlines():
        if line.startswith("PYTHON="):
            python_val = line[len("PYTHON="):]
    return python_val, result.returncode


def _make_failing_stub(path: Path) -> None:
    """Create a shell-script stub at path that exits 1.

    On MSYS2/Git Bash, an empty binary is treated as an empty shell script (exits 0),
    so we need an explicit exit-1 stub to simulate a broken Python interpreter.
    The shebang ensures bash executes it correctly regardless of file extension.
    """
    path.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    try:
        import stat as _stat
        path.chmod(path.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)
    except Exception:
        pass  # chmod may be a no-op on Windows NTFS; MSYS2 still runs it via shebang


# ---------------------------------------------------------------------------
# FP-01: Healthy venv — PYTHON set to venv path
# ---------------------------------------------------------------------------

def test_fp_01_healthy_venv_python_set():
    """FP-01: Healthy repo venv → PYTHON is set to .venv path."""
    python_val, _ = _source_and_check(_FIND_PYTHON_SH)
    assert python_val, "PYTHON must not be empty with healthy venv"
    assert ".venv" in python_val, f"PYTHON must point into .venv, got: {python_val!r}"


def test_fp_01_healthy_venv_exit_0():
    """FP-01: Healthy repo venv → source exits 0."""
    _, rc = _source_and_check(_FIND_PYTHON_SH)
    assert rc == 0, f"Expected exit 0, got {rc}"


# ---------------------------------------------------------------------------
# FP-04: python3 must NEVER appear in the PYTHON result
# ---------------------------------------------------------------------------

def test_fp_04_no_python3_in_result():
    """FP-04: PYTHON must not contain 'python3' (DR-01: venv-only, no fallback)."""
    python_val, _ = _source_and_check(_FIND_PYTHON_SH)
    assert "python3" not in python_val, (
        f"PYTHON must not reference python3 (bare fallback forbidden), got: {python_val!r}"
    )


def test_fp_04_no_bare_python_in_result():
    """FP-04: PYTHON must not be just 'python' or 'python3' (bare name without path)."""
    python_val, _ = _source_and_check(_FIND_PYTHON_SH)
    # Bare python names have no path separator
    assert python_val == "" or "/" in python_val or "\\" in python_val, (
        f"PYTHON looks like a bare name (no path separator): {python_val!r}"
    )


# ---------------------------------------------------------------------------
# FP-02: Stub-only venv — binary exists but health check fails
# ---------------------------------------------------------------------------

def test_fp_02_stub_only_venv_python_empty():
    """FP-02: Stub-only .venv (binary exists but exits 1) → PYTHON="" and exits 1."""
    tmp = Path(tempfile.mkdtemp(prefix="fp_test_"))
    try:
        # Create fake repo structure: tmp/scripts/ci/find_python.sh (copy)
        fake_scripts_ci = tmp / "scripts" / "ci"
        fake_scripts_ci.mkdir(parents=True)
        fake_find_python = fake_scripts_ci / "find_python.sh"
        shutil.copy2(_FIND_PYTHON_SH, fake_find_python)

        # Create stub .venv/Scripts/python.exe that explicitly exits 1.
        # An empty file would exit 0 on MSYS2 (treated as empty shell script).
        fake_venv = tmp / ".venv" / "Scripts"
        fake_venv.mkdir(parents=True)
        _make_failing_stub(fake_venv / "python.exe")
        # NO pyvenv.cfg (simulates OneDrive partial sync)

        python_val, rc = _source_and_check(fake_find_python)
        assert python_val == "", f"PYTHON must be empty with stub venv, got: {python_val!r}"
        assert rc != 0, f"Expected non-zero exit with stub venv, got: {rc}"
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


# ---------------------------------------------------------------------------
# FP-03: No venv directory — PYTHON="" and exits 1
# ---------------------------------------------------------------------------

def test_fp_03_no_venv_python_empty():
    """FP-03: No .venv directory → PYTHON="" and exits 1."""
    tmp = Path(tempfile.mkdtemp(prefix="fp_test_"))
    try:
        fake_scripts_ci = tmp / "scripts" / "ci"
        fake_scripts_ci.mkdir(parents=True)
        fake_find_python = fake_scripts_ci / "find_python.sh"
        shutil.copy2(_FIND_PYTHON_SH, fake_find_python)
        # Deliberately: no .venv/ directory created

        python_val, rc = _source_and_check(fake_find_python)
        assert python_val == "", f"PYTHON must be empty with no venv, got: {python_val!r}"
        assert rc != 0, f"Expected non-zero exit with no venv, got: {rc}"
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)

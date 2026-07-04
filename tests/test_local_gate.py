"""Tests for scripts/local_gate.py.

Covers _run_gate (pass, fail, timeout, FileNotFoundError) and
main() success / failure paths via subprocess mocking.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _make_proc(returncode: int) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    return m


# ---------------------------------------------------------------------------
# _run_gate
# ---------------------------------------------------------------------------

def test_run_gate_pass(capsys) -> None:
    """_run_gate returns True when subprocess exits 0."""
    from local_gate import _run_gate
    with patch("local_gate.subprocess.run", return_value=_make_proc(0)):
        result = _run_gate("Test Gate", ["echo", "ok"])
    assert result is True
    captured = capsys.readouterr()
    assert "PASS" in captured.out


def test_run_gate_fail(capsys) -> None:
    """_run_gate returns False when subprocess exits non-zero."""
    from local_gate import _run_gate
    with patch("local_gate.subprocess.run", return_value=_make_proc(1)):
        result = _run_gate("Test Gate", ["false"])
    assert result is False
    captured = capsys.readouterr()
    assert "FAIL" in captured.out


def test_run_gate_timeout(capsys) -> None:
    """_run_gate returns False when subprocess times out."""
    from local_gate import _run_gate
    with patch(
        "local_gate.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["slow"], timeout=300),
    ):
        result = _run_gate("Slow Gate", ["slow"])
    assert result is False
    captured = capsys.readouterr()
    assert "TIMEOUT" in captured.out


def test_run_gate_not_found(capsys) -> None:
    """_run_gate returns True (SKIP) when command is not found."""
    from local_gate import _run_gate
    with patch(
        "local_gate.subprocess.run",
        side_effect=FileNotFoundError("no such file"),
    ):
        result = _run_gate("Missing Gate", ["no-such-tool"])
    assert result is True
    captured = capsys.readouterr()
    assert "SKIP" in captured.out


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def test_main_all_pass_returns_0(capsys) -> None:
    """main() returns 0 when all gates pass."""
    from local_gate import main
    with patch("local_gate.subprocess.run", return_value=_make_proc(0)):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "All gates passed" in captured.out


def test_main_one_fail_returns_1(capsys) -> None:
    """main() returns 1 when any gate fails."""
    from local_gate import main
    call_count = {"n": 0}

    def side_effect(cmd, **kwargs):
        call_count["n"] += 1
        # First gate passes, second fails
        if call_count["n"] == 1:
            return _make_proc(0)
        return _make_proc(1)

    with patch("local_gate.subprocess.run", side_effect=side_effect):
        rc = main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "FAILED" in captured.out


def test_main_all_fail_returns_1(capsys) -> None:
    """main() returns 1 when all gates fail."""
    from local_gate import main
    with patch("local_gate.subprocess.run", return_value=_make_proc(1)):
        rc = main()
    assert rc == 1


def test_main_summary_lists_all_gates(capsys) -> None:
    """main() prints all gate names in the summary section."""
    from local_gate import main
    with patch("local_gate.subprocess.run", return_value=_make_proc(0)):
        main()
    out = capsys.readouterr().out
    assert "Skill Registry" in out
    assert "Test Suite" in out
    assert "SAST" in out or "bandit" in out.lower()
    assert "Dependency Audit" in out or "pip" in out.lower()

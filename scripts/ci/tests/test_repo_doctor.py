"""Tests for scripts/ci/checks/repo_doctor.py's --check <name> flag.

Added 2026-09-30 alongside session-start's hookspath-drift check being rewired to call
this script instead of a hand-inlined bash copy of the same logic (the exact
doc-vs-script drift pattern this repo has already been bitten by once — see
session-start.md step 6's check_plan_quality.py comment). Root incident: core.hooksPath
had drifted to a stale absolute path on one machine, silently disabling every local git
hook and letting a known content defect (duplicate aliases: across blog post locale
translations) reach main unblocked.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import repo_doctor  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    repo_doctor.configure()


def _fake_run(stdout: str, returncode: int = 0):
    def _inner(cmd, timeout=10):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return _inner


def test_check_git_hooks_ready_when_configured_correctly():
    repo_doctor.configure(run_fn=_fake_run("scripts/githooks"))
    result = repo_doctor.check_git_hooks()
    assert result == {"name": "git_hooks", "status": "READY",
                       "detail": "core.hooksPath = scripts/githooks", "remediation": None}


def test_check_git_hooks_blocked_when_stale_absolute_path():
    """The exact incident this check exists to catch: core.hooksPath pointing at an
    absolute path on a drive that doesn't match the current checkout."""
    repo_doctor.configure(run_fn=_fake_run(r"D:\onedrive\Documents\GitHub\aspose.org\scripts\githooks"))
    result = repo_doctor.check_git_hooks()
    assert result["status"] == "BLOCKED"
    assert "D:" in result["detail"]
    assert result["remediation"] == "bash scripts/install-hooks.sh"


def test_check_git_hooks_blocked_when_unset():
    repo_doctor.configure(run_fn=_fake_run(""))
    result = repo_doctor.check_git_hooks()
    assert result["status"] == "BLOCKED"
    assert "(unset)" in result["detail"]


def test_check_git_hooks_normalizes_backslashes():
    """A correctly-configured relative path on Windows may come back with backslashes
    (scripts\\githooks) — must still compare equal to the forward-slash form."""
    repo_doctor.configure(run_fn=_fake_run("scripts\\githooks"))
    result = repo_doctor.check_git_hooks()
    assert result["status"] == "READY"


def test_checks_by_name_matches_each_check_functions_own_name_field():
    """CHECKS_BY_NAME is a hand-written dict, not derived by calling each check
    function (that would execute every check, including a real pytest subprocess, just
    to read a name) -- so prove it hasn't drifted from what each function actually
    returns, using cheap/mocked checks only."""
    repo_doctor.configure(run_fn=_fake_run("scripts/githooks"))
    for expected_name, fn in repo_doctor.CHECKS_BY_NAME.items():
        if fn in (repo_doctor.check_venv, repo_doctor.check_knowledge_dir, repo_doctor.check_pytest_collection):
            continue  # these touch real repo/venv state regardless of _run mocking
        assert fn()["name"] == expected_name


def test_main_check_flag_runs_only_the_named_check(capsys):
    repo_doctor.configure(run_fn=_fake_run("scripts/githooks"))
    exit_code = repo_doctor.main(["--check", "git_hooks", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["overall"] == "READY"
    assert [c["name"] for c in out["checks"]] == ["git_hooks"]


def test_main_check_flag_propagates_blocked_exit_code(capsys):
    repo_doctor.configure(run_fn=_fake_run(r"D:\stale\path"))
    exit_code = repo_doctor.main(["--check", "git_hooks", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert out["overall"] == "BLOCKED"


def test_main_rejects_unknown_check_name(capsys):
    try:
        repo_doctor.main(["--check", "bogus"])
        assert False, "expected SystemExit from argparse"
    except SystemExit as exc:
        assert exc.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_main_without_check_flag_runs_full_suite(capsys):
    """Default (no --check) behavior is unchanged: every registered check runs."""
    repo_doctor.configure(run_fn=_fake_run("scripts/githooks"))
    exit_code = repo_doctor.main(["--json"])
    out = json.loads(capsys.readouterr().out)
    assert {c["name"] for c in out["checks"]} == set(repo_doctor.CHECKS_BY_NAME)
    assert exit_code in (0, 1)

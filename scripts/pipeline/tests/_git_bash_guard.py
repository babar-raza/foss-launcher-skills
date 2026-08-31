"""Shared guard for test suites that need a REAL MSYS/Git Bash harness.

TC-SG-20(a), 2026-08-31 (stale-guard plan): on POSIX hosts
git_plumb_commit._resolve_git_bash() returns None BY DESIGN -- its contract
accepts only MSYS/Cygwin `uname -s` answers, because on Windows a "linux"
answer means the WSL launcher stub, which silently defeats GIT_INDEX_FILE
isolation (see the resolver's own docstring). On an actual POSIX host there
is no Git Bash to find, so the bash-harness suites cannot run there at all;
their CI home is the windows-latest governance leg
(skill-governance.yml `governance-tests-windows`, green since 2026-08-30).

Decision recorded in the plan's TC-SG-20(a): SKIP on POSIX (an expected
platform state, not a broken machine) and FAIL on Windows (where a missing
Git Bash genuinely is a broken machine). Widening the production resolver to
accept native POSIX bash is a separate, human-gated decision -- do not fold
it into this guard.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_OPS_DIR = Path(__file__).resolve().parents[1] / "commands" / "ops"
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

import git_plumb_commit as _gpc  # noqa: E402

POSIX_SKIP_REASON = (
    "no MSYS/Git Bash on this host: _resolve_git_bash() rejects POSIX bash by "
    "contract (Windows WSL-stub hazard); these tests' CI home is the "
    "windows-latest governance leg (TC-SG-20a)"
)


def require_git_bash() -> str:
    """Return the resolved Git Bash path, or skip (POSIX) / fail (Windows)."""
    bash = _gpc._resolve_git_bash()
    if bash is None:
        if os.name != "nt":
            pytest.skip(POSIX_SKIP_REASON)
        pytest.fail("no working Git Bash found on this machine")
    return bash

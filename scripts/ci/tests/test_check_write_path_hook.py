"""Tests for scripts/ci/check_write_path_hook.sh.

Covers the out-of-repo write blocking added by TC-07 (DR-04).

Allowlisted external paths (exit 0):  ~/.claude/plans/, ~/.claude/projects/
Blocked external paths (exit 2):      ~/.claude/settings.json, /tmp/*, system paths
In-repo paths: governed by path_guard.py (existing behaviour, not retested here).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK_REL = "scripts/ci/hooks/check_write_path_hook.sh"


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()
_HOME = str(Path.home())


def _run(file_path: str) -> int:
    """Invoke the hook with the given file_path; return exit code."""
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path, "content": "x"}})
    env = dict(os.environ)
    env["CLAUDE_TOOL_INPUT"] = payload
    env.pop("ROOT_WRITE_AUTHORIZED", None)
    result = subprocess.run(
        [_BASH, _HOOK_REL],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode


# ---------------------------------------------------------------------------
# WR-01: Allowlisted external paths → exit 0
# ---------------------------------------------------------------------------

def test_wr_01_claude_plans_allowed():
    """WR-01: ~/.claude/plans/foo.md → exit 0 (allowlisted external path)."""
    path = str(Path(_HOME) / ".claude" / "plans" / "foo.md")
    # Normalise to forward slashes for cross-platform consistency
    path = path.replace("\\", "/")
    assert _run(path) == 0, f"Expected 0 for {path!r}"


def test_wr_01_claude_projects_allowed():
    """WR-01: ~/.claude/projects/bar.md → exit 0 (allowlisted external path)."""
    path = str(Path(_HOME) / ".claude" / "projects" / "bar.md")
    path = path.replace("\\", "/")
    assert _run(path) == 0, f"Expected 0 for {path!r}"


# ---------------------------------------------------------------------------
# WR-02: ~/.claude/settings.json → exit 2
# ---------------------------------------------------------------------------

def test_wr_02_claude_settings_blocked():
    """WR-02: ~/.claude/settings.json → exit 2 (not in allowlist)."""
    path = str(Path(_HOME) / ".claude" / "settings.json")
    path = path.replace("\\", "/")
    assert _run(path) == 2, f"Expected 2 for {path!r}"


# ---------------------------------------------------------------------------
# WR-03: /tmp/foo.py → exit 2
# ---------------------------------------------------------------------------

def test_wr_03_tmp_file_blocked():
    """WR-03: /tmp/foo.py → exit 2 (not in allowlist)."""
    assert _run("/tmp/foo.py") == 2


def test_wr_03_arbitrary_absolute_blocked():
    """WR-03: /etc/passwd → exit 2 (not in allowlist)."""
    assert _run("/etc/passwd") == 2


# ---------------------------------------------------------------------------
# Regression: in-repo writes still governed by path_guard
# ---------------------------------------------------------------------------

def test_in_repo_allowed_path_passes():
    """In-repo write to reports/ → exit 0 (path_guard allows)."""
    assert _run("reports/foo.txt") == 0


def test_in_repo_denied_path_blocked():
    """In-repo write to AGENTS.md → exit 2 (FORBIDDEN_EXACT in path_guard)."""
    assert _run("AGENTS.md") == 2

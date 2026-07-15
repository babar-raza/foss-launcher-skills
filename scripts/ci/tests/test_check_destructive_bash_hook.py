"""Tests for scripts/ci/check_destructive_bash_hook.sh.

The hook receives a JSON payload via CLAUDE_TOOL_INPUT and exits 2 (block)
when the command contains a high-blast-radius destructive operation.

Blocked: git reset in ANY form (bare, HEAD, --soft/--mixed/--hard, any target,
with or without a `-- <file>` suffix -- no allowed forms, closed 2026-07-15
after a concurrent-session git reset emptied a commit's index mid-hook and
pushed an empty commit to main, b860c6fb92), git clean -f, force-push to
main/master, git checkout -- ., git rm (without -n), mass filesystem deletions.

Allowed: --force-with-lease, git clean -n (dry-run), git restore --staged,
expendable-dir removals, empty/unparseable input (fail-open).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK_REL = "scripts/ci/hooks/check_destructive_bash_hook.sh"


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run(command: str, skip: bool = False) -> int:
    """Invoke the hook with the given Bash command string; return exit code."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = dict(os.environ)
    env["CLAUDE_TOOL_INPUT"] = payload
    if skip:
        env["SKIP_DESTRUCTIVE_BASH_CHECK"] = "1"
    else:
        env.pop("SKIP_DESTRUCTIVE_BASH_CHECK", None)
    result = subprocess.run(
        [_BASH, _HOOK_REL],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode


def _run_empty() -> int:
    """Invoke hook with empty input (simulates no CLAUDE_TOOL_INPUT)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_TOOL_INPUT"}
    env.pop("SKIP_DESTRUCTIVE_BASH_CHECK", None)
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
# Blocked operations (exit 2)
# ---------------------------------------------------------------------------

def test_db_01_git_reset_hard_head_blocked():
    """DB-01: git reset --hard HEAD → exit 2."""
    assert _run("git reset --hard HEAD") == 2


def test_db_02_git_push_force_main_blocked():
    """DB-02: git push --force origin main → exit 2."""
    assert _run("git push --force origin main") == 2


def test_db_02b_git_push_f_master_blocked():
    """DB-02b: git push -f origin master → exit 2."""
    assert _run("git push -f origin master") == 2


def test_db_03_git_clean_f_blocked():
    """DB-03: git clean -f → exit 2."""
    assert _run("git clean -f") == 2


def test_db_08_rm_rf_root_blocked():
    """DB-08: rm -rf / → exit 2."""
    assert _run("rm -rf /") == 2


# ---------------------------------------------------------------------------
# Allowed operations (exit 0)
# ---------------------------------------------------------------------------

def test_db_04_git_clean_n_allowed():
    """DB-04: git clean -n (dry-run) → exit 0."""
    assert _run("git clean -n") == 0


def test_db_06_force_with_lease_allowed():
    """DB-06: git push --force-with-lease → exit 0."""
    assert _run("git push --force-with-lease") == 0


def test_db_07_rm_rf_reports_allowed():
    """DB-07: rm -rf reports/ (expendable dir) → exit 0."""
    assert _run("rm -rf reports/") == 0


def test_db_07b_rm_rf_venv_allowed():
    """DB-07b: rm -rf .venv/ (venv rebuild) → exit 0."""
    assert _run("rm -rf .venv/") == 0


def test_db_09_empty_input_allowed():
    """DB-09: Empty input → fail-open (exit 0)."""
    assert _run_empty() == 0


def test_db_10_skip_flag_bypasses():
    """DB-10: SKIP_DESTRUCTIVE_BASH_CHECK=1 → exit 0 regardless of command."""
    assert _run("git reset --hard HEAD", skip=True) == 0


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_git_clean_dry_run_long_flag_allowed():
    """git clean --dry-run → exit 0."""
    assert _run("git clean --dry-run") == 0


def test_rm_rf_runs_allowed():
    """rm -rf runs/ → exit 0."""
    assert _run("rm -rf runs/") == 0


def test_git_push_force_non_main_allowed():
    """git push --force to a feature branch → exit 0 (not main/master)."""
    assert _run("git push --force origin feature/my-branch") == 0


# New blocks: remote-ref resets, HEAD~N, SHA resets (TC-GIT-002)

def test_reset_origin_head_blocked():
    assert _run("git reset origin/HEAD") == 2

def test_reset_origin_main_blocked():
    assert _run("git reset origin/main") == 2

def test_reset_refs_remotes_blocked():
    assert _run("git reset refs/remotes/origin/main") == 2

def test_reset_head_tilde_blocked():
    assert _run("git reset HEAD~1") == 2

def test_reset_head_caret_blocked():
    assert _run("git reset HEAD^") == 2

def test_reset_sha_no_file_blocked():
    assert _run("git reset abc1234abc1234") == 2


# Blanket git-reset prohibition (TC-GIT-003, 2026-07-15): the `-- <file>`
# exemption is gone -- no form of git reset is allowed via the Bash tool
# anymore, closing the gap that let a concurrent-session `git reset` empty a
# commit's index mid-hook and push an empty commit to main (b860c6fb92).

def test_db_05_git_reset_hard_specific_file_blocked():
    """DB-05: git reset --hard -- content/foo.md (specific file) → exit 2."""
    assert _run("git reset --hard -- content/foo.md") == 2

def test_reset_origin_file_blocked():
    assert _run("git reset origin/main -- content/foo.md") == 2

def test_reset_sha_file_blocked():
    assert _run("git reset abc1234 -- content/foo.md") == 2

def test_reset_head_blocked():
    assert _run("git reset HEAD") == 2

def test_reset_head_file_blocked():
    assert _run("git reset HEAD -- content/foo.md") == 2

def test_reset_bare_blocked():
    """Bare `git reset` (no args) -- the exact form that caused b860c6fb92."""
    assert _run("git reset") == 2

def test_reset_mixed_blocked():
    assert _run("git reset --mixed") == 2

def test_reset_soft_blocked():
    assert _run("git reset --soft") == 2

def test_reset_soft_head_blocked():
    assert _run("git reset --soft HEAD") == 2


# New blocks: hugo relative-public destination (TC-HUGO-03)

def test_db_11_hugo_d_public_relative_blocked():
    """DB-11: hugo -d public-whatever/ -> exit 2."""
    assert _run("hugo --config configs/x.toml -d public-whatever/ --quiet") == 2


def test_db_12_hugo_destination_public_iv_blocked():
    """DB-12: hugo --destination public-iv-docs/ -> exit 2."""
    assert _run("hugo --config configs/x.toml --destination public-iv-docs/") == 2


def test_db_13_hugo_d_public_slash_blocked():
    """DB-13: hugo -d public/ -> exit 2 (bare public/ is also blocked)."""
    assert _run("hugo --config configs/x.toml -d public/ --quiet") == 2


def test_db_14_hugo_server_no_d_allowed():
    """DB-14: hugo server (no -d flag) -> exit 0."""
    assert _run("hugo server --config configs/x.toml") == 0


def test_db_15_hugo_d_tmp_allowed():
    """DB-15: hugo -d /tmp/hugo-out -> exit 0 (absolute temp path)."""
    assert _run("hugo --config configs/x.toml -d /tmp/hugo-out --quiet") == 0


def test_db_16_hugo_d_mktemp_subshell_allowed():
    """DB-16: hugo -d $(mktemp -d) -> exit 0 (subshell literal, not public*)."""
    assert _run("hugo --config configs/x.toml -d $(mktemp -d) --quiet") == 0

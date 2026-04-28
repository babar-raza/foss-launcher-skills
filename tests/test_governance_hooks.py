"""TC-GOV-14: Governance hook test harness.

Baseline tests for all 8 PreToolUse hooks + commit-msg hook + regression suite.
These tests run each hook via subprocess with controlled CLAUDE_TOOL_INPUT and
assert expected exit codes.  They must pass BEFORE any hook behaviour is changed.

Regression suite (Section 14 of governance simplification plan):
- Destructive op blocking (git reset --hard -> exit 2)
- reports/ boundary (gitignored)
- --no-verify absence in executable code
- git push absence in pipeline/translator/ci scripts
- Installed hooks match source scripts
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run_hook(hook_rel: str, payload: dict | None, *, env_overrides: dict | None = None) -> int:
    """Run a hook script with optional JSON payload; return exit code."""
    env = dict(os.environ)
    # Clear any session-level bypass flags that might interfere
    for key in list(env.keys()):
        if key.startswith("SKIP_") or key.startswith("GOV_"):
            del env[key]
    env.pop("CLAUDE_TOOL_INPUT", None)
    env.pop("SESSION_GATE_OVERRIDE", None)

    if payload is not None:
        env["CLAUDE_TOOL_INPUT"] = json.dumps(payload)

    if env_overrides:
        env.update(env_overrides)

    result = subprocess.run(
        [_BASH, hook_rel],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode


def _run_hook_output(hook_rel: str, payload: dict | None, *, env_overrides: dict | None = None) -> tuple[int, str, str]:
    """Run a hook script; return (exit_code, stdout, stderr)."""
    env = dict(os.environ)
    for key in list(env.keys()):
        if key.startswith("SKIP_") or key.startswith("GOV_"):
            del env[key]
    env.pop("CLAUDE_TOOL_INPUT", None)
    env.pop("SESSION_GATE_OVERRIDE", None)

    if payload is not None:
        env["CLAUDE_TOOL_INPUT"] = json.dumps(payload)

    if env_overrides:
        env.update(env_overrides)

    result = subprocess.run(
        [_BASH, hook_rel],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Session gate helper: many hooks need the gate file to exist
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _session_gate_override(tmp_path):
    """Redirect session gate to a temp file so tests don't depend on .claude/.agents_read."""
    gate_file = tmp_path / "agents_read"
    gate_file.touch()
    os.environ["SESSION_GATE_OVERRIDE"] = str(gate_file)
    yield
    os.environ.pop("SESSION_GATE_OVERRIDE", None)


# =========================================================================
# 1. check_session_gate.sh
# =========================================================================

_SESSION_GATE = "scripts/ci/check_session_gate.sh"


class TestSessionGate:
    def test_read_tool_exempt(self):
        """Read tool is always allowed even without gate file."""
        payload = {"tool_name": "Read", "tool_input": {"file_path": "AGENTS.md"}}
        code = _run_hook(_SESSION_GATE, payload)
        assert code == 0

    def test_edit_blocked_without_gate(self, tmp_path):
        """Edit tool blocked when session not bootstrapped."""
        gate = tmp_path / "no_gate"
        # Don't create the file — gate is missing
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "scripts/ci/test.sh"}}
        code = _run_hook(_SESSION_GATE, payload,
                         env_overrides={"SESSION_GATE_OVERRIDE": str(gate)})
        assert code == 2

    def test_edit_allowed_with_gate(self, tmp_path):
        """Edit tool allowed when gate file exists."""
        gate = tmp_path / "gate_exists"
        gate.touch()
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "scripts/ci/test.sh"}}
        code = _run_hook(_SESSION_GATE, payload,
                         env_overrides={"SESSION_GATE_OVERRIDE": str(gate)})
        assert code == 0

    def test_bootstrap_command_exempt(self, tmp_path):
        """Bootstrap command is exempt even without gate file."""
        gate = tmp_path / "no_gate"
        payload = {"tool_name": "Bash", "tool_input": {"command": "bash scripts/ci/bootstrap_session_gate.sh"}}
        code = _run_hook(_SESSION_GATE, payload,
                         env_overrides={"SESSION_GATE_OVERRIDE": str(gate)})
        assert code == 0

    def test_empty_input_failopen(self):
        """Empty input -> fail-open (exit 0) to prevent bootstrap deadlock."""
        code = _run_hook(_SESSION_GATE, None)
        assert code == 0

    def test_skip_bypass(self, tmp_path):
        """SKIP_SESSION_GATE_CHECK=1 bypasses all checks."""
        gate = tmp_path / "no_gate"
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "content/foo.md"}}
        code = _run_hook(_SESSION_GATE, payload,
                         env_overrides={"SESSION_GATE_OVERRIDE": str(gate),
                                        "SKIP_SESSION_GATE_CHECK": "1"})
        assert code == 0


# =========================================================================
# 2. check_content_edit_hook.sh
# =========================================================================

_CONTENT_EDIT = "scripts/ci/check_content_edit_hook.sh"


class TestContentEditHook:
    def test_content_path_blocked(self):
        """Edit on content/ file is blocked (requires S-73)."""
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "content/docs.aspose.org/en/cells/net/index.md"}}
        code = _run_hook(_CONTENT_EDIT, payload)
        assert code == 2

    def test_non_content_path_allowed(self):
        """Edit on non-content path is allowed."""
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "scripts/ci/test.sh"}}
        code = _run_hook(_CONTENT_EDIT, payload)
        assert code == 0

    def test_skip_bypass(self):
        """SKIP_CONTENT_EDIT_CHECK=1 allows content edits."""
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "content/docs.aspose.org/en/cells/net/index.md"}}
        code = _run_hook(_CONTENT_EDIT, payload,
                         env_overrides={"SKIP_CONTENT_EDIT_CHECK": "1"})
        assert code == 0

    def test_empty_input_failclosed(self):
        """Empty input -> fail-closed (exit 2)."""
        code = _run_hook(_CONTENT_EDIT, None)
        assert code == 2


# =========================================================================
# 3. check_skill_context_hook.sh
# =========================================================================

_SKILL_CONTEXT = "scripts/ci/check_skill_context_hook.sh"


class TestSkillContextHook:
    def test_ungoverned_reports_allowed(self):
        """reports/ path is ungoverned -> always allowed."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "reports/test.txt"}}
        code = _run_hook(_SKILL_CONTEXT, payload)
        assert code == 0

    def test_ungoverned_tests_allowed(self):
        """tests/ path is ungoverned -> always allowed."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "tests/test_foo.py"}}
        code = _run_hook(_SKILL_CONTEXT, payload)
        assert code == 0

    def test_governed_content_blocked_no_context(self):
        """content/ path blocked when no ACTIVE.json skill context exists."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "content/docs.aspose.org/en/cells/net/index.md"}}
        code = _run_hook(_SKILL_CONTEXT, payload)
        assert code == 2

    def test_skip_bypass(self):
        """SKIP_SKILL_CONTEXT_CHECK=1 allows governed path edits."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "content/docs.aspose.org/en/cells/net/index.md"}}
        code = _run_hook(_SKILL_CONTEXT, payload,
                         env_overrides={"SKIP_SKILL_CONTEXT_CHECK": "1"})
        assert code == 0

    def test_empty_input_failclosed(self):
        """Empty input -> fail-closed (exit 2)."""
        code = _run_hook(_SKILL_CONTEXT, None)
        assert code == 2


# =========================================================================
# 4. check_write_path_hook.sh
# =========================================================================

_WRITE_PATH = "scripts/ci/check_write_path_hook.sh"


class TestWritePathHook:
    def test_allowed_path(self):
        """docs/ path is allowed by path_guard."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "docs/test.md"}}
        code = _run_hook(_WRITE_PATH, payload)
        assert code == 0

    def test_root_file_blocked(self):
        """Root-level file creation is blocked."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "NEWFILE.txt"}}
        code = _run_hook(_WRITE_PATH, payload)
        assert code == 2

    def test_empty_input_failclosed(self):
        """Empty input -> fail-closed (exit 2)."""
        code = _run_hook(_WRITE_PATH, None)
        assert code == 2


# =========================================================================
# 5. check_content_write_hook.sh
# =========================================================================

_CONTENT_WRITE = "scripts/ci/check_content_write_hook.sh"


class TestContentWriteHook:
    def test_non_content_allowed(self):
        """Non-content path is always allowed."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "scripts/ci/test.sh"}}
        code = _run_hook(_CONTENT_WRITE, payload)
        assert code == 0

    def test_content_blocked_no_marker(self):
        """Content path blocked when S-23 marker is absent."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "content/docs.aspose.org/en/cells/net/_test_no_marker.md"}}
        code = _run_hook(_CONTENT_WRITE, payload)
        assert code == 2

    def test_skip_bypass(self):
        """SKIP_CONTENT_WRITE_CHECK=1 bypasses marker check."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "content/docs.aspose.org/en/cells/net/_test.md"}}
        code = _run_hook(_CONTENT_WRITE, payload,
                         env_overrides={"SKIP_CONTENT_WRITE_CHECK": "1"})
        assert code == 0

    def test_empty_input_failclosed(self):
        """Empty input -> fail-closed (exit 2)."""
        code = _run_hook(_CONTENT_WRITE, None)
        assert code == 2


# =========================================================================
# 6. check_py_write_hook.sh
# =========================================================================

_PY_WRITE = "scripts/ci/check_py_write_hook.sh"


class TestPyWriteHook:
    def test_non_py_allowed(self):
        """Non-.py file is always allowed."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "docs/test.md"}}
        code = _run_hook(_PY_WRITE, payload)
        assert code == 0

    def test_sanctioned_location_allowed(self):
        """Python file in scripts/ci/ (sanctioned) is allowed."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "scripts/ci/test_helper.py"}}
        code = _run_hook(_PY_WRITE, payload)
        assert code == 0

    def test_skip_bypass(self):
        """SKIP_PY_PLACEMENT_CHECK=1 allows any .py write."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "bad_location.py"}}
        code = _run_hook(_PY_WRITE, payload,
                         env_overrides={"SKIP_PY_PLACEMENT_CHECK": "1"})
        assert code == 0

    def test_empty_input_failclosed(self):
        """Empty input -> fail-closed (exit 2)."""
        code = _run_hook(_PY_WRITE, None)
        assert code == 2


# =========================================================================
# 7. check_venv_bash_hook.sh
# =========================================================================

_VENV_BASH = "scripts/ci/check_venv_bash_hook.sh"


class TestVenvBashHook:
    def test_venv_python_allowed(self):
        """Venv-prefixed python is allowed."""
        payload = {"tool_name": "Bash", "tool_input": {"command": ".venv/Scripts/python script.py"}}
        code = _run_hook(_VENV_BASH, payload)
        assert code == 0

    def test_bare_python_blocked(self):
        """Bare python invocation is blocked."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "python script.py"}}
        code = _run_hook(_VENV_BASH, payload)
        assert code == 2

    def test_python_venv_bootstrap_exempt(self):
        """python -m venv is exempt (bootstrap)."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "python -m venv .venv"}}
        code = _run_hook(_VENV_BASH, payload)
        assert code == 0

    def test_python_version_exempt(self):
        """python --version is exempt (diagnostic)."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "python --version"}}
        code = _run_hook(_VENV_BASH, payload)
        assert code == 0

    def test_empty_input_failopen(self):
        """Empty input -> fail-open (exit 0)."""
        code = _run_hook(_VENV_BASH, None)
        assert code == 0

    def test_non_python_allowed(self):
        """Non-python command is allowed."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        code = _run_hook(_VENV_BASH, payload)
        assert code == 0


# =========================================================================
# 8. check_destructive_bash_hook.sh
# =========================================================================

_DESTRUCTIVE = "scripts/ci/check_destructive_bash_hook.sh"


class TestDestructiveBashHook:
    def test_git_reset_hard_blocked(self):
        """git reset --hard HEAD -> exit 2."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 2

    def test_git_push_force_main_blocked(self):
        """git push --force origin main -> exit 2."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 2

    def test_git_clean_f_blocked(self):
        """git clean -f -> exit 2."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git clean -f"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 2

    def test_rm_rf_root_blocked(self):
        """rm -rf / -> exit 2."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 2

    def test_git_reset_hard_specific_file_allowed(self):
        """git reset --hard -- <file> -> exit 0."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git reset --hard -- content/foo.md"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 0

    def test_force_with_lease_allowed(self):
        """git push --force-with-lease -> exit 0."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 0

    def test_rm_rf_reports_allowed(self):
        """rm -rf reports/ -> exit 0 (expendable dir)."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "rm -rf reports/"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 0

    def test_empty_input_failopen(self):
        """Empty input -> fail-open (exit 0)."""
        code = _run_hook(_DESTRUCTIVE, None)
        assert code == 0

    def test_skip_bypass(self):
        """SKIP_DESTRUCTIVE_BASH_CHECK=1 -> exit 0 regardless."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD"}}
        code = _run_hook(_DESTRUCTIVE, payload,
                         env_overrides={"SKIP_DESTRUCTIVE_BASH_CHECK": "1"})
        assert code == 0


# =========================================================================
# 9. commit-msg-skills.sh (baseline: block without Skills invoked:)
# =========================================================================

_COMMIT_MSG = "scripts/commit-msg-skills.sh"


class TestCommitMsgSkills:
    """Baseline tests for commit-msg hook.

    These tests create a temporary commit message file and simulate having
    content staged. The hook reads $1 (message file) and checks git diff --cached.
    Since we cannot easily fake git diff --cached in a subprocess test, we test
    the non-content path (exit 0 at line 11) and the message-file-missing path.
    """

    def test_no_message_file_exits_0(self):
        """No commit message file -> exit 0."""
        env = dict(os.environ)
        for key in list(env.keys()):
            if key.startswith("SKIP_") or key.startswith("GOV_"):
                del env[key]
        result = subprocess.run(
            [_BASH, _COMMIT_MSG],
            env=env,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_empty_message_file_arg(self):
        """Empty string as $1 -> exit 0 (line 14-16: empty or not-a-file)."""
        env = dict(os.environ)
        for key in list(env.keys()):
            if key.startswith("SKIP_") or key.startswith("GOV_"):
                del env[key]
        result = subprocess.run(
            [_BASH, _COMMIT_MSG, ""],
            env=env,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0


# =========================================================================
# 10. Regression suite
# =========================================================================

class TestRegressionSuite:
    """Must-preserve regression tests from Section 14."""

    def test_no_no_verify_in_scripts(self):
        """Regression #11: --no-verify must not appear in executable scripts."""
        result = subprocess.run(
            [_BASH, "-c",
             "grep -rn '\\-\\-no-verify' scripts/ --include='*.sh' --include='*.py' || true"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        # Should find 0 hits in executable code
        assert result.stdout.strip() == "", (
            f"Found --no-verify in scripts: {result.stdout.strip()}"
        )

    def test_no_no_verify_in_commands(self):
        """--no-verify in .claude/commands/ must only appear in documentation/prohibition context.

        We verify no .sh or .py scripts in .claude/commands/ contain --no-verify
        (executable usage). Markdown documentation that prohibits it is expected.
        """
        result = subprocess.run(
            [_BASH, "-c",
             "grep -rn '\\-\\-no-verify' .claude/commands/ --include='*.sh' --include='*.py' || true"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.stdout.strip() == "", (
            f"Found --no-verify in executable command scripts: {result.stdout.strip()}"
        )

    def test_no_git_push_in_pipeline_scripts(self):
        """Regression #12: No automated git push in pipeline/translator/ci scripts."""
        result = subprocess.run(
            [_BASH, "-c",
             "grep -rn 'git push' scripts/pipeline/ scripts/translator/ scripts/ci/ "
             "--include='*.sh' --include='*.py' || true"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        # Should find 0 executable hits (test files excluded by path, hook blocks are ok)
        lines = [l for l in result.stdout.strip().splitlines()
                 if l and "/tests/" not in l and "check_destructive" not in l]
        assert len(lines) == 0, (
            f"Found git push in pipeline/translator/ci scripts: {lines}"
        )

    def test_reports_gitignored(self):
        """Regression #5: reports/ is gitignored."""
        result = subprocess.run(
            [_BASH, "-c", "git check-ignore reports/test.txt"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, "reports/ is not gitignored"

    def test_installed_hooks_match_source(self):
        """Regression #13: Installed git hooks should match source scripts."""
        hooks_to_check = [
            ("scripts/pre-commit-audit.sh", ".git/hooks/pre-commit"),
            ("scripts/commit-msg-skills.sh", ".git/hooks/commit-msg"),
        ]
        for source, installed in hooks_to_check:
            source_path = _REPO_ROOT / source
            installed_path = _REPO_ROOT / installed
            if not installed_path.exists():
                pytest.skip(f"Installed hook {installed} not found (hooks may not be installed)")
            if not source_path.exists():
                pytest.skip(f"Source script {source} not found")
            # Compare content (ignoring trailing whitespace differences)
            source_content = source_path.read_text().strip()
            installed_content = installed_path.read_text().strip()
            assert source_content == installed_content, (
                f"Installed hook {installed} differs from source {source}. "
                f"Run: bash scripts/install-hooks.sh"
            )

    def test_destructive_hook_blocks_reset_hard(self):
        """Regression #1: Destructive hook must block git reset --hard."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}}
        code = _run_hook(_DESTRUCTIVE, payload)
        assert code == 2

    def test_write_path_blocks_agents_md(self):
        """Regression: Write to AGENTS.md (root governance file) is blocked."""
        payload = {"tool_name": "Write", "tool_input": {"file_path": "AGENTS.md"}}
        code = _run_hook(_WRITE_PATH, payload)
        assert code == 2

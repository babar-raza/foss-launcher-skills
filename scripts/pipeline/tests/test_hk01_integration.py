"""HK-01 TC-HK01-4 — Block→HEAL_HINT→route→resolve integration tests.

Demonstrates the full healing chain:
  1. A hook script blocks and emits a HEAL_HINT: line on stderr.
  2. The agent parses the HEAL_HINT JSON from that line.
  3. route_from_hint() looks up the violation type in the dispatch table.
  4. resolve_hint() returns a typed HintResolution the controller can execute.

Two test classes:
  - TestParseAndRoute: unit tests for the parse→route→resolve path across all
    6 violation types using simulated hook stderr.
  - TestE2eHookEmitsHealHint: runs the real check_py_write_hook.sh subprocess
    and verifies it emits a parseable HEAL_HINT: line on a block.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from heal_controller import HintResolution, resolve_hint, route_from_hint

# ---------------------------------------------------------------------------
# Helper: parse HEAL_HINT line from simulated stderr
# ---------------------------------------------------------------------------

_HEAL_HINT_PREFIX = "HEAL_HINT: "


def parse_heal_hint(stderr: str) -> dict:
    """Extract and parse the first HEAL_HINT JSON dict from stderr text."""
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped.startswith(_HEAL_HINT_PREFIX):
            return json.loads(stripped[len(_HEAL_HINT_PREFIX):])
    raise ValueError(f"No HEAL_HINT line found in stderr:\n{stderr}")


# ---------------------------------------------------------------------------
# Simulated hook stderr for each violation type
# ---------------------------------------------------------------------------

_SIMULATED_STDERR = {
    "forbidden_path": (
        "⛔ Write blocked: root.md\n"
        "   Reason: path not in allowlist\n"
        'HEAL_HINT: {"violation_type": "forbidden_path", "path": "root.md",'
        ' "reason": "path not in allowlist",'
        ' "unblock_condition": "move to an allowlisted path or use override_manager.py create"}'
    ),
    "no_active_context": (
        "⛔ Edit/Write blocked: No active skill context.\n"
        'HEAL_HINT: {"violation_type": "no_active_context",'
        ' "unblock_condition": "run skill_context.py begin --skill S-xx --scope \\"*\\""}'
    ),
    "missing_skill_context": (
        "⛔ Edit/Write blocked: Path not covered by active skill context.\n"
        'HEAL_HINT: {"violation_type": "missing_skill_context",'
        ' "suggested_skill": "S-21", "path": "content/foo.md",'
        ' "unblock_condition": "widen scope: skill_context.py begin --skill S-21 --scope \\"content/*\\""}'
    ),
    "missing_manual_edit_skill": (
        "⛔ Direct Edit on content file blocked by governance hook.\n"
        'HEAL_HINT: {"violation_type": "missing_manual_edit_skill",'
        ' "unblock_condition": "invoke /manual-edit (S-73)"}'
    ),
    "missing_content_check_pass": (
        "⛔ Write blocked: content-check (S-23) not passed.\n"
        'HEAL_HINT: {"violation_type": "missing_content_check_pass",'
        ' "path": "content/docs/foo.md",'
        ' "unblock_condition": "run /content-check (S-23) on this file"}'
    ),
    "unsanctioned_py_location": (
        "⛔ Write blocked: bad.py is not in a sanctioned location.\n"
        'HEAL_HINT: {"violation_type": "unsanctioned_py_location",'
        ' "path": "bad.py",'
        ' "unblock_condition": "move .py file to a sanctioned location"}'
    ),
}


# ---------------------------------------------------------------------------
# Unit tests: parse → route → resolve
# ---------------------------------------------------------------------------

class TestParseAndRoute:
    """Full chain: parse simulated HEAL_HINT → route → resolve."""

    def _chain(self, vtype: str) -> tuple[dict, dict, HintResolution]:
        stderr = _SIMULATED_STDERR[vtype]
        hint = parse_heal_hint(stderr)
        route = route_from_hint(hint)
        resolution = resolve_hint(hint)
        return hint, route, resolution

    def test_forbidden_path_resolves_run_command(self):
        hint, route, res = self._chain("forbidden_path")
        assert hint["violation_type"] == "forbidden_path"
        assert route["action"] == "run_command"
        assert route["resolved"] is True
        assert res.action == "run_command"
        assert "override_manager.py" in res.run_argv[0]

    def test_no_active_context_resolves_run_command(self):
        hint, route, res = self._chain("no_active_context")
        assert route["action"] == "run_command"
        assert res.action == "run_command"
        assert "skill_context.py" in res.run_argv[0]

    def test_missing_skill_context_resolves_run_command(self):
        hint, route, res = self._chain("missing_skill_context")
        assert route["action"] == "run_command"
        assert res.action == "run_command"
        assert "skill_context.py" in res.run_argv[0]

    def test_missing_manual_edit_skill_resolves_invoke_skill(self):
        hint, route, res = self._chain("missing_manual_edit_skill")
        assert route["action"] == "invoke_skill"
        assert res.action == "invoke_skill"
        assert res.skill_name == "/manual-edit"

    def test_missing_content_check_pass_resolves_invoke_skill(self):
        hint, route, res = self._chain("missing_content_check_pass")
        assert route["action"] == "invoke_skill"
        assert res.action == "invoke_skill"
        assert res.skill_name == "/content-check"

    def test_unsanctioned_py_location_resolves_escalate(self):
        hint, route, res = self._chain("unsanctioned_py_location")
        assert route["action"] == "escalate"
        assert res.action == "escalate"
        assert res.escalation_msg != ""

    def test_unknown_violation_type_escalates_unresolved(self):
        hint = {"violation_type": "totally_unknown_type"}
        route = route_from_hint(hint)
        res = resolve_hint(hint)
        assert route["resolved"] is False
        assert res.action == "escalate"
        assert res.resolved is False


# ---------------------------------------------------------------------------
# E2E test: run real hook → verify HEAL_HINT on stderr
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK_REL = "scripts/ci/check_py_write_hook.sh"
_HOOK = _REPO_ROOT / "scripts" / "ci" / "check_py_write_hook.sh"
_BASH = shutil.which("bash") or "bash"


@pytest.mark.skipif(
    not _HOOK.exists(),
    reason="check_py_write_hook.sh not found — skipping E2E hook test",
)
class TestE2eHookEmitsHealHint:
    """Run check_py_write_hook.sh with a path that triggers the block and verify
    that the HEAL_HINT: line is present and parseable."""

    def _run_hook(self, rel_file_path: str) -> subprocess.CompletedProcess:
        """Run the hook with a repo-relative file path (forward slashes).

        Passes tool input via CLAUDE_TOOL_INPUT env var — the hook reads this
        before falling back to stdin, avoiding stdin-pipe encoding issues on Windows.
        """
        import os
        tool_input = json.dumps({"tool_input": {"file_path": rel_file_path}})
        env = {**os.environ, "SKIP_PY_PLACEMENT_CHECK": "0", "CLAUDE_TOOL_INPUT": tool_input}
        return subprocess.run(
            [_BASH, _HOOK_REL],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            env=env,
        )

    def test_unsanctioned_py_emits_heal_hint(self):
        """A .py file at root triggers block; stderr must contain parseable HEAL_HINT."""
        result = self._run_hook("unsanctioned_root.py")
        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}\n{result.stderr}"
        hint = parse_heal_hint(result.stderr)
        assert hint["violation_type"] == "unsanctioned_py_location"
        # Full chain: route + resolve must also work on the real hint
        route = route_from_hint(hint)
        res = resolve_hint(hint)
        assert route["resolved"] is True
        assert res.action == "escalate"

    def test_sanctioned_py_is_allowed(self):
        """A .py file inside scripts/pipeline/ must NOT trigger a block."""
        result = self._run_hook("scripts/pipeline/heal_controller.py")
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\n{result.stderr}"

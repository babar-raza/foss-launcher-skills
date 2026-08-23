"""Tests for scripts/ci/hooks/check_ledger_init_hook.sh.

Mission plan: mission-plan-the-end-to-end-vast-hejlsberg.md, Task 24 (closes
G16 part 1). Covers: cheap-path no-op when a manifest already exists, cold-path
real init when absent, always-exit-0 (fail-open) regardless of outcome, and
the LEDGER_INIT_HOOK_REPO_ROOT_OVERRIDE test-isolation seam.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK_REL = "scripts/ci/hooks/check_ledger_init_hook.sh"


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run(tmp_root: Path, *, session_id: str | None, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Clear real identity env vars so the real harness session running this
    # test suite can never leak into what the hook resolves.
    env.pop("AGENT_SESSION_ID", None)
    env.pop("CODEX_THREAD_ID", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    if session_id is not None:
        env["AGENT_SESSION_ID"] = session_id
    # Forward-slash normalize: Git Bash/MSYS chokes on raw Windows backslash
    # paths (backslash is bash's escape char) -- same convention already used
    # by check_content_edit_hook.sh's own FILE_PATH normalization.
    env["LEDGER_INIT_HOOK_REPO_ROOT_OVERRIDE"] = str(tmp_root).replace("\\", "/")
    env.pop("SKIP_LEDGER_INIT_CHECK", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [_BASH, _HOOK_REL],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input="{}",
    )


def test_cold_path_creates_manifest(tmp_path):
    """First call this session: no manifest exists yet -> hook must create one."""
    manifest_path = tmp_path / "reports" / "session-state" / "test-hook-001.json"
    assert not manifest_path.exists()

    result = _run(tmp_path, session_id="test-hook-001")

    assert result.returncode == 0
    assert manifest_path.is_file(), f"expected manifest at {manifest_path}, stderr={result.stderr!r}"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["session_id"] == "test-hook-001"
    assert "dirty_at_start" in data


def test_cheap_path_is_noop_when_manifest_exists(tmp_path):
    """Second call this session: manifest already exists -> hook must not
    touch it again (proves the fast, subprocess-free path is taken)."""
    manifest_dir = tmp_path / "reports" / "session-state"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "test-hook-002.json"
    sentinel = {"session_id": "test-hook-002", "touched_files": {"marker": "untouched"}}
    manifest_path.write_text(json.dumps(sentinel), encoding="utf-8")

    result = _run(tmp_path, session_id="test-hook-002")

    assert result.returncode == 0
    # Content must be byte-for-byte unchanged -- the hook took the cheap
    # existence-check path and never invoked session_ledger.py at all.
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == sentinel


def test_no_resolvable_session_id_is_fail_open(tmp_path):
    """No AGENT_SESSION_ID/CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID at all ->
    hook must still exit 0 (never blocks the edit it's guarding)."""
    result = _run(tmp_path, session_id=None)
    assert result.returncode == 0


def test_skip_env_var_bypasses_entirely(tmp_path):
    manifest_path = tmp_path / "reports" / "session-state" / "test-hook-003.json"
    result = _run(tmp_path, session_id="test-hook-003", env_overrides={"SKIP_LEDGER_INIT_CHECK": "1"})
    assert result.returncode == 0
    assert not manifest_path.exists()


def test_always_exits_zero_even_with_broken_repo_root(tmp_path):
    """A repo-root override pointing at a location session_ledger.py cannot
    sensibly operate against must still never block the edit (fail-open)."""
    broken_root = tmp_path / "does-not-exist-as-a-real-tree"
    result = subprocess.run(
        [_BASH, _HOOK_REL],
        env={
            **{k: v for k, v in os.environ.items() if k not in
               ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID")},
            "AGENT_SESSION_ID": "test-hook-broken",
            "LEDGER_INIT_HOOK_REPO_ROOT_OVERRIDE": str(broken_root).replace("\\", "/"),
        },
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input="{}",
    )
    assert result.returncode == 0

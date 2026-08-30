"""Tests for the session-lifecycle ledger hooks (2026-08-30 stale-guard plan,
T6 / TC-SG-05): session_start_ledger_hook.sh (SessionStart: idempotent init at
TRUE session start, CLAUDE_ENV_FILE identity export, residue report),
session_end_ledger_hook.sh (SessionEnd: close), session_heartbeat_hook.sh
(Stop: mtime touch only, never close/create).

Invocation mirrors the sibling hook tests: run the bash script directly with
the payload on stdin, identity env popped for hermeticity, and the
PYTEST_CURRENT_TEST-gated SESSION_LEDGER_HOOK_ROOT_OVERRIDE seam pointing the
DATA root at a fixture (hook code always resolves from the real repo).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_HOOKS = _REPO_ROOT / "scripts" / "ci" / "hooks"


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _fixture_root(tmp_path: Path) -> Path:
    """A git repo as the DATA root so init records a real base_commit_sha."""
    root = tmp_path / "data_root"
    root.mkdir()
    for args in (["init", "-q", "-b", "main"],
                 ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)
    (root / "seed.txt").write_text("s", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=str(root), check=True,
                   capture_output=True)
    return root


def _run_hook(name: str, root: Path, *, sid: "str | None", extra_env: "dict | None" = None,
              payload: "dict | None" = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID",
                        "CLAUDE_ENV_FILE", "SKIP_SESSION_LEDGER_HOOKS")}
    env["SESSION_LEDGER_HOOK_ROOT_OVERRIDE"] = str(root).replace("\\", "/")
    env.setdefault("PYTEST_CURRENT_TEST", "manual")
    if sid is not None:
        env["CLAUDE_CODE_SESSION_ID"] = sid
    env.update(extra_env or {})
    return subprocess.run(
        [_BASH, str(_HOOKS / name)],
        input=json.dumps(payload if payload is not None else {"session_id": sid or ""}),
        env=env, cwd=str(_REPO_ROOT), capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )


def _manifest(root: Path, sid: str) -> "dict | None":
    p = root / "reports" / "session-state" / f"{sid}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def test_session_start_creates_manifest_with_true_base(tmp_path):
    root = _fixture_root(tmp_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()

    result = _run_hook("session_start_ledger_hook.sh", root, sid="lc-start-1")

    assert result.returncode == 0
    manifest = _manifest(root, "lc-start-1")
    assert manifest is not None
    assert manifest["status"] == "active"
    assert manifest["base_commit_sha"] == head  # HEAD at SESSION START, not first edit


def test_session_start_is_idempotent(tmp_path):
    root = _fixture_root(tmp_path)
    _run_hook("session_start_ledger_hook.sh", root, sid="lc-idem")
    first = _manifest(root, "lc-idem")
    result = _run_hook("session_start_ledger_hook.sh", root, sid="lc-idem")
    assert result.returncode == 0
    second = _manifest(root, "lc-idem")
    assert second["started_at"] == first["started_at"]
    assert second["base_commit_sha"] == first["base_commit_sha"]


def test_resume_after_close_reopens_without_wiping(tmp_path):
    root = _fixture_root(tmp_path)
    _run_hook("session_start_ledger_hook.sh", root, sid="lc-resume")
    base = _manifest(root, "lc-resume")["base_commit_sha"]
    _run_hook("session_end_ledger_hook.sh", root, sid="lc-resume")
    assert _manifest(root, "lc-resume")["status"] == "closed"

    result = _run_hook("session_start_ledger_hook.sh", root, sid="lc-resume")

    assert result.returncode == 0
    manifest = _manifest(root, "lc-resume")
    assert manifest["status"] == "active"
    assert manifest["base_commit_sha"] == base   # older base kept (wider window = safe)
    assert "reopened_at" in manifest


def test_session_end_closes(tmp_path):
    root = _fixture_root(tmp_path)
    _run_hook("session_start_ledger_hook.sh", root, sid="lc-end")
    result = _run_hook("session_end_ledger_hook.sh", root, sid="lc-end")
    assert result.returncode == 0
    assert _manifest(root, "lc-end")["status"] == "closed"


def test_heartbeat_bumps_mtime_and_never_creates(tmp_path):
    root = _fixture_root(tmp_path)
    _run_hook("session_start_ledger_hook.sh", root, sid="lc-beat")
    manifest_path = root / "reports" / "session-state" / "lc-beat.json"
    before = manifest_path.stat().st_mtime_ns
    time.sleep(0.05)

    result = _run_hook("session_heartbeat_hook.sh", root, sid="lc-beat")
    assert result.returncode == 0
    assert manifest_path.stat().st_mtime_ns >= before
    content = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert content["status"] == "active"        # touch only, no rewrite

    # Never creates: a heartbeat for an unknown session leaves nothing behind.
    result2 = _run_hook("session_heartbeat_hook.sh", root, sid="lc-never-inited")
    assert result2.returncode == 0
    assert _manifest(root, "lc-never-inited") is None


def test_no_identity_is_a_silent_noop(tmp_path):
    root = _fixture_root(tmp_path)
    for name in ("session_start_ledger_hook.sh", "session_end_ledger_hook.sh",
                 "session_heartbeat_hook.sh"):
        result = _run_hook(name, root, sid=None, payload={})
        assert result.returncode == 0, f"{name} must fail open with no identity"
    assert not (root / "reports" / "session-state").exists() or \
        not list((root / "reports" / "session-state").glob("*.json"))


def test_stdin_session_id_fallback_when_env_missing(tmp_path):
    root = _fixture_root(tmp_path)
    result = _run_hook("session_start_ledger_hook.sh", root, sid=None,
                       payload={"session_id": "lc-stdin-id", "hook_event_name": "SessionStart"})
    assert result.returncode == 0
    assert _manifest(root, "lc-stdin-id") is not None


def test_claude_env_file_gets_identity_export_only_when_unset(tmp_path):
    root = _fixture_root(tmp_path)
    env_file = tmp_path / "claude_env"
    env_file.write_text("", encoding="utf-8")

    _run_hook("session_start_ledger_hook.sh", root, sid="lc-envfile",
              extra_env={"CLAUDE_ENV_FILE": str(env_file)})
    assert 'export AGENT_SESSION_ID="lc-envfile"' in env_file.read_text(encoding="utf-8")

    env_file.write_text("", encoding="utf-8")
    _run_hook("session_start_ledger_hook.sh", root, sid="lc-envfile",
              extra_env={"CLAUDE_ENV_FILE": str(env_file),
                         "AGENT_SESSION_ID": "already-set"})
    assert env_file.read_text(encoding="utf-8") == ""  # a DIFFERENT value would split identity

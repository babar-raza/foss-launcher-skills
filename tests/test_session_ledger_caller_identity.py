"""Tests for session_ledger.py's caller_identity field (added 2026-08-29
alongside the session_identity.py port). Scoped narrowly to this addition --
session_ledger.py had no pre-existing test coverage in this repo before this
sync; a full retroactive test suite for its pre-existing behavior is out of
scope for this change and is filed separately (see TASK_BACKLOG.md)."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"))

import session_ledger  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_session_ledger(tmp_path, monkeypatch):
    """Point session_ledger at an isolated repo root for every test, and
    reset to defaults afterward so this test file can never leak state into
    others (matches this repo's autouse isolation convention)."""
    monkeypatch.chdir(tmp_path)
    session_ledger.configure(repo_root=tmp_path)
    yield tmp_path
    session_ledger.configure()


def _read_manifest(repo_root: Path, session_id: str) -> dict:
    manifest_path = repo_root / "reports" / "session-state" / f"{session_id}.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def test_init_session_records_caller_identity_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SESSION_ID", "caller-abc")
    sid = session_ledger.init_session()
    manifest = _read_manifest(tmp_path, sid)
    assert manifest["caller_identity"] == "caller-abc"


def test_init_session_caller_identity_is_none_when_no_env_set(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    sid = session_ledger.init_session()
    manifest = _read_manifest(tmp_path, sid)
    assert manifest["caller_identity"] is None


def test_init_session_still_generates_unique_ids_within_one_caller_identity(monkeypatch, tmp_path):
    """The key backward-compatibility guarantee: caller_identity is purely
    additive/informational. Two init() calls under the SAME resolved caller
    identity (e.g. two /commit invocations in one Claude Code conversation)
    must still get two DISTINCT session ledgers, not silently collide onto
    the same manifest file -- this is exactly the risk flagged in
    session_identity.py's own docstring about wiring identity into ID
    GENERATION rather than just recording it."""
    monkeypatch.setenv("AGENT_SESSION_ID", "same-caller")
    sid1 = session_ledger.init_session()
    sid2 = session_ledger.init_session()
    assert sid1 != sid2
    manifest1 = _read_manifest(tmp_path, sid1)
    manifest2 = _read_manifest(tmp_path, sid2)
    assert manifest1["caller_identity"] == "same-caller"
    assert manifest2["caller_identity"] == "same-caller"
    # First session should be closed, not silently overwritten
    assert manifest1["status"] == "closed"
    assert manifest2["status"] == "active"


def test_init_session_survives_broken_session_identity_module(monkeypatch, tmp_path):
    """caller_identity resolution must never break init_session() itself --
    it's best-effort and additive, not load-bearing."""
    def _boom():
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(session_ledger.session_identity, "resolve_sanitized", _boom)
    sid = session_ledger.init_session()
    manifest = _read_manifest(tmp_path, sid)
    assert manifest["caller_identity"] is None
    assert manifest["status"] == "active"

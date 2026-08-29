"""Tests for scripts/pipeline/lib/session_identity.py (ported 2026-08-29)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

import session_identity  # noqa: E402


def test_resolve_prefers_explicit(monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "env-agent")
    assert session_identity.resolve("explicit-id") == "explicit-id"


def test_resolve_prefers_agent_session_id_env(monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "env-agent")
    monkeypatch.setenv("CODEX_THREAD_ID", "env-codex")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "env-claude")
    assert session_identity.resolve() == "env-agent"


def test_resolve_falls_back_to_codex_thread_id(monkeypatch):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "env-codex")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "env-claude")
    assert session_identity.resolve() == "env-codex"


def test_resolve_falls_back_to_claude_code_session_id(monkeypatch):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "env-claude")
    assert session_identity.resolve() == "env-claude"


def test_resolve_returns_none_when_nothing_set(monkeypatch):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert session_identity.resolve() is None


def test_resolve_treats_blank_env_as_unset(monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "   ")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert session_identity.resolve() is None


def test_sanitize_strips_unsafe_characters():
    assert session_identity.sanitize("abc/def:ghi 123") == "abc-def-ghi-123"


def test_sanitize_preserves_alnum_dash_underscore():
    assert session_identity.sanitize("abc-DEF_123") == "abc-DEF_123"


def test_sanitize_truncates_to_max_len():
    long_value = "a" * 100
    assert len(session_identity.sanitize(long_value, max_len=10)) == 10


def test_resolve_sanitized_combines_resolve_and_sanitize(monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "weird id/with:chars")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert session_identity.resolve_sanitized() == "weird-id-with-chars"


def test_resolve_sanitized_returns_none_when_nothing_resolves(monkeypatch):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert session_identity.resolve_sanitized() is None

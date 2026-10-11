"""Tests for lib/session_identity.py (production concurrency redesign, 2026-08-01).

Extracted from skill_context.py's _derive_session_id (RC1/RC2 hardening,
2026-07-31) — see that module's docstring for full precedence rationale.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import session_identity  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_session_id_env(monkeypatch):
    """Keep tests hermetic against a live agent shell's exported identity and
    against CLAUDE_CODE_SESSION_ID, which is set by the real harness running
    this very test suite."""
    monkeypatch.delenv(session_identity.ENV_AGENT_SESSION_ID, raising=False)
    monkeypatch.delenv(session_identity.ENV_CODEX_THREAD_ID, raising=False)
    monkeypatch.delenv(session_identity.ENV_CLAUDE_CODE_SESSION_ID, raising=False)


class TestResolve:
    def test_no_source_returns_none(self):
        assert session_identity.resolve() is None

    def test_explicit_wins_over_everything(self, monkeypatch):
        monkeypatch.setenv(session_identity.ENV_AGENT_SESSION_ID, "agent-sess")
        monkeypatch.setenv(session_identity.ENV_CODEX_THREAD_ID, "codex-thread")
        monkeypatch.setenv(session_identity.ENV_CLAUDE_CODE_SESSION_ID, "conv-uuid")
        assert session_identity.resolve("explicit-id") == "explicit-id"

    def test_agent_session_id_wins_over_codex_and_claude(self, monkeypatch):
        monkeypatch.setenv(session_identity.ENV_AGENT_SESSION_ID, "agent-sess")
        monkeypatch.setenv(session_identity.ENV_CODEX_THREAD_ID, "codex-thread")
        monkeypatch.setenv(session_identity.ENV_CLAUDE_CODE_SESSION_ID, "conv-uuid")
        assert session_identity.resolve() == "agent-sess"

    def test_codex_thread_id_wins_over_claude_code_session_id(self, monkeypatch):
        monkeypatch.setenv(session_identity.ENV_CODEX_THREAD_ID, "codex-thread")
        monkeypatch.setenv(session_identity.ENV_CLAUDE_CODE_SESSION_ID, "conv-uuid")
        assert session_identity.resolve() == "codex-thread"

    def test_claude_code_session_id_is_last_resort(self, monkeypatch):
        monkeypatch.setenv(session_identity.ENV_CLAUDE_CODE_SESSION_ID, "conv-uuid")
        assert session_identity.resolve() == "conv-uuid"

    def test_empty_string_env_vars_are_treated_as_absent(self, monkeypatch):
        monkeypatch.setenv(session_identity.ENV_AGENT_SESSION_ID, "")
        monkeypatch.setenv(session_identity.ENV_CLAUDE_CODE_SESSION_ID, "conv-uuid")
        assert session_identity.resolve() == "conv-uuid"

    def test_whitespace_only_env_var_is_treated_as_absent(self, monkeypatch):
        monkeypatch.setenv(session_identity.ENV_AGENT_SESSION_ID, "   ")
        monkeypatch.setenv(session_identity.ENV_CLAUDE_CODE_SESSION_ID, "conv-uuid")
        assert session_identity.resolve() == "conv-uuid"


class TestSanitize:
    def test_alnum_passthrough(self):
        assert session_identity.sanitize("abc123") == "abc123"

    def test_hyphen_and_underscore_preserved(self):
        assert session_identity.sanitize("a-b_c") == "a-b_c"

    def test_other_chars_replaced_with_hyphen(self):
        assert session_identity.sanitize("thread/id with spaces") == "thread-id-with-spaces"

    def test_truncated_to_max_len(self):
        assert session_identity.sanitize("x" * 100, max_len=10) == "x" * 10


class TestResolveSanitized:
    def test_none_when_nothing_resolves(self):
        assert session_identity.resolve_sanitized() is None

    def test_sanitizes_the_resolved_value(self, monkeypatch):
        monkeypatch.setenv(session_identity.ENV_CODEX_THREAD_ID, "thread/id with spaces")
        assert session_identity.resolve_sanitized() == "thread-id-with-spaces"

    def test_explicit_value_is_also_sanitized(self):
        assert session_identity.resolve_sanitized("has spaces") == "has-spaces"

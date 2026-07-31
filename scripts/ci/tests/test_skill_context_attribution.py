"""Tests for scripts/ci/hooks/skill_context_attribution.py (HARDEN-A3/finding-3).

This logic previously lived inline as an untested 54-line Python heredoc
inside check_skill_context_hook.sh — reviewed and manually exercised during
HARDEN-A3, but with zero automated regression protection, unlike the sibling
check_commit_bash_hook.sh (40 tests). Extracted verbatim (same behavior) into
its own module so it can be tested directly, like the rest of this repo's
governance logic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import skill_context_attribution as sca  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_session_id_env(monkeypatch):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    # CLAUDE_CODE_SESSION_ID is set by the real harness running this very
    # test suite (RC1/RC2 hardening, 2026-07-31) — must be cleared here too
    # or these tests silently change behavior only when run inside an
    # actual Claude Code session.
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)


def _write(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def test_env_identity_resolves_matching_session_file(tmp_path, monkeypatch):
    """AGENT_SESSION_ID names a live per-session file -> that record wins,
    even if a legacy ACTIVE.json also exists (env identity is priority 1)."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "sess-abc.json", {"skill_id": "S-49"})
    _write(ctx / "ACTIVE.json", {"skill_id": "S-77"})  # should be ignored
    monkeypatch.setenv("AGENT_SESSION_ID", "sess-abc")

    result = sca.resolve_attribution(ctx)
    assert result == ("S-49", "sess-abc")


def test_env_identity_with_no_matching_file_falls_back_to_legacy(tmp_path, monkeypatch):
    """AGENT_SESSION_ID set but no active/<id>.json exists -> falls through to
    the legacy ACTIVE.json rather than resolving to nothing. The originally
    declared env identity is preserved as the session id (the legacy record
    itself carries none), so the touch still attributes to the right session
    rather than silently reverting to 'no session'."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "ACTIVE.json", {"skill_id": "S-77"})
    monkeypatch.setenv("AGENT_SESSION_ID", "sess-nonexistent")

    result = sca.resolve_attribution(ctx)
    assert result == ("S-77", "sess-nonexistent")


def test_codex_thread_id_resolves_when_agent_session_id_unset(tmp_path, monkeypatch):
    """RC1/RC2 hardening (2026-07-31): skill_context.py's own identity
    resolution already honored CODEX_THREAD_ID as tier 2 -- this file must
    match it, or a Codex caller's per-session context (written under its
    CODEX_THREAD_ID) would never be found here."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "codex-thread-1.json", {"skill_id": "S-49"})
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread-1")

    result = sca.resolve_attribution(ctx)
    assert result == ("S-49", "codex-thread-1")


def test_claude_code_session_id_resolves_as_last_resort(tmp_path, monkeypatch):
    """CLAUDE_CODE_SESSION_ID (RC1/RC2 hardening, 2026-07-31) is the harness's
    own per-conversation identifier, inherited automatically -- unlike
    AGENT_SESSION_ID/CODEX_THREAD_ID, which require the caller to set them.
    Since skill_context.py's cmd_begin/cmd_check now fall back to it too,
    most sessions land on the per-session path; this file must resolve the
    same identity or attribution falls through to the ambiguous tier-3 scan
    far more often than before this change."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "conv-uuid-1.json", {"skill_id": "S-73"})
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "conv-uuid-1")

    result = sca.resolve_attribution(ctx)
    assert result == ("S-73", "conv-uuid-1")


def test_agent_session_id_takes_precedence_over_the_other_two(tmp_path, monkeypatch):
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "sess-agent.json", {"skill_id": "S-20"})
    _write(ctx / "active" / "codex-thread-1.json", {"skill_id": "S-21"})
    _write(ctx / "active" / "conv-uuid-1.json", {"skill_id": "S-22"})
    monkeypatch.setenv("AGENT_SESSION_ID", "sess-agent")
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread-1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "conv-uuid-1")

    result = sca.resolve_attribution(ctx)
    assert result == ("S-20", "sess-agent")


def test_codex_thread_id_takes_precedence_over_claude_code_session_id(tmp_path, monkeypatch):
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "codex-thread-1.json", {"skill_id": "S-21"})
    _write(ctx / "active" / "conv-uuid-1.json", {"skill_id": "S-22"})
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread-1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "conv-uuid-1")

    result = sca.resolve_attribution(ctx)
    assert result == ("S-21", "codex-thread-1")


def test_legacy_active_json_carries_own_session_id(tmp_path):
    """A legacy ACTIVE.json that itself carries a session_id field surfaces
    that id, not an empty string."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "ACTIVE.json", {"skill_id": "S-23", "session_id": "legacy-sess"})

    result = sca.resolve_attribution(ctx)
    assert result == ("S-23", "legacy-sess")


def test_sole_live_session_file_used_when_no_env_and_no_legacy(tmp_path):
    """No env identity, no legacy ACTIVE.json, exactly one per-session file
    under active/ -> that file's stem is used as the session id (the
    single-concurrent-session common case)."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "sess-only.json", {"skill_id": "S-34"})

    result = sca.resolve_attribution(ctx)
    assert result == ("S-34", "sess-only")


def test_multiple_live_session_files_with_no_identity_is_unresolved(tmp_path):
    """Two or more per-session files and no identity given -> ambiguous;
    this best-effort recorder must NOT guess (unlike check_commit_bash_hook.sh's
    hard S-76 gate, this one simply records nothing rather than blocking)."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "sess-a.json", {"skill_id": "S-49"})
    _write(ctx / "active" / "sess-b.json", {"skill_id": "S-34"})

    result = sca.resolve_attribution(ctx)
    assert result is None


def test_no_context_anywhere_is_unresolved(tmp_path):
    ctx = tmp_path / "skill-context"
    assert sca.resolve_attribution(ctx) is None


def test_record_missing_skill_id_is_unresolved(tmp_path):
    """A context file exists but carries no skill_id — nothing to attribute."""
    ctx = tmp_path / "skill-context"
    _write(ctx / "ACTIVE.json", {"session_id": "sess-x"})

    assert sca.resolve_attribution(ctx) is None


def test_corrupt_json_is_treated_as_absent_not_a_crash(tmp_path, monkeypatch):
    """An unreadable/corrupt ACTIVE.json must not raise — falls through to
    'nothing resolves' just like a missing file."""
    ctx = tmp_path / "skill-context"
    (ctx).mkdir(parents=True)
    (ctx / "ACTIVE.json").write_text("{not valid json", encoding="utf-8")

    assert sca.resolve_attribution(ctx) is None


def test_corrupt_env_session_file_falls_back_to_legacy(tmp_path, monkeypatch):
    ctx = tmp_path / "skill-context"
    _write(ctx / "ACTIVE.json", {"skill_id": "S-77"})
    (ctx / "active").mkdir(parents=True)
    (ctx / "active" / "sess-x.json").write_text("{not valid", encoding="utf-8")
    monkeypatch.setenv("AGENT_SESSION_ID", "sess-x")

    assert sca.resolve_attribution(ctx) == ("S-77", "sess-x")


# ---------------------------------------------------------------------------
# CLI (main()) — output format used by the bash hook
# ---------------------------------------------------------------------------

def test_main_prints_tab_separated_skill_and_session(tmp_path, monkeypatch, capsys):
    ctx = tmp_path / "skill-context"
    _write(ctx / "active" / "sess-abc.json", {"skill_id": "S-49"})
    monkeypatch.setenv("AGENT_SESSION_ID", "sess-abc")

    rc = sca.main([str(ctx)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "S-49\tsess-abc"


def test_main_prints_nothing_when_unresolved(tmp_path, capsys):
    ctx = tmp_path / "skill-context"
    rc = sca.main([str(ctx)])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_main_with_no_args_is_a_no_op(capsys):
    """The hook always passes ctx_dir, but main() must not crash if invoked
    bare — this is a best-effort lookup, never a source of a hook failure."""
    rc = sca.main([])
    assert rc == 0
    assert capsys.readouterr().out == ""

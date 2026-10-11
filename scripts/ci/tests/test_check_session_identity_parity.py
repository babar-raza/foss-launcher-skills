"""test_check_session_identity_parity.py — Regression tests for
check_session_identity_parity.py (production concurrency redesign, 2026-08-01,
Step 2).

Covers the detection heuristic (all 3 identity env var names present, no
session_identity reference -> flagged) and, critically, runs the check
against this repo's own real scripts/ tree so a future hand-copied duplicate
is caught the same run this test suite runs, not only when someone remembers
to invoke the check by hand.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_session_identity_parity as parity  # noqa: E402


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_no_violation_when_session_identity_is_imported(tmp_path):
    _write(tmp_path / "consumer.py", """
import session_identity
AGENT_SESSION_ID = 1
CODEX_THREAD_ID = 2
CLAUDE_CODE_SESSION_ID = 3
""")
    assert parity.find_undelegated_files(tmp_path) == []


def test_violation_when_all_three_names_present_without_delegation(tmp_path):
    bad = tmp_path / "duplicate.py"
    _write(bad, """
import os
sid = (
    os.environ.get("AGENT_SESSION_ID", "")
    or os.environ.get("CODEX_THREAD_ID", "")
    or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
)
""")
    assert parity.find_undelegated_files(tmp_path) == [bad]


def test_no_violation_when_fewer_than_three_names_present(tmp_path):
    """Mirrors session_ledger.py's current (explicit > AGENT_SESSION_ID only)
    2-tier scheme -- an explicit, pending Step 3 decision, not a silent gap
    this check should flag."""
    _write(tmp_path / "two_tier.py", """
import os
sid = os.environ.get("AGENT_SESSION_ID", "")
""")
    assert parity.find_undelegated_files(tmp_path) == []


def test_test_files_are_excluded(tmp_path):
    _write(tmp_path / "test_duplicate.py", """
import os
sid = (
    os.environ.get("AGENT_SESSION_ID", "")
    or os.environ.get("CODEX_THREAD_ID", "")
    or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
)
""")
    assert parity.find_undelegated_files(tmp_path) == []


def test_tests_directory_is_excluded(tmp_path):
    _write(tmp_path / "tests" / "fixture_helper.py", """
AGENT_SESSION_ID = CODEX_THREAD_ID = CLAUDE_CODE_SESSION_ID = "x"
""")
    assert parity.find_undelegated_files(tmp_path) == []


def test_sh_file_with_inline_heredoc_delegation_passes(tmp_path):
    """check_commit_bash_hook.sh's own shape: a bash script whose embedded
    Python heredoc both defines the env var names and imports
    session_identity -- a plain whole-file substring scan sees both."""
    _write(tmp_path / "hook.sh", """#!/usr/bin/env bash
VERDICT=$("$PYTHON" -c "
import session_identity
# AGENT_SESSION_ID, CODEX_THREAD_ID, CLAUDE_CODE_SESSION_ID resolved via the
# shared module's precedence.
sid = session_identity.resolve_sanitized()
")
""")
    assert parity.find_undelegated_files(tmp_path) == []


def test_sh_file_without_delegation_is_flagged(tmp_path):
    bad = tmp_path / "legacy_hook.sh"
    _write(bad, """#!/usr/bin/env bash
VERDICT=$("$PYTHON" -c "
import os
sid = (
    os.environ.get('AGENT_SESSION_ID', '')
    or os.environ.get('CODEX_THREAD_ID', '')
    or os.environ.get('CLAUDE_CODE_SESSION_ID', '')
)
")
""")
    assert parity.find_undelegated_files(tmp_path) == [bad]


def test_session_identity_module_itself_is_exempt():
    """The real module (not a tmp_path copy) legitimately defines all 3 names
    without 'importing' itself -- must not flag itself as a violation."""
    real_module = (
        Path(__file__).resolve().parent.parent.parent
        / "pipeline" / "lib" / "session_identity.py"
    )
    assert real_module.is_file(), "fixture assumption: session_identity.py must exist"
    assert parity.find_undelegated_files(real_module.parent) == []


def test_multiple_violations_sorted_deterministically(tmp_path):
    dup_text = """
import os
sid = (
    os.environ.get("AGENT_SESSION_ID", "")
    or os.environ.get("CODEX_THREAD_ID", "")
    or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
)
"""
    _write(tmp_path / "b_dup.py", dup_text)
    _write(tmp_path / "a_dup.py", dup_text)
    result = parity.find_undelegated_files(tmp_path)
    assert result == sorted(result)
    assert len(result) == 2


# ── main() / exit codes ─────────────────────────────────────────────────────

def test_main_exits_zero_on_clean_tree(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(parity, "_SCAN_ROOT", tmp_path)
    _write(tmp_path / "clean.py", "import session_identity\n")
    rc = parity.main([])
    assert rc == 0
    assert "OK:" in capsys.readouterr().out


def test_main_exits_one_and_reports_on_violation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(parity, "_SCAN_ROOT", tmp_path)
    _write(tmp_path / "dup.py", """
import os
sid = (
    os.environ.get("AGENT_SESSION_ID", "")
    or os.environ.get("CODEX_THREAD_ID", "")
    or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
)
""")
    rc = parity.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "dup.py" in out


# ── real-repo integration: the actual parity guarantee ─────────────────────

def test_real_repo_scripts_tree_has_zero_violations():
    """The literal ask this check exists for: run it against this repo's
    actual scripts/ tree (default scan root) and confirm all 4 known former
    duplicates (skill_context.py, refresh_run.py, skill_context_attribution.py,
    check_commit_bash_hook.sh) are clean, and no 5th has appeared."""
    violations = parity.find_undelegated_files()
    assert violations == [], (
        f"un-migrated session-identity duplicate(s) found: {violations}"
    )

"""Hostile-locale regression tests for check_stale_file_regression.py (ST-096
+ the broader class found 2026-08-28, fixed 2026-08-29 Phase 0a).

The defect: `_run_git()` used subprocess text mode with the LOCALE codec, so
on this repo's Windows production platform (cp1252):
  - a blob byte cp1252 cannot map (0x81/0x8D/0x8F/0x90/0x9D, e.g. U+201D)
    killed the reader thread -> stdout=None -> exit 0 (silent PASS);
  - any mappable non-ASCII byte (e.g. U+00E9) decoded differently from the
    UTF-8 worktree read, so worktree-mode comparison was silently inert.

These tests run the checker CLI in a SUBPROCESS with UTF-8 mode disabled and a
C locale so the hostile decode environment is real on every platform: on
Windows that yields cp1252 (the silent class), on POSIX an ASCII locale (the
raise class). The fixed checker decodes git output as UTF-8 explicitly, so
both classes must now be DETECTED (exit 1). An in-process test also pins the
new exit-3 contract for ambiguous session identity (ST-095: previously a raw
traceback that pre-commit Step 34 misparsed as file-name findings).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from checks import check_stale_file_regression as sfr  # noqa: E402

_CHECKER = _HERE / "checks" / "check_stale_file_regression.py"
_OPS_DIR = _HERE.parent / "pipeline" / "commands" / "ops"
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

import session_ledger  # noqa: E402

# U+201D encodes to E2 80 9D -- 0x9D is unmappable in cp1252 (the ST-096 byte).
_CURLY_V1 = "say ”wrong”\n".encode("utf-8")
_CURLY_V2 = "say ”correct”\n".encode("utf-8")
# U+00E9 encodes to C3 A9 -- both bytes MAP in cp1252 (to Ã and ©), which is
# exactly why this class was silent: no crash, just a different decode.
_EACUTE_V1 = "café wrong\n".encode("utf-8")
_EACUTE_V2 = "café correct\n".encode("utf-8")


@pytest.fixture(autouse=True)
def _reset_session_ledger():
    yield
    session_ledger.configure()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def _repo_with_staged_revert(tmp_path: Path, v1: bytes, v2: bytes) -> "tuple[Path, str]":
    """base commit = v1; fix commit = v2; worktree AND index back at v1 (the
    silent-revert shape). Returns (repo, base_sha)."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.md").write_bytes(v1)
    _git(repo, "add", "f.md")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True,
        text=True, encoding="utf-8", check=True,
    ).stdout.strip()
    (repo / "f.md").write_bytes(v2)
    _git(repo, "add", "f.md")
    _git(repo, "commit", "-q", "-m", "fix by another session")
    (repo / "f.md").write_bytes(v1)  # the revert, in the worktree...
    _git(repo, "add", "f.md")        # ...and staged
    return repo, base_sha


def _hostile_env() -> dict:
    """UTF-8 mode OFF + C locale + no identity vars: the checker subprocess
    decodes with whatever the platform's hostile default is."""
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PYTHONUTF8", "PYTHONIOENCODING", "LC_ALL", "LANG",
                     "AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID")
    }
    env["PYTHONUTF8"] = "0"
    env["PYTHONCOERCECLOCALE"] = "0"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _run_checker(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_CHECKER), *args],
        cwd=str(repo), env=_hostile_env(), capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )


def test_fixture_bytes_are_genuinely_hostile():
    """Canary: if someone edits the fixture content to something benign, the
    whole suite silently stops testing the defect class. Pin the hostility."""
    assert b"\x9d" in _CURLY_V1 and b"\x9d" in _CURLY_V2
    with pytest.raises(UnicodeDecodeError):
        _CURLY_V1.decode("cp1252")
    with pytest.raises(UnicodeDecodeError):
        _EACUTE_V1.decode("ascii")
    _EACUTE_V1.decode("cp1252")  # mappable -- the SILENT class, must not raise


def test_unmappable_byte_revert_detected_staged_mode(tmp_path):
    repo, base_sha = _repo_with_staged_revert(tmp_path, _CURLY_V1, _CURLY_V2)
    result = _run_checker(repo, "--files", "f.md", "--base-sha", base_sha)
    assert "Traceback" not in result.stderr
    assert result.returncode == 1, (
        f"ST-096 regression: unmappable-byte revert not detected "
        f"(rc={result.returncode}, stderr={result.stderr[:400]})"
    )
    assert "f.md" in result.stdout


def test_unmappable_byte_revert_detected_worktree_mode(tmp_path):
    repo, base_sha = _repo_with_staged_revert(tmp_path, _CURLY_V1, _CURLY_V2)
    result = _run_checker(repo, "--files", "f.md", "--base-sha", base_sha, "--working-tree")
    assert "Traceback" not in result.stderr
    assert result.returncode == 1
    assert "f.md" in result.stdout


def test_mappable_nonascii_revert_detected_worktree_mode(tmp_path):
    """The broader-than-filed class: worktree mode compared a UTF-8 file read
    against a locale-decoded `git show` -- inert for ANY non-ASCII content,
    not only unmappable bytes (this is the mode git_plumb_commit.py uses)."""
    repo, base_sha = _repo_with_staged_revert(tmp_path, _EACUTE_V1, _EACUTE_V2)
    result = _run_checker(repo, "--files", "f.md", "--base-sha", base_sha, "--working-tree")
    assert "Traceback" not in result.stderr
    assert result.returncode == 1
    assert "f.md" in result.stdout


def test_clean_state_still_exits_zero_under_hostile_locale(tmp_path):
    repo, base_sha = _repo_with_staged_revert(tmp_path, _CURLY_V1, _CURLY_V2)
    # incorporate the fix: worktree+index now match the fix commit
    (repo / "f.md").write_bytes(_CURLY_V2)
    _git(repo, "add", "f.md")
    result = _run_checker(repo, "--files", "f.md", "--base-sha", base_sha)
    assert result.returncode == 0
    assert "Traceback" not in result.stderr


def test_ambient_ambiguity_proceeds_via_lookback_never_a_traceback(tmp_path, monkeypatch, capsys):
    """ST-095 endgame (Phase 1): >=2 live session ledgers and no explicit
    identity used to escape as a raw AmbiguousSessionError traceback (exit 1)
    that Step 34's parser misread as file-name findings. Now the check simply
    RUNS with the lookback window -- ambiguity cannot block, cannot skip, and
    a real revert is still caught (warn-class in the soak, block under
    --wide-findings=block)."""
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    session_ledger.configure(repo_root=tmp_path)
    session_ledger.init_session("amb-a")
    session_ledger.init_session("amb-b")

    repo, _base = _repo_with_staged_revert(tmp_path, b"wrong\n", b"correct\n")
    monkeypatch.chdir(repo)

    rc = sfr.main(["--files", "f.md"])  # no --base-sha, no --session-id
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert rc == 0                       # warn-class during the soak
    assert "WARN(lookback)" in captured.out

    rc_block = sfr.main(["--files", "f.md", "--wide-findings", "block"])
    assert rc_block == 1                 # the widened window genuinely protects


def test_explicit_bad_session_id_is_exit_3_with_message(tmp_path, monkeypatch, capsys):
    """An EXPLICIT --session-id naming a missing manifest is a caller error
    (exit 3, one actionable line) -- distinct from ambient ambiguity above."""
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    session_ledger.configure(repo_root=tmp_path)
    repo, _base = _repo_with_staged_revert(tmp_path, b"wrong\n", b"correct\n")
    monkeypatch.chdir(repo)

    rc = sfr.main(["--files", "f.md", "--session-id", "no-such-session"])

    err = capsys.readouterr().err
    assert rc == 3
    assert "no-such-session" in err
    assert "Traceback" not in err

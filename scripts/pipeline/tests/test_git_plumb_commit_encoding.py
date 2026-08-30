"""git_plumb_commit.py encoding + ambiguity containment tests (2026-08-29,
stale-guard plan Phase 0a / TC-SG-01).

Two defect shapes, both reproduced live 2026-08-28/29:
  1. Tier-1 output captured with the LOCALE codec: one cp1252-unmappable byte
     in scripts/pre-commit-audit.sh output (e.g. U+274C, or the U+FE0F
     selector in the hook warnings) killed the subprocess reader thread on
     Windows -> tier1_result.stdout=None -> a Tier-1 FAIL surfaced as a raw
     TypeError, and a Tier-1 PASS crashed main() with AttributeError AFTER the
     push but BEFORE the retroactive skill-run record was filed.
  2. >=2 live session ledgers with no explicit identity escaped as a raw
     session_ledger.AmbiguousSessionError -- not a PlumbCommitError, so
     main()'s handlers missed it (traceback, exit 1, nothing actionable).

Note on (1): under a UTF-8 dev locale the pre-fix code also happened to work;
the pinned contract here (stdout always str; failures always surface as
PlumbCommitTier1Failed) is what the Windows CI leg exercises under the real
cp1252 default.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_OPS_DIR = _TESTS_DIR.parent / "commands" / "ops"
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

import git_plumb_commit as gpc  # noqa: E402
import session_ledger  # noqa: E402
from commands.governance import override_manager  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_override_manager(tmp_path):
    override_manager.configure(repo_root=tmp_path, pending_dir=tmp_path / "overrides_pending")
    yield
    override_manager.configure()


@pytest.fixture(autouse=True)
def _reset_gpc_config():
    yield
    gpc.configure()


@pytest.fixture(autouse=True)
def _reset_session_ledger_config():
    yield
    session_ledger.configure()


@pytest.fixture(autouse=True)
def _clear_identity_env(monkeypatch):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )


def _init_repo_with_remote(tmp_path: Path) -> "tuple[Path, Path]":
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-q")
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "test@test.com")
    _git(work, "config", "user.name", "Test")
    (work / "seed.txt").write_text("seed", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "seed")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", "main")
    return work, bare


def _write_fake_tier1(work: Path, body_bytes: bytes, exit_code: int) -> None:
    """Fake pre-commit-audit.sh whose OUTPUT contains raw non-ASCII bytes --
    written as bytes so no test-side encoding can sanitize them."""
    scripts_dir = work / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    script = scripts_dir / "pre-commit-audit.sh"
    script.write_bytes(b"#!/bin/bash\n" + body_bytes + b"\nexit " + str(exit_code).encode() + b"\n")


# U+274C CROSS MARK = E2 9D 8C; 0x8D is cp1252-unmappable (the ST-096 byte class).
_CROSS_LINE = b'echo "[Step X] \xe2\x9d\x8c marker line"'


def test_tier1_output_with_unmappable_byte_is_string_not_none(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    _write_fake_tier1(work, _CROSS_LINE, exit_code=0)

    result = gpc.plumb_commit(
        ["f.txt"], "tier1 emits unmappable byte", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True, skip_ledger_check=True,
    )

    assert result["pushed"] is True
    assert isinstance(result["tier1_output"], str)
    assert "❌" in result["tier1_output"]  # decoded as UTF-8, not locale


def test_tier1_failure_with_unmappable_byte_raises_tier1failed_not_typeerror(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "g.txt").write_text("v", encoding="utf-8")
    _write_fake_tier1(work, _CROSS_LINE, exit_code=1)

    with pytest.raises(gpc.PlumbCommitTier1Failed) as exc_info:
        gpc.plumb_commit(
            ["g.txt"], "tier1 fails with unmappable byte", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True, skip_ledger_check=True,
        )
    assert "❌" in str(exc_info.value)


def test_ambiguous_ledger_raises_plumb_commit_error_not_raw_ambiguous(tmp_path):
    """ST-095 containment: the outer stale/ledger checks wrap
    AmbiguousSessionError into a PlumbCommitError with an actionable message,
    so main() exits 2 with a clear line instead of a traceback."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    session_ledger.configure(repo_root=work)
    session_ledger.init_session("plumb-amb-a")
    session_ledger.init_session("plumb-amb-b")

    with pytest.raises(gpc.PlumbCommitError) as exc_info:
        gpc.plumb_commit(
            ["f.txt"], "ambiguous identity", repo_root=work, branch="main",
            remote=str(bare), push=False, skip_tier1_checks=True,
        )
    assert not isinstance(exc_info.value, session_ledger.AmbiguousSessionError)
    assert "AMBIGUOUS" in str(exc_info.value)
    assert "--session-id" in str(exc_info.value)


def test_explicit_identity_still_works_under_ambiguity(tmp_path):
    """The documented remedy must actually work: with --base-sha given, the
    stale check runs and the ledger check is scoped to the named session."""
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "f.txt").write_text("v", encoding="utf-8")

    session_ledger.configure(repo_root=work)
    session_ledger.init_session("plumb-amb-c")
    session_ledger.init_session("plumb-amb-d")
    session_ledger.record_file("f.txt", action="created", session_id="plumb-amb-c")

    result = gpc.plumb_commit(
        ["f.txt"], "explicit identity", repo_root=work, branch="main",
        remote=str(bare), base_sha=base_sha, session_id="plumb-amb-c",
        skip_tier1_checks=True,
    )
    assert result["pushed"] is True

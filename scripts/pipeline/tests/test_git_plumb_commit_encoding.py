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


def test_ambiguous_ledger_proceeds_and_lookback_still_protects(tmp_path, capsys):
    """ST-095 endgame (Phase 1): >=2 live ledgers no longer block or crash the
    tool -- it proceeds on the lookback window with a loud warning, and a real
    byte-exact revert of a commit nobody's session covers is STILL caught
    (warn-class under the soak default; blocking under wide_findings="block")."""
    work, bare = _init_repo_with_remote(tmp_path)
    session_ledger.configure(repo_root=work)
    session_ledger.init_session("plumb-amb-a")
    session_ledger.init_session("plumb-amb-b")

    # A fix commit lands; this session's worktree then reverts it byte-exactly.
    (work / "data.txt").write_text("wrong", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed wrong")
    (work / "data.txt").write_text("right", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix nobody saw")
    _git(work, "push", "-q", "origin", "main")
    (work / "data.txt").write_text("wrong", encoding="utf-8")

    # Soak default: proceeds (warn-class), never a raw AmbiguousSessionError.
    result = gpc.plumb_commit(
        ["data.txt"], "ambiguous identity, soak policy", repo_root=work,
        branch="main", remote=str(bare), skip_tier1_checks=True,
    )
    assert result["pushed"] is True
    err = capsys.readouterr().err
    assert "ambiguous" in err.lower()
    assert "lookback" in err.lower()

    # Enforced policy: the same shape blocks.
    (work / "data.txt").write_text("right", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "re-fix")
    _git(work, "push", "-q", "origin", "main")
    (work / "data.txt").write_text("wrong", encoding="utf-8")
    with pytest.raises(gpc.PlumbCommitBlocked):
        gpc.plumb_commit(
            ["data.txt"], "ambiguous identity, block policy", repo_root=work,
            branch="main", remote=str(bare), skip_tier1_checks=True,
            wide_findings="block",
        )


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


# ---------------------------------------------------------------------------
# Governance-trail ordering + scoped token consumption (Phase 1, TC-SG-04)
# ---------------------------------------------------------------------------

def test_record_created_pending_before_push_and_finalized_after(tmp_path, monkeypatch):
    """The record carries the built commit's sha BEFORE the push (created
    pending), and is finalized success after -- so a crash between push and
    finalize leaves a sha-linked PENDING_FINALIZE record instead of no trail
    (the TC-SG-18 class, which fired live on this plan's own Phase 0a commit)."""
    import json
    records_dir = tmp_path / "runs"
    monkeypatch.setenv("SKILL_RUN_RECORDS_DIR", str(records_dir))
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["f.txt"], "record ordering", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True, skip_ledger_check=True,
        skip_tier1_checks=True, skills=["S-99"], plan="ordering test",
    )

    assert result["skill_run_id"]
    record = json.loads(
        (records_dir / f"{result['skill_run_id']}.json").read_text(encoding="utf-8"))
    assert record["outcome"] == "success"
    assert record["commit_sha"] == result["commit_sha"]


def test_crash_during_push_leaves_sha_linked_pending_record(tmp_path, monkeypatch):
    import json
    records_dir = tmp_path / "runs"
    monkeypatch.setenv("SKILL_RUN_RECORDS_DIR", str(records_dir))
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    import subprocess as _sp

    def _runner_that_dies_on_push(cmd, **kwargs):
        if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
            raise RuntimeError("simulated crash mid-push")
        return _sp.run(cmd, **kwargs)

    gpc.configure(repo_root=work, command_runner=_runner_that_dies_on_push)
    with pytest.raises(RuntimeError, match="simulated crash"):
        gpc.plumb_commit(
            ["f.txt"], "crash mid-push", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True, skip_ledger_check=True,
            skip_tier1_checks=True, skills=["S-99"], plan="crash test",
        )

    records = list(records_dir.glob("retroactive-*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["outcome"] == "pending"       # PENDING_FINALIZE, discoverable
    assert record["commit_sha"]                 # sha-linked despite the crash


def test_relied_override_token_consumed_by_id_after_push(tmp_path):
    """A finding allowed through by a token consumes exactly THAT token after
    the push -- plumbed commits never fire the porcelain post-commit hook, so
    the token previously lingered and was swept by an unrelated commit."""
    import json
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "data.txt").write_text("wrong", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed wrong")
    (work / "data.txt").write_text("right", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix")
    _git(work, "push", "-q", "origin", "main")
    (work / "data.txt").write_text("wrong", encoding="utf-8")  # intentional revert

    class Args:
        paths = ["data.txt"]
        reason = "intentional revert"
        plan = "token consumption test"
        scope = ""
        operation = "edit"
        retroactive = False

    override_manager.cmd_create(Args())
    pending = list(override_manager._PENDING_DIR.glob("*.json"))
    assert len(pending) == 1
    token_id = json.loads(pending[0].read_text(encoding="utf-8"))["override_id"]
    unrelated = override_manager._PENDING_DIR / "zz-unrelated.json"
    unrelated.write_text(
        '{"override_id": "zz-unrelated", "paths": ["docs/elsewhere.md"],'
        ' "operation": "edit", "reason": "someone else", '
        '"authorized_at": "2099-01-01T00:00:00Z", "retroactive": false,'
        ' "consumed_by_commit": null}\n', encoding="utf-8")

    result = gpc.plumb_commit(
        ["data.txt"], "governed revert", repo_root=work, branch="main",
        remote=str(bare), base_sha=base_sha, skip_tier1_checks=True,
    )
    assert result["pushed"] is True

    assert not (override_manager._PENDING_DIR / f"{token_id}.json").exists()
    archived = override_manager._ARCHIVED_DIR / f"{token_id}.json"
    assert json.loads(archived.read_text(encoding="utf-8"))["consumed_by_commit"] == result["commit_sha"]
    assert unrelated.exists()   # the other session's token was NOT swept


# ---------------------------------------------------------------------------
# TC-SG-19: temp-index robustness (private mkdtemp path + bounded transient
# retry) -- two consecutive `git read-tree ... unable to write new index file`
# failures were observed live 2026-08-30 (clean on retry and on a direct
# probe): an antivirus/indexer race on the old mkstemp->unlink->recreate
# dance over a flat %TEMP% name.
# ---------------------------------------------------------------------------

def _passthrough_runner_with(hook):
    import subprocess as _sp

    def _runner(cmd, **kwargs):
        intercepted = hook(cmd, kwargs)
        if intercepted is not None:
            return intercepted
        return _sp.run(cmd, **kwargs)
    return _runner


def test_transient_read_tree_failure_retries_and_succeeds(tmp_path, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    calls = {"read_tree": 0}

    def _fail_first_read_tree(cmd, kwargs):
        if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "read-tree":
            calls["read_tree"] += 1
            if calls["read_tree"] == 1:
                import subprocess as _sp
                return _sp.CompletedProcess(
                    cmd, 128, stdout="",
                    stderr="fatal: unable to write new index file")
        return None

    gpc.configure(repo_root=work, command_runner=_passthrough_runner_with(_fail_first_read_tree))
    result = gpc.plumb_commit(
        ["f.txt"], "transient retry", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, skip_ledger_check=True, skip_tier1_checks=True,
    )

    assert result["pushed"] is True
    assert calls["read_tree"] == 2          # failed once, retried once, succeeded
    assert "transient temp-index failure" in capsys.readouterr().err


def test_non_transient_read_tree_fails_fast_without_retry(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    calls = {"read_tree": 0}

    def _always_fail_read_tree(cmd, kwargs):
        if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "read-tree":
            calls["read_tree"] += 1
            import subprocess as _sp
            return _sp.CompletedProcess(cmd, 128, stdout="",
                                        stderr="fatal: not a tree object")
        return None

    gpc.configure(repo_root=work, command_runner=_passthrough_runner_with(_always_fail_read_tree))
    with pytest.raises(gpc.PlumbCommitError, match="not a tree object"):
        gpc.plumb_commit(
            ["f.txt"], "hard failure", repo_root=work, branch="main", remote=str(bare),
            skip_stale_check=True, skip_ledger_check=True, skip_tier1_checks=True,
        )
    assert calls["read_tree"] == 1          # no retry for a non-transient shape


def test_temp_index_lives_in_private_never_preexisting_dir(tmp_path):
    import os as _os
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    seen = {}

    def _capture_index_env(cmd, kwargs):
        if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "read-tree":
            path = (kwargs.get("env") or {}).get("GIT_INDEX_FILE", "")
            seen["path"] = path
            seen["preexisted"] = _os.path.exists(path)
        return None

    gpc.configure(repo_root=work, command_runner=_passthrough_runner_with(_capture_index_env))
    gpc.plumb_commit(
        ["f.txt"], "private dir", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, skip_ledger_check=True, skip_tier1_checks=True,
    )

    assert seen["path"].replace("\\", "/").split("/")[-1] == "index"
    assert "git_plumb_" in seen["path"]
    assert seen["preexisted"] is False      # never created-then-deleted (the AV race)
    assert not _os.path.exists(_os.path.dirname(seen["path"]))  # cleaned up

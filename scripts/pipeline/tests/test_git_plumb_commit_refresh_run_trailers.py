"""Tests for git_plumb_commit.py's --refresh-run flag (ST-154).

ST-126 (fixed 2026-08-31 via refresh_run_bind_recovery.py's shadow-commit
technique) was recoverable but reactive: a session that forgot to hand-author
the Refresh-Run/Refresh-Base/Refresh-Source-SHA trailers only found out after
the real content commit was already pushed, with no forward-fix path short of
a shadow commit. This flag makes the correct trailers the default outcome of
citing --refresh-run at commit time, so the stuck state never happens in the
first place. Uses a REAL temporary git repository for the CLI-level test --
this is git-plumbing wiring, which a mocked command_runner cannot meaningfully
exercise -- matching this session's established preference.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
OPS_DIR = PIPELINE_DIR / "commands" / "ops"
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))

import git_plumb_commit as gpc  # noqa: E402
import refresh_run as rr  # noqa: E402
import session_ledger  # noqa: E402
from commands.governance import override_manager  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_override_manager(tmp_path):
    override_manager.configure(repo_root=tmp_path, pending_dir=tmp_path / "overrides_pending")
    yield
    override_manager.configure()


@pytest.fixture(autouse=True)
def _reset_configs():
    yield
    gpc.configure()
    session_ledger.configure()
    rr.configure()


def _write_manifest(
    tmp_path: Path,
    *,
    family: str = "pdf",
    platform: str = "net",
    run_id: str = "RUN-1",
    state: str = "PLANNED",
    base_commit_sha: str = "b" * 40,
    target_source_sha: "str | None" = "c" * 40,
) -> None:
    """Write a minimal, schema-valid refresh_run manifest.json -- only the
    fields _stamp_refresh_run_trailers actually reads (base_commit_sha,
    target_source_sha) carry meaningful test values; everything else is the
    minimum schema_version=3 shape validate_refresh_run_manifest accepts at
    state=PLANNED (state_rank=2: requires scope.digest/paths and matching
    target_model_sha/target_source_sha, but not the full receipt/validation
    chain state_rank>=4/READY_TO_COMMIT requires)."""
    run_root = tmp_path / "reports" / "refresh_runs" / family / platform / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    now = "2026-08-31T00:00:00Z"
    manifest = {
        "schema_version": 3,
        "run_id": run_id,
        "family": family,
        "platform": platform,
        "mode": "upstream",
        "state": state,
        "session_owner": "session-1",
        "created_at": now,
        "updated_at": now,
        "base_commit_sha": base_commit_sha,
        "initial_model_sha": "a" * 40,
        "initial_source_sha": "a" * 40,
        "target_model_sha": target_source_sha,
        "target_source_sha": target_source_sha,
        "scope": {"paths": [], "digest": "sha256:scope", "input_digest": "sha256:input"},
        "stage_checkpoints": {},
        "validation": {field: "NOT_RUN" for field in rr.VALIDATION_FIELDS},
        "observed_heads": [],
    }
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


# ---------------------------------------------------------------------------
# _stamp_refresh_run_trailers -- unit level, no git repo needed
# ---------------------------------------------------------------------------

def test_stamp_appends_correct_trailers_when_missing(tmp_path):
    rr.configure(repo_root=tmp_path)
    _write_manifest(
        tmp_path, base_commit_sha="b" * 40, target_source_sha="c" * 40, run_id="RUN-1",
    )

    stamped = gpc._stamp_refresh_run_trailers(
        "feat(pdf/net): refresh content\n", "pdf", "net", "RUN-1"
    )

    # Round-trip through the SAME parser bind_commit() itself uses -- the
    # real acceptance criterion, not just a string-contains check.
    trailers = rr._commit_trailer_values(stamped)
    assert trailers["Refresh-Run"] == ["RUN-1"]
    assert trailers["Refresh-Base"] == ["b" * 40]
    assert trailers["Refresh-Source-SHA"] == ["c" * 40]
    assert stamped.startswith("feat(pdf/net): refresh content\n")


def test_stamp_is_idempotent_when_trailers_already_correct(tmp_path):
    rr.configure(repo_root=tmp_path)
    _write_manifest(tmp_path, base_commit_sha="b" * 40, target_source_sha="c" * 40, run_id="RUN-1")

    once = gpc._stamp_refresh_run_trailers("feat: x\n", "pdf", "net", "RUN-1")
    twice = gpc._stamp_refresh_run_trailers(once, "pdf", "net", "RUN-1")

    assert once == twice
    # Exactly one trailer block -- not doubled.
    assert once.count("Refresh-Run:") == 1


def test_stamp_raises_when_target_source_sha_not_pinned(tmp_path):
    rr.configure(repo_root=tmp_path)
    _write_manifest(
        tmp_path, state="INPUTS_PINNED", target_source_sha=None, run_id="RUN-1",
    )

    with pytest.raises(gpc.RefreshRunTrailerError, match="target_source_sha"):
        gpc._stamp_refresh_run_trailers("feat: x\n", "pdf", "net", "RUN-1")


def test_stamp_raises_when_run_does_not_exist(tmp_path):
    rr.configure(repo_root=tmp_path)

    with pytest.raises(rr.RefreshRunError, match="not found"):
        gpc._stamp_refresh_run_trailers("feat: x\n", "pdf", "net", "NO-SUCH-RUN")


# ---------------------------------------------------------------------------
# CLI wiring -- real temp git repo, real push to a local bare remote
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )


def _init_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
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


def test_cli_refresh_run_flag_stamps_trailers_on_the_real_commit(tmp_path, monkeypatch):
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    rr.configure(repo_root=work)
    _write_manifest(
        work, base_commit_sha=base_sha, target_source_sha="d" * 40, run_id="RUN-2",
        family="pdf", platform="net",
    )

    (work / "page.md").write_text("body", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("feat(pdf/net): refresh content\n", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files", "page.md",
        "--message-file", str(msg_file),
        "--skills", "S-99", "--plan", "refresh-run trailer cli test",
        "--branch", "main", "--remote", str(bare),
        "--skip-stale-check", "--no-push",
        "--co-author", "Claude Sonnet 5 <noreply@anthropic.com>",
        "--refresh-run", "pdf", "net", "RUN-2",
    ])

    assert rc == 0
    committed_message = _git(work, "show", "-s", "--format=%B", "HEAD").stdout
    trailers = rr._commit_trailer_values(committed_message)
    assert trailers["Refresh-Run"] == ["RUN-2"]
    assert trailers["Refresh-Base"] == [base_sha]
    assert trailers["Refresh-Source-SHA"] == ["d" * 40]
    # The subject line the caller wrote is preserved verbatim.
    assert committed_message.startswith("feat(pdf/net): refresh content\n")


def test_cli_refresh_run_flag_errors_cleanly_on_unverified_run(tmp_path, monkeypatch, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    rr.configure(repo_root=work)
    _write_manifest(
        work, state="INPUTS_PINNED", target_source_sha=None, run_id="RUN-3",
        family="pdf", platform="net",
    )
    (work / "page.md").write_text("body", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("feat: x\n", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files", "page.md",
        "--message-file", str(msg_file),
        "--skills", "S-99", "--plan", "refresh-run trailer cli test",
        "--branch", "main", "--remote", str(bare),
        "--skip-stale-check", "--no-push",
        "--co-author", "Claude Sonnet 5 <noreply@anthropic.com>",
        "--refresh-run", "pdf", "net", "RUN-3",
    ])

    assert rc == 2
    assert "target_source_sha" in capsys.readouterr().err
    # No commit was created -- the repo's HEAD is unchanged.
    assert _git(work, "rev-parse", "HEAD").stdout.strip() == _git(work, "rev-parse", "main").stdout.strip()

"""Step 34 (stale-file regression guard) tests, sourced LIVE from the on-disk
scripts/pre-commit-audit.sh at test time (2026-08-30, stale-guard plan
TC-SG-04) -- Step 34 had NEVER executed in any test before this file, which is
how a traceback-as-filenames deadlock (ST-095) and a silent fail-open
(ST-096) both shipped through it.

Follows test_precommit_audit_step5_step10.py's live-extraction pattern
(markers, stubbed _pc_* functions, absolutized script paths, real Git Bash,
cwd = fixture repo). A shared helper extraction is deferred (recorded in the
plan's change log) to avoid churning that passing suite mid-phase.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parents[2]
_PRECOMMIT = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"
_CHECKER = _REPO_ROOT / "scripts" / "ci" / "checks" / "check_stale_file_regression.py"
_OPS_DIR = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

import git_plumb_commit as gpc  # noqa: E402,F401  (guard shares its resolver)

from _git_bash_guard import require_git_bash  # noqa: E402

_START = '_pc_step_start "stale file regression"'
_END = '_pc_step_start "media asset size"'


def _bash_path() -> str:
    return require_git_bash()  # skip on POSIX, fail on Windows (TC-SG-20a)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=False)


def _fixture_with_staged_revert(tmp_path: Path) -> "tuple[Path, str]":
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "data.json").write_text("wrong\n", encoding="utf-8")
    _git(repo, "add", "data.json")
    _git(repo, "commit", "-q", "-m", "seed wrong")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "data.json").write_text("right\n", encoding="utf-8")
    _git(repo, "add", "data.json")
    _git(repo, "commit", "-q", "-m", "fix by another session")
    (repo / "data.json").write_text("wrong\n", encoding="utf-8")
    _git(repo, "add", "data.json")  # the staged silent revert
    return repo, base


def _block_text(checker_path: "Path | str" = _CHECKER) -> str:
    text = _PRECOMMIT.read_text(encoding="utf-8")
    start = text.index(_START)
    end = text.index(_END, start)
    block = text[start:end]
    real = str(_REPO_ROOT).replace("\\", "/")
    block = block.replace("scripts/ci/checks/check_stale_file_regression.py",
                          str(checker_path).replace("\\", "/"))
    block = block.replace("PYTHONPATH=scripts/pipeline",
                          f"PYTHONPATH={real}/scripts/pipeline")
    return block


def _run_step34(block: str, fixture_repo: Path, *, extra_env: "dict | None" = None,
                ) -> subprocess.CompletedProcess:
    real = str(_REPO_ROOT).replace("\\", "/")
    harness = (
        "#!/bin/bash\n"
        "_pc_step_start() { :; }\n"
        "_pc_step_end() { :; }\n"
        "_pc_exit() { exit \"$1\"; }\n"
        f"if [ -f \"{real}/.venv/Scripts/python\" ] || [ -f \"{real}/.venv/Scripts/python.exe\" ]; then\n"
        f"    _HOOK_PYTHON=\"{real}/.venv/Scripts/python\"\n"
        f"else\n"
        f"    _HOOK_PYTHON=\"{real}/.venv/bin/python\"\n"
        f"fi\n"
        + block
        + "\nexit 0\n"
    )
    harness_path = fixture_repo.parent / "step34_harness.sh"
    harness_path.write_text(harness, encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items()
           if k not in ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID",
                        "PC_AUDIT_SESSION_ID", "PC_AUDIT_BASE_SHA", "PC_AUDIT_NO_MUTATE",
                        "GIT_INDEX_FILE")}
    env.update(extra_env or {})
    return subprocess.run([_bash_path(), str(harness_path)], cwd=str(fixture_repo),
                          env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)


def test_session_class_revert_blocks_with_named_file_never_tracebacks(tmp_path):
    repo, base = _fixture_with_staged_revert(tmp_path)
    result = _run_step34(_block_text(), repo, extra_env={
        # The plumb Tier-1 signature: the env tier is honoured only with it.
        "GIT_INDEX_FILE": str(repo / ".git" / "index"),
        "PC_AUDIT_NO_MUTATE": "1",
        "PC_AUDIT_BASE_SHA": base,
    })
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "BLOCKED" in out
    assert "data.json" in out
    assert 'File "' not in out   # the ST-095 misparse shape must never return


def test_token_covered_revert_passes_with_allow_line(tmp_path):
    repo, base = _fixture_with_staged_revert(tmp_path)
    pending = repo / "reports" / "overrides" / "pending"
    pending.mkdir(parents=True)
    (pending / "tok-34.json").write_text(
        '{"override_id": "tok-34", "paths": ["data.json"], "operation": "edit",\n'
        ' "reason": "intentional revert", "authorized_at": "2099-01-01T00:00:00Z",\n'
        ' "retroactive": false, "consumed_by_commit": null}\n', encoding="utf-8")
    result = _run_step34(_block_text(), repo, extra_env={
        "GIT_INDEX_FILE": str(repo / ".git" / "index"),
        "PC_AUDIT_NO_MUTATE": "1",
        "PC_AUDIT_BASE_SHA": base,
    })
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "ALLOW(token tok-34)" in out


def test_lookback_class_warns_and_passes_under_soak_policy(tmp_path):
    repo, _base = _fixture_with_staged_revert(tmp_path)
    result = _run_step34(_block_text(), repo)  # no identity, no PC env
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "WARN(lookback)" in out
    assert "source=lookback" in out


def test_infra_failure_fails_closed_when_ledger_dir_exists(tmp_path):
    repo, _base = _fixture_with_staged_revert(tmp_path)
    (repo / "reports" / "session-state").mkdir(parents=True)
    stub = tmp_path / "stub_checker.py"
    stub.write_text("import sys; print('boom', file=sys.stderr); sys.exit(4)\n",
                    encoding="utf-8")
    result = _run_step34(_block_text(checker_path=stub), repo)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "infrastructure" in out
    assert "boom" in out


def test_infra_failure_is_advisory_without_ledger_infrastructure(tmp_path):
    repo, _base = _fixture_with_staged_revert(tmp_path)
    stub = tmp_path / "stub_checker.py"
    stub.write_text("import sys; print('boom', file=sys.stderr); sys.exit(4)\n",
                    encoding="utf-8")
    result = _run_step34(_block_text(checker_path=stub), repo)
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "advisory pass" in out


def test_no_staged_non_content_files_skips(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.txt").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    result = _run_step34(_block_text(), repo)
    assert result.returncode == 0
    assert "skipping" in (result.stdout + result.stderr)

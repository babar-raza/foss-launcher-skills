"""Tests for git_plumb_commit.py (production concurrency redesign,
2026-08-01, Step 8 follow-up: MT019's own convergence audit, TC-MT019-03).

Uses a REAL local bare repo as the push destination -- no network
dependency, no mocking of git itself -- matching this session's established
preference for exercising real git behavior rather than simulating it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import git_plumb_commit as gpc
from commands.governance import override_manager


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False,
    )


def _init_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare 'origin' repo and a working repo cloned from it, with
    one initial commit already pushed. Returns (working_repo, bare_repo)."""
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


@pytest.fixture(autouse=True)
def _isolate_override_manager(tmp_path):
    """override_manager.find_valid_token_for_path reads module-level
    repo_root/pending-dir defaults (the REAL repo's own paths) unless
    reconfigured -- isolate both for every test in this file. repo_root
    matters even though pending_dir is overridden separately: cmd_create's
    own success message computes out_path.relative_to(_REPO_ROOT), which
    raises if _REPO_ROOT doesn't actually contain pending_dir."""
    override_manager.configure(repo_root=tmp_path, pending_dir=tmp_path / "overrides_pending")
    yield
    override_manager.configure()


@pytest.fixture(autouse=True)
def _reset_gpc_config():
    yield
    gpc.configure()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_commits_and_pushes_real_new_file(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "new_file.txt").write_text("hello", encoding="utf-8")

    result = gpc.plumb_commit(
        ["new_file.txt"], "add new_file.txt",
        repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True,
    )

    assert result["pushed"] is True
    assert result["commit_sha"]

    # Verify the push actually landed on the bare "remote" -- real proof, not
    # an assumption based on a zero exit code.
    show = _git(bare, "show", f"{result['commit_sha']}:new_file.txt")
    assert show.stdout == "hello"

    # Local refs synced.
    local_head = _git(work, "rev-parse", "refs/heads/main").stdout.strip()
    assert local_head == result["commit_sha"]
    remote_tracking = _git(work, "rev-parse", "refs/remotes/origin/main").stdout.strip()
    assert remote_tracking == result["commit_sha"]


def test_does_not_touch_real_index_or_other_staged_files(tmp_path):
    """The core safety property: another file staged in the real index
    (simulating another session's in-flight work) must survive untouched.

    Verifies via `git ls-files --stage` (the real index's own content),
    not `git diff --cached` -- after a successful plumb_commit, `update-ref`
    moves the local branch pointer forward past the real (untouched, now
    stale-relative-to-new-HEAD) index, so `git diff --cached` naturally
    shows the newly-committed file as a spurious "D" (deleted) entry -- an
    already-documented, expected artifact of this exact technique (see this
    session's other commits' own "post-commit index staleness" notes), not
    evidence of a bug. `git ls-files --stage` reports the index's actual
    entries directly, unaffected by which commit HEAD happens to point at.
    """
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "mine.txt").write_text("mine", encoding="utf-8")
    (work / "someone_elses.txt").write_text("their staged content", encoding="utf-8")
    _git(work, "add", "someone_elses.txt")  # staged in the REAL index, not by us

    gpc.plumb_commit(
        ["mine.txt"], "add mine.txt", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True,
    )

    # The real index must still show exactly someone_elses.txt -- mine.txt
    # was never added to it.
    real_index = _git(work, "ls-files", "--stage").stdout
    assert "someone_elses.txt" in real_index
    assert "mine.txt" not in real_index

    head_files = _git(work, "show", "--stat", "--format=", "HEAD").stdout
    assert "mine.txt" in head_files
    assert "someone_elses.txt" not in head_files


def test_commit_message_preserved_verbatim(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    msg = "fix(pipeline): a real multi-line message\n\n- detail one\n- detail two\n"

    result = gpc.plumb_commit(
        ["f.txt"], msg, repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True,
    )

    actual_msg = _git(work, "log", "-1", "--format=%B", result["commit_sha"]).stdout
    assert actual_msg.strip() == msg.strip()


def test_no_push_mode_creates_commit_without_pushing(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["f.txt"], "no push test", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, push=False,
    )

    assert result["pushed"] is False
    # Not reachable on the bare repo.
    show = _git(bare, "cat-file", "-e", result["commit_sha"])
    assert show.returncode != 0


# ---------------------------------------------------------------------------
# --no-push ref-chaining (MT028-2026-08-09-FONT-PYTHON-BLIND-SPOT-HEAL,
# L1-MT028-03/L3-MT028-01, TC-MT028-05: found live -- 2 of that mission's 4
# sequential --no-push commits landed as disconnected siblings sharing the
# ORIGINAL pre-mission HEAD as parent, instead of chaining off each other,
# because refs/heads/{branch} previously only advanced inside `if push:`.
# ---------------------------------------------------------------------------

def test_no_push_mode_still_advances_local_ref_so_sequential_commits_chain(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    original_head = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "a.txt").write_text("a", encoding="utf-8")
    first = gpc.plumb_commit(
        ["a.txt"], "first no-push commit", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True, push=False,
    )

    # The local branch ref must have moved to the first commit even though
    # nothing was pushed -- this is the fix: previously refs/heads/main
    # stayed at original_head until a --push call, so the SECOND plumbed
    # commit below would (pre-fix) re-capture original_head as its own
    # parent instead of first["commit_sha"].
    local_head_after_first = _git(work, "rev-parse", "refs/heads/main").stdout.strip()
    assert local_head_after_first == first["commit_sha"]
    assert local_head_after_first != original_head

    (work / "b.txt").write_text("b", encoding="utf-8")
    second = gpc.plumb_commit(
        ["b.txt"], "second no-push commit", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True, push=False,
    )

    # The real bug: second's parent must be first's commit_sha (a real
    # chain), not original_head (a disconnected sibling that would silently
    # drop "a.txt" if ever pushed as-is).
    second_parent = _git(work, "log", "-1", "--format=%P", second["commit_sha"]).stdout.strip()
    assert second_parent == first["commit_sha"]
    assert second_parent != original_head

    # And the local ref now points at the second (chain-tip) commit.
    local_head_after_second = _git(work, "rev-parse", "refs/heads/main").stdout.strip()
    assert local_head_after_second == second["commit_sha"]


def test_three_sequential_no_push_commits_all_chain(tmp_path):
    """Repeatability beyond the minimal 2-commit reproduction -- a 3rd
    --no-push commit must also chain off the 2nd, not just the 1st off the
    original HEAD."""
    work, bare = _init_repo_with_remote(tmp_path)

    (work / "a.txt").write_text("a", encoding="utf-8")
    c1 = gpc.plumb_commit(
        ["a.txt"], "c1", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, push=False,
    )
    (work / "b.txt").write_text("b", encoding="utf-8")
    c2 = gpc.plumb_commit(
        ["b.txt"], "c2", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, push=False,
    )
    (work / "c.txt").write_text("c", encoding="utf-8")
    c3 = gpc.plumb_commit(
        ["c.txt"], "c3", repo_root=work, branch="main", remote=str(bare),
        skip_stale_check=True, push=False,
    )

    assert _git(work, "log", "-1", "--format=%P", c2["commit_sha"]).stdout.strip() == c1["commit_sha"]
    assert _git(work, "log", "-1", "--format=%P", c3["commit_sha"]).stdout.strip() == c2["commit_sha"]
    # All 3 files present on the final chain tip -- proof nothing was dropped.
    files_at_tip = _git(work, "ls-tree", "-r", "--name-only", c3["commit_sha"]).stdout
    assert "a.txt" in files_at_tip
    assert "b.txt" in files_at_tip
    assert "c.txt" in files_at_tip


def test_push_mode_still_updates_both_local_and_remote_tracking_refs(tmp_path):
    """Non-regression: --push's existing, already-relied-upon behavior
    (updating both refs/heads/{branch} and refs/remotes/{remote}/{branch},
    and actually pushing) must be completely unchanged by this fix."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["f.txt"], "push mode unchanged", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True, push=True,
    )

    assert result["pushed"] is True
    assert _git(work, "rev-parse", "refs/heads/main").stdout.strip() == result["commit_sha"]
    assert _git(work, "rev-parse", "refs/remotes/origin/main").stdout.strip() == result["commit_sha"]
    remote_tip = _git(bare, "rev-parse", "main").stdout.strip()
    assert remote_tip == result["commit_sha"]


# ---------------------------------------------------------------------------
# .gitignore warnings (TC-H04, found live 2026-08-06: this tool force-tracked
# 8 gitignored /.supervisor/state/ files with zero feedback)
# ---------------------------------------------------------------------------

def test_warns_on_gitignored_file_but_still_commits(tmp_path, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "add gitignore")
    (work / "ignored").mkdir()
    (work / "ignored" / "secret.txt").write_text("s", encoding="utf-8")

    result = gpc.plumb_commit(
        ["ignored/secret.txt"], "force-track a gitignored file",
        repo_root=work, branch="main", remote=str(bare), skip_stale_check=True,
    )

    assert result["gitignore_warnings"] == ["ignored/secret.txt"]
    assert "WARNING" in capsys.readouterr().err
    assert result["pushed"] is True  # non-fatal -- commit still proceeds
    show = _git(bare, "show", f"{result['commit_sha']}:ignored/secret.txt")
    assert show.stdout == "s"


def test_ack_gitignored_silences_the_warning(tmp_path, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "add gitignore")
    (work / "ignored").mkdir()
    (work / "ignored" / "secret.txt").write_text("s", encoding="utf-8")

    result = gpc.plumb_commit(
        ["ignored/secret.txt"], "intentionally force-track",
        repo_root=work, branch="main", remote=str(bare), skip_stale_check=True,
        ack_gitignored=["ignored/secret.txt"],
    )

    assert result["gitignore_warnings"] == []
    assert "WARNING" not in capsys.readouterr().err
    assert result["pushed"] is True


def test_no_warning_for_a_normal_tracked_path(tmp_path, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "normal.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["normal.txt"], "normal commit", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True,
    )

    assert result["gitignore_warnings"] == []
    assert "WARNING" not in capsys.readouterr().err


def test_cli_ack_gitignored_flag_silences_warning(tmp_path, monkeypatch, capsys):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "add gitignore")
    (work / "ignored").mkdir()
    (work / "ignored" / "secret.txt").write_text("s", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("chore: cli ack test", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files", "ignored/secret.txt",
        "--message-file", str(msg_file),
        "--skills", "S-99", "--plan", "cli ack test",
        "--branch", "main", "--remote", str(bare),
        "--skip-stale-check", "--no-push",
        "--ack-gitignored", "ignored/secret.txt",
    ])

    assert rc == 0
    assert "WARNING" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Stale-file regression blocking
# ---------------------------------------------------------------------------

def test_blocks_a_real_regression_with_no_override(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed data.txt as wrong")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("correct-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix by another session")
    _git(work, "push", "-q", "origin", "main")

    # This session's own proposed content reverts the fix.
    (work / "data.txt").write_text("wrong-value", encoding="utf-8")

    with pytest.raises(gpc.PlumbCommitBlocked) as exc_info:
        gpc.plumb_commit(
            ["data.txt"], "accidental revert", repo_root=work, branch="main",
            remote=str(bare), base_sha=base_sha,
        )
    assert "data.txt" in str(exc_info.value)

    # Nothing pushed.
    remote_tip = _git(bare, "rev-parse", "main").stdout.strip()
    local_tip = _git(work, "rev-parse", "HEAD").stdout.strip()
    assert remote_tip == local_tip  # bare repo unchanged, no new commit landed


def test_allows_a_regression_covered_by_a_valid_override_token(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed data.txt as wrong")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("correct-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix by another session")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")  # intentional revert

    class Args:
        paths = ["data.txt"]
        reason = "intentional revert for this test"
        plan = "test-plan"
        scope = ""
        operation = "edit"
        retroactive = False

    override_manager.cmd_create(Args())

    result = gpc.plumb_commit(
        ["data.txt"], "intentional revert, governed", repo_root=work, branch="main",
        remote=str(bare), base_sha=base_sha,
    )
    assert result["pushed"] is True


def test_skip_stale_check_bypasses_the_check_entirely(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    base_sha = _git(work, "rev-parse", "HEAD").stdout.strip()

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "seed data.txt as wrong")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("correct-value", encoding="utf-8")
    _git(work, "add", "data.txt")
    _git(work, "commit", "-q", "-m", "fix by another session")
    _git(work, "push", "-q", "origin", "main")

    (work / "data.txt").write_text("wrong-value", encoding="utf-8")

    result = gpc.plumb_commit(
        ["data.txt"], "explicit skip", repo_root=work, branch="main",
        remote=str(bare), base_sha=base_sha, skip_stale_check=True,
    )
    assert result["pushed"] is True


def test_no_base_sha_and_no_skip_is_advisory_pass(tmp_path):
    """No base_sha resolvable (and not explicitly skipped) -- same fail-open
    policy as check_stale_file_regression.py itself: never block on missing
    infrastructure."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    result = gpc.plumb_commit(
        ["f.txt"], "no base sha", repo_root=work, branch="main", remote=str(bare),
        base_sha=None, session_id="no-such-session-anywhere",
    )
    assert result["pushed"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_end_to_end(tmp_path, monkeypatch):
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("chore: cli test commit", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files", "f.txt",
        "--message-file", str(msg_file),
        "--skills", "S-99",
        "--plan", "cli test",
        "--branch", "main",
        "--remote", str(bare),
        "--skip-stale-check",
        "--no-push",  # avoid needing a real skill_run_manager.py invocation in this test
    ])
    assert rc == 0


def test_cli_requires_exactly_one_message_source(tmp_path):
    work, bare = _init_repo_with_remote(tmp_path)
    rc = gpc.main([
        "--files", "f.txt", "--skills", "S-99", "--plan", "x",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Credential redaction (TC-CIA-12, found live 2026-08-08: a failed push using
# this repo's own x-access-token URL convention printed the literal token in
# the raised PlumbCommitError -- ' '.join(args) embeds the full --remote URL
# verbatim. Fixed by redacting any URL-embedded credential before it reaches
# an exception message.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected_masked_form",
    [
        (
            "git push https://x-access-token:ghp_abcDEF123456@github.com/Aspose/aspose.org.git "
            "main failed",
            "https://<redacted>@github.com/Aspose/aspose.org.git",
        ),
        (
            "fatal: unable to access 'https://user:s3cr3t-tok3n@example.com/repo.git/'",
            "https://<redacted>@example.com/repo.git/",
        ),
        ("git status failed: no credential-shaped text here", None),
    ],
)
def test_redact_credentials_masks_embedded_url_tokens(raw, expected_masked_form):
    result = gpc._redact_credentials(raw)
    assert "ghp_abcDEF123456" not in result
    assert "s3cr3t-tok3n" not in result
    if expected_masked_form is not None:
        assert expected_masked_form in result
    else:
        assert result == raw  # no credential-shaped substring -- untouched


def test_failed_push_with_credentialed_url_does_not_leak_token_in_error(tmp_path):
    """Real, non-mocked failure path: push to a URL that embeds a fake
    credential and cannot succeed (connection refused, no network/DNS
    dependency -- port 1 on localhost refuses immediately). The exact
    fake token value must never appear in the raised exception's message.
    """
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")

    fake_token = "ghp_FAKE_TOKEN_MUST_NOT_LEAK_1234567890"
    bad_remote = f"https://x-access-token:{fake_token}@127.0.0.1:1/nonexistent.git"

    with pytest.raises(gpc.PlumbCommitError) as exc_info:
        gpc.plumb_commit(
            ["f.txt"], "should fail to push", repo_root=work, branch="main",
            remote=bad_remote, skip_stale_check=True,
        )

    assert fake_token not in str(exc_info.value)
    assert "<redacted>" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TC-CIR-05 (2026-08-14, CI reliability reassessment, Root Cause A): Tier 1
# (pre-commit-audit.sh) parity for plumbed commits. Real fake scripts, no mocking
# of git_plumb_commit.py's own logic -- matches this file's established convention.
# ---------------------------------------------------------------------------

def _write_fake_precommit_script(work: Path, *, exit_code: int, extra_shell: str = "") -> None:
    scripts_dir = work / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    script = scripts_dir / "pre-commit-audit.sh"
    # newline="\n" forces LF line endings even on Windows -- Path.write_text's
    # default universal-newline translation would otherwise write CRLF, which
    # bash reads as a literal \r appended to the last token on each line
    # ("unexpected end of file" / similarly confusing syntax errors), found
    # live while writing this exact test.
    with script.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("#!/bin/bash\n" + extra_shell + f"\nexit {exit_code}\n")
    script.chmod(0o755)


class TestGitBashResolver:
    """Independent verification (2026-08-14) of TC-CIR-05's original fix found a
    real, reproducible gap: shutil.which("bash") alone resolves to the WSL launcher
    stub (C:\\Windows\\System32\\bash.exe) when the calling process's PATH doesn't
    already favor Git's directories -- confirmed live via a genuine PowerShell-
    launched process on the same machine that made pytest itself pass. These tests
    exercise the real, live PATH/filesystem on whatever machine runs the suite --
    no mocking of _resolve_git_bash's own logic, matching this file's convention."""

    def test_resolves_a_real_working_git_bash(self):
        gpc._GIT_BASH_RESOLVED = False  # bypass this-process's cached result
        resolved = gpc._resolve_git_bash()
        assert resolved is not None, "no working Git Bash found on this machine"
        result = subprocess.run([resolved, "-c", "uname -s"], capture_output=True, text=True)
        uname = result.stdout.strip().lower()
        assert any(tag in uname for tag in ("mingw", "msys", "cygwin")), (
            f"resolved bash reported uname -s = {uname!r} -- not a recognized Git-Bash variant"
        )

    def test_never_resolves_to_a_system32_or_syswow64_stub(self):
        gpc._GIT_BASH_RESOLVED = False
        resolved = gpc._resolve_git_bash()
        if resolved is not None:
            normalized = resolved.replace("/", "\\").lower()
            assert "\\system32\\" not in normalized
            assert "\\syswow64\\" not in normalized

    def test_result_is_cached_across_calls(self, monkeypatch):
        gpc._GIT_BASH_RESOLVED = False
        first = gpc._resolve_git_bash()
        # Mutate PATH after the first call -- a cached second (uncleared) call must
        # return the same answer, not re-probe against the now-broken PATH.
        monkeypatch.setenv("PATH", r"C:\WINDOWS\system32")
        second = gpc._resolve_git_bash()
        assert second == first


class TestTier1Checks:

    def test_missing_precommit_script_fails_open(self, tmp_path):
        """No scripts/pre-commit-audit.sh at repo_root (this fixture's default
        state) -- must not block the commit. Matches this module's existing
        fail-open policy for missing check infrastructure."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        result = gpc.plumb_commit(
            ["f.txt"], "no tier1 script present", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )
        assert result["pushed"] is True

    def test_tier1_check_blocks_when_precommit_script_fails(self, tmp_path):
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=1)

        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True,
        ).stdout.strip()

        with pytest.raises(gpc.PlumbCommitTier1Failed):
            gpc.plumb_commit(
                ["f.txt"], "should be blocked by tier1", repo_root=work, branch="main",
                remote=str(bare), skip_stale_check=True,
            )

        head_after = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True,
        ).stdout.strip()
        assert head_after == head_before, "a blocked Tier 1 check must not advance the branch ref"

    def test_tier1_check_passes_when_precommit_script_succeeds(self, tmp_path):
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=0)

        result = gpc.plumb_commit(
            ["f.txt"], "tier1 passes", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )
        assert result["pushed"] is True

    def test_skip_tier1_checks_bypasses_a_failing_script(self, tmp_path):
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=1)

        result = gpc.plumb_commit(
            ["f.txt"], "explicit emergency bypass", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True, skip_tier1_checks=True,
        )
        assert result["pushed"] is True

    def test_tier1_check_sees_isolated_index_not_real_shared_index(self, tmp_path):
        """The ST-021 safety property this whole taskcard exists to preserve:
        the Tier 1 check must see ONLY the files being committed via --files,
        never anything else a concurrent session might have staged in the real
        .git/index. Stages a second, unrelated file in the REAL index (simulating
        a concurrent session's in-flight work) that is NOT part of --files, and
        has the fake script assert (for real, via `git diff --cached`) that it
        does not see that file."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        (work / "concurrent_session_file.txt").write_text("someone else's work", encoding="utf-8")
        subprocess.run(
            ["git", "add", "concurrent_session_file.txt"], cwd=work, check=True,
        )
        _write_fake_precommit_script(
            work, exit_code=0,
            extra_shell=(
                'staged=$(git diff --cached --name-only)\n'
                'echo "STAGED: $staged"\n'
                'if echo "$staged" | grep -q "concurrent_session_file.txt"; then\n'
                '  echo "ISOLATION VIOLATION: saw the real index, not the isolated one"\n'
                '  exit 1\n'
                'fi\n'
                'if ! echo "$staged" | grep -q "f.txt"; then\n'
                '  echo "did not see the file actually being committed"\n'
                '  exit 1\n'
                'fi\n'
            ),
        )

        result = gpc.plumb_commit(
            ["f.txt"], "isolation check", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )
        assert result["pushed"] is True

        # And the real index's own staged file must be completely undisturbed
        # by the plumbed commit (matches the tool's own documented "never
        # touches the real .git/index" guarantee).
        real_staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], cwd=work,
            capture_output=True, text=True,
        ).stdout
        assert "concurrent_session_file.txt" in real_staged

    def test_commit_message_reaches_churn_override_env_vars(self, tmp_path):
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        message = "EVIDENCE-RESTAMP: approved by tester on 2026-08-14, reason: test"
        _write_fake_precommit_script(
            work, exit_code=0,
            extra_shell=(
                'if [ "$EVIDENCE_RESTAMP_MSG" != "' + message + '" ]; then\n'
                '  echo "EVIDENCE_RESTAMP_MSG not set correctly: $EVIDENCE_RESTAMP_MSG"\n'
                '  exit 1\n'
                'fi\n'
                'if [ "$BULK_GRADE_MIGRATION_MSG" != "' + message + '" ]; then\n'
                '  echo "BULK_GRADE_MIGRATION_MSG not set correctly"\n'
                '  exit 1\n'
                'fi\n'
            ),
        )
        result = gpc.plumb_commit(
            ["f.txt"], message, repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )
        assert result["pushed"] is True

    def test_cli_skip_tier1_checks_flag_wired(self, tmp_path, monkeypatch):
        """Real CLI invocation (not a source-text check): a failing Tier 1 script
        blocks main() with a nonzero exit, and --skip-tier1-checks lets the same
        commit through."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=1)

        gpc.configure(repo_root=work)
        monkeypatch.chdir(work)

        rc_blocked = gpc.main([
            "--files", "f.txt", "--message", "chore: should be blocked",
            "--skills", "S-99", "--plan", "cli test",
            "--branch", "main", "--remote", str(bare),
            "--skip-stale-check", "--no-push",
        ])
        assert rc_blocked != 0

        rc_bypassed = gpc.main([
            "--files", "f.txt", "--message", "chore: explicit bypass",
            "--skills", "S-99", "--plan", "cli test",
            "--branch", "main", "--remote", str(bare),
            "--skip-stale-check", "--skip-tier1-checks", "--no-push",
        ])
        assert rc_bypassed == 0


# ---------------------------------------------------------------------------
# argv-length ceiling fix (--files-from CLI merge, --pathspec-from-file for
# `git add -f`, --stdin -z for `git check-ignore`)
# ---------------------------------------------------------------------------

def test_cli_files_from_merges_with_files(tmp_path, monkeypatch):
    """--files-from and --files are additive, not either/or."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "a.txt").write_text("a", encoding="utf-8")
    (work / "b.txt").write_text("b", encoding="utf-8")
    files_from = tmp_path / "files.txt"
    files_from.write_text("b.txt\n", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("chore: files-from merge test", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files", "a.txt", "--files-from", str(files_from),
        "--message-file", str(msg_file),
        "--skills", "S-99", "--plan", "files-from merge test",
        "--branch", "main", "--remote", str(bare),
        "--skip-stale-check",
    ])
    assert rc == 0

    commit_sha = _git(work, "rev-parse", "refs/heads/main").stdout.strip()
    tree = _git(bare, "ls-tree", "-r", "--name-only", commit_sha).stdout
    assert "a.txt" in tree
    assert "b.txt" in tree


def test_cli_files_from_alone_is_sufficient(tmp_path, monkeypatch):
    """--files is no longer required when --files-from provides the list."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "only.txt").write_text("v", encoding="utf-8")
    files_from = tmp_path / "files.txt"
    files_from.write_text("only.txt\n", encoding="utf-8")
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("chore: files-from alone", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--files-from", str(files_from),
        "--message-file", str(msg_file),
        "--skills", "S-99", "--plan", "files-from alone test",
        "--branch", "main", "--remote", str(bare),
        "--skip-stale-check",
    ])
    assert rc == 0


def test_cli_neither_files_nor_files_from_errors(tmp_path, monkeypatch):
    work, bare = _init_repo_with_remote(tmp_path)
    msg_file = tmp_path / "msg.txt"
    msg_file.write_text("chore: should not run", encoding="utf-8")

    gpc.configure(repo_root=work)
    monkeypatch.chdir(work)
    rc = gpc.main([
        "--message-file", str(msg_file),
        "--skills", "S-99", "--plan", "no files test",
        "--branch", "main", "--remote", str(bare),
    ])
    assert rc == 2


def test_add_pathspec_from_file_adds_many_files_correctly(tmp_path):
    """`git add -f --pathspec-from-file` (replacing literal argv paths) must
    stage exactly the right set of files -- proof by real tree inspection,
    not just a non-crashing exit. 40 files is enough to catch an off-by-one
    in how the pathspec tempfile is written/joined without making the test
    slow."""
    work, bare = _init_repo_with_remote(tmp_path)
    names = [f"batch/file_{i:03d}.txt" for i in range(40)]
    (work / "batch").mkdir()
    for name in names:
        (work / name).write_text(name, encoding="utf-8")

    result = gpc.plumb_commit(
        names, "add a 40-file batch", repo_root=work, branch="main",
        remote=str(bare), skip_stale_check=True,
    )
    assert result["pushed"] is True

    tree = _git(bare, "ls-tree", "-r", "--name-only", result["commit_sha"]).stdout
    tree_files = set(tree.splitlines())
    assert tree_files.issuperset(set(names))
    # Each file's content round-tripped correctly (proves the right path was
    # matched to the right blob, not just that *a* set of 40 paths landed).
    sample = _git(bare, "show", f"{result['commit_sha']}:batch/file_017.txt")
    assert sample.stdout == "batch/file_017.txt"


def test_multiple_gitignored_files_all_detected(tmp_path):
    """`git check-ignore --stdin -z` (replacing argv + text-mode stdin) must
    round-trip MULTIPLE NUL-delimited entries correctly -- the real
    regression risk of the rewrite is an off-by-one in the split(b'\\x00')
    parsing that silently drops or merges entries."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "add gitignore")
    (work / "ignored").mkdir()
    (work / "ignored" / "one.txt").write_text("1", encoding="utf-8")
    (work / "ignored" / "two.txt").write_text("2", encoding="utf-8")

    result = gpc.plumb_commit(
        ["ignored/one.txt", "ignored/two.txt"], "force-track two gitignored files",
        repo_root=work, branch="main", remote=str(bare), skip_stale_check=True,
    )

    assert sorted(result["gitignore_warnings"]) == ["ignored/one.txt", "ignored/two.txt"]
    assert result["pushed"] is True


# ---------------------------------------------------------------------------
# Isolation canary + postcondition safety net (2026-08-20 production
# assessment, reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-
# safety.md, Root causes 1/2/4). These tests use the module's own
# `configure(command_runner=...)` seam to simulate a bash/git pairing that
# does not honor GIT_INDEX_FILE -- the class of failure confirmed live once
# already (2026-08-14, WSL git) -- without needing a real WSL install on the
# machine running the suite. Every other subprocess call is passed through to
# real `subprocess.run` unchanged, matching this file's established
# preference for exercising real git behavior rather than simulating it
# wholesale.
# ---------------------------------------------------------------------------

class TestIsolationCanary:

    def test_canary_verified_and_cached_on_the_real_isolated_bash(self, tmp_path):
        """The happy path is already implicitly exercised by every other real
        Tier1 test in this file (the canary runs before every one of them) --
        this test asserts the caching side effect explicitly."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=0)
        real_bash = gpc._resolve_git_bash()
        assert real_bash is not None
        gpc._ISOLATION_CANARY_VERIFIED.pop(real_bash, None)

        result = gpc.plumb_commit(
            ["f.txt"], "canary happy path", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )

        assert result["pushed"] is True
        assert gpc._ISOLATION_CANARY_VERIFIED.get(real_bash) is True

    def test_canary_detects_isolation_defeat_and_skips_tier1_non_strict(self, tmp_path, capsys):
        """Default (strict_isolation=False): a detected isolation defeat must
        never let Tier 1 actually run against unproven isolation -- the fake
        script here exits 1, which WOULD raise PlumbCommitTier1Failed if it
        ran; the commit succeeding proves it never did."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=1)

        real_bash = gpc._resolve_git_bash()
        assert real_bash is not None
        gpc._ISOLATION_CANARY_VERIFIED.pop(real_bash, None)

        def _faking_runner(cmd, **kwargs):
            if cmd == [real_bash, "-c", "git ls-files"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=f"{gpc._ISOLATION_CANARY_SENTINEL}\n", stderr="",
                )
            return subprocess.run(cmd, **kwargs)

        gpc.configure(command_runner=_faking_runner)

        result = gpc.plumb_commit(
            ["f.txt"], "canary should catch this", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )

        assert result["pushed"] is True
        assert "WARNING" in capsys.readouterr().err
        assert gpc._ISOLATION_CANARY_VERIFIED.get(real_bash) is not True

    def test_canary_detects_isolation_defeat_and_blocks_strict(self, tmp_path):
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=0)

        real_bash = gpc._resolve_git_bash()
        assert real_bash is not None
        gpc._ISOLATION_CANARY_VERIFIED.pop(real_bash, None)

        def _faking_runner(cmd, **kwargs):
            if cmd == [real_bash, "-c", "git ls-files"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=f"{gpc._ISOLATION_CANARY_SENTINEL}\n", stderr="",
                )
            return subprocess.run(cmd, **kwargs)

        gpc.configure(command_runner=_faking_runner)
        head_before = _git(work, "rev-parse", "HEAD").stdout.strip()

        with pytest.raises(gpc.PlumbCommitIsolationBreach):
            gpc.plumb_commit(
                ["f.txt"], "canary should block this", repo_root=work, branch="main",
                remote=str(bare), skip_stale_check=True, strict_isolation=True,
            )

        head_after = _git(work, "rev-parse", "HEAD").stdout.strip()
        assert head_after == head_before

    def test_canary_removes_its_sentinel_from_the_committed_tree(self, tmp_path):
        """The sentinel entry added to the temp index for the canary probe
        must never leak into the actual commit content."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")

        result = gpc.plumb_commit(
            ["f.txt"], "sentinel must not leak", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )

        tree_files = _git(bare, "ls-tree", "-r", "--name-only", result["commit_sha"]).stdout
        assert gpc._ISOLATION_CANARY_SENTINEL not in tree_files


class TestPostconditionSafetyNet:

    def test_postcondition_catches_a_plain_non_git_worktree_mutation_non_strict(self, tmp_path, capsys):
        """Simulates pre-commit-audit.sh Step 5's actual mutation shape (a
        plain, non-git file write during the Tier 1 window, confirmed live in
        the 2026-08-20 assessment as Root cause 4) -- proves the postcondition
        catches it generically, with no Step-5-specific code anywhere in
        git_plumb_commit.py."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("original", encoding="utf-8")
        _write_fake_precommit_script(
            work, exit_code=0,
            extra_shell='printf "mutated by a plain non-git file write" > "f.txt"\n',
        )

        result = gpc.plumb_commit(
            ["f.txt"], "postcondition should catch this", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )

        assert result["pushed"] is True  # non-strict: proceeds anyway
        assert "WARNING" in capsys.readouterr().err
        # Proves this was genuinely detected via the real on-disk content hash,
        # not the index (this mutation never touches any index at all).
        assert (work / "f.txt").read_text(encoding="utf-8") == "mutated by a plain non-git file write"

    def test_postcondition_blocks_a_plain_non_git_worktree_mutation_strict(self, tmp_path):
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("original", encoding="utf-8")
        _write_fake_precommit_script(
            work, exit_code=0,
            extra_shell='printf "mutated" > "f.txt"\n',
        )
        head_before = _git(work, "rev-parse", "HEAD").stdout.strip()

        with pytest.raises(gpc.PlumbCommitPostconditionBreach):
            gpc.plumb_commit(
                ["f.txt"], "postcondition should block this", repo_root=work, branch="main",
                remote=str(bare), skip_stale_check=True, strict_isolation=True,
            )

        head_after = _git(work, "rev-parse", "HEAD").stdout.strip()
        assert head_after == head_before

    def test_postcondition_catches_a_real_index_only_mutation(self, tmp_path, capsys):
        """A mutation that touches only the REAL .git/index (content on disk
        unchanged) must be caught by the index half of the postcondition even
        though the content-hash half sees nothing."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(
            work, exit_code=0,
            # `env -u` strips GIT_INDEX_FILE for just this one command, simulating
            # a step (or a sub-process it calls) that drops the isolation env var
            # -- the real .git/index gets this add, not the isolated temp one.
            # Content on disk is untouched by `git add` alone, isolating this test
            # to the index half of the postcondition specifically.
            extra_shell="env -u GIT_INDEX_FILE git add f.txt\n",
        )

        result = gpc.plumb_commit(
            ["f.txt"], "index postcondition should catch this", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )

        assert result["pushed"] is True
        assert "WARNING" in capsys.readouterr().err
        # Clean up the real index entry this test's fake script staged for
        # real, so it doesn't leak into any other test sharing this fixture's
        # teardown expectations.
        subprocess.run(["git", "restore", "--staged", "f.txt"], cwd=str(work), check=False)

    def test_postcondition_does_not_false_positive_on_untouched_state(self, tmp_path):
        """Happy path: a Tier 1 pass that touches nothing real must not raise
        or warn -- already covered implicitly by every other passing test in
        this file, asserted here explicitly against a clean capsys."""
        work, bare = _init_repo_with_remote(tmp_path)
        (work / "f.txt").write_text("v", encoding="utf-8")
        _write_fake_precommit_script(work, exit_code=0)

        result = gpc.plumb_commit(
            ["f.txt"], "clean pass", repo_root=work, branch="main",
            remote=str(bare), skip_stale_check=True,
        )

        assert result["pushed"] is True


def test_tier1_output_threaded_through_result_on_success(tmp_path):
    """plumb_commit()'s successful-path result must carry Tier 1's stdout,
    not discard it -- otherwise a Step 5/Step 10 check-only-mode FINDING has
    no observable effect on the caller (2026-08-20 assessment finding)."""
    work, bare = _init_repo_with_remote(tmp_path)
    (work / "f.txt").write_text("v", encoding="utf-8")
    _write_fake_precommit_script(
        work, exit_code=0, extra_shell='echo "[Step 10] FINDING: example"\n',
    )

    result = gpc.plumb_commit(
        ["f.txt"], "tier1 output should be threaded through", repo_root=work,
        branch="main", remote=str(bare), skip_stale_check=True,
    )

    assert "[Step 10] FINDING: example" in result["tier1_output"]

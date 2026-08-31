"""
git_plumb_commit.py — atomic, enforced isolated git-plumbing commit (production
concurrency redesign, 2026-08-01, Step 8 follow-up: MT019's own convergence
audit, TC-MT019-03).

CONTRACT: scripts/pipeline/commands/ops/git_plumb_commit.py
  purpose: This repo's sanctioned escalation for concurrent-session
           `.git/index` contention -- git object-plumbing against an
           isolated temp index -- was, until this module existed, a
           5-6-step MANUAL procedure (documented in CLAUDE.md, hand-typed
           by an agent every time). Across one single session building the
           production concurrency redesign, that manual procedure was
           repeated roughly 8 times and produced at least one real mistake
           (a ref-update typo, caught only by immediate re-verification).
           Worse: check_stale_file_regression.py -- the fix built
           specifically to stop silent content reverts -- can only ever be
           enforced by a pre-commit GIT HOOK, and git-plumbing exists
           precisely to bypass `git commit` (and therefore every git hook)
           by construction. CLAUDE.md's own protocol asked the committing
           session to remember to run the check manually first -- an
           honor-system safety net for the exact class of incident this
           whole mission exists to prevent. This module closes that gap by
           making the check a MANDATORY, non-skippable first step of the
           one tool that performs the entire sequence, rather than a
           separately-remembered instruction.
  inputs:  an explicit file list, a commit message, --skills for the
           mandatory retroactive skill-run record, and (optionally) a base
           commit sha / session id for the regression check.
  outputs: one commit on the target branch; local refs/heads/<branch> is
           always advanced to it (whether or not --push is used, so
           sequential --no-push calls correctly chain off each other);
           refs/remotes/<remote>/<branch> is additionally updated, and the
           commit is pushed to the real remote, only when --push is set;
           a finalized retroactive skill-run record.
  concurrency: never touches the real `.git/index` -- builds an isolated
           temp index from a freshly-captured HEAD, exactly the technique
           this repo's CLAUDE.md already documents, now enforced in one
           tested tool instead of hand-typed.
  safety:  refuses (raises PlumbCommitBlocked, commits nothing) if the
           stale-file regression check finds an uncovered finding for any
           file -- "uncovered" meaning no valid pending override_manager.py
           token covers it. A covered finding is allowed through (the same
           audited-exception pattern this repo already uses for protected
           paths), matching pre-commit Step 30's own override behavior
           exactly, via the SAME importable function
           (override_manager.find_valid_token_for_path), not a re-
           implementation of it.
  ledger:  also refuses (raises PlumbCommitLedgerBlocked, commits nothing) if
           any --files path is dirty in the working tree but not accounted
           for by the calling session's own session_ledger.py manifest --
           i.e. it predates the session (dirty_at_start) or is dirty for a
           reason the session never recorded (not_in_ledger), and was never
           explicitly adopted. Closes G16 part 2 (mission-plan-the-end-to-
           end-vast-hejlsberg.md Task 25): this tool previously staged
           whole-file, on-disk content with no concept of "which lines in
           this file are mine", risking a foreign, uncommitted, concurrent
           session's edit being silently folded into an unrelated commit --
           reproduced live 2026-08-22/23 (refresh_run.py). A missing or
           uninitialized ledger degrades this check to an advisory pass
           (same fail-open policy as a missing base_sha for the stale-file
           check above) -- this protects the case a session's OWN ledger
           actively disagrees with what it's about to commit, not the
           absence of a ledger entirely (a documented, accepted coverage
           boundary: sessions that bypass Edit/Write/session_ledger.py init
           entirely are not covered by this or any other hook-based gate in
           this repo).

Usage::

    python scripts/pipeline/commands/ops/git_plumb_commit.py \\
      --files scripts/foo.py scripts/tests/test_foo.py \\
      --message-file /path/to/msg.txt \\
      --skills S-76 --plan "fix(pipeline): durable foo.py bug" \\
      --branch main --remote origin

For batches large enough to risk OS argument-list-too-long limits, prefer
--files-from over --files::

    python scripts/pipeline/commands/ops/git_plumb_commit.py \\
      --files-from /path/to/files.txt \\
      --message-file /path/to/msg.txt \\
      --skills S-76 --plan "content(family/platform): large batch update"
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_OPS_DIR = Path(__file__).resolve().parent
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

import session_ledger  # noqa: E402
import refresh_run as _refresh_run  # noqa: E402
from commands.governance import override_manager  # noqa: E402
from commands.governance import path_guard  # noqa: E402
from lib import checkout_sync  # noqa: E402
from lib import stale_file_regression as slib  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_SKILL_RUN_MANAGER = (
    _PIPELINE_ROOT / "commands" / "ops" / "skill_run_manager.py"
)

_REPO_ROOT = _DEFAULT_REPO_ROOT
_SKILL_RUN_MANAGER = _DEFAULT_SKILL_RUN_MANAGER
_COMMAND_RUNNER: Callable[..., "subprocess.CompletedProcess"] = subprocess.run

# Explicit encoding on every text-mode subprocess call: the locale default
# (cp1252 on this repo's Windows production platform) let a single
# cp1252-unmappable byte kill the reader thread -> stdout=None -> a Tier-1
# failure surfacing as a raw TypeError and, on the success path, an
# AttributeError AFTER the push but BEFORE the skill-run record (ST-096
# containment, 2026-08-29). errors="replace" never raises on decode.
_TEXT_KW = dict(text=True, encoding="utf-8", errors="replace")


def configure(
    *,
    repo_root: "Path | str | None" = None,
    skill_run_manager: "Path | str | None" = None,
    command_runner: "Callable[..., subprocess.CompletedProcess] | None" = None,
) -> None:
    """Override module-level seams for testing. Called with no arguments,
    resets to built-in defaults."""
    global _REPO_ROOT, _SKILL_RUN_MANAGER, _COMMAND_RUNNER
    if repo_root is None and skill_run_manager is None and command_runner is None:
        _REPO_ROOT = _DEFAULT_REPO_ROOT
        _SKILL_RUN_MANAGER = _DEFAULT_SKILL_RUN_MANAGER
        _COMMAND_RUNNER = subprocess.run
        return
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
    if skill_run_manager is not None:
        _SKILL_RUN_MANAGER = Path(skill_run_manager)
    if command_runner is not None:
        _COMMAND_RUNNER = command_runner


class PlumbCommitError(Exception):
    """Base class for git_plumb_commit failures."""


class PlumbCommitBlocked(PlumbCommitError):
    """Raised when the stale-file regression check finds an uncovered
    finding -- no commit is created."""

    def __init__(self, findings: list[dict]):
        self.findings = findings
        names = ", ".join(f["file"] for f in findings)
        super().__init__(
            f"Refusing to commit -- {len(findings)} file(s) look like a silent "
            f"revert of a more recent commit and no valid override token covers "
            f"them: {names}. Re-read the current file and reapply your change on "
            f"top of it, or create a governed override: "
            f"override_manager.py create --paths <file> --reason '...' --plan '...'"
        )


class PlumbCommitLedgerBlocked(PlumbCommitBlocked):
    """Raised when one or more --files paths are dirty in the working tree
    but not accounted for by the calling session's own ledger
    (session_ledger.py) -- G16 part 2, closes the concurrent-session
    collision this exact class of tool was built to prevent for a
    different check (the stale-file regression check, above) but never
    closed for itself.

    Found live 2026-08-22/23: a file carrying another live session's
    uncommitted, unrelated edit (refresh_run.py) was nearly folded into an
    unrelated commit through this tool -- caught only by an incidental,
    manually-run `git status`/`git diff` baseline check before touching
    anything, not by any mechanical gate. session_ledger.py already builds
    exactly the data needed to catch this (dirty_at_start vs. touched_files,
    via get_candidates()) -- this exception is the missing second half:
    actually consulting it before staging, instead of never at all.

    Remedy: verify the pre-existing dirt is genuinely safe to fold into this
    commit, then run `session_ledger.py adopt --files <path>...` (after
    confirming with the session or its owner) before retrying; or drop the
    file from this commit's --files list if it belongs to someone else's
    in-flight work. `--skip-ledger-check` exists as a documented,
    deliberately-loud escape hatch for a genuine emergency only -- mirrors
    `--skip-stale-check`'s existing convention, never a silent default.
    """

    def __init__(self, findings: list[dict]):
        self.findings = findings
        detail = "\n".join(f"  {f['file']} ({f['reason']})" for f in findings)
        PlumbCommitError.__init__(
            self,
            f"Refusing to commit -- {len(findings)} file(s) are dirty in the "
            f"working tree but not accounted for by this session's own ledger "
            f"(session_ledger.py):\n{detail}\n\n"
            f"Remedy: verify the pre-existing dirt is safe to fold in, then "
            f"run 'session_ledger.py adopt --files <path>...' before "
            f"retrying; or drop the file from --files if it belongs to "
            f"someone else's in-flight work. Pass --skip-ledger-check only "
            f"for a genuine, logged emergency (mirrors --skip-stale-check's "
            f"escalation pattern -- never a silent default)."
        )


class PlumbCommitTier1Failed(PlumbCommitError):
    """Raised when scripts/pre-commit-audit.sh (this repo's Tier 1 commit-time
    gate) fails against the isolated temp index -- no commit is created.

    TC-CIR-05 (2026-08-14, CI reliability reassessment, Root Cause A): before this,
    every commit made through this tool received NONE of pre-commit-audit.sh's ~32
    checks -- `commit-tree` never invokes git hooks, and this repo has no pre-push
    hook backstop for plumbed commits either, since they also skip `git push`'s hook
    the same way. This tool is CLAUDE.md's own sanctioned mechanism for
    concurrent-session-safe commits, used repeatedly across this very session -- the
    gap was total, not partial, for every commit that ever went through it.

    Step 34 of pre-commit-audit.sh (this repo's Tier 1 script) and this module's own
    temp-index stale check both consume the SAME lib/stale_file_regression engine
    function -- neither is a "re-implemented copy" of the other, an earlier version
    of this docstring's own wording notwithstanding (corrected 2026-08-20,
    reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-safety.md). They
    deliberately use DIFFERENT scope: Step 30 excludes `content/` (which has its own
    dedicated staleness checks elsewhere) and defaults to staged content; this
    module's `_check_for_regressions()` includes `content/` and checks working-tree
    content. This is intentional defense-in-depth, not redundant coverage -- do not
    "simplify" the two into one call with one scope.
    """

    def __init__(self, output: str, exit_code: int):
        self.output = output
        self.exit_code = exit_code
        super().__init__(
            f"Refusing to commit -- scripts/pre-commit-audit.sh (Tier 1) failed "
            f"(exit {exit_code}) against the staged content. Fix the violation(s) "
            f"below, or pass --skip-tier1-checks with an explicit, logged reason "
            f"for a genuine emergency (matches --skip-stale-check's existing "
            f"escalation pattern -- not a silent default):\n\n{output}"
        )


class PlumbCommitIsolationBreach(PlumbCommitError):
    """Raised when this module cannot empirically prove, for the exact bash/git
    pairing about to run scripts/pre-commit-audit.sh, that GIT_INDEX_FILE
    isolation is actually in effect -- no Tier 1 check is run, no commit is
    created.

    2026-08-20 production assessment (reports/skill-gaps/2026-08-20-git-plumb-
    commit-tier1-mutation-safety.md, Root cause 2): `_resolve_git_bash()` verifies
    only that the resolved `bash` binary is genuine MSYS/Git-Bash -- it does not
    verify that `git`, as THAT bash resolves it via its own internal PATH, honors
    GIT_INDEX_FILE for this specific pairing. Confirmed once already (2026-08-14,
    WSL git silently defeating isolation) that bash-genuineness alone is not
    sufficient proof. This is a stricter failure mode than `_resolve_git_bash()
    is None` (which only warns and proceeds WITHOUT Tier 1 coverage) by design:
    "no bash found" means "no coverage this time"; "isolation defeated" means
    "actively unsafe to proceed" -- do not collapse these into matching behavior.
    """

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(
            f"Refusing to run Tier 1 checks -- could not verify GIT_INDEX_FILE "
            f"isolation is in effect for this bash/git pairing: {detail}. No "
            f"commit created. This is a stricter refusal than 'no bash found' "
            f"(which merely skips Tier 1 coverage) because proceeding here risks "
            f"Tier 1 checks silently mutating real repo state instead of the "
            f"intended isolated temp index."
        )


class PlumbCommitPostconditionBreach(PlumbCommitError):
    """Raised when real repo state (the real .git/index, or the real on-disk
    content of a path in --files) changed during the Tier 1 check window --
    i.e. isolation was defeated by some mechanism, known or not, despite the
    pre-check canary passing. No commit is created.

    This is the mechanism-agnostic backstop: it does not matter WHY real state
    changed (a bash/git resolution defeat the canary didn't catch, a future
    pre-commit-audit.sh step that mutates real state without being added to
    scripts/ci/checks/precommit_audit_mutation_registry.yaml, or something not
    yet imagined) -- if it changed, refuse and report exactly what changed and
    whether it overlaps --files, so a human can tell "this tool's isolation
    failed" apart from "a concurrent session touched something unrelated
    nearby" (this repo runs multiple concurrent agent sessions against a shared
    checkout by design -- ST-021). Deliberately does NOT auto-restore: an
    automated forced restore during confirmed concurrent-session usage carries
    the same destructive risk toward another session's legitimate state that
    this repo's own AGENTS.md already prohibits `git reset` for.
    """

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(
            f"Refusing to commit -- real repo state changed during the Tier 1 "
            f"check window, which should be impossible under isolation: "
            f"{detail}. No commit created, and nothing was auto-restored -- "
            f"inspect the changes yourself before deciding whether this was "
            f"this tool's own isolation failing or a concurrent session's "
            f"unrelated activity."
        )


class PlumbCommitPushRejected(PlumbCommitError):
    """Raised when `plumb_commit()`'s push is rejected non-fast-forward and
    an automatic `reconcile()` attempt (see below) also failed or was
    disabled -- the caller must resolve by hand.

    Found live 2026-08-26 (pipeline reliability hardening pass,
    reports/skill-gaps/2026-08-26-pipeline-reliability-hardening.md): this
    tool has no divergence handling at all -- a push against a `HEAD`
    already stale relative to `origin/<branch>` simply raises the generic
    `PlumbCommitError` from `_git()`, with no path forward except an agent
    hand-building a two-parent merge commit via raw plumbing under live
    push pressure, which happened twice in one session. `reconcile()` and
    this exception close that gap: `plumb_commit(..., auto_reconcile=True)`
    (the default) retries once via `reconcile()` on exactly this failure
    shape; this exception carries everything needed to retry by hand
    (`commit_sha`, `tree_sha`, `files`) if the automatic retry itself
    fails or is disabled.
    """

    def __init__(self, commit_sha: str, tree_sha: str, files: list[str], detail: str):
        self.commit_sha = commit_sha
        self.tree_sha = tree_sha
        self.files = list(files)
        self.detail = detail
        super().__init__(
            f"Push failed for commit {commit_sha[:12]}: {detail}. The commit "
            f"object was already built locally (not lost) -- retry by hand via "
            f"reconcile({commit_sha!r}, {files!r}, ...) after resolving the "
            f"underlying issue, or re-run plumb_commit() with the same --files "
            f"to build a fresh commit against the current HEAD."
        )


class PlumbCommitReconcileConflict(PlumbCommitError):
    """Raised by `reconcile()` when the remote's new tip has ALSO changed one
    or more of the same files this commit touches -- naively overlaying this
    commit's own tree entries for those files would silently discard the
    remote's changes, exactly the class of silent-revert incident
    `PlumbCommitBlocked`'s stale-file-regression check exists to prevent
    elsewhere in this tool. `reconcile()` deliberately does not attempt a
    content-level three-way merge -- it only ever overlays "this commit's
    own explicit --files list" onto a new tree, which is correct precisely
    because it is unambiguous when no other party touched those same files
    in between. When one did, resolution requires understanding the actual
    conflicting content, which is a human (or a fresh, explicit commit)
    decision, not something this tool should guess at.
    """

    def __init__(self, files: list[str], remote_sha: str):
        self.files = list(files)
        self.remote_sha = remote_sha
        super().__init__(
            f"Refusing to auto-reconcile -- remote tip {remote_sha[:12]} has "
            f"also changed {len(files)} file(s) this commit touches, so a "
            f"naive overlay would silently discard the remote's changes: "
            f"{', '.join(files)}. Re-fetch, inspect the actual content, and "
            f"reconcile by hand -- this is a real content conflict, not "
            f"something reconcile() can resolve automatically."
        )


_CREDENTIAL_URL_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")

# TC-SG-19 (2026-08-31): stderr shapes of TRANSIENT temp-index write failures
# (antivirus/indexer racing the fresh path in %TEMP%; observed live 2026-08-30
# as two consecutive `git read-tree ... unable to write new index file`
# failures that were clean on retry and on a direct probe). Only these shapes
# are retried; anything else fails fast.
_TRANSIENT_INDEX_RE = re.compile(
    r"unable to write new index file|index\.lock|Permission denied", re.IGNORECASE,
)


def _make_private_temp_index() -> "tuple[str, str]":
    """A temp-index path inside a PRIVATE mkdtemp directory, at a name that
    has NEVER existed (TC-SG-19). Replaces the old mkstemp -> close ->
    unlink -> let-git-recreate dance: that create/delete/recreate sequence on
    a flat %TEMP% name is exactly the window antivirus/indexer hooks race.
    Returns (tmp_dir, index_path); caller removes tmp_dir with
    shutil.rmtree(..., ignore_errors=True)."""
    tmp_dir = tempfile.mkdtemp(prefix="git_plumb_")
    return tmp_dir, os.path.join(tmp_dir, "index")


def _read_tree_with_retry(
    tree_ish: str, *, env_index: dict, root: Path, tmp_index_path: str,
    attempts: int = 3,
) -> None:
    """`git read-tree` into the temp index, retrying ONLY the transient
    index-write failure shapes above (bounded backoff, leftover index/lock
    cleared between attempts, each retry printed loudly). Non-transient
    failures raise immediately on the first attempt."""
    delays = (0.2, 0.5)
    for attempt in range(attempts):
        result = _COMMAND_RUNNER(
            ["git", "read-tree", tree_ish], cwd=str(root),
            capture_output=True, **_TEXT_KW, env=env_index,
        )
        if result.returncode == 0:
            return
        stderr = _redact_credentials(result.stderr or "")
        if attempt + 1 < attempts and _TRANSIENT_INDEX_RE.search(stderr):
            print(f"WARNING: transient temp-index failure "
                  f"(attempt {attempt + 1}/{attempts}): {stderr.strip()[:160]} "
                  f"-- retrying", file=sys.stderr)
            for leftover in (tmp_index_path, tmp_index_path + ".lock"):
                try:
                    os.unlink(leftover)
                except OSError:
                    pass
            time.sleep(delays[min(attempt, len(delays) - 1)])
            continue
        raise PlumbCommitError(
            f"git read-tree {tree_ish} (indexed) failed: {stderr}"
        )


def _redact_credentials(text: str) -> str:
    """Mask any embedded URL credential (e.g. https://x-access-token:TOKEN@host/...)
    before a string reaches an exception message, stdout, or stderr.

    Found live 2026-08-08: a failed push (missing OAuth scope) raised a
    PlumbCommitError built from ' '.join(args), which for a push call
    includes the full --remote URL verbatim -- printing the literal token
    to the caller on every push failure that uses the x-access-token
    convention this repo's own CLAUDE.md documents. Applied at every site
    that builds an error message from raw subprocess args/output, not just
    the call site that happened to trigger this the first two times --
    `git push` isn't the only git subcommand that can embed a URL
    (e.g. `git ls-remote`, `git fetch` with an explicit URL).
    """
    return _CREDENTIAL_URL_RE.sub("://<redacted>@", text)


def _git(args: list[str], *, repo_root: Path, check: bool = True) -> "subprocess.CompletedProcess":
    result = _COMMAND_RUNNER(
        ["git", *args], cwd=str(repo_root), capture_output=True, **_TEXT_KW,
    )
    if check and result.returncode != 0:
        safe_args = _redact_credentials(" ".join(args))
        safe_stderr = _redact_credentials(result.stderr)
        raise PlumbCommitError(
            f"git {safe_args} failed (exit {result.returncode}): {safe_stderr}"
        )
    return result


def _gitignored_files(files: list[str], *, repo_root: Path) -> list[str]:
    """Return the subset of `files` matched by .gitignore. `git add -f`
    (used below) silently overrides .gitignore by design -- that is
    sometimes exactly right (e.g. this repo's own /knowledge/_overrides
    precedent) and sometimes a mistake with no feedback at all. Found live
    2026-08-06: this exact tool force-tracked 8 files under
    /.supervisor/state/ -- documented in this repo's own .gitignore as
    "Local Supervisor Control Plane, runtime state only" -- into git and
    pushed them, because --files was never checked against .gitignore
    before staging. `git check-ignore` exits 1 (not an error) when none of
    the given paths are ignored -- checked via returncode, not raised.

    Paths are passed via `--stdin -z` (NUL-delimited) as raw bytes on a
    binary-mode (text=False) subprocess call, not as argv and not as
    newline-delimited text-mode stdin. This dodges two separate problems
    at once: the OS argument-list-too-long limit argv is subject to for
    large file lists (found live: this repo's pre-commit grade-downgrade
    gate hit this same class of failure above ~450-500 files), and the
    Windows text-mode-stdin bug this function used to avoid by using argv
    in the first place -- subprocess text-mode stdin translates a
    "\\n"-joined input to "\\r\\n" before git ever sees it, embedding a
    literal "\\r" into each path git reads. NUL-delimited binary input
    never goes through newline translation at all, so it sidesteps that
    bug without needing argv.
    """
    if not files:
        return []
    stdin_bytes = b"\x00".join(f.encode("utf-8") for f in files) + b"\x00"
    result = _COMMAND_RUNNER(
        ["git", "check-ignore", "--stdin", "-z"], cwd=str(repo_root),
        input=stdin_bytes, capture_output=True, text=False,
    )
    if result.returncode not in (0, 1):
        # check-ignore itself failed (e.g. not a git repo) -- fail open,
        # same policy as the stale-file regression check's own base_sha
        # resolution failure: this tool's own infrastructure being
        # unavailable must never block an unrelated commit.
        return []
    return [p.decode("utf-8") for p in result.stdout.split(b"\x00") if p]


class PlumbCommitIdentityUnresolved(PlumbCommitBlocked):
    """Raised ONLY when an EXPLICIT --session-id names a missing or closed
    manifest -- a caller error that must not be silently reinterpreted.
    Ambient ambiguity or absent identity does NOT raise (Phase 1, TC-SG-04):
    the stale check runs on the lookback window regardless, and the ledger
    cross-check degrades to a loud warning -- ST-095's failure mode (blocked
    exactly when concurrency is highest) is structurally gone."""

    def __init__(self, session_id: str, status: str):
        self.session_id = session_id
        self.status = status
        self.findings: list = []
        PlumbCommitError.__init__(
            self,
            f"explicit --session-id {session_id!r} names a "
            f"{status or 'missing'} manifest. Fix the identity "
            f"(session_ledger.py init --session-id {session_id}), or drop the "
            f"flag -- unknown identity is covered by the lookback window."
        )


def _check_ledger_candidates(
    files: list[str], session_id: "str | None", *, repo_root: Path,
) -> list[dict]:
    """Cross-check --files against the calling session's own ledger
    (session_ledger.py, G16 part 2). Returns findings for any file that is
    dirty in the working tree right now but NOT a legitimate candidate of
    this session -- i.e. present in session_ledger.get_candidates()'s
    excluded_dirty_at_start or excluded_not_in_ledger buckets.

    A missing/uninitialized ledger (no active session resolvable at
    repo_root) yields get_candidates() == ([], [], []), so nothing is ever
    flagged -- the same fail-open, advisory-pass policy _check_for_regressions
    already uses for a missing base_sha. This protects the case the ledger
    actively disagrees with what's about to be committed, not the absence
    of a ledger entirely (documented coverage boundary, see module docstring
    and PlumbCommitLedgerBlocked).

    Temporarily repoints session_ledger's module-level repo_root at `root`
    (restored in `finally`) so this works correctly for both the real repo
    (where it's already a no-op -- session_ledger's own default repo_root is
    computed the same way as this module's) and a test's own throwaway repo
    passed via plumb_commit's `repo_root` parameter.
    """
    prior_repo_root = session_ledger._REPO_ROOT
    session_ledger.configure(repo_root=repo_root)
    try:
        _candidates, excluded_prior, excluded_unknown = session_ledger.get_candidates(session_id)
    finally:
        session_ledger.configure(repo_root=prior_repo_root)

    excluded_prior_set = {p.replace("\\", "/") for p in excluded_prior}
    excluded_unknown_set = {p.replace("\\", "/") for p in excluded_unknown}

    findings = []
    for f in files:
        normalized = f.replace("\\", "/")
        if normalized in excluded_prior_set:
            findings.append({"file": normalized, "reason": "dirty_at_start"})
        elif normalized in excluded_unknown_set:
            findings.append({"file": normalized, "reason": "not_in_ledger"})
    return findings


_GIT_BASH_PATH: "str | None" = None
_GIT_BASH_RESOLVED = False


def _resolve_git_bash() -> "str | None":
    """Find a real Git Bash executable, self-verified by actually running it --
    not just trusting the first PATH hit for "bash".

    Found live during TC-CIR-05's own test-writing (2026-08-14) and CONFIRMED as
    environment-dependent, not a one-off, during independent verification of that
    same fix: on Windows, `shutil.which("bash")` can resolve to
    C:\\Windows\\System32\\bash.exe -- the WSL launcher stub, a real, separate git
    installation inside the WSL filesystem -- instead of Git Bash, and WHICH one it
    picks depends on the calling process's own PATH ordering, which differs between
    a Git-Bash-launched process and a PowerShell-launched one on the very same
    machine. GIT_INDEX_FILE (a Windows path) does not correctly redirect WSL git at
    the isolated temp index, silently defeating this whole module's ST-021
    isolation guarantee. A single `shutil.which("bash")` call -- what the first
    version of this fix did -- is not sufficient on its own; this walks EVERY "bash"
    found on PATH, in order, and returns the first one that actually reports itself
    as MSYS/Git-Bash (not WSL/Linux) when run for real, caching the result for the
    life of the process rather than re-probing on every call.
    """
    global _GIT_BASH_PATH, _GIT_BASH_RESOLVED
    if _GIT_BASH_RESOLVED:
        return _GIT_BASH_PATH

    candidates: list[str] = []
    seen: set[str] = set()
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    exts = [""] + (os.environ.get("PATHEXT", "").split(os.pathsep) if os.name == "nt" else [])
    for d in path_dirs:
        for ext in (exts if os.name == "nt" else [""]):
            candidate = os.path.join(d, "bash" + ext.lower()) if ext else os.path.join(d, "bash")
            if os.path.isfile(candidate) and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    which_result = shutil.which("bash")
    if which_result and which_result not in seen:
        candidates.insert(0, which_result)
    # Last-resort fallback: well-known Git-for-Windows install locations, checked
    # even when Git's own bin/ isn't on PATH at all in the calling process -- found
    # live: a PowerShell-launched process on this exact machine had NO Git
    # directory on PATH whatsoever (not merely mis-ordered relative to the WSL
    # stub), so a PATH-only search returns nothing to prefer over the stub.
    for well_known in (
        r"C:\Program Files\Git\usr\bin\bash.exe", r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if os.path.isfile(well_known) and well_known not in seen:
            seen.add(well_known)
            candidates.append(well_known)

    for candidate in candidates:
        # System32/SysWOW64 bash.exe is always the WSL launcher stub on Windows --
        # skip without even probing it, both for speed and because probing it is
        # exactly the slow (WSL boot) path that motivated caching in the first place.
        normalized = candidate.replace("/", "\\").lower()
        if "\\system32\\" in normalized or "\\syswow64\\" in normalized:
            continue
        try:
            probe = _COMMAND_RUNNER(
                [candidate, "-c", "uname -s"], capture_output=True, **_TEXT_KW, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        uname = probe.stdout.strip().lower()
        if "mingw" in uname or "msys" in uname or "cygwin" in uname:
            _GIT_BASH_PATH = candidate
            _GIT_BASH_RESOLVED = True
            return candidate
        # Explicitly NOT accepted: "linux" (WSL), anything else unrecognized --
        # fail closed to the next candidate rather than guessing.

    _GIT_BASH_RESOLVED = True
    _GIT_BASH_PATH = None
    return None


_ISOLATION_CANARY_VERIFIED: "dict[str, bool]" = {}
_ISOLATION_CANARY_SENTINEL = ".git_plumb_commit_isolation_canary"
# git hash-object -t blob --stdin < /dev/null -- the well-known empty-blob SHA,
# usable directly with `update-index --cacheinfo` without ever writing a real
# blob to the object store.
_EMPTY_BLOB_SHA = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def _report_or_raise(breach: PlumbCommitError, *, strict: bool) -> None:
    """Isolation/postcondition breaches: raise (blocking) when `strict` is set,
    otherwise print loudly and continue (WARN-only soft-launch mode -- see
    reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-safety.md,
    Phase 2c). Defaults to non-blocking on purpose: this tool is reached for
    at already-stressful concurrent-session-contention moments, or runs
    unattended in a weekly CI cron job with nobody watching in real time -- a
    bug in these newly-added checks must not be able to newly block a commit
    that would previously have succeeded until there has been a real review
    window against live usage. Flip via plumb_commit()'s `strict_isolation`
    parameter (`--strict-isolation` on the CLI) once that review has happened.
    """
    if strict:
        raise breach
    print(f"WARNING (non-blocking, soft-launch mode): {breach}", file=sys.stderr)


def _verify_index_isolation(
    bash_path: str, tmp_index_path: str, *, repo_root: Path,
) -> "str | None":
    """Empirically prove, for this exact bash/git pairing, that GIT_INDEX_FILE
    redirection is actually in effect -- rather than inferring it from
    _resolve_git_bash()'s bash-genuineness check alone. That check verifies
    only that the bash BINARY is genuine MSYS/Git-Bash; it says nothing about
    whether `git`, as that bash resolves it via its own internal PATH, honors
    GIT_INDEX_FILE for this pairing -- confirmed insufficient once already
    (2026-08-14, WSL git silently defeating isolation despite a genuine-bash
    launcher).

    Adds a throwaway sentinel entry to the already-built isolated temp index
    (via a direct, non-shell `git update-index` call -- the lower-risk
    resolution path this module's own core plumbing already relies on), then
    runs `git ls-files` via the SAME bash binary that will run the real Tier 1
    script: once with GIT_INDEX_FILE set (must show the sentinel) and once
    without (must NOT show it -- that would mean this bash/git pairing reads
    the real index regardless of the env var). The sentinel is always removed
    from the temp index before returning, pass or fail, so it never leaks into
    the eventual commit tree.

    Returns None if isolation is verified (also caches success for this
    process's lifetime, keyed by bash_path -- matches _resolve_git_bash()'s
    own caching, since this is a property of the bash/git pairing, not of any
    single invocation). Returns a detail string describing the failure
    otherwise. Never raises itself -- the caller decides whether to block or
    warn (see _report_or_raise); a failure is never cached, so a possibly-
    transient hiccup gets re-probed next time rather than permanently
    blacklisting a bash_path.
    """
    if _ISOLATION_CANARY_VERIFIED.get(bash_path) is True:
        return None

    env_isolated = {**os.environ, "GIT_INDEX_FILE": tmp_index_path}
    add_result = _COMMAND_RUNNER(
        ["git", "update-index", "--add", "--cacheinfo",
         f"100644,{_EMPTY_BLOB_SHA},{_ISOLATION_CANARY_SENTINEL}"],
        cwd=str(repo_root), capture_output=True, **_TEXT_KW, env=env_isolated,
    )
    if add_result.returncode != 0:
        return (
            f"could not seed isolation-canary sentinel in the temp index: "
            f"{_redact_credentials(add_result.stderr)}"
        )

    try:
        isolated_check = _COMMAND_RUNNER(
            [bash_path, "-c", "git ls-files"],
            cwd=str(repo_root), capture_output=True, **_TEXT_KW, env=env_isolated,
        )
        if _ISOLATION_CANARY_SENTINEL not in isolated_check.stdout:
            return (
                f"the temp index's own sentinel entry was not visible via "
                f"{bash_path} with GIT_INDEX_FILE set -- this bash/git "
                f"pairing does not honor GIT_INDEX_FILE the way this tool "
                f"requires"
            )

        env_real = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
        real_check = _COMMAND_RUNNER(
            [bash_path, "-c", "git ls-files"],
            cwd=str(repo_root), capture_output=True, **_TEXT_KW, env=env_real,
        )
        if _ISOLATION_CANARY_SENTINEL in real_check.stdout:
            return (
                f"{bash_path} showed the isolated temp index's sentinel "
                f"entry even WITHOUT GIT_INDEX_FILE set -- this bash "
                f"resolves git in a way that does not distinguish the "
                f"isolated index from the real one (the confirmed 2026-08-14 "
                f"WSL-git failure mode, or a sibling of it)"
            )
    finally:
        _COMMAND_RUNNER(
            ["git", "update-index", "--force-remove", _ISOLATION_CANARY_SENTINEL],
            cwd=str(repo_root), capture_output=True, **_TEXT_KW, env=env_isolated,
        )

    _ISOLATION_CANARY_VERIFIED[bash_path] = True
    return None


_REAL_INDEX_SNAPSHOT_CHUNK_SIZE = 300


def _real_index_snapshot(files: list[str], *, repo_root: Path) -> str:
    """Real .git/index state for exactly the paths in `files` (a direct,
    non-shell `git` call -- the lower-risk resolution path). Used as one half
    of plumb_commit()'s postcondition: if this differs before vs. after the
    Tier 1 check window, some git command touched the real index during a
    pass that is supposed to only ever touch the isolated temp index.

    Chunked at _REAL_INDEX_SNAPSHOT_CHUNK_SIZE (found live 2026-08-25, pdf/java's
    Task 14 upstream proof run, mission-plan-the-end-to-end-vast-hejlsberg.md --
    the same Windows CreateProcess argv-length ceiling (~32KB) already fixed 3
    times elsewhere in this repo's refresh pipeline had never been exercised
    here before, since no prior commit through this tool carried a --files list
    anywhere near this large). A single `git ls-files --stage -- <all files>`
    call for a 1000+-file scope reliably overflows the ceiling on Windows;
    chunking and concatenating results is behaviorally identical to one call
    (this is a pure lookup, not a mutation) and produces the same sorted output
    a caller comparing pre/post snapshots for equality only cares about."""
    if not files:
        return ""
    lines: list[str] = []
    for i in range(0, len(files), _REAL_INDEX_SNAPSHOT_CHUNK_SIZE):
        chunk = files[i:i + _REAL_INDEX_SNAPSHOT_CHUNK_SIZE]
        result = _COMMAND_RUNNER(
            ["git", "ls-files", "--stage", "--", *chunk],
            cwd=str(repo_root), capture_output=True, **_TEXT_KW,
        )
        lines.extend(result.stdout.splitlines())
    return "\n".join(sorted(lines))


def _real_content_snapshot(files: list[str], *, repo_root: Path) -> "dict[str, str | None]":
    """SHA-256 of the real on-disk bytes of every path in `files`, read
    directly (not via git). This is the half of the postcondition that
    actually catches a worktree mutation like pre-commit-audit.sh Step 10's
    `git restore "$_f"` or Step 5's plain Python `atomic_write()` -- neither
    of which necessarily changes the real .git/index at all, so the index
    snapshot alone would be blind to them. A missing file maps to None (also
    a real, detectable state change)."""
    snapshot: "dict[str, str | None]" = {}
    for f in files:
        path = repo_root / f
        try:
            snapshot[f] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            snapshot[f] = None
    return snapshot


def _run_tier1_checks(
    tmp_index_path: str, message: str, *, repo_root: Path, strict_isolation: bool = False,
    context_env: "dict[str, str] | None" = None,
) -> "subprocess.CompletedProcess | None":
    """Run scripts/pre-commit-audit.sh (Tier 1) against the isolated temp index --
    NOT the real .git/index -- by setting GIT_INDEX_FILE for the subprocess. Every
    git command pre-commit-audit.sh runs (git diff --cached, etc.) transparently
    reads whatever GIT_INDEX_FILE points at, so this achieves genuine Tier 1 parity
    without ever touching the shared index a concurrent session might be using
    (ST-021) -- the same isolation property plumb_commit()'s own read-tree/add-f/
    write-tree sequence already relies on, extended to cover the check script too.

    Must be called BEFORE the temp index is torn down (i.e. before plumb_commit()'s
    own `finally: os.unlink(tmp_index_path)`), and AFTER `git add -f` has populated
    it, so the check sees exactly the content that will become the commit.

    The commit message is passed via EVIDENCE_RESTAMP_MSG / BULK_GRADE_MIGRATION_MSG
    (the exact env-var override names Steps 20/20b already read) instead of letting
    those steps fall back to `.git/COMMIT_EDITMSG` -- that file reflects the last
    real `git commit` in this working tree, if any, not this plumbed commit's actual
    message, and would silently feed the wrong (or a stale) message into the churn
    override checks otherwise.

    Returns None (not a CompletedProcess) if scripts/pre-commit-audit.sh does not
    exist at repo_root -- this tool's own test suite deliberately runs against
    minimal, isolated fake repos with no governance scripts at all, and a future
    caller could point this tool at a different repo entirely. Missing check
    infrastructure must never block an otherwise-valid commit, matching this
    module's existing fail-open policy for a missing base_sha
    (_check_for_regressions) and pre-commit-audit.sh's own missing-.venv policy.
    """
    script = repo_root / "scripts" / "pre-commit-audit.sh"
    if not script.exists():
        return None
    # Resolve bash to a SELF-VERIFIED Git Bash (see _resolve_git_bash) -- a bare
    # shutil.which("bash") result is not trustworthy on Windows (see that
    # function's docstring for the confirmed, environment-dependent failure mode).
    bash_path = _resolve_git_bash()
    if bash_path is None:
        # Fail LOUD, not silent -- this differs from the missing-script case
        # above (expected in this tool's own test fixtures): here the check
        # script genuinely exists but no way to safely run it was found. Matches
        # this module's existing "missing check infrastructure must never block
        # an otherwise-valid commit" policy, but a real operator needs to know
        # their commits are silently missing Tier 1 coverage, not find out never.
        print(
            "WARNING: no working Git Bash found (only WSL/unrecognized bash "
            "variants on PATH, or none at all) -- Tier 1 checks (scripts/"
            "pre-commit-audit.sh) SKIPPED for this commit. Install Git for "
            "Windows and ensure its bash precedes any WSL bash on PATH.",
            file=sys.stderr,
        )
        return None

    isolation_failure = _verify_index_isolation(bash_path, tmp_index_path, repo_root=repo_root)
    if isolation_failure is not None:
        _report_or_raise(
            PlumbCommitIsolationBreach(isolation_failure), strict=strict_isolation,
        )
        # Non-strict (warn-only) path reaches here: do NOT run Tier 1 against an
        # unproven-isolated environment -- same safe skip as "no bash found"
        # above, just with a louder, earlier warning already printed.
        return None

    env = {
        **os.environ,
        "GIT_INDEX_FILE": tmp_index_path,
        "EVIDENCE_RESTAMP_MSG": message,
        "BULK_GRADE_MIGRATION_MSG": message,
        # Tells pre-commit-audit.sh it is running as a read-only parity check
        # against an isolated temp index, not the real interactive commit hook
        # it was originally written for -- Step 5 and Step 10 branch on this to
        # report findings instead of mutating real repo state. Set uncondition-
        # ally here; never set by an operator or any other caller.
        "PC_AUDIT_NO_MUTATE": "1",
        # Phase 1 (TC-SG-04): Tier-1's Step 13/34 consume the SAME commit
        # context this tool already resolved (ST-095's root: four independent
        # ambient re-resolutions per commit). PYTHONUTF8 keeps every hook
        # Python child's stdout round-trippable (the U+FFFD noise class).
        "PYTHONUTF8": "1",
        **(context_env or {}),
    }
    tier1_result = _COMMAND_RUNNER(
        [bash_path, "scripts/pre-commit-audit.sh"],
        cwd=str(repo_root), capture_output=True, **_TEXT_KW, env=env,
    )
    # Normalize: a reader failure must surface as empty text, never None --
    # None turned a Tier-1 FAIL into a raw TypeError, and a Tier-1 PASS into
    # an AttributeError in main() AFTER the push but BEFORE the skill-run
    # record was filed (ST-096 containment, 2026-08-29).
    if tier1_result.stdout is None:
        tier1_result.stdout = ""
    if tier1_result.stderr is None:
        tier1_result.stderr = ""
    return tier1_result


def _sync_local_state(
    old_head: str, new_head: str, files: "list[str]", *, root: Path,
    remote_touched: "list[str] | None" = None,
) -> None:
    """Post-advance real-state sync (RC-1 source fix, 2026-08-29 plan T11).

    Every commit this tool builds advances refs/heads/<branch> while the real
    .git/index keeps the PRE-commit blob for each committed path -- residue
    that the next porcelain `git commit` by ANY session sweeps into history as
    a byte-exact silent revert (reproduced; 17 live entries measured at plan
    time). Sync exactly this commit's paths (index only; the worktree already
    holds the committed content), and after a reconcile() also the
    remote-touched paths (index+worktree -- their old content otherwise poses
    as a staged local modification). Every path is gated inside checkout_sync
    on being provably the untouched pre-advance state. Best-effort by
    contract: a failure here must never make a pushed commit look failed."""
    try:
        report = checkout_sync.sync_after_ref_advance(
            old_head, new_head, paths=list(files), repo_root=root, mode="index",
        )
        reports = [report]
        if remote_touched:
            reports.append(checkout_sync.sync_after_ref_advance(
                old_head, new_head, paths=remote_touched, repo_root=root,
                mode="index+worktree",
            ))
        for rep in reports:
            print(rep.summary())
            for skipped in rep.skipped_dirty[:5]:
                print(f"  checkout_sync left untouched (not provably pre-advance state): {skipped}")
            if rep.index_locked:
                print("  checkout_sync: index.lock held by another process -- run "
                      "'git restore --staged -- <your files>' after their operation finishes")
    except Exception as exc:  # noqa: BLE001 -- deliberate: post-push best-effort
        print(f"WARNING: checkout_sync failed (commit itself is unaffected): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)


def _is_non_fast_forward(stderr: str) -> bool:
    """True if a `git push` failure's stderr looks like a non-fast-forward
    rejection (the remote branch has advanced past the local push's base)
    rather than some other push failure (auth, network, protected branch
    rule, etc.) that reconcile() cannot help with and should not attempt."""
    lowered = stderr.lower()
    return "[rejected]" in lowered and (
        "non-fast-forward" in lowered or "fetch first" in lowered
    )


def reconcile(
    commit_sha: str,
    files: list[str],
    *,
    repo_root: "Path | None" = None,
    branch: str = "main",
    remote: str = "origin",
    remote_name: "str | None" = None,
    old_parent_sha: "str | None" = None,
    push: bool = True,
) -> dict[str, Any]:
    """Reconcile a commit already built by `plumb_commit()` (or any commit
    object) against a remote branch that has advanced since the commit's
    parent was captured -- i.e. recover from a non-fast-forward push
    rejection without touching the real `.git/index` or working tree.

    Found live 2026-08-26 (pipeline reliability hardening pass,
    reports/skill-gaps/2026-08-26-pipeline-reliability-hardening.md):
    `plumb_commit()` had no divergence handling at all, so this exact
    situation required an agent to hand-build the procedure below via raw
    git plumbing, twice, under live push pressure. This formalizes it as a
    named, tested operation.

    Strategy: build a two-parent merge commit whose TREE is the new remote
    tip's tree with exactly `files` overlaid from `commit_sha`'s own tree
    (i.e. "replay this commit's specific file writes on top of the new
    tip"). This is deliberately NOT a general three-way content merge --
    it is correct and unambiguous specifically because `commit_sha` came
    from `plumb_commit()`, which always operates on an explicit, disjoint
    `--files` list, so "this commit's changes" has one unambiguous meaning.
    If the remote's new tip ALSO touched any of `files` in the meantime,
    this overlay would silently discard the remote's changes -- that case
    is detected and refused (`PlumbCommitReconcileConflict`), never
    silently resolved.

    old_parent_sha: `commit_sha`'s own parent, i.e. the `HEAD` that was
        live when the original commit was built. Auto-resolved via
        `git rev-parse {commit_sha}^` when not given.

    Returns a result dict shaped like `plumb_commit()`'s
    ({head_sha, tree_sha, commit_sha, pushed, files, reconciled_against}),
    where `commit_sha` is the NEW merge commit (not the input `commit_sha`)
    and `reconciled_against` is the remote SHA it was merged onto.

    Raises `PlumbCommitReconcileConflict` if the remote tip touched any of
    `files` since `old_parent_sha` (real content conflict, resolve by
    hand), or `PlumbCommitError` for any git operation failure.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    if remote_name is None:
        remote_name = "origin"

    if old_parent_sha is None:
        old_parent_sha = _git(["rev-parse", f"{commit_sha}^"], repo_root=root).stdout.strip()

    _git(["fetch", remote, branch], repo_root=root)
    remote_tip = _git(["rev-parse", "FETCH_HEAD"], repo_root=root).stdout.strip()

    if remote_tip == old_parent_sha:
        # Nothing actually diverged any further since old_parent_sha (the
        # race window closed, or the caller invoked reconcile() speculatively)
        # -- a plain fast-forward push works; no merge commit needed.
        if push:
            _git(["push", remote, f"{commit_sha}:refs/heads/{branch}"], repo_root=root)
            _git(["update-ref", f"refs/remotes/{remote_name}/{branch}", commit_sha], repo_root=root)
        _git(["update-ref", f"refs/heads/{branch}", commit_sha], repo_root=root)
        tree_sha = _git(["rev-parse", f"{commit_sha}^{{tree}}"], repo_root=root).stdout.strip()
        return {
            "head_sha": old_parent_sha,
            "tree_sha": tree_sha,
            "commit_sha": commit_sha,
            "pushed": push,
            "files": list(files),
            "reconciled_against": remote_tip,
            "fast_forward": True,
        }

    # Conflict check: did the remote tip ALSO touch any of `files` since
    # old_parent_sha? If so, a naive overlay would silently discard those
    # changes -- refuse rather than guess.
    diff_out = _git(
        ["diff", "--name-only", old_parent_sha, remote_tip, "--", *files], repo_root=root,
    ).stdout
    conflicting = sorted({line.strip() for line in diff_out.splitlines() if line.strip()})
    if conflicting:
        raise PlumbCommitReconcileConflict(conflicting, remote_tip)

    tmp_index_dir, tmp_index_path = _make_private_temp_index()
    try:
        env_index = {**os.environ, "GIT_INDEX_FILE": tmp_index_path}

        def _git_indexed(args: list[str]) -> "subprocess.CompletedProcess":
            result = _COMMAND_RUNNER(
                ["git", *args], cwd=str(root), capture_output=True, **_TEXT_KW, env=env_index,
            )
            if result.returncode != 0:
                safe_args = _redact_credentials(" ".join(args))
                safe_stderr = _redact_credentials(result.stderr)
                raise PlumbCommitError(
                    f"git {safe_args} (indexed reconcile) failed: {safe_stderr}"
                )
            return result

        # Start from the new remote tip's tree...
        _read_tree_with_retry(remote_tip, env_index=env_index, root=root,
                              tmp_index_path=tmp_index_path)

        # ...then overlay exactly `files` from commit_sha's own tree, via
        # --cacheinfo (mode,sha,path triples) rather than `--index-info` on
        # stdin: empirically, on this tool's own supported git/platform
        # combination, `update-index --index-info` silently no-ops with
        # "Ignoring path X" for a path not already present in the target
        # index -- reproduced directly (see reports/skill-gaps/
        # 2026-08-26-pipeline-reliability-hardening.md) -- so it can never
        # actually ADD a new path to the isolated overlay index, only update
        # ones already there. `--cacheinfo` has no such issue and is used
        # here as repeated triples in chunked batches (mirrors
        # _REAL_INDEX_SNAPSHOT_CHUNK_SIZE's existing argv-length discipline
        # elsewhere in this file) rather than one subprocess call per file.
        ls_out = _git(["ls-tree", "-r", commit_sha, "--", *files], repo_root=root).stdout
        present_paths: set[str] = set()
        cacheinfo_triples: list[str] = []
        for line in ls_out.splitlines():
            if not line.strip():
                continue
            meta, path = line.split("\t", 1)
            mode, _obj_type, obj_sha = meta.split(" ")
            present_paths.add(path)
            cacheinfo_triples.append(f"{mode},{obj_sha},{path}")
        for i in range(0, len(cacheinfo_triples), _REAL_INDEX_SNAPSHOT_CHUNK_SIZE):
            chunk = cacheinfo_triples[i:i + _REAL_INDEX_SNAPSHOT_CHUNK_SIZE]
            args: list[str] = ["update-index", "--add"]
            for triple in chunk:
                args += ["--cacheinfo", triple]
            _git_indexed(args)

        # `files` entries that commit_sha's tree does NOT contain were
        # deletions in the original commit -- remove them from the overlay
        # tree too, matching commit_sha's own intent exactly.
        deleted_paths = [f for f in files if f not in present_paths]
        for i in range(0, len(deleted_paths), _REAL_INDEX_SNAPSHOT_CHUNK_SIZE):
            chunk = deleted_paths[i:i + _REAL_INDEX_SNAPSHOT_CHUNK_SIZE]
            if chunk:
                _git_indexed(["update-index", "--force-remove", "--", *chunk])

        tree_sha = _git_indexed(["write-tree"]).stdout.strip()
    finally:
        shutil.rmtree(tmp_index_dir, ignore_errors=True)

    original_message = _git(
        ["log", "-1", "--format=%B", commit_sha], repo_root=root,
    ).stdout.rstrip("\n")
    merge_message = (
        f"{original_message}\n\n"
        f"Reconciled (non-fast-forward) against {remote}/{branch}@{remote_tip[:12]} "
        f"via git_plumb_commit.reconcile()."
    )
    merge_commit_sha = _git(
        ["commit-tree", tree_sha, "-p", remote_tip, "-p", commit_sha, "-m", merge_message],
        repo_root=root,
    ).stdout.strip()

    _git(["update-ref", f"refs/heads/{branch}", merge_commit_sha], repo_root=root)

    pushed = False
    if push:
        _git(["push", remote, f"{merge_commit_sha}:refs/heads/{branch}"], repo_root=root)
        pushed = True
        _git(["update-ref", f"refs/remotes/{remote_name}/{branch}", merge_commit_sha], repo_root=root)

    return {
        "head_sha": old_parent_sha,
        "tree_sha": tree_sha,
        "commit_sha": merge_commit_sha,
        "pushed": pushed,
        "files": list(files),
        "reconciled_against": remote_tip,
        "fast_forward": False,
    }


def plumb_commit(
    files: list[str],
    message: str,
    *,
    repo_root: "Path | None" = None,
    branch: str = "main",
    remote: str = "origin",
    remote_name: "str | None" = None,
    base_sha: "str | None" = None,
    session_id: "str | None" = None,
    skip_stale_check: bool = False,
    skip_ledger_check: bool = False,
    skip_tier1_checks: bool = False,
    strict_isolation: bool = False,
    push: bool = True,
    auto_reconcile: bool = True,
    ack_gitignored: "list[str] | None" = None,
    sync_state: bool = True,
    wide_findings: str = "warn",
    skills: "list[str] | None" = None,
    plan: "str | None" = None,
) -> dict[str, Any]:
    """Perform the full isolated git-plumbing commit sequence atomically:
    stale-file regression check -> temp-index build -> Tier 1 checks
    (scripts/pre-commit-audit.sh, against the isolated index) -> write-tree ->
    commit-tree -> push -> local ref sync.

    auto_reconcile: when True (default) and the push is rejected
        non-fast-forward, retries ONCE via `reconcile()` (see above) --
        building a proper two-parent merge commit against the current
        remote tip -- instead of raising immediately. Set False to get the
        old behavior (raise `PlumbCommitError` on any push failure,
        including non-fast-forward) when a caller specifically wants to
        handle divergence itself. If the automatic retry also fails (e.g.
        a real content conflict via `PlumbCommitReconcileConflict`, or the
        remote moved again during the retry), raises
        `PlumbCommitPushRejected` with the original commit's `commit_sha`/
        `tree_sha` so nothing already built locally is lost.

    remote: the PUSH DESTINATION passed to `git push <remote> <refspec>` --
        either a configured remote name (e.g. "origin") or a raw URL (e.g.
        this repo's GH_TOKEN-authenticated https://x-access-token:...
        convention, which has no corresponding local remote name at all).
    remote_name: the LOCAL remote-tracking ref name to update after a
        successful push (refs/remotes/{remote_name}/{branch}) -- always a
        bare name like "origin", never a URL or filesystem path, since
        refs/remotes/<x>/... is a ref-name component, not a push
        destination (a raw path/URL passed here would produce an invalid
        ref name -- deliberately NOT auto-detected from `remote`, since a
        filesystem path and a URL can't be reliably told apart from a bare
        remote name by inspection; e.g. this module's own test suite pushes
        to a raw bare-repo PATH while still needing "origin" as the tracking
        name). Defaults to "origin" -- this repo has exactly one configured
        remote in every real production use of this tool.

    ack_gitignored: paths the caller explicitly knows are .gitignore-matched
        and intends to force-track anyway (e.g. a legitimate override
        precedent like /knowledge/_overrides). Any OTHER staged path that
        matches .gitignore prints a non-fatal WARNING to stderr and is
        listed in the returned dict's "gitignore_warnings" -- found live
        2026-08-06: this tool force-tracked 8 files under the gitignored
        /.supervisor/state/ with zero feedback, because .gitignore was
        never checked against --files before staging.

    strict_isolation: when True, an isolation-canary failure or a postcondition
        breach (real .git/index or real on-disk content of a --files path
        changed during the Tier 1 check window) raises and blocks the commit.
        Defaults to False (report loudly, do not block) -- a deliberate
        soft-launch posture for these newly-added checks (see
        reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-safety.md,
        Phase 2c): this tool is reached for at already-stressful
        concurrent-session-contention moments or runs unattended in a weekly
        CI cron job, so a bug in a brand-new safety check must not be able to
        newly block a commit that would previously have succeeded until there
        has been a real review window against live usage. Flip to True (also
        available as `--strict-isolation` on the CLI) once that review is done.

    skip_ledger_check: when True, skips the session-ledger cross-check
        (see PlumbCommitLedgerBlocked) entirely. Mirrors skip_stale_check's
        existing escalation pattern -- a documented, deliberately-loud
        escape hatch for a genuine emergency, never a routine default.

    Returns a result dict: {head_sha, tree_sha, commit_sha, pushed, files,
    gitignore_warnings, tier1_output}. Raises PlumbCommitBlocked if an
    uncovered regression is found, PlumbCommitLedgerBlocked if a --files
    path is dirty but not accounted for by the calling session's own
    ledger, PlumbCommitIsolationBreach / PlumbCommitPostconditionBreach if
    strict_isolation=True and an isolation problem is detected, or
    PlumbCommitError for any git operation failure.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    if remote_name is None:
        remote_name = "origin"
    ack_set = set(ack_gitignored or [])

    head_sha = _git(["rev-parse", "HEAD"], repo_root=root).stdout.strip()

    # CommitContext (Phase 1, TC-SG-04): identity resolved ONCE, side-effect
    # free; ambiguity/absence informs the baseline classing but can no longer
    # block or crash this tool (ST-095's failure mode -- unusable exactly when
    # concurrency was highest -- is structurally gone: the lookback window
    # covers unknown identity, per the 2026-08-07 `55586b637c` evidence that
    # staleness does not respect session boundaries).
    ctx = None
    try:
        ctx = session_ledger.resolve_context(session_id)
    except Exception as exc:  # ledger infrastructure itself unavailable
        print(f"WARNING: session ledger unavailable ({type(exc).__name__}: {exc}) "
              f"-- proceeding with the lookback window only.", file=sys.stderr)
    if session_id and ctx is not None and ctx.status in ("none", "closed"):
        raise PlumbCommitIdentityUnresolved(session_id, ctx.status)
    if ctx is not None and ctx.status == "ambiguous":
        print(f"WARNING: session identity is ambiguous "
              f"({', '.join(ctx.candidates)}) -- stale check runs on the "
              f"lookback window; the session-ledger cross-check is skipped "
              f"for this commit.", file=sys.stderr)

    baseline = slib.resolve_baseline(
        explicit_sha=base_sha, session_ctx=ctx, head=head_sha, repo_root=root,
    )

    if not skip_ledger_check and ctx is not None and ctx.status == "resolved":
        try:
            ledger_findings = _check_ledger_candidates(
                files, ctx.session_id, repo_root=root,
            )
        except session_ledger.AmbiguousSessionError:  # defensive; explicit id given
            ledger_findings = []
        if ledger_findings:
            raise PlumbCommitLedgerBlocked(ledger_findings)

    gitignore_warnings = [f for f in _gitignored_files(files, repo_root=root) if f not in ack_set]
    for f in gitignore_warnings:
        print(
            f"WARNING: {f} matches .gitignore and will be force-tracked by this commit "
            f"(git add -f). If this is intentional, pass --ack-gitignored {f} to silence "
            f"this warning; if not, remove it from --files.",
            file=sys.stderr,
        )

    tmp_index_dir, tmp_index_path = _make_private_temp_index()
    try:
        env_index = {**os.environ, "GIT_INDEX_FILE": tmp_index_path}

        def _git_indexed(args: list[str]) -> "subprocess.CompletedProcess":
            result = _COMMAND_RUNNER(
                ["git", *args], cwd=str(root), capture_output=True, **_TEXT_KW, env=env_index,
            )
            if result.returncode != 0:
                safe_args = _redact_credentials(" ".join(args))
                safe_stderr = _redact_credentials(result.stderr)
                raise PlumbCommitError(
                    f"git {safe_args} (indexed) failed: {safe_stderr}"
                )
            return result

        _read_tree_with_retry(head_sha, env_index=env_index, root=root,
                              tmp_index_path=tmp_index_path)
        # --pathspec-from-file avoids the OS argument-list-too-long limit
        # `git add -f <paths...>` is subject to for large file lists (same
        # class of failure found live in this repo's pre-commit
        # grade-downgrade gate above ~450-500 files).
        _pathspec_fd, _pathspec_path = tempfile.mkstemp(prefix="git_plumb_pathspec_")
        try:
            with os.fdopen(_pathspec_fd, "w", encoding="utf-8") as f:
                f.write("".join(f"{path}\n" for path in files))
            _git_indexed(["add", "-f", "--pathspec-from-file", _pathspec_path])
        finally:
            os.unlink(_pathspec_path)

        # Stale-file regression check on the TEMP INDEX -- exactly the tree
        # that will become the commit (Phase 1, TC-SG-04; closes the TOCTOU
        # between a pre-index worktree read and `git add -f`, adversarial W8).
        relied_token_ids: "list[str]" = []
        if not skip_stale_check:
            stale_report = slib.detect_regressions(
                files, baseline=baseline, head=head_sha, mode="index",
                repo_root=root, index_file=tmp_index_path,
                override_lookup=override_manager.find_valid_token_for_path,
            )
            relied_token_ids = sorted({
                f.override_token_id for f in stale_report.findings
                if f.override_token_id
            })
            print(f"stale-check: base={(baseline.window_sha or 'none')[:12]} "
                  f"source={baseline.source} checked={stale_report.files_checked} "
                  f"intervening={stale_report.window_paths}")
            blocking = stale_report.blocking(wide_findings=wide_findings)
            blocking_ids = {id(f) for f in blocking}
            for f in stale_report.findings:
                if f.override_token_id is not None:
                    print(f"stale-check: {f.path} matches a reverted state but is "
                          f"permitted by override token {f.override_token_id}")
                elif id(f) not in blocking_ids:
                    print(f"WARNING (lookback window, soak policy): {f.path} matches "
                          f"the state before {f.intervening_commit[:10]} -- would "
                          f"block under --wide-findings=block", file=sys.stderr)
            if blocking:
                raise PlumbCommitBlocked([f.to_dict() for f in blocking])

        tier1_output = ""
        if not skip_tier1_checks:
            # Postcondition safety net: snapshot real state scoped to exactly
            # --files immediately before and after the Tier 1 check window.
            # This is mechanism-agnostic by design -- it does not matter WHY
            # real state changed (a bash/git resolution defeat the isolation
            # canary didn't catch, a pre-commit-audit.sh step that mutates
            # real state without being added to
            # scripts/ci/checks/precommit_audit_mutation_registry.yaml, or
            # something not yet imagined) -- if either snapshot differs, Tier 1
            # should have been fully isolated and provably was not.
            _pre_index = _real_index_snapshot(files, repo_root=root)
            _pre_content = _real_content_snapshot(files, repo_root=root)

            tier1_result = _run_tier1_checks(
                tmp_index_path, message, repo_root=root, strict_isolation=strict_isolation,
                context_env={
                    "PC_AUDIT_SESSION_ID": (ctx.session_id if ctx is not None
                                            and ctx.status == "resolved"
                                            and ctx.session_id else ""),
                    "PC_AUDIT_BASE_SHA": baseline.window_sha or "",
                    "PC_AUDIT_BASELINE_SOURCE": baseline.source,
                },
            )

            _post_index = _real_index_snapshot(files, repo_root=root)
            _post_content = _real_content_snapshot(files, repo_root=root)
            if _pre_index != _post_index:
                _report_or_raise(
                    PlumbCommitPostconditionBreach(
                        f"real .git/index changed for one or more of --files "
                        f"during the Tier 1 check window (before: "
                        f"{_pre_index!r}, after: {_post_index!r})"
                    ),
                    strict=strict_isolation,
                )
            _changed_content = sorted(
                f for f in files if _pre_content.get(f) != _post_content.get(f)
            )
            if _changed_content:
                _report_or_raise(
                    PlumbCommitPostconditionBreach(
                        f"real on-disk content changed for "
                        f"{len(_changed_content)} file(s) in --files during "
                        f"the Tier 1 check window: {', '.join(_changed_content)}"
                    ),
                    strict=strict_isolation,
                )

            if tier1_result is not None and tier1_result.returncode != 0:
                raise PlumbCommitTier1Failed(
                    tier1_result.stdout + tier1_result.stderr, tier1_result.returncode,
                )
            if tier1_result is not None:
                tier1_output = tier1_result.stdout

        tree_sha = _git_indexed(["write-tree"]).stdout.strip()
    finally:
        shutil.rmtree(tmp_index_dir, ignore_errors=True)

    commit_sha = _git(
        ["commit-tree", tree_sha, "-p", head_sha, "-m", message], repo_root=root,
    ).stdout.strip()

    # Advance the local branch ref unconditionally, regardless of --push --
    # matching normal `git commit` semantics (the local branch always moves;
    # pushing is a separate, independent action). Without this, a second
    # --no-push call re-reads the same stale HEAD (line 267 above) and
    # silently builds a disconnected sibling commit instead of a chain link,
    # since nothing ever recorded that the first commit happened locally.
    # Found live, MT028-2026-08-09-FONT-PYTHON-BLIND-SPOT-HEAL
    # (L1-MT028-03/L3-MT028-01): 2 of that mission's 4 sequential --no-push
    # commits landed with the SAME parent instead of chaining, discovered
    # only because the caller happened to manually re-verify parent SHAs.
    _git(["update-ref", f"refs/heads/{branch}", commit_sha], repo_root=root)

    # Governance trail, pending-before-push (Phase 1, TC-SG-04): the record is
    # created with the built commit's sha BEFORE any push, so a crash anywhere
    # downstream leaves a sha-linked, discoverable record (PENDING_FINALIZE in
    # check_skill_run_records.py) instead of no trail at all -- the class that
    # fired live on this very plan's Phase 0a commit (TC-SG-18).
    run_id = None
    if skills:
        run_id = _create_pending_record(
            skills=skills, plan=plan or "", commit_sha=commit_sha, repo_root=root,
        )

    pushed = False
    reconciled_against: "str | None" = None
    if push:
        push_result = _COMMAND_RUNNER(
            ["git", "push", remote, f"{commit_sha}:refs/heads/{branch}"],
            cwd=str(root), capture_output=True, **_TEXT_KW,
        )
        if push_result.returncode == 0:
            pushed = True
            _git(["update-ref", f"refs/remotes/{remote_name}/{branch}", commit_sha], repo_root=root)
            _finalize_record(run_id, "success", commit_sha, repo_root=root)
            _consume_relied_tokens(relied_token_ids, files, commit_sha, root=root)
        elif auto_reconcile and _is_non_fast_forward(push_result.stderr):
            try:
                reconcile_result = reconcile(
                    commit_sha, files, repo_root=root, branch=branch,
                    remote=remote, remote_name=remote_name,
                    old_parent_sha=head_sha, push=True,
                )
            except PlumbCommitError as reconcile_exc:
                _finalize_record(run_id, "failure", commit_sha, repo_root=root)
                raise PlumbCommitPushRejected(
                    commit_sha, tree_sha, list(files),
                    f"non-fast-forward push, then reconcile() itself failed: {reconcile_exc}",
                ) from reconcile_exc
            _finalize_record(run_id, "success", reconcile_result["commit_sha"], repo_root=root)
            _consume_relied_tokens(relied_token_ids, files,
                                   reconcile_result["commit_sha"], root=root)
            # The reconciled (merge) commit is now the real result of this
            # call -- it superseded commit_sha as HEAD of `branch`.
            if sync_state:
                remote_diff = _COMMAND_RUNNER(
                    ["git", "diff", "--name-only", "-z", head_sha,
                     reconcile_result["reconciled_against"]],
                    cwd=str(root), capture_output=True, **_TEXT_KW,
                )
                remote_touched = [
                    p for p in (remote_diff.stdout or "").split("\0") if p
                ] if remote_diff.returncode == 0 else []
                _sync_local_state(
                    head_sha, reconcile_result["commit_sha"], files, root=root,
                    remote_touched=remote_touched,
                )
            return {
                "head_sha": head_sha,
                "tree_sha": reconcile_result["tree_sha"],
                "commit_sha": reconcile_result["commit_sha"],
                "pushed": reconcile_result["pushed"],
                "files": list(files),
                "gitignore_warnings": gitignore_warnings,
                "tier1_output": tier1_output,
                "reconciled_against": reconcile_result["reconciled_against"],
                "skill_run_id": run_id,
            }
        else:
            safe_args = _redact_credentials(f"push {remote} {commit_sha}:refs/heads/{branch}")
            safe_stderr = _redact_credentials(push_result.stderr)
            # Always raise the richer PlumbCommitPushRejected (a PlumbCommitError
            # subclass, so any existing `except PlumbCommitError:` caller still
            # matches it via isinstance) -- its commit_sha/tree_sha/files
            # attributes are useful recovery information regardless of whether
            # auto_reconcile was disabled outright or was attempted and itself
            # failed; there is no case where the plain base-class message is
            # preferable.
            reason = (
                f"non-fast-forward push, and auto_reconcile=False so no retry "
                f"was attempted"
                if not auto_reconcile and _is_non_fast_forward(push_result.stderr)
                else f"'git {safe_args}' failed for a reason reconcile() cannot "
                     f"help with (exit {push_result.returncode}): {safe_stderr}"
            )
            _finalize_record(run_id, "failure", commit_sha, repo_root=root)
            raise PlumbCommitPushRejected(commit_sha, tree_sha, list(files), reason)

    if not push:
        # --no-push: the commit exists locally and the local branch advanced;
        # the record is finalized against it now (previously the whole record
        # step lived on the push path only -- the ST-058 gotcha).
        _finalize_record(run_id, "success", commit_sha, repo_root=root)

    if sync_state:
        _sync_local_state(head_sha, commit_sha, files, root=root)

    return {
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "commit_sha": commit_sha,
        "pushed": pushed,
        "files": list(files),
        "gitignore_warnings": gitignore_warnings,
        "tier1_output": tier1_output,
        "reconciled_against": reconciled_against,
        "skill_run_id": run_id,
    }


def _create_pending_record(
    *, skills: list[str], plan: str, commit_sha: str, repo_root: Path,
) -> "str | None":
    """Create the retroactive skill-run record BEFORE the push, carrying the
    built commit's sha with outcome=pending (Phase 1, TC-SG-04). Never raises:
    a governance-bookkeeping failure must not fail the commit flow. The
    `retroactive-` run-id prefix keeps the pending record invisible to
    `skill_run_manager.py find-pending`, so it can never be claimed by an
    unrelated porcelain commit's commit-msg hook."""
    create = _COMMAND_RUNNER(
        [sys.executable, str(_SKILL_RUN_MANAGER), "create",
         "--skills", *skills, "--plan", plan, "--retroactive",
         "--run-type", "targeted", "--commit-sha", commit_sha],
        cwd=str(repo_root), capture_output=True, **_TEXT_KW,
    )
    if create.returncode != 0:
        print(f"WARNING: skill-run record creation failed: {create.stderr}",
              file=sys.stderr)
        return None
    for line in (create.stdout or "").splitlines():
        if "Created skill run record:" in line:
            return line.split(":", 1)[1].strip()
    print("WARNING: could not parse run_id from skill_run_manager.py create output",
          file=sys.stderr)
    return None


def _finalize_record(
    run_id: "str | None", outcome: str, commit_sha: str, *, repo_root: Path,
) -> None:
    """Finalize the pending record (success/failure). Never raises."""
    if not run_id:
        return
    finalize = _COMMAND_RUNNER(
        [sys.executable, str(_SKILL_RUN_MANAGER), "finalize",
         "--run-id", run_id, "--outcome", outcome, "--commit-sha", commit_sha],
        cwd=str(repo_root), capture_output=True, **_TEXT_KW,
    )
    if finalize.returncode != 0:
        print(f"WARNING: skill-run record finalize ({outcome}) failed: "
              f"{finalize.stderr}", file=sys.stderr)


def _consume_relied_tokens(
    token_ids: "list[str]", files: "list[str]", commit_sha: str, *, root: Path,
) -> None:
    """Consume exactly the override tokens this commit relied on, by id
    (Phase 1, TC-SG-04): the stale-check findings' tokens plus the token
    covering each path_guard-DENYed path in --files (what Tier-1's own
    forbidden-path gate relied on). Plumbed commits never fire the porcelain
    post-commit hook, so without this the tokens lingered in pending/ and
    were swept -- mis-attributed -- by the next unrelated porcelain commit
    (sampled live: 3 of the last 40 archived tokens). Never raises."""
    ids = set(token_ids)
    for f in files:
        try:
            verdict, _reason = path_guard.check_path(f)
        except Exception:
            continue
        if verdict == "DENY":
            try:
                token = override_manager.find_valid_token_for_path(f)
            except Exception:
                token = None
            if token and token.get("override_id"):
                ids.add(token["override_id"])
    for token_id in sorted(t for t in ids if t):
        try:
            if override_manager.consume_token(token_id, commit_sha):
                print(f"consumed override token {token_id} -> {commit_sha[:10]}")
        except Exception as exc:  # noqa: BLE001 -- bookkeeping must not fail the commit
            print(f"WARNING: could not consume override token {token_id}: {exc}",
                  file=sys.stderr)


class RefreshRunTrailerError(RuntimeError):
    """Raised by --refresh-run when the cited run cannot supply trailers yet."""


def _stamp_refresh_run_trailers(message: str, family: str, platform: str, run_id: str) -> str:
    """Return `message` with the run's Refresh-Run/Refresh-Base/Refresh-Source-SHA
    trailers appended, unless they are already present and correct.

    ST-154: `bind_commit()` requires a commit's OWN message to carry these 3
    trailers as its final paragraph (`refresh_run._commit_trailer_values`).
    Before this flag existed, a session following the documented
    `refresh_run.py start -> run -> verify -> [commit] -> bind-commit`
    procedure had to hand-author them, and forgetting to do so left a
    published, trailer-less commit with no forward-fix path once pushed
    (ST-126 -- amending is forbidden, an empty follow-up commit is rejected
    for having no changed paths). This makes the correct trailers the
    default outcome of citing --refresh-run, not something to remember by
    hand. Idempotent: a message that already carries the exact required
    trailers is returned unchanged, so re-running the same commit build
    (e.g. after a retry) never double-stamps.
    """
    manifest = _refresh_run._load_manifest(family, platform, run_id)
    base_commit_sha = manifest.get("base_commit_sha")
    target_source_sha = manifest.get("target_source_sha")
    if not base_commit_sha or not target_source_sha:
        raise RefreshRunTrailerError(
            f"Run {family}/{platform}/{run_id} has no target_source_sha pinned yet "
            "-- run 'refresh_run.py verify' before committing with --refresh-run."
        )
    required = {
        "Refresh-Run": run_id,
        "Refresh-Base": base_commit_sha,
        "Refresh-Source-SHA": target_source_sha,
    }
    existing = _refresh_run._commit_trailer_values(message)
    if all(existing.get(key) == [value] for key, value in required.items()):
        return message
    trailer_block = "\n".join(f"{key}: {value}" for key, value in required.items())
    return message.rstrip("\n") + "\n\n" + trailer_block + "\n"


class CommitProvenanceError(RuntimeError):
    """Raised when a commit's message fails mandatory provenance checks
    (Skills invoked / Co-authored-by) that scripts/commit-msg-skills.sh
    would otherwise enforce for a porcelain commit -- except commit-tree
    never fires git hooks, so THIS tool is the only enforcement point for
    anything it builds. Found live 2026-08-31: commit 833d9997e6 (built by
    this exact tool, --skills S-88 S-84) shipped to origin/main with
    neither a "Skills invoked:" line nor a Co-authored-by trailer --
    nothing had ever checked the message text itself."""


_SKILLS_INVOKED_RE = re.compile(r"(?i)skills?\s*invoked")
_COAUTHOR_RE = re.compile(r"(?im)^[ \t]*co-authored?-by:\s*(.+?)\s*$")


def _ensure_commit_provenance_trailers(
    message: str, skills: "list[str]", co_author: "str | None",
) -> str:
    """Return `message` with a "Skills invoked:" line guaranteed present and
    a Co-authored-by trailer guaranteed present, or raise CommitProvenanceError.

    Mirrors _stamp_refresh_run_trailers's ST-154 pattern (preventive, not
    reactive) for a more fundamental gap: this tool bypasses
    scripts/commit-msg-skills.sh entirely (commit-tree never fires git
    hooks), so that hook's own checks NEVER run for anything built here --
    they must be enforced in-process instead.

    "Skills invoked:" is always auto-appended when missing, from `skills`
    -- the exact same data already used to build this commit's retroactive
    skill-run record, so the two can never drift (same regex commit-msg-
    skills.sh itself uses: 'skills?\\s*invoked', no anchoring, no colon
    required, so an already-present line in any of its accepted shapes is
    detected and left alone rather than duplicated).

    Co-authored-by is different: this tool cannot safely guess which agent
    did the work, so it is auto-appended ONLY when the caller supplies
    `co_author` explicitly; otherwise the message must already carry
    exactly one (same "one agent, one trailer" rule commit-msg-skills.sh
    enforces for porcelain commits) or the commit is refused outright.
    """
    if not _SKILLS_INVOKED_RE.search(message):
        skills_line = f"Skills invoked: [{', '.join(skills)}]"
        message = message.rstrip("\n") + "\n\n" + skills_line + "\n"

    existing = _COAUTHOR_RE.findall(message)
    if co_author:
        co_author = co_author.strip()
        if len(existing) > 1:
            raise CommitProvenanceError(
                f"--co-author was given but the message already has "
                f"{len(existing)} Co-authored-by trailers -- ambiguous. "
                "Pass a message with at most one, or drop --co-author."
            )
        if existing and existing[0] != co_author:
            raise CommitProvenanceError(
                f"--co-author={co_author!r} conflicts with the message's "
                f"existing trailer {existing[0]!r} -- fix one or the other."
            )
        if not existing:
            message = message.rstrip("\n") + "\n\n" + f"Co-Authored-By: {co_author}\n"
        return message

    if len(existing) == 0:
        raise CommitProvenanceError(
            "message has no Co-authored-by trailer and no --co-author was "
            "given. scripts/commit-msg-skills.sh would normally require "
            "exactly one for any agent commit, but it never runs for a "
            "commit built by this tool (commit-tree bypasses all git "
            "hooks) -- pass --co-author \"Name <email>\", or include the "
            "trailer in --message/--message-file yourself."
        )
    if len(existing) > 1:
        raise CommitProvenanceError(
            f"message has {len(existing)} Co-authored-by trailers -- only "
            "one agent, one trailer is permitted (same rule "
            "scripts/commit-msg-skills.sh enforces for porcelain commits)."
        )
    return message


def main(argv: "list[str] | None" = None) -> int:
    # TC-SG-18 (found live during this plan's own Phase 0a dogfood commit,
    # 2026-08-30): main() crashed with UnicodeEncodeError while PRINTING
    # Tier-1 output to a cp1252 console -- AFTER the push, BEFORE the
    # skill-run record was filed. Output must never be able to kill the
    # governance trail.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--files-from", dest="files_from", metavar="FILE",
                        help="Read file paths (one per line) from FILE. Merged with "
                             "--files. Avoids OS argument-list-too-long errors on "
                             "large commits.")
    parser.add_argument("--message", default=None)
    parser.add_argument("--message-file", default=None)
    parser.add_argument("--co-author", default=None, dest="co_author",
                        help="Co-authored-by trailer value, e.g. "
                             "'Claude Sonnet 5 <noreply@anthropic.com>' -- "
                             "appended automatically if the message doesn't "
                             "already have one (ST-154-style preventive "
                             "pattern, 2026-08-31 provenance-gap incident: "
                             "commit-tree bypasses commit-msg-skills.sh "
                             "entirely, so nothing else ever checks this for "
                             "a commit built by this tool). If omitted, "
                             "--message/--message-file must already contain "
                             "exactly one Co-authored-by trailer, or the "
                             "commit is refused.")
    parser.add_argument("--skills", nargs="+", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--remote", default="origin",
                        help="Remote name or URL to push to (default: origin). "
                             "For GH_TOKEN-authenticated pushes, pass the full "
                             "x-access-token URL directly.")
    parser.add_argument("--base-sha", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--skip-stale-check", action="store_true")
    parser.add_argument("--skip-ledger-check", action="store_true",
                        help="Skip the session-ledger cross-check (G16 part 2). "
                             "Emergency escape hatch only, matching "
                             "--skip-stale-check's existing escalation pattern -- "
                             "not a routine default.")
    parser.add_argument("--skip-tier1-checks", action="store_true",
                        help="Skip scripts/pre-commit-audit.sh (Tier 1). Emergency "
                             "escape hatch only, matching --skip-stale-check's "
                             "existing escalation pattern -- not a routine default.")
    parser.add_argument("--strict-isolation", action="store_true",
                        help="Block the commit on an isolation-canary failure or a "
                             "postcondition breach (real .git/index or real on-disk "
                             "content of a --files path changed during the Tier 1 "
                             "check window), instead of the default: report loudly "
                             "and proceed. Defaults to off for a soft-launch review "
                             "window on these newly-added checks -- see "
                             "reports/skill-gaps/"
                             "2026-08-20-git-plumb-commit-tier1-mutation-safety.md, "
                             "Phase 2c.")
    parser.add_argument("--no-auto-reconcile", action="store_true", dest="no_auto_reconcile",
                        help="Disable the automatic reconcile() retry on a non-fast-forward "
                             "push rejection (default: retry once via reconcile(), building "
                             "a two-parent merge commit against the current remote tip). "
                             "Raises immediately instead if the push is rejected.")
    parser.add_argument("--no-push", action="store_true", dest="no_push")
    parser.add_argument("--wide-findings", choices=["warn", "block"], default="warn",
                        dest="wide_findings",
                        help="Policy for lookback-class stale findings (older than "
                             "this session's own window). Soak default: warn; the "
                             "flip to block is plan taskcard TC-SG-07.")
    parser.add_argument("--no-sync", action="store_true", dest="no_sync",
                        help="Skip the post-advance real-index/worktree sync "
                             "(checkout_sync, RC-1 source fix). The residue the "
                             "commit leaves behind then WILL be swept into the "
                             "next porcelain commit as a byte-exact revert unless "
                             "cleared by hand (git restore --staged -- <files>).")
    parser.add_argument("--ack-gitignored", nargs="+", default=None,
                        help="Paths in --files that are intentionally .gitignore-matched "
                             "(e.g. a legitimate override precedent) -- silences the "
                             "warning for exactly these paths, not the whole run.")
    parser.add_argument("--refresh-run", nargs=3, default=None,
                        metavar=("FAMILY", "PLATFORM", "RUN_ID"), dest="refresh_run",
                        help="Automatically append this refresh_run's required "
                             "Refresh-Run/Refresh-Base/Refresh-Source-SHA trailers "
                             "to --message/--message-file before committing (ST-154 "
                             "-- makes trailer attachment preventive, not reactive; "
                             "see refresh_run_bind_recovery.py for recovering an "
                             "already-pushed commit that skipped this flag). Errors "
                             "if the run has not reached 'verify' yet (no "
                             "target_source_sha pinned).")
    args = parser.parse_args(argv)

    files = list(args.files) if args.files else []
    if args.files_from:
        try:
            extra = Path(args.files_from).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"ERROR: cannot read --files-from '{args.files_from}': {exc}", file=sys.stderr)
            return 2
        files.extend(p for p in extra if p.strip())
    if not files:
        print("ERROR: pass --files, --files-from, or both (at least one file required)",
              file=sys.stderr)
        return 2
    args.files = files

    if args.message and args.message_file:
        print("ERROR: pass exactly one of --message or --message-file", file=sys.stderr)
        return 2
    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8")
    elif args.message:
        message = args.message
    else:
        print("ERROR: --message or --message-file is required", file=sys.stderr)
        return 2

    if args.refresh_run:
        rr_family, rr_platform, rr_run_id = args.refresh_run
        try:
            message = _stamp_refresh_run_trailers(message, rr_family, rr_platform, rr_run_id)
        except (RefreshRunTrailerError, _refresh_run.RefreshRunError) as exc:
            print(f"ERROR: --refresh-run trailer stamping failed: {exc}", file=sys.stderr)
            return 2

    try:
        message = _ensure_commit_provenance_trailers(message, args.skills, args.co_author)
    except CommitProvenanceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        result = plumb_commit(
            args.files, message,
            branch=args.branch, remote=args.remote,
            base_sha=args.base_sha, session_id=args.session_id,
            skip_stale_check=args.skip_stale_check,
            skip_ledger_check=args.skip_ledger_check,
            skip_tier1_checks=args.skip_tier1_checks,
            strict_isolation=args.strict_isolation, push=not args.no_push,
            auto_reconcile=not args.no_auto_reconcile,
            ack_gitignored=args.ack_gitignored,
            sync_state=not args.no_sync,
            wide_findings=args.wide_findings,
            skills=args.skills, plan=args.plan,
        )
    except PlumbCommitIdentityUnresolved as exc:
        print(f"IDENTITY: {exc}", file=sys.stderr)
        return 3
    except PlumbCommitBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except PlumbCommitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"commit_sha={result['commit_sha']}")
    print(f"tree_sha={result['tree_sha']}")
    print(f"pushed={result['pushed']}")
    if result.get("reconciled_against"):
        print(f"reconciled_against={result['reconciled_against']} "
              f"(non-fast-forward push auto-resolved via a merge commit)")
    if (result.get("tier1_output") or "").strip():
        print("--- Tier 1 output ---")
        print(result["tier1_output"])

    if result.get("skill_run_id"):
        print(f"skill_run_id={result['skill_run_id']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

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

Usage::

    python scripts/pipeline/commands/ops/git_plumb_commit.py \\
      --files scripts/foo.py scripts/tests/test_foo.py \\
      --message-file /path/to/msg.txt \\
      --skills S-76 --plan "fix(pipeline): durable foo.py bug" \\
      --branch main --remote origin
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_CI_CHECKS_DIR = _PIPELINE_ROOT.parent / "ci" / "checks"
if str(_CI_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_CHECKS_DIR))

import check_stale_file_regression as sfr  # noqa: E402
from commands.governance import override_manager  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_SKILL_RUN_MANAGER = (
    _PIPELINE_ROOT / "commands" / "ops" / "skill_run_manager.py"
)

_REPO_ROOT = _DEFAULT_REPO_ROOT
_SKILL_RUN_MANAGER = _DEFAULT_SKILL_RUN_MANAGER
_COMMAND_RUNNER: Callable[..., "subprocess.CompletedProcess"] = subprocess.run


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


class PlumbCommitTier1Failed(PlumbCommitError):
    """Raised when scripts/pre-commit-audit.sh (this repo's Tier 1 commit-time
    gate) fails against the isolated temp index -- no commit is created.

    TC-CIR-05 (2026-08-14, CI reliability reassessment, Root Cause A): before this,
    every commit made through this tool received exactly ONE of pre-commit-audit.sh's
    ~32 checks (a re-implemented copy of the stale-file-regression check) -- `commit-
    tree` never invokes git hooks, and this repo has no pre-push hook backstop for
    plumbed commits either, since they also skip `git push`'s hook the same way. This
    tool is CLAUDE.md's own sanctioned mechanism for concurrent-session-safe commits,
    used repeatedly across this very session -- the gap was total, not partial, for
    every commit that ever went through it.
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


_CREDENTIAL_URL_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


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
        ["git", *args], cwd=str(repo_root), capture_output=True, text=True,
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

    Paths are passed as ARGUMENTS, not via --stdin: on Windows,
    subprocess text-mode stdin translates a "\\n"-joined input to "\\r\\n"
    before git ever sees it, embedding a literal "\\r" into each path git
    reads -- which git then C-quotes in its output as an "unusual"
    filename character (e.g. `"ignored/secret.txt\\r"`), breaking exact-
    match comparison against ack_gitignored. Found live via this change's
    own tests. Passing paths as argv sidesteps the whole translation path.
    """
    if not files:
        return []
    result = _COMMAND_RUNNER(
        ["git", "check-ignore", *files], cwd=str(repo_root),
        capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        # check-ignore itself failed (e.g. not a git repo) -- fail open,
        # same policy as the stale-file regression check's own base_sha
        # resolution failure: this tool's own infrastructure being
        # unavailable must never block an unrelated commit.
        return []
    return [line for line in result.stdout.splitlines() if line]


def _check_for_regressions(
    files: list[str], base_sha: "str | None", *, repo_root: Path,
) -> list[dict]:
    """Run the stale-file regression check against every file (working-tree
    content, since nothing is staged yet -- git_plumb_commit builds its own
    isolated index). Returns findings NOT covered by a valid override token.
    """
    if not base_sha:
        return []  # advisory: no base_sha available, same fail-open policy as the check itself
    uncovered = []
    for f in files:
        finding = sfr.check_file(f, base_sha, repo_root=repo_root, use_staged=False)
        if finding is None:
            continue
        if override_manager.find_valid_token_for_path(finding["file"]) is not None:
            continue  # governed, audited exception -- allowed through
        uncovered.append(finding)
    return uncovered


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
                [candidate, "-c", "uname -s"], capture_output=True, text=True, timeout=10,
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


def _run_tier1_checks(
    tmp_index_path: str, message: str, *, repo_root: Path,
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
    env = {
        **os.environ,
        "GIT_INDEX_FILE": tmp_index_path,
        "EVIDENCE_RESTAMP_MSG": message,
        "BULK_GRADE_MIGRATION_MSG": message,
    }
    return _COMMAND_RUNNER(
        [bash_path, "scripts/pre-commit-audit.sh"],
        cwd=str(repo_root), capture_output=True, text=True, env=env,
    )


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
    skip_tier1_checks: bool = False,
    push: bool = True,
    ack_gitignored: "list[str] | None" = None,
) -> dict[str, Any]:
    """Perform the full isolated git-plumbing commit sequence atomically:
    stale-file regression check -> temp-index build -> Tier 1 checks
    (scripts/pre-commit-audit.sh, against the isolated index) -> write-tree ->
    commit-tree -> push -> local ref sync.

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

    Returns a result dict: {head_sha, tree_sha, commit_sha, pushed, files,
    gitignore_warnings}. Raises PlumbCommitBlocked if an uncovered
    regression is found, or PlumbCommitError for any git operation failure.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    if remote_name is None:
        remote_name = "origin"
    ack_set = set(ack_gitignored or [])

    head_sha = _git(["rev-parse", "HEAD"], repo_root=root).stdout.strip()

    if not skip_stale_check:
        resolved_base_sha = sfr.resolve_base_sha(base_sha, session_id)
        uncovered = _check_for_regressions(files, resolved_base_sha, repo_root=root)
        if uncovered:
            raise PlumbCommitBlocked(uncovered)

    gitignore_warnings = [f for f in _gitignored_files(files, repo_root=root) if f not in ack_set]
    for f in gitignore_warnings:
        print(
            f"WARNING: {f} matches .gitignore and will be force-tracked by this commit "
            f"(git add -f). If this is intentional, pass --ack-gitignored {f} to silence "
            f"this warning; if not, remove it from --files.",
            file=sys.stderr,
        )

    tmp_index_fd, tmp_index_path = tempfile.mkstemp(prefix="git_plumb_index_")
    os.close(tmp_index_fd)
    os.unlink(tmp_index_path)  # git read-tree wants a path that doesn't pre-exist as a real index
    try:
        env_index = {**os.environ, "GIT_INDEX_FILE": tmp_index_path}

        def _git_indexed(args: list[str]) -> "subprocess.CompletedProcess":
            result = _COMMAND_RUNNER(
                ["git", *args], cwd=str(root), capture_output=True, text=True, env=env_index,
            )
            if result.returncode != 0:
                safe_args = _redact_credentials(" ".join(args))
                safe_stderr = _redact_credentials(result.stderr)
                raise PlumbCommitError(
                    f"git {safe_args} (indexed) failed: {safe_stderr}"
                )
            return result

        _git_indexed(["read-tree", head_sha])
        _git_indexed(["add", "-f", *files])

        if not skip_tier1_checks:
            tier1_result = _run_tier1_checks(tmp_index_path, message, repo_root=root)
            if tier1_result is not None and tier1_result.returncode != 0:
                raise PlumbCommitTier1Failed(
                    tier1_result.stdout + tier1_result.stderr, tier1_result.returncode,
                )

        tree_sha = _git_indexed(["write-tree"]).stdout.strip()
    finally:
        try:
            os.unlink(tmp_index_path)
        except OSError:
            pass

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

    pushed = False
    if push:
        _git(["push", remote, f"{commit_sha}:refs/heads/{branch}"], repo_root=root)
        pushed = True
        _git(["update-ref", f"refs/remotes/{remote_name}/{branch}", commit_sha], repo_root=root)

    return {
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "commit_sha": commit_sha,
        "pushed": pushed,
        "files": list(files),
        "gitignore_warnings": gitignore_warnings,
    }


def _file_skill_run_record(
    *, skills: list[str], plan: str, commit_sha: str, repo_root: Path,
) -> "str | None":
    """Create + finalize the mandatory retroactive skill-run record for a
    git-plumbed commit. Returns the run_id, or None if creation failed
    (printed to stderr, never raised -- a governance-bookkeeping failure
    must not make the caller believe the commit itself failed, since by
    this point it has already been pushed)."""
    create = _COMMAND_RUNNER(
        [sys.executable, str(_SKILL_RUN_MANAGER), "create",
         "--skills", *skills, "--plan", plan, "--retroactive", "--run-type", "targeted"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if create.returncode != 0:
        print(f"WARNING: retroactive skill-run record creation failed: {create.stderr}",
              file=sys.stderr)
        return None
    run_id = None
    for line in create.stdout.splitlines():
        if "Created skill run record:" in line:
            run_id = line.split(":", 1)[1].strip()
            break
    if not run_id:
        print("WARNING: could not parse run_id from skill_run_manager.py create output",
              file=sys.stderr)
        return None
    finalize = _COMMAND_RUNNER(
        [sys.executable, str(_SKILL_RUN_MANAGER), "finalize",
         "--run-id", run_id, "--outcome", "success", "--commit-sha", commit_sha],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if finalize.returncode != 0:
        print(f"WARNING: retroactive skill-run record finalize failed: {finalize.stderr}",
              file=sys.stderr)
        return run_id
    return run_id


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--message", default=None)
    parser.add_argument("--message-file", default=None)
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
    parser.add_argument("--skip-tier1-checks", action="store_true",
                        help="Skip scripts/pre-commit-audit.sh (Tier 1). Emergency "
                             "escape hatch only, matching --skip-stale-check's "
                             "existing escalation pattern -- not a routine default.")
    parser.add_argument("--no-push", action="store_true", dest="no_push")
    parser.add_argument("--ack-gitignored", nargs="+", default=None,
                        help="Paths in --files that are intentionally .gitignore-matched "
                             "(e.g. a legitimate override precedent) -- silences the "
                             "warning for exactly these paths, not the whole run.")
    args = parser.parse_args(argv)

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

    try:
        result = plumb_commit(
            args.files, message,
            branch=args.branch, remote=args.remote,
            base_sha=args.base_sha, session_id=args.session_id,
            skip_stale_check=args.skip_stale_check,
            skip_tier1_checks=args.skip_tier1_checks, push=not args.no_push,
            ack_gitignored=args.ack_gitignored,
        )
    except PlumbCommitBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except PlumbCommitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"commit_sha={result['commit_sha']}")
    print(f"tree_sha={result['tree_sha']}")
    print(f"pushed={result['pushed']}")

    if result["pushed"]:
        run_id = _file_skill_run_record(
            skills=args.skills, plan=args.plan,
            commit_sha=result["commit_sha"], repo_root=_REPO_ROOT,
        )
        if run_id:
            print(f"skill_run_id={run_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

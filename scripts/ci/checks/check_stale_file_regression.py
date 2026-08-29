"""check_stale_file_regression.py -- detects a commit silently reverting a
MORE RECENT commit made by someone else since this session's own baseline.

Adapted from aspose.org scripts/ci/checks/check_stale_file_regression.py
(2026-08-29 sync) for standalone use. Found live at aspose.org 2026-08-01: a
commit silently reverted an unrelated fix committed by another session hours
earlier -- byte-exact regression of corrected content back to a known-wrong
value, with the reverting commit's own message never mentioning the file.
This is the general mechanism, not a one-off: guarding governance metadata
or coordination artifacts is not the same as inspecting ordinary file
CONTENT for regression at commit time. This check closes that gap for any
repo where more than one agent/session may commit concurrently.

ADAPTATION NOTE: aspose.org's version resolves its base commit SHA via a
companion module (session_ledger.py's get_base_commit_sha()) as a
convenience fallback when --base-sha isn't passed explicitly. This repo's
own scripts/pipeline/commands/ops/session_ledger.py tracks a DIFFERENT data
model (a dirty-file-touch ledger, not a base commit SHA) and has no
equivalent function -- so that convenience fallback does not exist here.
--base-sha is required; there is no --session-id auto-resolve mode. This is
a deliberate scope cut, not an oversight: building a base-commit-SHA tracker
here would mean porting session_ledger's SHA-tracking concept on top of an
already-different session_ledger design, which is exactly the kind of
larger, separately-scoped concurrency-infrastructure work this sync
explicitly deferred (see TASK_BACKLOG.md).

For each candidate file:
  1. Find its most recent commit on HEAD (git log -1 --format=%H -- <file>).
  2. If that commit is a strict descendant of base_sha (i.e. genuinely
     happened DURING this session, not before it) -- an "intervening commit"
     this session may not know about -- compare the file's proposed content
     against that commit's blob and its PARENT's blob for the same path.
  3. If proposed content matches the PARENT (the state the intervening
     commit specifically replaced) and does NOT match the intervening
     commit itself, this is a silent revert: report it.

Deliberately a byte-exact match, not a fuzzy/similarity heuristic (honest
limit, not an oversight): a session that reverts AND makes some further
legitimate edit to the same file in the same commit would not be caught by
this check.

Usage:
    git diff --cached --name-only | .venv/bin/python scripts/ci/checks/check_stale_file_regression.py --base-sha <sha>
    .venv/bin/python scripts/ci/checks/check_stale_file_regression.py --files a.py b.py --base-sha <sha>

Exit codes:
  0 -- no regressions detected (including: no --base-sha given -- advisory,
       fails OPEN, since this check's own infrastructure being unavailable
       must never itself block an unrelated commit)
  1 -- at least one regression detected
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _run_git(args: list[str], *, repo_root: Path) -> "subprocess.CompletedProcess":
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=str(repo_root), timeout=30,
    )


def find_intervening_commit(
    file_path: str, base_sha: str, *, repo_root: Path = _REPO_ROOT
) -> "str | None":
    """Return the SHA of file_path's most recent commit on HEAD, if it is a
    STRICT descendant of base_sha (a genuine intervening commit this session
    may not know about). Returns None if the file hasn't changed since
    base_sha, or if base_sha isn't an ancestor of that commit at all
    (unrelated/rewritten history -- nothing meaningful to compare)."""
    last = _run_git(["log", "-1", "--format=%H", "HEAD", "--", file_path], repo_root=repo_root)
    if last.returncode != 0:
        return None
    last_sha = last.stdout.strip()
    if not last_sha or last_sha == base_sha:
        return None
    ancestor_check = _run_git(
        ["merge-base", "--is-ancestor", base_sha, last_sha], repo_root=repo_root,
    )
    if ancestor_check.returncode != 0:
        return None
    return last_sha


def get_blob_at(commit_sha: str, file_path: str, *, repo_root: Path = _REPO_ROOT) -> "str | None":
    """Return file_path's text content at commit_sha, or None if the path
    didn't exist there (or isn't decodable as UTF-8 text -- binary files are
    out of scope for this check, treated as 'nothing to compare')."""
    result = _run_git(["show", f"{commit_sha}:{file_path}"], repo_root=repo_root)
    if result.returncode != 0:
        return None
    return result.stdout


def get_staged_content(file_path: str, *, repo_root: Path = _REPO_ROOT) -> "str | None":
    """Return file_path's currently STAGED (index) content -- what will
    actually be committed -- or None if not staged / doesn't exist there."""
    result = _run_git(["show", f":{file_path}"], repo_root=repo_root)
    if result.returncode != 0:
        return None
    return result.stdout


def detect_regression(
    proposed_content: "str | None",
    parent_content: "str | None",
    intervening_content: "str | None",
) -> bool:
    """Pure comparison, no I/O. True if proposed_content looks like a silent
    revert of the intervening commit: matches the PARENT's (pre-intervening)
    state and does not match the intervening commit's own state."""
    if intervening_content is None:
        return False  # intervening commit didn't leave a comparable text blob here
    if parent_content is None:
        return False  # file was newly created by the intervening commit -- no older state to revert to
    if proposed_content == intervening_content:
        return False  # already incorporates the intervening commit -- fine
    return proposed_content == parent_content


def check_file(
    file_path: str, base_sha: str, *, repo_root: Path = _REPO_ROOT, use_staged: bool = True
) -> "dict | None":
    """Check one file. Returns a finding dict if a regression is detected,
    else None."""
    intervening = find_intervening_commit(file_path, base_sha, repo_root=repo_root)
    if intervening is None:
        return None

    intervening_content = get_blob_at(intervening, file_path, repo_root=repo_root)
    parent_content = get_blob_at(f"{intervening}^", file_path, repo_root=repo_root)
    proposed_content = (
        get_staged_content(file_path, repo_root=repo_root)
        if use_staged
        else (repo_root / file_path).read_text(encoding="utf-8", errors="replace")
        if (repo_root / file_path).is_file()
        else None
    )

    if detect_regression(proposed_content, parent_content, intervening_content):
        return {
            "file": file_path,
            "intervening_commit": intervening,
        }
    return None


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files", nargs="*", default=None,
                        help="Files to check (default: read newline-delimited paths from stdin)")
    parser.add_argument("--base-sha", default=None,
                        help="Session's base commit sha (required -- no auto-resolve fallback in this repo)")
    parser.add_argument("--working-tree", action="store_true",
                        help="Compare working-tree content instead of the git INDEX (staged) content")
    args = parser.parse_args(argv)

    files = args.files
    if files is None:
        files = [line.strip() for line in sys.stdin if line.strip()]
    if not files:
        return 0

    base_sha = args.base_sha
    if not base_sha:
        # Advisory: this check's own infrastructure being unavailable (no
        # --base-sha given) must never itself block an unrelated commit.
        print("check_stale_file_regression: no --base-sha given -- skipping (advisory).",
              file=sys.stderr)
        return 0

    # Resolve repo_root from CWD, not the module-level _REPO_ROOT default --
    # a function default parameter is bound once at def time, so relying on
    # it here would silently ignore the caller's actual working directory.
    repo_root = Path.cwd()

    findings = []
    for f in files:
        result = check_file(f, base_sha, repo_root=repo_root, use_staged=not args.working_tree)
        if result:
            findings.append(result)

    if findings:
        print(f"STALE FILE REGRESSION: {len(findings)} file(s) look like a silent revert "
              f"of a more recent commit:")
        for f in findings:
            print(f"  {f['file']}")
            print(f"    matches the state BEFORE commit {f['intervening_commit'][:10]}, "
                  f"which changed this file after your session began.")
            print(f"    Re-read the current file and reapply your own change on top of it, "
                  f"or if this revert is intentional, say so explicitly in the commit message.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

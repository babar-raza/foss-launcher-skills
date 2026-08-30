"""check_stale_file_regression.py — detects a commit silently reverting a
MORE RECENT commit made by someone else since this session's own baseline.

Found live 2026-08-01: TC-MT018-06's commit d2dce37de5 silently reverted an
unrelated fix to fetch_aspose_com_targets.py / data/aspose_com_targets.json
committed by another session hours earlier -- byte-exact regression of
corrected entries back to known-wrong values (e.g. pdf/go's URL reverted from
the corrected bundled-page redirect target back to a 404), with the reverting
commit's own message never mentioning either file. This is the general
mechanism, not a one-off: every protection built in the production
concurrency redesign (session_identity.py, taskcard_store.py,
master_plan_index.py) guards governance METADATA or shared coordination
artifacts -- none of them ever inspected ordinary file CONTENT for regression
at commit time. This check closes that gap.

Requires session_ledger.py's base_commit_sha (added alongside this check --
the HEAD sha recorded at the committing session's init_session() time). For
each candidate file:
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
this check. Exact match is the high-confidence, low-false-positive signal
that matches the actual incident this check exists to prevent; a fuzzier
heuristic was deliberately not attempted here to avoid false-positive risk
without first observing whether partial-revert cases occur in practice.

Usage:
    git diff --cached --name-only | python check_stale_file_regression.py --base-sha <sha>
    python check_stale_file_regression.py --files a.py b.py --base-sha <sha>
    python check_stale_file_regression.py --files a.py --session-id <id>   # resolves base-sha via session_ledger

Exit codes:
  0 -- no regressions detected (including: base sha unresolvable -- advisory,
       fails OPEN, since this check's own infrastructure being unavailable
       must never itself block an unrelated commit)
  1 -- at least one regression detected
  3 -- session identity AMBIGUOUS (>=2 live ledgers, no explicit identity) --
       a clear one-line message, never a traceback (ST-095 containment,
       2026-08-29; the full JSON/exit-code contract lands in Phase 1)
  4 -- infrastructure error (git subprocess failure, undecodable state) --
       previously indistinguishable from "regression found" (exit 1 via
       traceback) or from "clean" (exit 0 via a dead reader thread)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PIPELINE_OPS_DIR = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"


class StaleCheckInfraError(RuntimeError):
    """The check itself could not run (git failure, no captured output).

    Deliberately distinct from both "clean" and "regression found": ST-096
    (2026-08-28) proved a subprocess reader-thread death produced stdout=None
    and a silent exit 0 -- an infrastructure failure must never be readable
    as a verdict in either direction."""


def _run_git(args: list[str], *, repo_root: Path) -> "subprocess.CompletedProcess":
    # encoding= is explicit because subprocess text-mode otherwise decodes
    # with the locale codec (cp1252 on Windows): content bytes cp1252 cannot
    # map killed the reader thread (stdout=None -> silent pass, ST-096), and
    # mappable non-ASCII bytes decoded DIFFERENTLY from the UTF-8 worktree
    # read in check_file(), making the comparison silently inert for any
    # non-ASCII file (reproduced 2026-08-28). errors="replace" keeps both
    # sides of every comparison in the same codec, so equality semantics are
    # preserved exactly (both blobs pass through the identical decode).
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(repo_root), timeout=30,
    )
    if result.stdout is None or result.stderr is None:
        raise StaleCheckInfraError(
            f"git {' '.join(args)}: subprocess returned no captured output "
            f"(reader failure) -- refusing to treat missing output as a verdict"
        )
    return result


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


def resolve_base_sha(explicit: "str | None", session_id: "str | None") -> "str | None":
    if explicit:
        return explicit
    if str(_PIPELINE_OPS_DIR) not in sys.path:
        sys.path.insert(0, str(_PIPELINE_OPS_DIR))
    import session_ledger  # noqa: E402 (repo layout requires the sys.path insert above)
    return session_ledger.get_base_commit_sha(session_id)


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="*", default=None,
                        help="Files to check (default: read newline-delimited paths from stdin)")
    parser.add_argument("--base-sha", default=None,
                        help="Session's base commit sha (default: resolve via session_ledger)")
    parser.add_argument("--session-id", default=None,
                        help="Explicit session id for base-sha resolution (default: env/unambiguous scan)")
    parser.add_argument("--working-tree", action="store_true",
                        help="Compare working-tree content instead of the git INDEX (staged) content")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    files = args.files
    if files is None:
        files = [line.strip() for line in sys.stdin if line.strip()]
    if not files:
        return 0

    try:
        base_sha = resolve_base_sha(args.base_sha, args.session_id)
    except Exception as exc:
        # session_ledger.AmbiguousSessionError reaches here as a duck-typed
        # name check (importing it eagerly would couple this module to the
        # ops package even when --base-sha is explicit). Before this guard,
        # >=2 live session ledgers produced a raw traceback with exit 1 --
        # which pre-commit Step 34 then misparsed as file-name findings
        # needing override tokens (an unbypassable deadlock, ST-095).
        if type(exc).__name__ == "AmbiguousSessionError":
            print(f"check_stale_file_regression: AMBIGUOUS session identity -- {exc}",
                  file=sys.stderr)
            print("Fix: pass --session-id <id> or --base-sha <sha>, or export "
                  "AGENT_SESSION_ID=<id> for this invocation.", file=sys.stderr)
            return 3
        print(f"check_stale_file_regression: INFRASTRUCTURE ERROR resolving baseline: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    if not base_sha:
        # Advisory: this check's own infrastructure being unavailable (no
        # session ledger, fresh repo, etc.) must never itself block an
        # unrelated commit.
        print("check_stale_file_regression: no base commit sha available -- skipping (advisory).",
              file=sys.stderr)
        return 0

    # Resolve repo_root from CWD, not the module-level _REPO_ROOT default --
    # a function default parameter is bound once at def time, so relying on
    # it here would silently ignore the caller's actual working directory
    # (the pre-commit hook and every git-plumbing caller always run with CWD
    # at the repo root; hardcoding the module's own on-disk location would
    # be wrong for anyone invoking this against a different checkout).
    repo_root = Path.cwd()

    findings = []
    try:
        for f in files:
            result = check_file(f, base_sha, repo_root=repo_root, use_staged=not args.working_tree)
            if result:
                findings.append(result)
    except (StaleCheckInfraError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"check_stale_file_regression: INFRASTRUCTURE ERROR while checking files: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

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

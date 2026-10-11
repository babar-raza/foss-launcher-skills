"""check_stale_file_regression.py — detects a commit silently reverting a
MORE RECENT commit (thin CLI over scripts/pipeline/lib/stale_file_regression.py
since 2026-08-30; stale-guard plan T2 / TC-SG-04).

Found live 2026-08-01 (TC-MT018-06's commit d2dce37de5) and again 2026-08-07
(`55586b637c` reverting 19 keyword files to a 5-day-old state): a commit whose
own message never mentions a file can land byte-exact stale content for it.
The engine now compares git blob OIDs (clean-filtered for worktree mode, so
core.autocrlf worktrees compare correctly) over a window that is the OLDEST of
the caller's explicit base, the session ledger's base, and a bounded lookback
(14 days / 5000 first-parent commits) — session identity is helpful for
classing findings, but no longer required for the check to run (the 08-07
revert predated the committing session entirely).

Finding classes: `session` (inside the resolved session window — always
blocking, today's guarantee) and `lookback` (visible only through the wider
window — WARN by default during the soak, `--wide-findings=block` to enforce;
the flip is plan taskcard TC-SG-07).

Usage:
    git diff --cached --name-only | python check_stale_file_regression.py
    python check_stale_file_regression.py --files a.py b.py --base-sha <sha>
    python check_stale_file_regression.py --files a.py --session-id <id>
    ... --format json          # machine consumers (pre-commit Step 34)
    ... --working-tree         # compare worktree content instead of the index

Env tier (tool-set only; honoured ONLY when GIT_INDEX_FILE and
PC_AUDIT_NO_MUTATE are also present — the git_plumb_commit.py Tier-1
signature, so `PC_AUDIT_BASE_SHA=... git commit` cannot bypass the gate):
PC_AUDIT_SESSION_ID, PC_AUDIT_BASE_SHA.

Exit codes:
  0 -- clean; or no window computable (advisory); or every finding is
       token-covered / lookback-class under the default warn policy
  1 -- at least one blocking, uncovered finding
  2 -- usage error
  3 -- an EXPLICIT --session-id names a missing/closed manifest (caller error;
       ambient ambiguity does NOT exit 3 -- the lookback window covers it)
  4 -- infrastructure error (git failure, missing capture) -- never a verdict
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PIPELINE_DIR = _REPO_ROOT / "scripts" / "pipeline"
_PIPELINE_OPS_DIR = _PIPELINE_DIR / "commands" / "ops"
for _p in (str(_PIPELINE_DIR), str(_PIPELINE_OPS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import stale_file_regression as slib  # noqa: E402

StaleCheckInfraError = slib.StaleCheckInfraError


# ---------------------------------------------------------------------------
# Back-compat wrappers (import surface used by git_plumb_commit.py history and
# the pre-existing test suite; the OID engine lives in the lib)
# ---------------------------------------------------------------------------

def detect_regression(
    proposed_content: "str | None",
    parent_content: "str | None",
    intervening_content: "str | None",
) -> bool:
    """Pure predicate on already-obtained states (content or OIDs alike):
    True iff proposed matches the PARENT of the intervening change and not
    the intervening change itself."""
    if intervening_content is None:
        return False
    if parent_content is None:
        return False
    if proposed_content == intervening_content:
        return False
    return proposed_content == parent_content


def find_intervening_commit(
    file_path: str, base_sha: str, *, repo_root: Path = _REPO_ROOT
) -> "str | None":
    """Newest commit in base..HEAD touching file_path (membership semantics --
    a side-branch commit merged after base counts; the old ancestry predicate
    missed those). None when the range is empty/invalid."""
    try:
        head = slib._rev_parse("HEAD", repo_root=Path(repo_root))
        if head is None or slib._rev_parse(base_sha, repo_root=Path(repo_root)) is None:
            return None
        found = slib.intervening_commits(base_sha, head, [file_path], repo_root=Path(repo_root))
    except StaleCheckInfraError:
        return None
    return found.get(file_path.replace("\\", "/"))


def check_file(
    file_path: str, base_sha: str, *, repo_root: Path = _REPO_ROOT, use_staged: bool = True
) -> "dict | None":
    """Single-file compatibility check with the ORIGINAL semantics (explicit
    base = the whole window; every finding blocking). Returns a finding dict
    or None."""
    root = Path(repo_root)
    head = slib._rev_parse("HEAD", repo_root=root)
    if head is None:
        return None
    baseline = slib.Baseline(window_sha=base_sha, source="explicit",
                             session_sha=base_sha, session_id=None)
    try:
        report = slib.detect_regressions(
            [file_path], baseline=baseline, head=head,
            mode="index" if use_staged else "worktree", repo_root=root,
            content_prefix_session_only=False,
        )
    except StaleCheckInfraError:
        return None
    for finding in report.findings:
        return {"file": finding.path, "intervening_commit": finding.intervening_commit}
    return None


def resolve_base_sha(explicit: "str | None", session_id: "str | None") -> "str | None":
    if explicit:
        return explicit
    import session_ledger  # noqa: E402 (repo layout requires the sys.path insert above)
    return session_ledger.get_base_commit_sha(session_id)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_repo_root(explicit: "str | None") -> Path:
    if explicit:
        return Path(explicit)
    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    top = (probe.stdout or "").strip()
    return Path(top) if probe.returncode == 0 and top else Path.cwd()


def _override_lookup(repo_root: Path):
    try:
        from commands.governance import override_manager  # noqa: E402
    except Exception:
        return None
    override_manager.configure(repo_root=repo_root)
    return override_manager.find_valid_token_for_path


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="*", default=None,
                        help="Files to check (default: newline-delimited paths on stdin)")
    parser.add_argument("--base-sha", default=None,
                        help="Explicit window anchor (must be an ancestor of HEAD)")
    parser.add_argument("--session-id", default=None,
                        help="Explicit session identity for baseline classing")
    parser.add_argument("--working-tree", action="store_true",
                        help="Compare working-tree content instead of the index")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--wide-findings", choices=["warn", "block"], default="warn",
                        help="Policy for lookback-class findings (soak default: warn; "
                             "the flip to block is plan taskcard TC-SG-07)")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--head", default=None)
    args = parser.parse_args(argv)

    files = args.files
    if files is None:
        files = [line.strip() for line in sys.stdin if line.strip()]
    if not files:
        return 0

    repo_root = _resolve_repo_root(args.repo_root)

    # Env tier: honoured only alongside the plumb tool's Tier-1 signature.
    env_session = env_base = None
    if os.environ.get("PC_AUDIT_NO_MUTATE") and os.environ.get("GIT_INDEX_FILE"):
        env_session = os.environ.get("PC_AUDIT_SESSION_ID") or None
        env_base = os.environ.get("PC_AUDIT_BASE_SHA") or None
    session_id = args.session_id or env_session
    explicit_base = args.base_sha or env_base

    ctx = None
    try:
        import session_ledger  # noqa: E402
        ctx = session_ledger.resolve_context(session_id)
    except Exception as exc:  # ledger infrastructure unavailable: proceed windowed
        print(f"check_stale_file_regression: note: session ledger unavailable "
              f"({type(exc).__name__}) -- using the lookback window.", file=sys.stderr)

    if args.session_id and ctx is not None and ctx.status in ("none", "closed"):
        print(f"check_stale_file_regression: explicit --session-id "
              f"{args.session_id!r} names a {ctx.status or 'missing'} manifest -- "
              f"fix the identity or pass --base-sha.", file=sys.stderr)
        return 3

    try:
        head = args.head or slib._rev_parse("HEAD", repo_root=repo_root)
        if head is None:
            raise StaleCheckInfraError("HEAD does not resolve")
        baseline = slib.resolve_baseline(explicit_sha=explicit_base, session_ctx=ctx,
                                         head=head, repo_root=repo_root)
        report = slib.detect_regressions(
            files, baseline=baseline, head=head,
            mode="worktree" if args.working_tree else "index",
            repo_root=repo_root, override_lookup=_override_lookup(repo_root),
        )
    except (StaleCheckInfraError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"check_stale_file_regression: INFRASTRUCTURE ERROR: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    if args.format == "json":
        payload = report.to_dict()
        payload["wide_findings_policy"] = args.wide_findings
        payload["blocking"] = [f.to_dict() for f in report.blocking(wide_findings=args.wide_findings)]
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(slib.format_text(report, wide_findings=args.wide_findings))

    blocking = report.blocking(wide_findings=args.wide_findings)
    if blocking:
        print(f"STALE FILE REGRESSION: {len(blocking)} blocking file(s) look like a "
              f"silent revert of a more recent commit. Re-read the current file and "
              f"reapply your change on top of it, or create a governed override: "
              f"override_manager.py create --paths <file> --reason '...' --plan '...'",
              file=sys.stderr)
        return 1
    if report.status == "no_baseline":
        print("check_stale_file_regression: no window computable -- advisory pass.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

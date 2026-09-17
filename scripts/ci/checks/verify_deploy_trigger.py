"""verify_deploy_trigger.py — Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION,
taskcard TC-PKG-04-L3 (Layer 3 of PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX).

THE CONFIRMED MECHANISM (read directly from both repos' real source, 2026-09-17):

Sibling repo `Aspose/aspose.org-workflows`'s `change-scanner.yml` runs daily,
checks out this content repo, and calls `scripts/deploy/detect_changes.py
<content_repo> <last_scanned_sha> --manifest scripts/deploy/deploy_manifest.json`.
`detect_changes.py::map_path_to_workflow()` maps a changed file path to a deploy
workflow ONLY if it starts with `content/<site>/`, is `configs/<site>.toml`, or
falls under a small GLOBAL_PATHS list (`themes/`, `layouts/`, `archetypes/`,
`static/`, `i18n/`). `data/package_registry.json` matches none of these -- a
commit that touches only that file maps to ZERO workflows. If every changed
file in a day's diff is such an unmapped path, `has_changes` is "false" and
`detect_changes.py` never writes `deploy_manifest.json` at all for that day --
genuinely silent, no trace left in the sibling repo.

`deploy_manifest.json` is a SINGLE mutable file (not an append log): each new
scan's "Deploy manifest: <date>" commit overwrites it with a fresh
scan_id/content_sha/previous_sha, and `trigger_workflows.py`/`check_status.py`
mutate the SAME file in place as the cycle progresses through
pending -> staging -> production -> completed|failed. `scan_state.json`
(`last_scanned_sha`) only ever advances when a cycle reaches "completed"
(confirmed: its `last_scan_time` exactly matches the corresponding "Deploy
status: completed" commit's timestamp, live-verified against
Aspose/aspose.org-workflows on 2026-09-17).

CONFIRMED REAL DEFECT (not hypothetical -- reconstructed from real commit
history in both repos, 2026-09-17): scan_id `20260913-090311`
(`deploy_manifest.json` commit `f9564bbfd4`, content_sha `92b8818286e4...`) was
written with `state: pending` and NEVER received a "Deploy triggered" or later
status commit -- it was silently superseded by the next day's fresh scan
(`392e7aea20`, `previous_sha` reverted to `bf33a2a19...`, the OLDER pre-09-13
baseline) before ever reaching a terminal state. Two real
`data/package_registry.json`-only commits in THIS repo
(`7bb086aa90250b967696b001c83bfab136d5acdf`, 2026-09-12 13:26 UTC, and
`ee3ea35a77c1876a0cb6e02524865299d0af3b10`, 2026-09-13 14:11 UTC) fell inside
that orphaned cycle's window and had zero dedicated confirmation -- they were
only swept into a real deploy by the NEXT day's cycle (`392e7aea20` /
`3385f5bb1a`, completed 2026-09-14T17:30:03Z), one day late and with no record
that they, specifically, ever landed. This is "recognized (scanned) but not
deployed" via the native cycle -- exactly the confirmation gap this taskcard
exists to close, distinct from a permanent loss (Hugo builds the full checked-
out tree, so a file's *content* is never lost -- but nothing ever confirmed
THIS commit reached a rebuild until this tool existed).

CLASSIFICATION (see classify_sha()):
  CONFIRMED_DEPLOYED       -- the SHA's own native scan cycle reached "completed".
  RECOVERED_VIA_LATER_CYCLE -- the native cycle never completed (orphaned/failed),
                               but a LATER cycle's window covers the SHA and DID
                               complete -- the change did reach a real site
                               rebuild, just with zero dedicated confirmation and
                               a delay.
  SILENTLY_DROPPED         -- no cycle, native or later, has ever completed
                               coverage of the SHA, and it is older than
                               --drop-threshold-days -- actionable.
  PENDING                  -- too recent to judge yet (within the grace period,
                               or no scan has run since).

Data access: `gh api` against Aspose/aspose.org-workflows (read-only; this repo
has confirmed `gh auth status` access with 'repo' scope). Ancestry checks
(`is_ancestor`) run locally against THIS repo's own git history -- the sibling
repo never needs aspose.org's git objects, only its recorded SHAs as strings.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/ci/checks/verify_deploy_trigger.py --sha <sha>
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/ci/checks/verify_deploy_trigger.py --sha <sha> --file-issue-if-dropped

Exit codes:
    0  CONFIRMED_DEPLOYED, RECOVERED_VIA_LATER_CYCLE, or PENDING
    1  SILENTLY_DROPPED
    2  configuration/lookup error (bad SHA, gh unavailable, etc.)
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_WORKFLOWS_REPO = "Aspose/aspose.org-workflows"
MANIFEST_PATH = "scripts/deploy/deploy_manifest.json"
SCAN_STATE_PATH = "scripts/deploy/scan_state.json"
DEFAULT_DROP_THRESHOLD_DAYS = 3
DEFAULT_MAX_PAGES = 10
DEFAULT_PER_PAGE = 100

ISSUE_LABEL = "package-registry-deploy-drop"

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT

CommandRunner = Callable[..., "subprocess.CompletedProcess[str]"]


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing (configure() seam,
    AGENTS.md 16 -- used instead of monkeypatch.setattr on module internals)."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


# ---------------------------------------------------------------------------
# Local git ancestry (this repo only -- the sibling repo's SHAs are just strings)
# ---------------------------------------------------------------------------

def is_ancestor(candidate_sha: str, of_sha: str, *, repo_root: "Path | None" = None,
                 runner: CommandRunner = subprocess.run) -> bool:
    """True if candidate_sha is an ancestor of (or equal to) of_sha, in the LOCAL
    content repo. Equal SHAs short-circuit to True without shelling out."""
    if candidate_sha == of_sha:
        return True
    root = repo_root if repo_root is not None else REPO_ROOT
    result = runner(
        ["git", "merge-base", "--is-ancestor", candidate_sha, of_sha],
        cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.returncode == 0


def commit_date(sha: str, *, repo_root: "Path | None" = None,
                 runner: CommandRunner = subprocess.run) -> "datetime | None":
    """Return the author date of `sha` in the local repo, or None if it can't
    be resolved (e.g. the SHA doesn't exist locally)."""
    root = repo_root if repo_root is not None else REPO_ROOT
    result = runner(
        ["git", "show", "-s", "--format=%aI", sha],
        cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return datetime.fromisoformat(result.stdout.strip())


def sha_exists_locally(sha: str, *, repo_root: "Path | None" = None,
                        runner: CommandRunner = subprocess.run) -> bool:
    root = repo_root if repo_root is not None else REPO_ROOT
    result = runner(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Sibling repo access (gh api; read-only)
# ---------------------------------------------------------------------------

def _run_gh(args: "list[str]", *, runner: CommandRunner = subprocess.run) -> "subprocess.CompletedProcess[str]":
    return runner(["gh", *args], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=60)


def fetch_file_at_ref(
    repo: str, path: str, ref: str, *, runner: CommandRunner = subprocess.run,
) -> "dict[str, Any] | None":
    """Fetch and JSON-parse a file from `repo` at `ref` via `gh api`.

    Returns None if the file doesn't exist at that ref (404) or the response
    isn't valid JSON -- callers treat that as "no data for this revision",
    never as a crash.
    """
    try:
        result = _run_gh(
            ["api", f"repos/{repo}/contents/{path}?ref={ref}", "--jq", ".content"],
            runner=runner,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        content = base64.b64decode(raw).decode("utf-8")
        return json.loads(content)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def list_path_commits(
    repo: str, path: str, *, per_page: int = DEFAULT_PER_PAGE, max_pages: int = DEFAULT_MAX_PAGES,
    runner: CommandRunner = subprocess.run,
) -> "list[dict[str, Any]]":
    """Return every commit that touched `path` in `repo`, NEWEST FIRST (matches
    the GitHub commits API's own order), each as {"sha", "date", "message"}."""
    commits: "list[dict[str, Any]]" = []
    page = 1
    while page <= max_pages:
        try:
            result = _run_gh(
                ["api", f"repos/{repo}/commits?path={path}&per_page={per_page}&page={page}"],
                runner=runner,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            break
        if result.returncode != 0 or not result.stdout.strip():
            break
        try:
            batch = json.loads(result.stdout)
        except json.JSONDecodeError:
            break
        if not batch:
            break
        for c in batch:
            commits.append({
                "sha": c["sha"],
                "date": c["commit"]["author"]["date"],
                "message": c["commit"]["message"],
            })
        if len(batch) < per_page:
            break
        page += 1
    return commits


# ---------------------------------------------------------------------------
# Cycle reconstruction (pure -- operates on already-fetched data)
# ---------------------------------------------------------------------------

@dataclass
class DeployCycle:
    scan_id: str
    content_sha: str
    previous_sha: str
    detected_at: str
    final_state: str
    completed_at: "str | None"
    manifest_commit_shas: "list[str]" = field(default_factory=list)
    orphaned: bool = False


def reconstruct_cycles(
    manifest_commits: "list[dict[str, Any]]",
    fetch_manifest_at: "Callable[[str], dict[str, Any] | None]",
) -> "list[DeployCycle]":
    """Group deploy_manifest.json's commit history (newest-first, as returned by
    list_path_commits()) into per-scan cycles, oldest-first in the result.

    Each "Deploy manifest: <date>" commit overwrites the file with a fresh
    scan_id/content_sha (confirmed via detect_changes.py::write_manifest() and
    change-scanner.yml -- both mutate the SAME path in place, never append).
    Every subsequent commit up to (not including) the next such fresh-scan
    commit is a state-transition on the SAME content_sha, mutated in place by
    trigger_workflows.py / check_status.py.

    A cycle whose `final_state` is still "pending" (or "staging"/"production")
    when a NEW content_sha appears is marked `orphaned=True` -- it was silently
    superseded before ever reaching a terminal state. Confirmed as a real, live
    occurrence: scan_id 20260913-090311 (see module docstring).

    Commits for which `fetch_manifest_at` returns None are skipped (missing
    data for that specific revision, e.g. not fetched) without breaking
    grouping -- correctness only requires the cycle-start ("pending") and the
    eventual terminal-state revision to be present, not every intermediate one.
    """
    commits_oldest_first = list(reversed(manifest_commits))
    cycles: "list[DeployCycle]" = []
    current: "DeployCycle | None" = None

    for c in commits_oldest_first:
        blob = fetch_manifest_at(c["sha"])
        if blob is None:
            continue
        content_sha = blob.get("content_sha")
        if current is None or content_sha != current.content_sha:
            if current is not None and current.final_state not in ("completed", "failed"):
                current.orphaned = True
            current = DeployCycle(
                scan_id=blob.get("scan_id", ""),
                content_sha=content_sha or "",
                previous_sha=blob.get("previous_sha") or "",
                detected_at=blob.get("detected_at", ""),
                final_state=blob.get("state", "pending"),
                completed_at=blob.get("completed_at"),
                manifest_commit_shas=[c["sha"]],
                orphaned=False,
            )
            cycles.append(current)
        else:
            current.final_state = blob.get("state", current.final_state)
            current.completed_at = blob.get("completed_at") or current.completed_at
            current.manifest_commit_shas.append(c["sha"])

    return cycles


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

VERDICT_CONFIRMED = "CONFIRMED_DEPLOYED"
VERDICT_RECOVERED = "RECOVERED_VIA_LATER_CYCLE"
VERDICT_DROPPED = "SILENTLY_DROPPED"
VERDICT_PENDING = "PENDING"


@dataclass
class VerificationResult:
    sha: str
    verdict: str
    native_cycle: "DeployCycle | None"
    covering_cycle: "DeployCycle | None"
    detail: str

    def to_dict(self) -> "dict[str, Any]":
        return {
            "sha": self.sha,
            "verdict": self.verdict,
            "native_cycle": self.native_cycle.scan_id if self.native_cycle else None,
            "covering_cycle": self.covering_cycle.scan_id if self.covering_cycle else None,
            "detail": self.detail,
        }


def classify_sha(
    sha: str,
    cycles: "list[DeployCycle]",
    *,
    repo_root: "Path | None" = None,
    now: "datetime | None" = None,
    drop_threshold_days: int = DEFAULT_DROP_THRESHOLD_DAYS,
    ancestor_check: "Callable[[str, str], bool] | None" = None,
    date_lookup: "Callable[[str], datetime | None] | None" = None,
) -> VerificationResult:
    """Classify `sha`'s deploy-confirmation fate against a list of reconstructed
    cycles (oldest-first, as returned by reconstruct_cycles()).

    `ancestor_check`/`date_lookup` are injectable seams for testing against
    real captured data without shelling out to `git` for every call.
    """
    now = now or datetime.now(timezone.utc)
    ancestor_check = ancestor_check or (lambda a, b: is_ancestor(a, b, repo_root=repo_root))
    date_lookup = date_lookup or (lambda s: commit_date(s, repo_root=repo_root))

    native_cycle: "DeployCycle | None" = None
    completed_cycle: "DeployCycle | None" = None

    for cycle in cycles:
        if not cycle.content_sha:
            continue
        covers = ancestor_check(sha, cycle.content_sha) and not (
            cycle.previous_sha and ancestor_check(sha, cycle.previous_sha)
        )
        if not covers:
            continue
        if native_cycle is None:
            native_cycle = cycle
        if cycle.final_state == "completed" and completed_cycle is None:
            completed_cycle = cycle

    if completed_cycle is not None:
        if native_cycle is completed_cycle:
            return VerificationResult(
                sha, VERDICT_CONFIRMED, native_cycle, completed_cycle,
                f"Native scan cycle {completed_cycle.scan_id} reached 'completed' at "
                f"{completed_cycle.completed_at}.",
            )
        native_desc = (
            f"{native_cycle.scan_id} (state={native_cycle.final_state}, "
            f"orphaned={native_cycle.orphaned})" if native_cycle else "none found"
        )
        return VerificationResult(
            sha, VERDICT_RECOVERED, native_cycle, completed_cycle,
            f"Native cycle {native_desc} never reached a terminal 'completed' state "
            f"(silently superseded before triggering). A LATER cycle "
            f"{completed_cycle.scan_id} completed at {completed_cycle.completed_at} and its "
            f"diff range also covers this SHA -- the change did reach a real site rebuild, "
            f"one cycle late, with zero dedicated confirmation until this tool.",
        )

    if native_cycle is None:
        return VerificationResult(
            sha, VERDICT_PENDING, None, None,
            "No scan cycle's diff range covers this SHA yet -- either too recent, or newer "
            "than the sibling repo's most recently recorded scan.",
        )

    sha_date = date_lookup(sha)
    if sha_date is None:
        return VerificationResult(
            sha, VERDICT_PENDING, native_cycle, None,
            f"Native cycle {native_cycle.scan_id} has not completed yet "
            f"(state={native_cycle.final_state}); could not resolve the commit's own date "
            f"locally to evaluate the drop threshold.",
        )
    age_days = (now - sha_date).days
    if age_days >= drop_threshold_days:
        return VerificationResult(
            sha, VERDICT_DROPPED, native_cycle, None,
            f"Native cycle {native_cycle.scan_id} never reached 'completed' "
            f"(state={native_cycle.final_state}, orphaned={native_cycle.orphaned}), and no "
            f"later cycle's completed diff range covers this SHA either, {age_days} day(s) "
            f"after the commit -- exceeds the {drop_threshold_days}-day threshold.",
        )
    return VerificationResult(
        sha, VERDICT_PENDING, native_cycle, None,
        f"Native cycle {native_cycle.scan_id} has not completed yet "
        f"(state={native_cycle.final_state}); only {age_days} day(s) old, within the "
        f"{drop_threshold_days}-day grace period.",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _filter_commits_at_or_after(
    manifest_commits: "list[dict[str, Any]]", cutoff: "datetime | None",
) -> "list[dict[str, Any]]":
    """Drop manifest commits older than `cutoff` (a cycle whose content_sha
    predates the target SHA can never cover it, by construction -- keeping
    them would only cost extra `gh api` round-trips for no classification
    benefit). No-op if `cutoff` is None (date unresolved)."""
    if cutoff is None:
        return manifest_commits
    kept = []
    for c in manifest_commits:
        try:
            d = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            kept.append(c)  # unparseable date -- keep it, fail open on filtering only
            continue
        if d >= cutoff:
            kept.append(c)
    return kept


def verify_sha(
    sha: str,
    *,
    workflows_repo: str = DEFAULT_WORKFLOWS_REPO,
    repo_root: "Path | None" = None,
    now: "datetime | None" = None,
    drop_threshold_days: int = DEFAULT_DROP_THRESHOLD_DAYS,
    runner: CommandRunner = subprocess.run,
) -> VerificationResult:
    """Live orchestration: fetch real data from `workflows_repo` via `gh api`
    and classify `sha`. This is the only function in this module that performs
    network I/O by default -- everything it calls accepts injected data/seams
    for testing.

    Performance note: `deploy_manifest.json`'s commit history spans this
    sibling repo's entire lifetime (hundreds of commits, one `gh api` round
    trip per blob fetch) -- but only cycles at or after the target SHA's own
    commit date can possibly cover it (a cycle's content_sha necessarily
    postdates every commit it covers). We resolve the SHA's local commit date
    first and drop everything older BEFORE fetching any blob content, turning
    an O(full history) network cost into O(days since this commit).
    """
    sha_date = commit_date(sha, repo_root=repo_root)
    manifest_commits = list_path_commits(workflows_repo, MANIFEST_PATH, runner=runner)
    manifest_commits = _filter_commits_at_or_after(manifest_commits, sha_date)

    def fetch(ref: str) -> "dict[str, Any] | None":
        return fetch_file_at_ref(workflows_repo, MANIFEST_PATH, ref, runner=runner)

    cycles = reconstruct_cycles(manifest_commits, fetch)
    return classify_sha(sha, cycles, repo_root=repo_root, now=now,
                         drop_threshold_days=drop_threshold_days)


# ---------------------------------------------------------------------------
# Issue filing (only ever called for a real, confirmed SILENTLY_DROPPED result)
# ---------------------------------------------------------------------------

def format_issue_body(result: VerificationResult) -> str:
    lines = [
        f"## Package-registry commit `{result.sha[:12]}` never confirmed deployed",
        "",
        f"**Verdict**: {result.verdict}",
        "",
        result.detail,
        "",
        "### Background",
        "`Aspose/aspose.org-workflows`'s `detect_changes.py::map_path_to_workflow()` never "
        "maps `data/package_registry.json` to any deploy workflow on its own (it only "
        "recognizes `content/<site>/`, `configs/<site>.toml`, and a small GLOBAL_PATHS list). "
        "A registry-only commit relies entirely on riding along with an unrelated content "
        "change in the same scan window -- this SHA's native window never completed and no "
        "later window has covered it either.",
        "",
        "### Action required",
        "1. Verify independently whether the change described in "
        f"`{result.sha}` is actually live on the affected site(s).",
        "2. If not, manually trigger `change-scanner.yml` (workflow_dispatch) in "
        "`Aspose/aspose.org-workflows`, or file the separately-tracked Layer 2 PR "
        "(SHARED_DATA_CONSUMERS in `detect_changes.py::map_path_to_workflow()`) -- see "
        "taskcard `PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX`.",
    ]
    return "\n".join(lines)


def file_issue(
    result: VerificationResult, *, repo: str, runner: CommandRunner = subprocess.run,
) -> "dict[str, Any]":
    """Create a GitHub issue in `repo` (THIS repo, never the sibling) for a
    confirmed SILENTLY_DROPPED result. Never called for any other verdict --
    callers must check result.verdict themselves."""
    if result.verdict != VERDICT_DROPPED:
        raise ValueError(f"file_issue() called for non-dropped verdict: {result.verdict}")
    title = f"Package-registry deploy drop: {result.sha[:12]} never confirmed deployed"
    body = format_issue_body(result)
    try:
        proc = runner(
            ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body,
             "--label", ISSUE_LABEL],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"action": "failed", "issue_number": None}
    if proc.returncode != 0:
        return {"action": "failed", "issue_number": None}
    url = proc.stdout.strip()
    tail = url.rsplit("/", 1)[-1]
    number = int(tail) if tail.isdigit() else None
    return {"action": "created", "issue_number": number}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_deploy_trigger",
        description="Confirm whether a data/package_registry.json auto-commit's SHA "
                    "actually surfaced in Aspose/aspose.org-workflows's deploy pipeline.",
    )
    parser.add_argument("--sha", required=True, help="Commit SHA in THIS repo to verify")
    parser.add_argument("--workflows-repo", default=DEFAULT_WORKFLOWS_REPO)
    parser.add_argument("--drop-threshold-days", type=int, default=DEFAULT_DROP_THRESHOLD_DAYS)
    parser.add_argument("--file-issue-if-dropped", action="store_true",
                         help="File a GitHub issue in THIS repo if the verdict is "
                              "SILENTLY_DROPPED (never for any other verdict)")
    parser.add_argument("--issue-repo", default="Aspose/aspose.org",
                         help="Repo to file the issue in (THIS repo, never the sibling)")
    args = parser.parse_args(argv)

    if not sha_exists_locally(args.sha):
        print(f"ERROR: {args.sha} does not exist in the local repo -- cannot verify.", file=sys.stderr)
        return 2

    result = verify_sha(
        args.sha, workflows_repo=args.workflows_repo,
        drop_threshold_days=args.drop_threshold_days,
    )
    print(json.dumps(result.to_dict(), indent=2))

    if result.verdict == VERDICT_DROPPED and args.file_issue_if_dropped:
        outcome = file_issue(result, repo=args.issue_repo)
        print(f"Issue: {outcome['action']} (#{outcome['issue_number']})")

    return 1 if result.verdict == VERDICT_DROPPED else 0


if __name__ == "__main__":
    sys.exit(main())

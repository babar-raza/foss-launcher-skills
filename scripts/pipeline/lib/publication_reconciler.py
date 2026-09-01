"""publication_reconciler.py -- asks GitHub what actually landed, read-only.

CONTRACT: scripts/pipeline/lib/publication_reconciler.py
  purpose: TC-15 (readme-refresh-trackb-and-followon-2026-09-01). SW-B ("nothing ever asks
           GitHub what actually landed") named this gap; this session found it live, twice,
           by hand: `3d/net` PR #3 (merged 2026-08-19) and `cells/typescript` PR #2 (merged
           2026-08-14) are both real, human-approved /readme-refresh publications with ZERO
           entry in `data/readme_published_state.json` -- `_record_publication()`
           (readme_refresh_run.py) only fires from this repo's own `push()` call, so any
           publication that happened before this CLI existed, or through any other path,
           is structurally invisible to every consumer of that registry (audit-portfolio's
           `published_readme_current` tripwire included). This module closes that blind
           spot mechanically instead of requiring a fresh `gh pr view` investigation every
           time a product's disposition checks look suspiciously, unexplainedly wrong.
  detection signal: a merged PR whose head branch matches `readme-refresh/YYYY-MM-DD` --
           the exact, literal, code-enforced branch name `_do_push()` creates
           (`f"readme-refresh/{_now().strftime('%Y-%m-%d')}"`). Deliberately NOT a fuzzy
           match on PR title/body text (this session read 3 real PR bodies for 3 different
           products -- 3d/net, note/python, cells/typescript -- and each used genuinely
           different, LLM-authored wording; only the branch name is a structural constant).
  writes: ONLY `data/readme_published_state.json` (this repo's own registry), and only when
          `apply=True` is passed explicitly. NEVER writes to any product's own GitHub repo --
          `gh pr list`/`gh api repos/{repo}`/`gh api repos/{repo}/compare/...` are the only
          subprocess calls this module makes, all read-only GitHub API calls.
  TC-41 addendum (MT061-2026-09-01-TRACKB-FOLLOWON-2): built to feed TC-17's
           live-published-regression gate and TC-27's PR-merge-based publication gate,
           per reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/
           phase6b-production-hardening-design.md S3.VII. That document's literal
           mechanism ("checking the merging actor's GitHub identity is not the pipeline's
           own bot/token identity") was investigated live BEFORE being built, per this
           mission's own "verify a spec against real behavior first" discipline (TC-17's
           own precedent) -- and found NOT exercisable in this repository: `gh api user`
           for the live `GH_TOKEN` resolves to `babar-raza`, the human maintainer's own
           personal account, not a separate bot/service identity. Sampled every real
           readme-refresh PR merge event available (3d/net #3, note/python #5, and
           font/python #1 -- the one case the hard rule most needs to catch) via the
           single-PR endpoint (`merged_by` is null on the LIST endpoint, a real,
           easily-missed API quirk fixed here): all three show `merged_by: babar-raza`,
           identical to the token's own identity, with zero PR review-approval trail on
           any of them either. There is no externally-observable GitHub signal in this
           repo's real history that distinguishes "a human merged this with real
           scrutiny" from "the agent ran `gh pr merge` after a chat go-ahead" -- both
           produce byte-identical API responses. Building an identity-gate on this
           non-signal would either always-fail (blocking every real publication) or be
           purely vacuous (font/python's own REVERTED case is already caught by the
           existing ancestor-reachability check, not by identity). `merged_by_login` is
           therefore recorded as an AUDIT field only (informational, never a gate).
           `published_blob_sha256` (a real, structurally sound fingerprint of the live
           README content, independent of the identity question) IS built and gates
           TC-17's regression check. See MT061's TC-41 taskcard evidence for the full
           live investigation.
  states: `IN_SYNC` (registry already reflects the most recent readme-refresh PR),
          `UNRECORDED_PUBLICATION` (a real readme-refresh PR merged upstream, confirmed
          reachable from the live default branch, with no matching registry entry, or an
          entry that doesn't cite that PR), `REVERTED` (a readme-refresh PR shows merged
          but its merge commit is NOT an ancestor of the live default branch -- confirmed
          live and load-bearing on `font/python`'s real, twice-wiped PR #1; never safe to
          record as IN_SYNC), `UNCONFIRMED_REACHABILITY` (the ancestry check itself failed
          -- treated as "cannot confirm", never coerced into UNRECORDED_PUBLICATION),
          `UNPUBLISHED` (no readme-refresh-shaped PR found at all -- nothing to reconcile),
          `NO_REPO_ACCESS` (a `gh` call failed -- advisory, never raised; a reconciler
          failure must never block any other work, per the plan's own Failure Handling
          section).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root
_cfg_repo_root = _REPO_ROOT
_cfg_command_runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run
_cfg_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

_README_REFRESH_BRANCH_RE = re.compile(r"^readme-refresh/\d{4}-\d{2}-\d{2}")


def configure(
    *,
    repo_root: "Path | str | None" = None,
    command_runner: "Callable[..., subprocess.CompletedProcess[str]] | None" = None,
    now: "Callable[[], datetime] | None" = None,
) -> None:
    """Override external boundaries for tests; call without arguments to reset."""
    global _cfg_repo_root, _cfg_command_runner, _cfg_now
    _cfg_repo_root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    _cfg_command_runner = command_runner or subprocess.run
    _cfg_now = now or (lambda: datetime.now(timezone.utc))


def _utc_now_iso() -> str:
    return _cfg_now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _products_path() -> Path:
    return _cfg_repo_root / "data" / "products.json"


def _published_state_path() -> Path:
    return _cfg_repo_root / "data" / "readme_published_state.json"


def _load_json(path: Path) -> "dict | list | None":
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_full_name(family: str, platform: str) -> "str | None":
    products = _load_json(_products_path()) or []
    for p in products:
        if p.get("family") == family and p.get("platform") == platform:
            url = p.get("repo_url") or ""
            return url.split("github.com/", 1)[-1].rstrip("/") or None
    return None


def _registry_entry(family: str, platform: str) -> "dict | None":
    state = _load_json(_published_state_path()) or {}
    for row in state.get("products", []):
        if row.get("family") == family and row.get("platform") == platform:
            return row
    return None


def _fetch_merged_prs(repo_full_name: str) -> "list[dict] | None":
    """Returns merged PRs (newest first) or None on a real gh failure -- never raises."""
    result = _cfg_command_runner(
        ["gh", "pr", "list", "--repo", repo_full_name, "--state", "merged",
         "--json", "number,mergedAt,headRefName,mergeCommit,url",
         "--limit", "100"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _merge_commit_reachable_from_default_branch(repo_full_name: str, merge_commit_sha: str) -> "bool | None":
    """RC-1 safety check (readme-refresh-trackb-and-followon-2026-09-01): `gh pr list
    --state merged` reports a PR as merged FOREVER, even if the branch it merged into was
    later reset/force-pushed past that point -- GitHub's PR state is a historical record,
    not a live claim about the current default branch. Confirmed live and load-bearing:
    `font/python`'s real PR #1 (merge commit 7971880964...) shows up exactly this way --
    `gh pr list` reports it merged, but `gh api .../compare/7971880...∙∙∙main` returns HTTP
    404 'No common ancestor', proving the commit is genuinely gone from history (matching
    this repo's own prior finding that this exact PR "has been wiped twice"). Without this
    check, `reconcile_product` would misclassify a REVERTED publication as a merely-
    UNRECORDED one -- and `apply_reconciliation` would then write a false 'this is
    published and in sync' record for the one product under the strictest hard rule in
    this entire mission (font/python must never be treated as safely published).

    Returns True (an ancestor of the live default branch -- safe), False (genuinely
    unreachable -- REVERTED), or None (the check itself failed, e.g. rate limit -- treated
    as "cannot confirm", never silently coerced to True).
    """
    result = _cfg_command_runner(
        ["gh", "api", f"repos/{repo_full_name}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        default_branch = json.loads(result.stdout).get("default_branch")
    except json.JSONDecodeError:
        return None
    if not default_branch:
        return None

    compare = _cfg_command_runner(
        ["gh", "api", f"repos/{repo_full_name}/compare/{merge_commit_sha}...{default_branch}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if compare.returncode != 0:
        # 404 "No common ancestor" is the real, expected REVERTED signal -- gh's own exit
        # code is nonzero for any non-2xx response, so this branch covers both that case
        # and a genuine transient failure; either way, "not confirmed reachable" is the
        # only safe read.
        return False
    if not compare.stdout:
        return None
    try:
        status = json.loads(compare.stdout).get("status")
    except json.JSONDecodeError:
        return None
    # "identical"/"ahead" both mean merge_commit_sha IS an ancestor of the live default
    # branch (base=merge_commit, head=default_branch in GitHub's compare semantics).
    # "behind"/"diverged" mean it is not currently reachable that way.
    return status in ("identical", "ahead")


def _fetch_pr_merged_by(repo_full_name: str, pr_number: int) -> "str | None":
    """TC-41: `merged_by` is populated only on the single-PR endpoint, never on `gh pr
    list`/the list endpoint used by `_fetch_merged_prs` (confirmed live -- every row from
    the list call comes back with `merged_by: null` regardless of real merge state).
    Returns the merging actor's login, or None on any gh failure or missing field --
    informational only, never gates a state transition."""
    result = _cfg_command_runner(
        ["gh", "api", f"repos/{repo_full_name}/pulls/{pr_number}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        merged_by = json.loads(result.stdout).get("merged_by") or {}
    except json.JSONDecodeError:
        return None
    return merged_by.get("login")


def _fetch_readme_blob_sha256(repo_full_name: str, ref: str) -> "str | None":
    """TC-41: sha256 of the live README.md's raw content at `ref` (the PR's merge_commit_sha
    -- never a mutable branch pointer, so this fingerprint is reproducible/pinned). Returns
    None on any gh failure or an empty/missing file -- callers must never write a fingerprint
    they could not really confirm.

    `ref` is embedded directly in the URL query string, never passed via `-f ref=...` --
    confirmed live that `-f`/`--raw-field` silently makes `gh api` default to a POST
    request unless `--method GET` is also passed, which 404s against this GET-only
    contents endpoint. Live-verified against the real 3d/net repo before trusting either
    form (this exact 404-vs-real-content gap is why the fix is a query string, not a flag)."""
    result = _cfg_command_runner(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw",
         f"repos/{repo_full_name}/contents/README.md?ref={ref}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()


def reconcile_product(family: str, platform: str) -> dict:
    """Read-only. Returns a reconciliation report; never mutates anything.

    `{"family", "platform", "state", "reason", "latest_readme_refresh_pr": {...} | None,
    "registry_entry": {...} | None}`. `state` is one of IN_SYNC / UNRECORDED_PUBLICATION /
    REVERTED / UNCONFIRMED_REACHABILITY / UNPUBLISHED / NO_REPO_ACCESS.
    """
    repo_full_name = _repo_full_name(family, platform)
    if not repo_full_name:
        return {
            "family": family, "platform": platform, "state": "NO_REPO_ACCESS",
            "reason": f"no active data/products.json entry (or no repo_url) for {family}/{platform}",
            "latest_readme_refresh_pr": None, "registry_entry": None,
        }

    prs = _fetch_merged_prs(repo_full_name)
    registry_entry = _registry_entry(family, platform)
    if prs is None:
        return {
            "family": family, "platform": platform, "state": "NO_REPO_ACCESS",
            "reason": f"gh pr list failed for {repo_full_name} (rate limit, auth, or network)",
            "latest_readme_refresh_pr": None, "registry_entry": registry_entry,
        }

    refresh_prs = [pr for pr in prs if _README_REFRESH_BRANCH_RE.match(pr.get("headRefName") or "")]
    if not refresh_prs:
        return {
            "family": family, "platform": platform, "state": "UNPUBLISHED",
            "reason": "no merged PR with a readme-refresh/YYYY-MM-DD head branch found",
            "latest_readme_refresh_pr": None, "registry_entry": registry_entry,
        }

    # Newest first, by merge time (gh's own default order is not documented as guaranteed).
    refresh_prs.sort(key=lambda pr: pr.get("mergedAt") or "", reverse=True)
    latest = refresh_prs[0]
    latest_summary = {
        "number": latest.get("number"),
        "merged_at": latest.get("mergedAt"),
        "merge_commit_sha": (latest.get("mergeCommit") or {}).get("oid"),
        "head_ref_name": latest.get("headRefName"),
        "url": latest.get("url"),
    }

    reachable = None
    if latest_summary["merge_commit_sha"]:
        reachable = _merge_commit_reachable_from_default_branch(
            repo_full_name, latest_summary["merge_commit_sha"],
        )
    if reachable is False:
        return {
            "family": family, "platform": platform, "state": "REVERTED",
            "reason": f"PR #{latest_summary['number']} shows merged, but merge commit "
                      f"{latest_summary['merge_commit_sha']} is not an ancestor of the live "
                      "default branch -- the publication was reverted, force-pushed away, or "
                      "the repo's history was rewritten past it. Never safe to record as "
                      "IN_SYNC.",
            "latest_readme_refresh_pr": latest_summary, "registry_entry": registry_entry,
        }
    if reachable is None:
        return {
            "family": family, "platform": platform, "state": "UNCONFIRMED_REACHABILITY",
            "reason": f"PR #{latest_summary['number']} shows merged, but reachability from the "
                      "live default branch could not be confirmed (gh api failure/rate limit) -- "
                      "not safe to classify as UNRECORDED_PUBLICATION without this check.",
            "latest_readme_refresh_pr": latest_summary, "registry_entry": registry_entry,
        }

    if registry_entry is None:
        return {
            "family": family, "platform": platform, "state": "UNRECORDED_PUBLICATION",
            "reason": f"PR #{latest_summary['number']} (merged {latest_summary['merged_at']}) "
                      "has no data/readme_published_state.json entry at all",
            "latest_readme_refresh_pr": latest_summary, "registry_entry": None,
        }

    recorded_evidence = str(registry_entry.get("evidence") or "")
    pr_number_str = str(latest_summary["number"])
    if (
        f"PR #{pr_number_str}" in recorded_evidence
        or f"PR: {latest_summary['url']}" in recorded_evidence
        or (latest_summary["merge_commit_sha"] or "unmatchable") in recorded_evidence
    ):
        return {
            "family": family, "platform": platform, "state": "IN_SYNC",
            "reason": "registry evidence already cites this PR",
            "latest_readme_refresh_pr": latest_summary, "registry_entry": registry_entry,
        }

    return {
        "family": family, "platform": platform, "state": "UNRECORDED_PUBLICATION",
        "reason": f"PR #{latest_summary['number']} (merged {latest_summary['merged_at']}) is not "
                  "cited anywhere in the existing registry entry's own evidence text",
        "latest_readme_refresh_pr": latest_summary, "registry_entry": registry_entry,
    }


def _fetch_fingerprint_fields(report: dict) -> dict:
    """TC-41: best-effort published_blob_sha256 + merged_by_login for a report whose
    `latest_readme_refresh_pr` is populated and confirmed reachable. Never raises; a failed
    gh call simply omits that field rather than writing a stale/fabricated value."""
    pr = report.get("latest_readme_refresh_pr") or {}
    repo_full_name = _repo_full_name(report["family"], report["platform"])
    fields: dict = {}
    if repo_full_name and pr.get("number") is not None:
        merged_by_login = _fetch_pr_merged_by(repo_full_name, pr["number"])
        if merged_by_login:
            fields["merged_by_login"] = merged_by_login
    if repo_full_name and pr.get("merge_commit_sha"):
        blob_sha256 = _fetch_readme_blob_sha256(repo_full_name, pr["merge_commit_sha"])
        if blob_sha256:
            fields["published_blob_sha256"] = blob_sha256
            fields["published_commit"] = pr["merge_commit_sha"]
    return fields


def apply_reconciliation(report: dict) -> "dict | None":
    """Writes a discovered UNRECORDED_PUBLICATION into data/readme_published_state.json,
    or (TC-41) refreshes the fingerprint fields on an already-IN_SYNC row.

    No-op (returns None) for any other state -- REVERTED/UNCONFIRMED_REACHABILITY/
    UNPUBLISHED/NO_REPO_ACCESS have nothing confirmed to record, and IN_SYNC with no
    resolvable PR/repo (e.g. a synthetic report) leaves the row untouched. Additive to the
    existing 4-field schema (family/platform/last_known_publication/evidence): also stamps
    pr_number, merged_at, merge_commit_sha, last_reconciled_at, and (TC-41)
    published_blob_sha256/published_commit/merged_by_login, per the governing plan's own
    ADDITIVE schema for this file -- existing readers that only know the original 4 fields
    are unaffected. `merged_by_login` is informational only (see module docstring TC-41
    addendum for why it cannot safely gate anything in this repository) -- it is never
    read by any check, only recorded for audit visibility.
    """
    if report["state"] == "IN_SYNC":
        pr = report.get("latest_readme_refresh_pr")
        registry_entry = report.get("registry_entry")
        if not pr or not registry_entry:
            return None
        fingerprint = _fetch_fingerprint_fields(report)
        if not fingerprint:
            return None
        family, platform = report["family"], report["platform"]
        state = _load_json(_published_state_path()) or {"schema_version": 1, "products": []}
        rows = state.setdefault("products", [])
        for row in rows:
            if row.get("family") == family and row.get("platform") == platform:
                row.update(fingerprint)
                row["last_reconciled_at"] = _utc_now_iso()
                _published_state_path().write_text(
                    json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                )
                return row
        return None

    if report["state"] != "UNRECORDED_PUBLICATION":
        return None
    pr = report["latest_readme_refresh_pr"]
    family, platform = report["family"], report["platform"]
    state = _load_json(_published_state_path()) or {"schema_version": 1, "products": []}
    rows = state.setdefault("products", [])
    reconciled_at = _utc_now_iso()
    entry = {
        "family": family, "platform": platform,
        "last_known_publication": (pr.get("merged_at") or "")[:10],
        "evidence": f"reconciled by publication_reconciler.py: PR #{pr['number']} "
                    f"({pr.get('url')}), merged {pr.get('merged_at')}",
        "pr_number": pr["number"],
        "merged_at": pr.get("merged_at"),
        "merge_commit_sha": pr.get("merge_commit_sha"),
        "last_reconciled_at": reconciled_at,
        "reconciliation_state": "IN_SYNC",
    }
    entry.update(_fetch_fingerprint_fields(report))
    for i, row in enumerate(rows):
        if row.get("family") == family and row.get("platform") == platform:
            rows[i] = entry
            break
    else:
        rows.append(entry)
    _published_state_path().write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return entry


def reconcile_portfolio(pairs: "list[tuple[str, str]]") -> "list[dict]":
    """Read-only sweep over an explicit list of (family, platform) pairs -- never unscoped
    by default (this repo's own hard-won audit-portfolio lesson: always pass an explicit
    target list, a caller-supplied `data/products.json` scan included)."""
    return [reconcile_product(family, platform) for family, platform in pairs]

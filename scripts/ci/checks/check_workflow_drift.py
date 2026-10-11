#!/usr/bin/env python3
"""Three-way drift classification for scripts/seo/workflows/*.yml templates
against their deployed copies in Aspose/aspose.org-workflows (Finding #64/F10).

All 4 SEO workflow templates in this repo are copy-deployed by hand into
Aspose/aspose.org-workflows/.github/workflows/ (see scripts/seo/README.md);
nothing here keeps the two copies in sync automatically, so they can drift
silently in either direction with no warning. F10 additionally found 3 of
the 4 local templates were untracked by git entirely.

Classification per workflow, computed from three SHA-256 hashes (local
template text, live deployed text via `gh api`, and the last approved
baseline recorded in data/workflow_deploy_baselines.json):

  IN_SYNC             -- local == deployed == approved baseline.
  DEPLOYED_UNAPPROVED -- the deployed copy no longer matches the last
                         approved baseline, regardless of what the local
                         template says. This is the governance-relevant
                         case: someone (or something) changed the live
                         workflow file outside the reviewed deploy path.
                         Checked first because it is the more severe class
                         -- a deployed-unapproved file could coincidentally
                         match today's local template and would otherwise
                         be misreported as merely IN_SYNC.
  DIVERGED            -- the deployed copy still matches its approved
                         baseline (no unapproved live change), but the
                         local template itself differs from it -- ordinary
                         lag (local edited but not yet deployed, or the
                         two never matched). Also used when the deployed
                         file cannot be fetched at all, since drift can't
                         be ruled out from local content alone. (MT069 HC-09: that
                         sentence now applies ONLY to a definite 404 -- the file
                         really is absent from the deployed repo. A lookup that
                         merely FAILED is UNRESOLVED, below.)
  UNRESOLVED          -- the deployed copy could not be fetched for a reason
                         that says nothing about drift (network, timeout, TLS,
                         5xx) even after bounded retries. Reported as its own
                         status with its own exit code so a transient blip is
                         never mistaken for real drift, and is never mistaken
                         for "in sync" either (MT069 HC-09, 2026-09-18: a single
                         `net/http: TLS handshake timeout` used to surface as
                         DIVERGED).

No baseline exists for any of the 4 templates yet (this module and its data
file are new). On first run each workflow's baseline is seeded from its
*current* deployed content -- there is nothing to approve retroactively, so
today's live state is adopted as the trusted starting point, exactly as
SEO-AUTONOMY-STATE-MACHINE's seed_from_product_review_log() adopted the
review log's real verdicts rather than inventing history.

Approving a reviewed deploy (MT069 HC-09: approval is a verb, not a hand-edit):
  --approve NAME --reason "what was reviewed"
refuses unless NAME is DEPLOYED_UNAPPROVED *and* the deployed copy equals the
local template (i.e. the thing being blessed is the thing that was reviewed),
then records the reason in the baseline entry.

Usage (run with the repo venv's interpreter):
    check_workflow_drift.py
    check_workflow_drift.py --no-seed
    check_workflow_drift.py --baselines PATH     # alternate baseline file (control tests)
    check_workflow_drift.py --approve NAME --reason "..."

Exit codes:
  0 -- every workflow IN_SYNC
  1 -- at least one workflow DEPLOYED_UNAPPROVED or DIVERGED
  2 -- configuration error (workflows dir missing, gh unavailable/unauthenticated)
  3 -- no confirmed drift, but at least one workflow UNRESOLVED (lookup failed)
  4 -- --approve refused
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT
WORKFLOWS_DIR = REPO_ROOT / "scripts" / "seo" / "workflows"
# MT069 PHB-05 (2026-09-17): a second source directory for non-SEO workflows
# migrated to the public repo (first tenant: aspose-com-targets-watch.yml).
# Both directories deploy into the SAME .github/workflows/ prefix in
# Aspose/aspose.org-workflows, so results stay keyed by filename alone --
# no per-directory namespacing needed, matching how GitHub itself has no
# concept of subdirectories under .github/workflows/.
DEPLOYED_WORKFLOWS_DIR = REPO_ROOT / "scripts" / "ci" / "deployed-workflows"
SOURCE_DIRS = (WORKFLOWS_DIR, DEPLOYED_WORKFLOWS_DIR)
BASELINES_PATH = REPO_ROOT / "data" / "workflow_deploy_baselines.json"

DEPLOYED_REPO = "Aspose/aspose.org-workflows"
DEPLOYED_PREFIX = ".github/workflows"

IN_SYNC = "IN_SYNC"
DEPLOYED_UNAPPROVED = "DEPLOYED_UNAPPROVED"
DIVERGED = "DIVERGED"
UNRESOLVED = "UNRESOLVED"


class TransientFetchError(Exception):
    """The deployed copy could not be fetched for a reason unrelated to drift."""


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, WORKFLOWS_DIR, DEPLOYED_WORKFLOWS_DIR, SOURCE_DIRS, BASELINES_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    WORKFLOWS_DIR = REPO_ROOT / "scripts" / "seo" / "workflows"
    DEPLOYED_WORKFLOWS_DIR = REPO_ROOT / "scripts" / "ci" / "deployed-workflows"
    SOURCE_DIRS = (WORKFLOWS_DIR, DEPLOYED_WORKFLOWS_DIR)
    BASELINES_PATH = REPO_ROOT / "data" / "workflow_deploy_baselines.json"


CommandRunner = Callable[..., "subprocess.CompletedProcess[str]"]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_NOT_FOUND = re.compile(r"\b404\b|Not Found", re.IGNORECASE)


def fetch_deployed_content(
    deployed_path: str, *, repo: str = DEPLOYED_REPO, runner: CommandRunner = subprocess.run,
    attempts: int = 3, backoff_s: "tuple[float, ...]" = (2.0, 5.0),
    sleep_fn: "Callable[[float], None]" = time.sleep,
) -> "str | None":
    """Fetch a file's raw text content from `repo` via `gh api`.

    Returns the text; returns None ONLY when the file definitely does not exist
    there (HTTP 404 -- `gh api --jq` puts that error JSON on stdout, so both
    streams are inspected); raises TransientFetchError when every one of
    `attempts` tries failed for any other reason (network, timeout, TLS, 5xx,
    undecodable body). A caller must never treat a raised error as "matches" --
    only as "unresolved". `gh` itself being absent is a configuration problem,
    not a blip, so it is raised at once without retries.
    """
    last = "no attempt made"
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            result = runner(
                ["gh", "api", f"repos/{repo}/contents/{deployed_path}", "--jq", ".content"],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
        except FileNotFoundError as exc:
            raise TransientFetchError(f"gh CLI not found: {exc}") from exc
        except subprocess.TimeoutExpired:
            last = "timed out after 30s"
        else:
            out = result.stdout or ""
            err = getattr(result, "stderr", "") or ""
            if result.returncode != 0:
                if _NOT_FOUND.search(out + " " + err):
                    return None
                last = f"gh exited {result.returncode}: {(err or out).strip()[:160]}"
            elif not out.strip():
                last = "gh returned an empty body"
            else:
                try:
                    return base64.b64decode("".join(out.split())).decode("utf-8")
                except ValueError as exc:
                    last = f"undecodable response: {exc}"
        if attempt < attempts:
            sleep_fn(backoff_s[min(attempt - 1, len(backoff_s) - 1)])
    raise TransientFetchError(f"{deployed_path}: {last} (after {attempts} attempt(s))")


def load_baselines() -> dict:
    try:
        return json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_baselines(baselines: dict) -> None:
    BASELINES_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINES_PATH.write_text(json.dumps(baselines, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def classify(local_sha: str, deployed_sha: "str | None", baseline_sha: "str | None") -> str:
    """Pure three-way classification -- see module docstring for the rules."""
    if deployed_sha is None:
        return DIVERGED
    if baseline_sha is not None and deployed_sha != baseline_sha:
        return DEPLOYED_UNAPPROVED
    if local_sha != deployed_sha:
        return DIVERGED
    return IN_SYNC


def check_workflow_drift(
    *,
    workflows_dir: "Path | list[Path] | tuple[Path, ...] | None" = None,
    fetch_fn: "Callable[[str], str | None] | None" = None,
    seed_missing_baselines: bool = True,
) -> dict:
    """Run the drift check across every *.yml in `workflows_dir`.

    `workflows_dir` accepts a single directory (kept for backward
    compatibility -- e.g. a test isolating one source), a list/tuple of
    directories, or None (defaults to SOURCE_DIRS, i.e. every known template
    source -- currently `scripts/seo/workflows/` and
    `scripts/ci/deployed-workflows/`, both deployed into the same
    `.github/workflows/` prefix, so results are keyed by filename alone
    across all of them).

    Returns {"results": {filename: {status, local_sha256, deployed_sha256,
    approved_baseline_sha256}}, "baselines": <baselines dict, updated in
    memory with any newly-seeded entries -- caller decides whether to
    persist via save_baselines()>}.

    Pure(ish): reads local template files and BASELINES_PATH, calls
    `fetch_fn` (defaults to a real `gh api` call) for the deployed side,
    never writes anything itself.
    """
    if workflows_dir is None:
        dirs: "tuple[Path, ...]" = SOURCE_DIRS
    elif isinstance(workflows_dir, (list, tuple)):
        dirs = tuple(workflows_dir)
    else:
        dirs = (workflows_dir,)
    fetch_fn = fetch_fn or (lambda deployed_path: fetch_deployed_content(deployed_path))
    baselines = load_baselines()

    results: dict = {}
    for source_dir in dirs:
        if not source_dir.is_dir():
            continue
        for yml_path in sorted(source_dir.glob("*.yml")):
            name = yml_path.name
            local_text = yml_path.read_text(encoding="utf-8")
            local_sha = sha256_text(local_text)

            deployed_path = f"{DEPLOYED_PREFIX}/{name}"
            unresolved_reason = None
            try:
                deployed_text = fetch_fn(deployed_path)
            except TransientFetchError as exc:
                deployed_text, unresolved_reason = None, str(exc)
            deployed_sha = sha256_text(deployed_text) if deployed_text is not None else None

            entry = baselines.get(name, {})
            baseline_sha = entry.get("approved_baseline_sha256")

            if baseline_sha is None and seed_missing_baselines and deployed_sha is not None:
                baseline_sha = deployed_sha
                baselines[name] = {
                    "deployed_repo": DEPLOYED_REPO,
                    "deployed_path": deployed_path,
                    "approved_baseline_sha256": baseline_sha,
                    "baseline_source": "seeded_from_deployed",
                    "baseline_recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }

            results[name] = {
                "status": UNRESOLVED if unresolved_reason else classify(local_sha, deployed_sha, baseline_sha),
                "local_sha256": local_sha,
                "deployed_sha256": deployed_sha,
                "approved_baseline_sha256": baseline_sha,
            }
            if unresolved_reason:
                results[name]["unresolved_reason"] = unresolved_reason

    return {"results": results, "baselines": baselines}


def approve_baseline(name: str, reason: str, results: dict, baselines: dict) -> "tuple[bool, str]":
    """Record `name`'s deployed hash as its approved baseline -- only when that is safe.

    Refuses unless the workflow is DEPLOYED_UNAPPROVED *and* the deployed copy
    equals the local template: approving is "this deployed file is the one I
    reviewed", and the reviewed thing is the local template, so a deployed copy
    that differs from it is exactly the unreviewed live change the baseline
    exists to catch. Mutates `baselines` in place on success.
    """
    if not reason.strip():
        return False, "--reason is required and must say what was reviewed"
    r = results.get(name)
    if r is None:
        return False, f"{name}: not a known template (known: {', '.join(sorted(results))})"
    status = r["status"]
    if status == IN_SYNC:
        return True, f"{name}: already IN_SYNC, nothing to approve"
    if status == UNRESOLVED:
        return False, f"{name}: UNRESOLVED ({r.get('unresolved_reason', 'lookup failed')}) -- cannot approve what could not be read"
    if status == DIVERGED:
        return False, (f"{name}: DIVERGED -- the deployed copy still matches its approved baseline; there is no "
                       f"unreviewed live change to approve. Deploy the local template first, then approve.")
    if r["local_sha256"] != r["deployed_sha256"]:
        return False, (f"{name}: deployed copy != local template. Refusing: that is an unreviewed live change. "
                       f"Diff them, bring the local template in line (or revert the live file), then approve.")
    old = r["approved_baseline_sha256"]
    entry = dict(baselines.get(name, {}))
    entry.update({
        "deployed_repo": entry.get("deployed_repo", DEPLOYED_REPO),
        "deployed_path": entry.get("deployed_path", f"{DEPLOYED_PREFIX}/{name}"),
        "approved_baseline_sha256": r["deployed_sha256"],
        "baseline_source": f"approved_after_review: {reason.strip()}",
        "baseline_recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    baselines[name] = entry
    return True, f"{name}: baseline {str(old)[:12]} -> {r['deployed_sha256'][:12]} (reason recorded)"


def _gh_auth_ok() -> bool:
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10).returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main(
    argv: "list[str] | None" = None,
    *,
    gh_auth_ok_fn: "Callable[[], bool] | None" = None,
    drift_fn: "Callable[..., dict] | None" = None,
) -> int:
    global BASELINES_PATH
    parser = argparse.ArgumentParser(
        description="Three-way drift check for scripts/seo/workflows/*.yml and "
                     "scripts/ci/deployed-workflows/*.yml"
    )
    parser.add_argument("--no-seed", action="store_true",
                         help="Do not seed a missing baseline from today's deployed content")
    parser.add_argument("--baselines", metavar="PATH",
                         help="Use this baseline file instead of data/workflow_deploy_baselines.json "
                              "(for control tests against a scratch baseline; never seeds)")
    parser.add_argument("--approve", metavar="NAME",
                         help="Approve NAME's deployed hash as its baseline (needs --reason)")
    parser.add_argument("--reason", help="What was reviewed (recorded in the baseline entry)")
    args = parser.parse_args(argv)

    if args.baselines:
        BASELINES_PATH = Path(args.baselines)
    if args.approve and not (args.reason or "").strip():
        parser.error("--approve requires --reason")

    existing_dirs = [d for d in SOURCE_DIRS if d.is_dir()]
    if not existing_dirs:
        print(f"ERROR: none of {list(SOURCE_DIRS)} exist", file=sys.stderr)
        return 2

    if not (gh_auth_ok_fn or _gh_auth_ok)():
        print("ERROR: gh CLI not available or not authenticated", file=sys.stderr)
        return 2

    seed = not (args.no_seed or args.baselines or args.approve)
    outcome = (drift_fn or check_workflow_drift)(seed_missing_baselines=seed)
    results = outcome["results"]

    for name, r in sorted(results.items()):
        deployed_display = (r["deployed_sha256"] or "unresolved")[:12]
        print(f"  {r['status']:20s} {name}: local={r['local_sha256'][:12]} deployed={deployed_display}")
        if r["status"] == UNRESOLVED:
            print(f"  {'':20s} ^ {r.get('unresolved_reason', 'lookup failed')}")

    if args.approve:
        ok, msg = approve_baseline(args.approve, args.reason, results, outcome["baselines"])
        print(("APPROVED: " if ok else "REFUSED: ") + msg)
        if ok and results.get(args.approve, {}).get("status") != IN_SYNC:
            save_baselines(outcome["baselines"])
        return 0 if ok else 4

    if seed:
        save_baselines(outcome["baselines"])

    drifted = {name: r for name, r in results.items() if r["status"] in (DEPLOYED_UNAPPROVED, DIVERGED)}
    unresolved = {name: r for name, r in results.items() if r["status"] == UNRESOLVED}
    if drifted:
        print(f"\nACTION REQUIRED: {len(drifted)} of {len(results)} workflow(s) not in sync")
        for name, r in drifted.items():
            print(f"  - {name}: {r['status']}")
        if unresolved:
            print(f"  (and {len(unresolved)} UNRESOLVED: {', '.join(sorted(unresolved))})")
        return 1
    if unresolved:
        print(f"\nNO CONFIRMED DRIFT, but {len(unresolved)} of {len(results)} workflow(s) could not be checked "
              f"(lookup failed): {', '.join(sorted(unresolved))}")
        return 3

    print(f"\nAll {len(results)} workflow(s) in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
                         be ruled out from local content alone.

No baseline exists for any of the 4 templates yet (this module and its data
file are new). On first run each workflow's baseline is seeded from its
*current* deployed content -- there is nothing to approve retroactively, so
today's live state is adopted as the trusted starting point, exactly as
SEO-AUTONOMY-STATE-MACHINE's seed_from_product_review_log() adopted the
review log's real verdicts rather than inventing history.

Usage:
    python scripts/ci/checks/check_workflow_drift.py
    python scripts/ci/checks/check_workflow_drift.py --no-seed

Exit codes:
  0 -- every workflow IN_SYNC
  1 -- at least one workflow DEPLOYED_UNAPPROVED or DIVERGED
  2 -- configuration error (workflows dir missing, gh unavailable/unauthenticated)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
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


def fetch_deployed_content(
    deployed_path: str, *, repo: str = DEPLOYED_REPO, runner: CommandRunner = subprocess.run,
) -> "str | None":
    """Fetch a file's raw text content from `repo` via `gh api`.

    Returns None if the file does not exist there, the call fails (network,
    auth, timeout), or the response cannot be decoded -- a caller must never
    treat None as "matches", only as "unresolved".
    """
    try:
        result = runner(
            ["gh", "api", f"repos/{repo}/contents/{deployed_path}", "--jq", ".content"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        raw_b64 = "".join(result.stdout.split())
        return base64.b64decode(raw_b64).decode("utf-8")
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return None


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
            deployed_text = fetch_fn(deployed_path)
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
                "status": classify(local_sha, deployed_sha, baseline_sha),
                "local_sha256": local_sha,
                "deployed_sha256": deployed_sha,
                "approved_baseline_sha256": baseline_sha,
            }

    return {"results": results, "baselines": baselines}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Three-way drift check for scripts/seo/workflows/*.yml and "
                     "scripts/ci/deployed-workflows/*.yml"
    )
    parser.add_argument("--no-seed", action="store_true",
                         help="Do not seed a missing baseline from today's deployed content")
    args = parser.parse_args(argv)

    existing_dirs = [d for d in SOURCE_DIRS if d.is_dir()]
    if not existing_dirs:
        print(f"ERROR: none of {list(SOURCE_DIRS)} exist", file=sys.stderr)
        return 2

    try:
        gh_check = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        gh_check = None
    if gh_check is None or gh_check.returncode != 0:
        print("ERROR: gh CLI not available or not authenticated", file=sys.stderr)
        return 2

    outcome = check_workflow_drift(seed_missing_baselines=not args.no_seed)
    results = outcome["results"]

    for name, r in sorted(results.items()):
        deployed_display = (r["deployed_sha256"] or "unresolved")[:12]
        print(f"  {r['status']:20s} {name}: local={r['local_sha256'][:12]} deployed={deployed_display}")

    if not args.no_seed:
        save_baselines(outcome["baselines"])

    drifted = {name: r for name, r in results.items() if r["status"] != IN_SYNC}
    if drifted:
        print(f"\nACTION REQUIRED: {len(drifted)} of {len(results)} workflow(s) not in sync")
        for name, r in drifted.items():
            print(f"  - {name}: {r['status']}")
        return 1

    print(f"\nAll {len(results)} workflow(s) in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

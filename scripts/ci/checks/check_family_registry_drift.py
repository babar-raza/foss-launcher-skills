#!/usr/bin/env python3
"""Detect a launched product family with real content but no registry entry
(Finding #70).

The SEO pipeline's own family-handling is already correctly dynamic --
`get_keywords.py`/`review_keywords.py`/`site_planner.py` all pull family
scope from `canonical_families()` (`scripts/seo/pipeline/schema.py`), which
in turn reads `data/family_descriptions.json`. That file is entirely
hand-maintained (a handful of manual commits, zero automated writers) and
structurally disconnected from `/launch-product`/repo-scout/discovery-
triage: a newly-launched family with real content stays invisible to the
entire weekly Schema A refresh cron until a human remembers to hand-add an
entry.

Decision (per the design authority this task cites): detect and alert, do
NOT silently write into `data/family_descriptions.json` directly -- that
file feeds 4 Hugo home templates repo-wide, not just SEO, so writing into
it from a check script would be exactly the boundary violation this whole
mission exists to eliminate. This script scans real launched content
directories (`content/{docs,kb,products}.aspose.org/en/*/`) for family-level
subdirectory names, diffs against the registry's current keys, and for any
family with real launched content but no registry entry, files/dedupes a
`family-registry-gap` issue (the same find-or-create pattern established in
`check_upstream_drift.py`, FRESH-001) rather than guessing at a description.

Reads `data/family_descriptions.json` directly (the same file
`canonical_families()` itself reads) instead of importing `scripts/seo/`
internals, so this module has no cross-package import dependency.

Usage:
    python scripts/ci/checks/check_family_registry_drift.py
    python scripts/ci/checks/check_family_registry_drift.py --file-issues
    python scripts/ci/checks/check_family_registry_drift.py --file-issues --repo Aspose/aspose.org

Exit codes:
  0 -- no registry gaps found
  1 -- at least one launched family has no registry entry
  2 -- configuration error (registry file missing/unreadable)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT
REGISTRY_PATH = REPO_ROOT / "data" / "family_descriptions.json"

# The 3 sites where a real, human-facing product family launch shows up as a
# family-level content directory. reference.aspose.org and blog.aspose.org
# are deliberately excluded: reference is generated per already-known
# family/platform pairs (never a launch signal of its own) and blog posts
# live under the same family dirs docs/kb/products already cover.
CONTENT_SITES = ("docs.aspose.org", "kb.aspose.org", "products.aspose.org")

DEFAULT_REPO = "Aspose/aspose.org"
ISSUE_LABEL = "family-registry-gap"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, REGISTRY_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    REGISTRY_PATH = REPO_ROOT / "data" / "family_descriptions.json"


CommandRunner = Callable[..., "subprocess.CompletedProcess[str]"]


def load_registered_families() -> set[str]:
    """The current set of registry keys in data/family_descriptions.json.

    Raises FileNotFoundError/json.JSONDecodeError on a missing/unreadable
    registry -- unlike canonical_families()'s own fail-open-to-[] behavior,
    this check's whole job is comparing against the registry, so silently
    treating "unreadable" as "empty" would misreport every launched family
    as a gap. The CLI maps this to exit code 2 (configuration error).
    """
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{REGISTRY_PATH} does not contain a JSON object")
    return set(raw.keys())


def find_launched_families(*, content_root: "Path | None" = None, sites=CONTENT_SITES) -> set[str]:
    """Real, launched family-level directory names under content/{site}/en/*/.

    A directory counts as "launched" if it exists at all under any of the 3
    sites -- even a single `_index.md` (a family-root landing page with no
    docs/kb content yet) is real, committed, human-facing content, not a
    stub the registry gap check should ignore.
    """
    content_root = content_root or (REPO_ROOT / "content")
    launched: set[str] = set()
    for site in sites:
        en_dir = content_root / site / "en"
        if not en_dir.is_dir():
            continue
        for child in en_dir.iterdir():
            if child.is_dir() and not child.name.startswith("_") and not child.name.startswith("."):
                launched.add(child.name)
    return launched


def find_registry_gaps(*, content_root: "Path | None" = None) -> list[str]:
    """Sorted list of launched families with no registry entry."""
    registered = load_registered_families()
    launched = find_launched_families(content_root=content_root)
    return sorted(launched - registered)


def _family_label(family: str) -> str:
    return f"family:{family}"


def find_existing_issue(family: str, *, repo: str, runner: CommandRunner) -> "int | None":
    """Search open issues carrying BOTH ISSUE_LABEL and this family's label.
    Returns the issue number, or None if no such issue is open."""
    try:
        result = runner(
            ["gh", "issue", "list", "--repo", repo,
             "--label", ISSUE_LABEL, "--label", _family_label(family),
             "--state", "open", "--json", "number", "--limit", "1"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "[]")
        return data[0]["number"] if data else None
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
        return None


def _issue_body(family: str, *, sites_present: list[str], run_url: "str | None") -> str:
    lines = [
        f"## Family registry gap: `{family}`",
        "",
        f"`{family}` has real, launched content ({', '.join(sites_present)}) but no entry in "
        "`data/family_descriptions.json`.",
        "",
        "### Why this matters",
        "`canonical_families()` (`scripts/seo/pipeline/schema.py`) is the single source of truth "
        "the entire SEO pipeline uses to decide which families exist -- the weekly Schema A "
        f"keyword refresh cron, `site_planner.py`, and 4 Hugo home templates all read it. Until "
        f"`{family}` has a real entry, it stays invisible to all of them.",
        "",
        "### Next step",
        "A human (or the owning launch skill, per this finding's own out-of-scope note) needs to "
        f"add a real, descriptive `{family}` entry to `data/family_descriptions.json` -- this check "
        "deliberately does not write one itself: that file feeds 4 Hugo home templates repo-wide, "
        "not just SEO, so guessing a description here would be a boundary violation, not a fix.",
    ]
    if run_url:
        lines += ["", f"Triggered by: [workflow run]({run_url})"]
    return "\n".join(lines)


def file_or_update_issue(
    family: str, *, sites_present: list[str], repo: str, runner: CommandRunner,
    run_url: "str | None" = None,
) -> dict:
    """Create a new issue for this family's gap, or comment on the existing
    deduped issue if one is already open. Returns
    {"action": "created"|"commented"|"failed", "issue_number": int|None}."""
    existing = find_existing_issue(family, repo=repo, runner=runner)
    body = _issue_body(family, sites_present=sites_present, run_url=run_url)

    if existing is not None:
        try:
            result = runner(
                ["gh", "issue", "comment", str(existing), "--repo", repo, "--body", body],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                return {"action": "commented", "issue_number": existing}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return {"action": "failed", "issue_number": existing}

    try:
        result = runner(
            ["gh", "issue", "create", "--repo", repo,
             "--title", f"Family registry gap: {family}",
             "--label", ISSUE_LABEL, "--label", _family_label(family),
             "--body", body],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            new_number = None
            try:
                new_number = int(result.stdout.strip().rsplit("/", 1)[-1])
            except (ValueError, IndexError):
                pass
            return {"action": "created", "issue_number": new_number}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return {"action": "failed", "issue_number": None}


def _sites_present_for(family: str, *, content_root: "Path | None" = None, sites=CONTENT_SITES) -> list[str]:
    content_root = content_root or (REPO_ROOT / "content")
    present = []
    for site in sites:
        if (content_root / site / "en" / family).is_dir():
            present.append(site)
    return present


def check_family_registry_drift(
    *, file_issues: bool = False, repo: str = DEFAULT_REPO,
    runner: CommandRunner = subprocess.run, run_url: "str | None" = None,
    content_root: "Path | None" = None,
) -> dict:
    """Run the full check. Returns a JSON-serializable report dict."""
    gaps = find_registry_gaps(content_root=content_root)
    report: dict = {"gaps": gaps, "issue_actions": {}}
    if file_issues:
        for family in gaps:
            sites_present = _sites_present_for(family, content_root=content_root)
            report["issue_actions"][family] = file_or_update_issue(
                family, sites_present=sites_present, repo=repo, runner=runner, run_url=run_url,
            )
    return report


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file-issues", action="store_true", help="File/dedupe a GitHub issue per gap found")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"Repo to file issues against (default: {DEFAULT_REPO})")
    parser.add_argument("--run-url", default=None, help="CI run URL to include in a filed issue body")
    args = parser.parse_args(argv)

    try:
        report = check_family_registry_drift(file_issues=args.file_issues, repo=args.repo, run_url=args.run_url)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"::error::check_family_registry_drift configuration error: {e}", file=sys.stderr)
        return 2

    if not report["gaps"]:
        print("OK: every launched family has a data/family_descriptions.json entry.")
        return 0

    print(f"FOUND {len(report['gaps'])} family registry gap(s):")
    for family in report["gaps"]:
        action = report["issue_actions"].get(family)
        suffix = f" -- issue {action['action']} (#{action['issue_number']})" if action else ""
        print(f"  - {family}{suffix}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

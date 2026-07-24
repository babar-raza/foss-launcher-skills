"""publish_watcher.py — Mission MT008 (plans/master-plan.md) D-03.

For every Java-FOSS family/platform in data/foss_packages.json with published:false,
independently verifies whether the scouted coordinate is now live on Maven Central --
never inferred from a green release-workflow exit code (this repo's own history
documents a workflow that can report success while the artifact silently sits in
"Pending Validation": the waitUtil/waitUntil typo, see .claude/commands/foss-java-publish.md).

This closes Finding F-05: S-110 (foss-java-publish)'s content-healing phase is
manually triggered and was never run for 2 of 4 families. This script replaces
"someone must remember" with a scheduled check (see .github/workflows/maven-publish-watcher.yml).

Design note: does NOT auto-commit a state flip to data/foss_packages.json, and does
NOT open a pull request. It detects and reports only -- a human reviews the finding
(via a GitHub issue, following this repo's existing scripts/ci/checks/check_upstream_drift.py
+ .github/workflows/upstream-monitor.yml precedent) before the data file is ever
touched. This is a deliberate adaptation of the mission plan's original "opens a PR"
design: an issue requires zero git/branch/commit operations (strictly lower blast
radius than a PR) while preserving the same human-review-before-landing guarantee,
and matches this repo's own proven, already-working pattern instead of introducing a
new one.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.publish_watcher
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.publish_watcher --issue-body-out path.md

Exit codes:
    0  no unpublished family resolved live (nothing to report)
    1  at least one unpublished family now resolves live (report to stdout / issue body)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DATA_PATH = _DEFAULT_REPO_ROOT / "data" / "foss_packages.json"
DATA_PATH = _DEFAULT_DATA_PATH
_LIVE_CHECKER: "Callable[[str, str], str | None] | None" = None


def configure(
    *,
    data_path: "Path | str | None" = None,
    live_checker: "Callable[[str, str], str | None] | None" = None,
) -> None:
    """Override module-level constants for testing (configure() seam, AGENTS.md 16 --
    used instead of monkeypatch.setattr on module functions directly)."""
    global DATA_PATH, _LIVE_CHECKER
    DATA_PATH = Path(data_path) if data_path is not None else _DEFAULT_DATA_PATH
    _LIVE_CHECKER = live_checker


def default_live_checker(group_id: str, artifact_id: str) -> "str | None":
    """Query Maven Central's maven-metadata.xml directly for group_id/artifact_id.

    Returns the live release version string if the artifact resolves, or None on
    any failure (network error, 404, malformed XML). Never raises -- a checker
    failure must never be mistaken for "confirmed unpublished"; callers treat
    None as "could not confirm this run", not as a negative result to act on.
    """
    group_path = group_id.replace(".", "/")
    url = f"https://repo1.maven.org/maven2/{group_path}/{artifact_id}/maven-metadata.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; aspose-org-publish-watcher/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError):
        return None
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None
    return root.findtext("versioning/release") or root.findtext("versioning/latest")


def check_unpublished_families(
    data: dict[str, Any],
    live_checker: Callable[[str, str], "str | None"] = default_live_checker,
) -> list[dict[str, Any]]:
    """Return proposed state flips for every published:false entry whose scouted
    coordinate now resolves live on Maven Central.

    Pure detection -- never mutates `data`. INV-02 (plans/master-plan.md): the only
    signal that can produce a proposal is `live_checker`'s own return value, never a
    workflow exit code or any other indirect signal.
    """
    proposals: list[dict[str, Any]] = []
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            if entry.get("published"):
                continue
            scouted = entry.get("scouted") or {}
            group_id, artifact_id = scouted.get("group_id"), scouted.get("artifact_id")
            if not group_id or not artifact_id:
                continue
            live_version = live_checker(group_id, artifact_id)
            if live_version:
                proposals.append({
                    "family": family,
                    "platform": platform,
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": live_version,
                    "central_url": f"https://repo1.maven.org/maven2/{group_id.replace('.', '/')}/{artifact_id}/",
                })
    return proposals


def apply_proposal(data: dict[str, Any], proposal: dict[str, Any], *, checked_at: "str | None" = None) -> dict[str, Any]:
    """Mutate `data` in place to reflect a confirmed proposal.

    NOT called by the automatic scheduled run (see module docstring) -- this is the
    pure state-transition function used by tests and by a human-reviewed follow-up
    action after reading the issue this module's CLI helps generate.
    """
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    entry = data[proposal["family"]][proposal["platform"]]
    entry["published"] = True
    entry["confirmed"] = {
        "group_id": proposal["group_id"],
        "artifact_id": proposal["artifact_id"],
        "version": proposal["version"],
    }
    entry["confirmed_at"] = checked_at
    entry["confirmed_evidence"] = f"publish-watcher live check, {checked_at}"
    entry["central_url"] = proposal["central_url"]
    return entry


def format_issue_body(proposals: list[dict[str, Any]]) -> str:
    """Build the GitHub issue body for a batch of proposals, following the
    check_upstream_drift.py / upstream-monitor.yml precedent (actionable next
    steps, not just a raw dump)."""
    lines = [
        "## Java-FOSS Package(s) Now Live on Maven Central",
        "",
        "The scheduled publish-watcher found that one or more Java-FOSS packages "
        "previously marked `published: false` in `data/foss_packages.json` now "
        "resolve live on Maven Central.",
        "",
        "### Action Required",
        "1. Verify each finding below independently before applying it (this issue "
        "is a proposal, not an auto-applied change).",
        "2. Update `data/foss_packages.json` for each confirmed family (see "
        "`publish_watcher.apply_proposal` for the exact shape).",
        "3. Re-run `/repo-scout {family} java` and `/truth-merge {family} java` to "
        "reconcile `knowledge/` with the newly-confirmed coordinate.",
        "4. Run the full test suite (`scripts/pipeline/tests/test_foss_packages_data.py` "
        "at minimum) before committing.",
        "",
        "### Findings",
        "",
    ]
    for p in proposals:
        lines.append(
            f"- **{p['family']}/{p['platform']}**: `{p['group_id']}:{p['artifact_id']}:{p['version']}` "
            f"— {p['central_url']}"
        )
    return "\n".join(lines)


def run_watch(*, live_checker: "Callable[[str, str], str | None] | None" = None) -> list[dict[str, Any]]:
    """Load DATA_PATH, check every unpublished entry, return proposals (if any).

    Does not write anything -- see module docstring for why the automatic path
    never mutates data/foss_packages.json directly.

    `live_checker` defaults to None and is resolved INSIDE the function body
    (not as a bound default parameter value), falling back to a `configure()`-
    injected checker and then to the module-level `default_live_checker` --
    a bound default would silently keep referencing the original function
    object regardless of `configure()`, confirmed as a real gotcha while
    testing this module.
    """
    checker = live_checker if live_checker is not None else (_LIVE_CHECKER or default_live_checker)
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return check_unpublished_families(data, checker)


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="publish_watcher")
    parser.add_argument("--issue-body-out", metavar="PATH", help="Write the GitHub issue body to this path if any proposals are found")
    args = parser.parse_args(argv)

    proposals = run_watch()

    if not proposals:
        print("publish_watcher: no unpublished family resolves live yet. Nothing to report.")
        return 0

    body = format_issue_body(proposals)
    print(body)
    if args.issue_body_out:
        Path(args.issue_body_out).write_text(body, encoding="utf-8")

    return 1


if __name__ == "__main__":
    sys.exit(main())

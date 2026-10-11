"""sync_tracked_issues.py — PKGINSTALL-DEFECT-SWEEP-REDESIGN (MT066 plan
section R.3.4).

Fixes the un-deduplicated weekly issue-spam gap: install-literal-sweep.yml's
own workflow (actions/github-script's `github.rest.issues.create()`) files a
brand-new GitHub issue every single week any findings remain, with zero
dedup logic -- an ever-growing pile of duplicate issues at the current
~5,237-finding pace (see governing plan section R.1 point 6/R.3.4).

Dedup key: (family, platform, defect_class). Each key maps to at most one
OPEN tracked issue at a time, identified by a hidden HTML-comment marker
embedded in the issue body (`<!-- tracked-issue-key: {key} -->`) plus a
shared label (`install-defect-sweep`) -- listing open issues with that label
and matching the marker is enough to find "the" issue for a key without a
separate persisted issue-number mapping file (one less thing to keep in
sync with GitHub's own state).

- A key with nonzero findings and no existing open issue -> create.
- A key with nonzero findings and an existing open issue -> update its body
  (never a new issue).
- A key with zero findings and an existing open issue -> close it.
- A key with zero findings and no existing issue -> no-op.

All GitHub I/O goes through an injected GitHubIssuesClient -- tests inject a
fake implementing the same 4 methods (list_issues/create_issue/update_issue/
close_issue), never mocking `requests` internals directly.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Protocol

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

TRACKED_LABEL = "install-defect-sweep"
_KEY_MARKER_RE = re.compile(r"<!--\s*tracked-issue-key:\s*(\S+)\s*-->")


def _tracked_issue_key(family: str, platform: str, defect_class: str) -> str:
    return f"{family}/{platform}/{defect_class}"


def _key_marker(key: str) -> str:
    return f"<!-- tracked-issue-key: {key} -->"


class GitHubIssuesClient(Protocol):
    def list_issues(self, *, label: str, state: str = "open") -> list[dict[str, Any]]: ...
    def create_issue(self, *, title: str, body: str, labels: list[str]) -> dict[str, Any]: ...
    def update_issue(self, number: int, *, body: "str | None" = None) -> dict[str, Any]: ...
    def close_issue(self, number: int) -> dict[str, Any]: ...


class RealGitHubIssuesClient:
    """requests-based implementation -- matches this repo's established
    GitHub REST API convention (lib/org_scanner.py): GH_TOKEN precedence,
    Bearer auth, https://api.github.com."""

    def __init__(self, *, owner: str, repo: str, token: "str | None" = None):
        self.owner = owner
        self.repo = repo
        self.token = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _url(self, path: str = "") -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/issues{path}"

    def list_issues(self, *, label: str, state: str = "open") -> list[dict[str, Any]]:
        import requests
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = requests.get(
                self._url(), headers=self._headers(),
                params={"labels": label, "state": state, "per_page": 100, "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out

    def create_issue(self, *, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        import requests
        resp = requests.post(
            self._url(), headers=self._headers(),
            json={"title": title, "body": body, "labels": labels}, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def update_issue(self, number: int, *, body: "str | None" = None) -> dict[str, Any]:
        import requests
        payload: dict[str, Any] = {}
        if body is not None:
            payload["body"] = body
        resp = requests.patch(self._url(f"/{number}"), headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def close_issue(self, number: int) -> dict[str, Any]:
        import requests
        resp = requests.patch(
            self._url(f"/{number}"), headers=self._headers(), json={"state": "closed"}, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def find_tracked_issue(client: GitHubIssuesClient, key: str) -> "dict[str, Any] | None":
    """Return the open issue whose body carries this key's marker, or None."""
    for issue in client.list_issues(label=TRACKED_LABEL, state="open"):
        match = _KEY_MARKER_RE.search(issue.get("body") or "")
        if match and match.group(1) == key:
            return issue
    return None


def format_issue_body(family: str, platform: str, defect_class: str, count: int, sample: list[dict[str, Any]]) -> str:
    key = _tracked_issue_key(family, platform, defect_class)
    lines = [
        _key_marker(key),
        "",
        f"# {family}/{platform}: {defect_class} ({count} finding(s))",
        "",
        f"The scheduled install-defect-sweep found **{count}** finding(s) of defect class "
        f"`{defect_class}` for `{family}/{platform}`.",
        "",
    ]
    if sample:
        lines.append("## Sample findings")
        lines.append("")
        for s in sample:
            lines.append(f"- `{s.get('path', '?')}`: {s.get('message', '')}")
        lines.append("")
    lines.append(
        "This issue is automatically updated by the scheduled sweep -- do not close it manually "
        "unless the underlying defect is actually fixed (it will be reopened by the next sweep "
        "run's create step if findings still remain and this issue was closed in error)."
    )
    return "\n".join(lines)


def sync_one(
    client: GitHubIssuesClient, *, family: str, platform: str, defect_class: str,
    count: int, sample: "list[dict[str, Any]] | None" = None,
) -> dict[str, Any]:
    """Reconcile exactly one (family, platform, defect_class) key against
    GitHub issue state. Returns {"action": "created"|"updated"|"closed"|"noop", ...}."""
    key = _tracked_issue_key(family, platform, defect_class)
    existing = find_tracked_issue(client, key)
    sample = sample or []

    if count > 0:
        body = format_issue_body(family, platform, defect_class, count, sample)
        if existing is None:
            issue = client.create_issue(
                title=f"install-defect-sweep: {family}/{platform} {defect_class} ({count})",
                body=body, labels=[TRACKED_LABEL],
            )
            return {"action": "created", "key": key, "issue": issue}
        issue = client.update_issue(existing["number"], body=body)
        return {"action": "updated", "key": key, "issue": issue}

    if existing is not None:
        issue = client.close_issue(existing["number"])
        return {"action": "closed", "key": key, "issue": issue}
    return {"action": "noop", "key": key, "issue": None}


def sync_all(client: GitHubIssuesClient, findings: "list[dict[str, Any]]") -> list[dict[str, Any]]:
    """Sync every (family, platform, defect_class) key present in
    `findings` -- see install_defect_sweep.defect_class_findings() for the
    expected shape ({family, platform, defect_class, count, sample}).

    Does NOT close keys absent from `findings` entirely (a key with zero
    findings must still be explicitly passed with count=0 to be closed --
    matching install_defect_sweep.py's own current-run-only scope; closing
    every previously-tracked key never seen this run is a separate,
    higher-risk operation this function deliberately does not attempt)."""
    return [
        sync_one(
            client, family=f["family"], platform=f["platform"], defect_class=f["defect_class"],
            count=f["count"], sample=f.get("sample"),
        )
        for f in findings
    ]


def main(argv: "list[str] | None" = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings", required=True, metavar="PATH", help="JSON file from install_defect_sweep.py --issues-out")
    parser.add_argument("--owner", default="Aspose")
    parser.add_argument("--repo", default="aspose.org")
    args = parser.parse_args(argv)

    findings = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    client = RealGitHubIssuesClient(owner=args.owner, repo=args.repo)
    results = sync_all(client, findings)
    for r in results:
        print(f"{r['action']}: {r['key']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

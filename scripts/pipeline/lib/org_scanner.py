"""GitHub organisation scanner.

Scans a GitHub organisation for repositories and returns structured metadata.

Public API:
    scan_org(org, *, token=None, per_page=100) -> list[dict]
    scan_orgs(orgs, *, token=None, state_dir=None) -> list[dict]

Each returned repo dict contains:
    name        str   — repo name (e.g. "aspose-3d-python")
    full_name   str   — "org/name"
    html_url    str   — GitHub URL
    clone_url   str   — HTTPS clone URL
    pushed_at   str   — ISO 8601 timestamp of last push (or "")
    archived    bool  — True if repo is archived
    description str   — repo description (or "")

Requirements: requests>=2.28
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise ImportError("org_scanner requires 'requests>=2.28' — pip install requests") from exc

_GITHUB_API = "https://api.github.com"
_RATE_SLEEP = 1.0  # seconds between paginated requests to stay well under rate limits


def _headers(token: str | None) -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _paginate(url: str, params: dict, token: str | None) -> Iterator[dict]:
    """Yield every repo dict across all pages for a list-repos endpoint."""
    while url:
        resp = requests.get(url, params=params, headers=_headers(token), timeout=30)
        if resp.status_code == 403:
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(1, reset - int(time.time())) + 2
            time.sleep(wait)
            resp = requests.get(url, params=params, headers=_headers(token), timeout=30)
        resp.raise_for_status()
        for repo in resp.json():
            yield repo
        # Follow Link header for next page
        link = resp.headers.get("Link", "")
        url = None
        for part in link.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        params = {}  # params are already encoded in the next-page URL
        if url:
            time.sleep(_RATE_SLEEP)


def scan_org(org: str, *, token: str | None = None, per_page: int = 100) -> list[dict]:
    """Return metadata for every repository in *org*.

    Parameters
    ----------
    org:
        GitHub organisation login (e.g. "aspose-free").
    token:
        Personal access token or fine-grained PAT with ``read:org`` + ``public_repo``
        scopes.  When *None* the public unauthenticated API is used (60 req/hr limit).
    per_page:
        Page size (GitHub max: 100).
    """
    url = f"{_GITHUB_API}/orgs/{org}/repos"
    params = {"type": "public", "per_page": per_page, "sort": "pushed"}
    repos: list[dict] = []
    for raw in _paginate(url, params, token):
        repos.append(
            {
                "name": raw["name"],
                "full_name": raw["full_name"],
                "html_url": raw["html_url"],
                "clone_url": raw["clone_url"],
                "pushed_at": raw.get("pushed_at") or "",
                "archived": bool(raw.get("archived")),
                "description": raw.get("description") or "",
            }
        )
    return repos


def scan_orgs(
    orgs: list[str],
    *,
    token: str | None = None,
    state_dir: Path | str | None = None,
) -> list[dict]:
    """Scan multiple organisations, optionally caching results in *state_dir*.

    Parameters
    ----------
    orgs:
        List of GitHub organisation logins.
    token:
        GitHub token (see :func:`scan_org`).
    state_dir:
        Directory for caching raw API results between runs.  Cached data is
        used as a fallback when the GitHub API is unreachable.
    """
    if state_dir is not None:
        state_path = Path(state_dir)
        state_path.mkdir(parents=True, exist_ok=True)
    else:
        state_path = None

    all_repos: list[dict] = []
    for org in orgs:
        cache_file = state_path / f"{org}.json" if state_path else None
        try:
            repos = scan_org(org, token=token)
            if cache_file:
                cache_file.write_text(json.dumps(repos, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            if cache_file and cache_file.is_file():
                repos = json.loads(cache_file.read_text(encoding="utf-8"))
            else:
                repos = []
        all_repos.extend(repos)
    return all_repos

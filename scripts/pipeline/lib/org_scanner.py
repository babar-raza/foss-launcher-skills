"""GitHub organisation scanner.

Scans a GitHub organisation for repositories and returns structured metadata.

Public API:
    resolve_token(explicit=None) -> (token | None, auth_mode)
    preflight(org, *, token=None) -> None            (raises TokenRejected)
    scan_org(org, *, token=None, per_page=100, max_rate_wait=300) -> list[dict]
    scan_orgs(orgs, *, token=None, max_rate_wait=300) -> (list[dict], list[dict])

Each returned repo dict contains:
    name        str   — repo name (e.g. "aspose-3d-python")
    full_name   str   — "org/name"
    html_url    str   — GitHub URL
    clone_url   str   — HTTPS clone URL
    pushed_at   str   — ISO 8601 timestamp of last push (or "")
    archived    bool  — True if repo is archived
    description str   — repo description (or "")

``scan_orgs`` additionally returns one *outcome* dict per org::

    {"org": str,
     "status": "ok" | "auth_denied" | "rate_limited" | "not_found"
               | "http_error" | "network_error",
     "repo_count": int,
     "detail": str}     # never contains the token

Failure contract (ST-058): a failed scan is NEVER reported as an empty success.
``scan_orgs`` records a typed outcome for every org so callers can distinguish
"this org has no matching repos" from "this org was never reached". GitHub
returns HTTP 403 for BOTH rate-limiting and authorization/policy denial; the two
are distinguished via ``X-RateLimit-Remaining`` / ``Retry-After`` rather than
being conflated (which previously caused a ~54-minute sleep per org against a
token the org will never accept).

Requirements: requests>=2.28
"""
from __future__ import annotations

import os
import time
from typing import Iterator

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise ImportError("org_scanner requires 'requests>=2.28' — pip install requests") from exc

_GITHUB_API = "https://api.github.com"
_RATE_SLEEP = 1.0  # seconds between paginated requests to stay well under rate limits

# Upper bound on a single rate-limit backoff. GitHub's X-RateLimit-Reset can be
# up to an hour out; sleeping that long per org turns a transient throttle into
# an overnight hang. Callers may override via max_rate_wait.
_DEFAULT_MAX_RATE_WAIT = 300

# Actionable remedy appended to every auth denial. The aspose-*-foss orgs reject
# fine-grained PATs whose lifetime exceeds 366 days; the classic PAT in GH_TOKEN
# is accepted. Confirmed live 2026-08-05 (ST-058).
_AUTH_HINT = (
    "token rejected by GitHub (authorization/org policy, not rate limiting). "
    "The aspose-*-foss orgs forbid fine-grained PATs with a lifetime over 366 days — "
    "use a classic PAT via GH_TOKEN, or pass --token explicitly."
)


class OrgScanError(RuntimeError):
    """A single org could not be scanned.

    Carries the originating HTTP ``status`` (None for non-HTTP failures) so callers
    classify from the status code rather than by substring-matching the rendered
    message. Message parsing is a lossy channel and previously absorbed every
    non-404 status into "rate_limited" (MT020-L1-01) — the same conflation this
    module exists to eliminate one layer down.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class TokenRejected(OrgScanError):
    """The supplied credential was rejected (HTTP 401, or 403 that is not throttling)."""


# ---------------------------------------------------------------------------
# Token resolution — single authority for both CLI entrypoints
# ---------------------------------------------------------------------------

def resolve_token(explicit: str | None = None) -> tuple[str | None, str]:
    """Resolve the GitHub credential and report which source supplied it.

    Precedence: explicit ``--token`` > ``GH_TOKEN`` > ``GITHUB_TOKEN`` > none.

    ``GH_TOKEN`` is preferred because it holds the classic PAT this repo's orgs
    accept; ``GITHUB_TOKEN`` holds a fine-grained PAT that the orgs reject under
    their >366-day-lifetime policy (ST-058). Returns ``(token, auth_mode)``
    where *auth_mode* is a label safe to record in reports — never the token.
    """
    if explicit:
        return explicit, "explicit --token"
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val, var
    return None, "unauthenticated"


def _headers(token: str | None) -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ---------------------------------------------------------------------------
# Response classification
# ---------------------------------------------------------------------------

def _is_rate_limited(resp) -> bool:
    """True when a 403/429 is genuine throttling rather than authorization denial.

    GitHub overloads 403. The discriminators, in order of authority:
      - HTTP 429                       -> always throttling
      - Retry-After header present     -> secondary rate limit
      - X-RateLimit-Remaining == 0     -> primary rate limit exhausted
    Anything else (notably a 403 arriving with thousands of requests remaining)
    is an authorization or org-policy denial and must fail fast.
    """
    if getattr(resp, "status_code", None) == 429:
        return True
    headers = getattr(resp, "headers", None) or {}
    if headers.get("Retry-After"):
        return True
    remaining = headers.get("X-RateLimit-Remaining")
    if remaining is None:
        return False
    try:
        return int(remaining) <= 0
    except (TypeError, ValueError):
        return False


def _rate_wait_seconds(resp, max_rate_wait: int) -> int:
    """Seconds to sleep before retrying a throttled request, capped at *max_rate_wait*."""
    headers = getattr(resp, "headers", None) or {}
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return max(1, min(int(retry_after), max_rate_wait))
        except (TypeError, ValueError):
            pass
    reset = headers.get("X-RateLimit-Reset")
    if reset:
        try:
            wait = int(reset) - int(time.time()) + 2
            return max(1, min(wait, max_rate_wait))
        except (TypeError, ValueError):
            pass
    return min(60, max_rate_wait)


def _detail_from(resp) -> str:
    """Short, token-free description of a failure response."""
    try:
        body = resp.json()
        msg = body.get("message") if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001 — body may be empty or non-JSON
        msg = None
    if not msg:
        msg = (getattr(resp, "text", "") or "")[:200]
    return str(msg)[:300]


def _raise_for_status(resp, org: str) -> None:
    """Translate a non-2xx response into a typed OrgScanError."""
    status = getattr(resp, "status_code", None)
    if status is None or 200 <= status < 300:
        return
    detail = _detail_from(resp)
    if status in (401, 403):
        raise TokenRejected(f"HTTP {status} on org '{org}': {detail} — {_AUTH_HINT}",
                            status=status)
    if status == 404:
        raise OrgScanError(f"HTTP 404 on org '{org}': {detail or 'organisation not found'}",
                           status=404)
    raise OrgScanError(f"HTTP {status} on org '{org}': {detail}", status=status)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def _paginate(
    url: str,
    params: dict,
    token: str | None,
    *,
    org: str = "",
    max_rate_wait: int = _DEFAULT_MAX_RATE_WAIT,
) -> Iterator[dict]:
    """Yield every repo dict across all pages for a list-repos endpoint.

    A throttling 403/429 is retried once after a capped sleep. An authorization
    403/401 raises ``TokenRejected`` immediately — no sleep, no retry.
    """
    while url:
        resp = requests.get(url, params=params, headers=_headers(token), timeout=30)
        if getattr(resp, "status_code", None) in (403, 429):
            if not _is_rate_limited(resp):
                _raise_for_status(resp, org)  # fail fast — always raises
            time.sleep(_rate_wait_seconds(resp, max_rate_wait))
            resp = requests.get(url, params=params, headers=_headers(token), timeout=30)
        _raise_for_status(resp, org)
        for repo in resp.json():
            yield repo
        # Follow Link header for next page
        link = (getattr(resp, "headers", None) or {}).get("Link", "")
        url = None
        for part in link.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        params = {}  # params are already encoded in the next-page URL
        if url:
            time.sleep(_RATE_SLEEP)


# ---------------------------------------------------------------------------
# Public scan API
# ---------------------------------------------------------------------------

def preflight(org: str, *, token: str | None = None) -> None:
    """Probe one org to validate the credential before sweeping all of them.

    Raises ``TokenRejected`` when the credential is refused, so a bad token costs
    one request instead of one per org. Throttling and transient network errors
    are deliberately NOT raised here — the full scan handles those per-org.
    """
    try:
        resp = requests.get(
            f"{_GITHUB_API}/orgs/{org}/repos",
            params={"type": "public", "per_page": 1},
            headers=_headers(token),
            timeout=30,
        )
    except Exception:  # noqa: BLE001 — network problems are not credential problems
        return
    if getattr(resp, "status_code", None) in (401, 403) and not _is_rate_limited(resp):
        _raise_for_status(resp, org)


def scan_org(
    org: str,
    *,
    token: str | None = None,
    per_page: int = 100,
    max_rate_wait: int = _DEFAULT_MAX_RATE_WAIT,
) -> list[dict]:
    """Return metadata for every repository in *org*.

    Raises ``TokenRejected`` / ``OrgScanError`` on failure — never returns a
    misleading empty list.

    Parameters
    ----------
    org:
        GitHub organisation login (e.g. "aspose-3d-foss").
    token:
        Personal access token.  When *None* the public unauthenticated API is
        used (60 req/hr limit).
    per_page:
        Page size (GitHub max: 100).
    max_rate_wait:
        Upper bound in seconds on a single throttling backoff.
    """
    url = f"{_GITHUB_API}/orgs/{org}/repos"
    params = {"type": "public", "per_page": per_page, "sort": "pushed"}
    repos: list[dict] = []
    for raw in _paginate(url, params, token, org=org, max_rate_wait=max_rate_wait):
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


def _outcome(org: str, status: str, repo_count: int = 0, detail: str = "") -> dict:
    return {"org": org, "status": status, "repo_count": repo_count, "detail": detail}


def _status_for(exc: Exception) -> str:
    """Map an exception to an outcome status, classifying from the HTTP status code.

    Never infer the class by substring-matching the message: a GitHub 500 would then
    be reported as "rate_limited", telling an operator to wait out an outage
    (MT020-L1-01).
    """
    if isinstance(exc, TokenRejected):
        return "auth_denied"
    if isinstance(exc, OrgScanError):
        status = getattr(exc, "status", None)
        if status == 404:
            return "not_found"
        if status in (403, 429):
            return "rate_limited"
        if status is not None:
            return "http_error"
        return "network_error"
    return "network_error"


def scan_orgs(
    orgs: list[str],
    *,
    token: str | None = None,
    max_rate_wait: int = _DEFAULT_MAX_RATE_WAIT,
) -> tuple[list[dict], list[dict]]:
    """Scan multiple organisations.

    Returns ``(repos, outcomes)`` — one outcome dict per org, in input order.
    A failed org contributes an outcome with a non-"ok" status; it never
    silently contributes zero repos with no trace. Callers MUST inspect
    *outcomes* before treating *repos* as a complete picture.
    """
    all_repos: list[dict] = []
    outcomes: list[dict] = []
    for org in orgs:
        try:
            repos = scan_org(org, token=token, max_rate_wait=max_rate_wait)
        except Exception as exc:  # noqa: BLE001 — classified, recorded, never swallowed
            outcomes.append(_outcome(org, _status_for(exc), 0, str(exc)[:300]))
            continue
        outcomes.append(_outcome(org, "ok", len(repos)))
        all_repos.extend(repos)
    return all_repos, outcomes

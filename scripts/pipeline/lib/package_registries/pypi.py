"""pypi.py — PyPI publish-verification adapter.

Public API endpoint: https://pypi.org/pypi/{name}/json (unauthenticated GET,
no rate-limit auth required for reasonable polling cadence).
"""

from __future__ import annotations

import json

from . import CheckResult, default_fetch


def _extract_project_url(info: dict) -> "str | None":
    """PyPI's project_urls is a free-form dict (e.g. {"Homepage": "...",
    "Repository": "...", "Issues": "..."}) -- prefer Repository/Homepage,
    fall back to home_page, else None."""
    urls = info.get("project_urls") or {}
    for key in ("Repository", "Homepage", "Source", "Source Code"):
        if urls.get(key):
            return urls[key]
    if urls:
        return next(iter(urls.values()))
    return info.get("home_page") or None


def check_published(candidate: dict, *, fetch=None) -> CheckResult:
    fetch = fetch or default_fetch
    name = candidate["name"]
    url = f"https://pypi.org/pypi/{name}/json"
    resp = fetch(url)

    if resp is None:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="pypi-json-api")

    if resp.status_code == 404:
        return CheckResult(published=False, ambiguous=False, evidence_url=url, method="pypi-json-api")

    if resp.status_code != 200:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="pypi-json-api")

    try:
        data = json.loads(resp.body)
        info = data.get("info", {})
        author = info.get("author") or info.get("maintainer")
    except (json.JSONDecodeError, AttributeError):
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="pypi-json-api")

    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="pypi-json-api",
        verified_owner=author,
        project_url=_extract_project_url(info),
        candidate_name=name,
    )


def search(family: str, *, fetch=None) -> list[CheckResult]:
    """PyPI has no free-text search API (removed years ago) -- this tries a
    small, deterministic set of name variants instead of a true search,
    covering the real non-convention-naming case found 2026-08-01
    (note/python's actual package is `aspose-note`, not the naming-convention
    guess `aspose-note-foss`). Returns only variants that resolve (200),
    each with its own project_url for the caller to apply
    is_corroborated_match() against -- this function never itself decides
    whether a match is genuine.
    """
    variants = [
        f"aspose-{family}",
        f"aspose_{family}",
        f"aspose{family}",
        f"aspose-{family}-foss",
    ]
    seen = set()
    results = []
    for name in variants:
        if name in seen:
            continue
        seen.add(name)
        result = check_published({"name": name}, fetch=fetch)
        if result.published and not result.ambiguous:
            results.append(result)
    return results

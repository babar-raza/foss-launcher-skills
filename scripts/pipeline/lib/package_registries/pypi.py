"""pypi.py — PyPI publish-verification adapter.

Public API endpoint: https://pypi.org/pypi/{name}/json (unauthenticated GET,
no rate-limit auth required for reasonable polling cadence).
"""

from __future__ import annotations

import json

from . import CheckResult, default_fetch


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
        author = data.get("info", {}).get("author") or data.get("info", {}).get("maintainer")
    except (json.JSONDecodeError, AttributeError):
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="pypi-json-api")

    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="pypi-json-api",
        verified_owner=author,
    )

"""npm.py — npm registry publish-verification adapter.

Public API endpoint: https://registry.npmjs.org/{name} (unauthenticated GET;
scoped names like @asposefoss/pdf must be URL-encoded, since the registry's
scoped-package convention uses the literal '/' as a path separator and
requires the '@' to be percent-encoded when used directly in a URL path).
"""

from __future__ import annotations

import json
import urllib.parse

from . import CheckResult, default_fetch


def check_published(candidate: dict, *, fetch=None) -> CheckResult:
    fetch = fetch or default_fetch
    name = candidate["name"]
    # npm's registry API accepts scoped names either raw ("@scope/name") or
    # fully percent-encoded ("%40scope%2Fname") -- percent-encode defensively
    # so scoped names round-trip correctly through any intermediate proxy.
    encoded_name = urllib.parse.quote(name, safe="")
    url = f"https://registry.npmjs.org/{encoded_name}"
    resp = fetch(url)

    if resp is None:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="npm-registry-api")

    if resp.status_code == 404:
        return CheckResult(published=False, ambiguous=False, evidence_url=url, method="npm-registry-api")

    if resp.status_code != 200:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="npm-registry-api")

    try:
        data = json.loads(resp.body)
        maintainers = data.get("maintainers") or []
        owner = maintainers[0].get("name") if maintainers else None
    except (json.JSONDecodeError, AttributeError, IndexError):
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="npm-registry-api")

    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="npm-registry-api",
        verified_owner=owner,
    )

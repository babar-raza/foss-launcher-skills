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
        repository = data.get("repository") or {}
        project_url = repository.get("url") if isinstance(repository, dict) else repository
        if not project_url:
            project_url = data.get("homepage")
        version = (data.get("dist-tags") or {}).get("latest")
    except (json.JSONDecodeError, AttributeError, IndexError):
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="npm-registry-api")

    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="npm-registry-api",
        verified_owner=owner,
        project_url=project_url,
        candidate_name=name,
        version=version,
    )


def search(family: str, *, fetch=None) -> list[CheckResult]:
    """Real npm search API. Queries for "aspose {family}" and returns
    check_published() results for every hit whose package name looks
    aspose-related, each with its own project_url for the caller to
    corroborate."""
    fetch = fetch or default_fetch
    query_url = f"https://registry.npmjs.org/-/v1/search?text=aspose+{family}&size=20"
    resp = fetch(query_url)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = json.loads(resp.body)
        objects = data.get("objects", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    results = []
    for obj in objects:
        pkg_name = obj.get("package", {}).get("name", "")
        if "aspose" not in pkg_name.lower():
            continue
        result = check_published({"name": pkg_name}, fetch=fetch)
        if result.published and not result.ambiguous:
            results.append(result)
    return results

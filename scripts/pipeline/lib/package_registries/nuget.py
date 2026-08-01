"""nuget.py — NuGet publish-verification adapter.

Public API endpoint: https://api.nuget.org/v3-flatcontainer/{id-lower}/index.json
(unauthenticated GET; NuGet package IDs are case-insensitive but the
flatcontainer API requires the lowercase form in the URL path).

Shared across the .net and cpp platforms of the same family under distinct
package IDs (e.g. words/net -> Aspose.Words.FOSS, pdf/cpp ->
Aspose.PDF.Cpp.FOSS) -- this adapter is registry-identity-agnostic, the
distinction lives in which candidate.name a given {family, platform} entry
carries in data/package_registry.json, not in this module.
"""

from __future__ import annotations

import json

from . import CheckResult, default_fetch


def _fetch_registration_metadata(package_id: str, *, fetch) -> "tuple[str | None, str | None]":
    """Query the registration API for authors/projectUrl -- the flatcontainer
    endpoint alone confirms existence but exposes no publisher identity
    (Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-04: this
    metadata is required to apply the foss-substring-or-corroboration
    identity rule). Never raises -- returns (None, None) on any failure,
    same fail-closed posture as the rest of this module."""
    url = f"https://api.nuget.org/v3/registration5-semver1/{package_id.lower()}/index.json"
    resp = fetch(url)
    if resp is None or resp.status_code != 200:
        return None, None
    try:
        data = json.loads(resp.body)
        items = data.get("items", [{}])[0].get("items", [{}])
        entry = items[0].get("catalogEntry", {}) if items else {}
        authors = entry.get("authors")
        project_url = entry.get("projectUrl") or entry.get("licenseUrl")
        return authors, project_url
    except (json.JSONDecodeError, AttributeError, IndexError, KeyError):
        return None, None


def check_published(candidate: dict, *, fetch=None) -> CheckResult:
    fetch = fetch or default_fetch
    package_id = candidate["name"]
    url = f"https://api.nuget.org/v3-flatcontainer/{package_id.lower()}/index.json"
    resp = fetch(url)

    if resp is None:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="nuget-flatcontainer-api")

    if resp.status_code == 404:
        return CheckResult(published=False, ambiguous=False, evidence_url=url, method="nuget-flatcontainer-api")

    if resp.status_code != 200:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="nuget-flatcontainer-api")

    authors, project_url = _fetch_registration_metadata(package_id, fetch=fetch)
    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="nuget-flatcontainer-api",
        verified_owner=authors,
        project_url=project_url,
        candidate_name=package_id,
    )


def search(family: str, *, fetch=None) -> list[CheckResult]:
    """Real NuGet search API (azuresearch), unlike PyPI's variant-guessing
    fallback. Queries for "aspose {family}" and returns check_published()
    results for every hit whose id looks aspose-related, each with its own
    project_url for the caller to corroborate."""
    fetch = fetch or default_fetch
    query_url = f"https://azuresearch-usnc.nuget.org/query?q=aspose+{family}&take=20"
    resp = fetch(query_url)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = json.loads(resp.body)
        hits = data.get("data", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    results = []
    for hit in hits:
        pkg_id = hit.get("id", "")
        if "aspose" not in pkg_id.lower():
            continue
        result = check_published({"name": pkg_id}, fetch=fetch)
        if result.published and not result.ambiguous:
            results.append(result)
    return results

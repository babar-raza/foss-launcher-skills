"""nuget.py — NuGet publish-verification adapter.

Public API endpoint: https://api.nuget.org/v3-flatcontainer/{id-lower}/index.json
(unauthenticated GET; NuGet package IDs are case-insensitive but the
flatcontainer API requires the lowercase form in the URL path).

Shared across the .net and cpp platforms of the same family under distinct
package IDs (e.g. words/net -> Aspose.Words.FOSS, pdf/cpp ->
Aspose.PDF.Cpp.FOSS) -- this adapter is registry-identity-agnostic, the
distinction lives in which candidate.name a given {family, platform} entry
carries in data/package_registry.json, not in this module.

Note: the flatcontainer API does not expose publisher/owner identity (no
`verified_owner` available via this endpoint) -- the NuGet Gallery's search
API (api.nuget.org/v3/registration5-semver1/...) or website scraping would
be needed for that, and is deliberately not attempted here (out of scope for
this taskcard; owner_match remains null for NuGet entries until a future
pass adds it).
"""

from __future__ import annotations

from . import CheckResult, default_fetch


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

    return CheckResult(published=True, ambiguous=False, evidence_url=url, method="nuget-flatcontainer-api")

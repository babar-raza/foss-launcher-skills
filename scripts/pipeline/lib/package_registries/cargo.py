"""cargo.py — crates.io publish-verification adapter.

Public API endpoint: https://crates.io/api/v1/crates/{name} (unauthenticated
GET). Unlike the other 4 adapters (TC-MT015-04), this one was not built in
that pass -- cargo/Cargo.toml already yields a reliable candidate at scout
time (structurally mandatory [package] name/version, unlike .csproj), so the
existing cargo-crate.html shortcode + data/package_registry.json migration
(TC-MT015-01/02) covered the render path. What was missing was the actual
crates.io publish CHECK -- the real gap RUST-CRATESIO-001 names ("crates.io
publication watch for aspose-cells-foss-rust"). Added here (TC-MT015-09) so
/package-publish-watch can cover cargo alongside pypi/nuget/npm/go_modules.
"""

from __future__ import annotations

import json

from . import CheckResult, default_fetch


def check_published(candidate: dict, *, fetch=None) -> CheckResult:
    fetch = fetch or default_fetch
    name = candidate["name"]
    url = f"https://crates.io/api/v1/crates/{name}"
    resp = fetch(url)

    if resp is None:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="crates-io-api")

    if resp.status_code == 404:
        return CheckResult(published=False, ambiguous=False, evidence_url=url, method="crates-io-api")

    if resp.status_code != 200:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="crates-io-api")

    try:
        data = json.loads(resp.body)
        crate = data.get("crate", {})
        owner = crate.get("id")
        project_url = crate.get("repository") or crate.get("homepage")
    except (json.JSONDecodeError, AttributeError):
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="crates-io-api")

    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="crates-io-api",
        verified_owner=owner,
        project_url=project_url,
        candidate_name=name,
    )


def search(family: str, *, fetch=None) -> list[CheckResult]:
    """Real crates.io search API. Queries for "aspose {family}" and returns
    check_published() results for every hit whose crate name looks
    aspose-related, each with its own project_url for the caller to
    corroborate."""
    fetch = fetch or default_fetch
    query_url = f"https://crates.io/api/v1/crates?q=aspose+{family}&per_page=20"
    resp = fetch(query_url)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = json.loads(resp.body)
        crates = data.get("crates", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    results = []
    for c in crates:
        crate_name = c.get("name", "")
        if "aspose" not in crate_name.lower():
            continue
        result = check_published({"name": crate_name}, fetch=fetch)
        if result.published and not result.ambiguous:
            results.append(result)
    return results

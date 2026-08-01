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
        owner = data.get("crate", {}).get("id")
    except (json.JSONDecodeError, AttributeError):
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="crates-io-api")

    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="crates-io-api",
        verified_owner=owner,
    )

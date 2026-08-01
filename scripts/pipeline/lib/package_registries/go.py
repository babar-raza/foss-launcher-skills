"""go.py — Go Modules publish-verification adapter.

Public API endpoint: https://proxy.golang.org/{module-path}/@v/list
(unauthenticated GET; module path must be lowercase-escaped per the Go
module proxy protocol's case-encoding rule -- uppercase letters are escaped
as '!' + lowercase, e.g. "GitHub.com" -> "!git!hub.com" -- most Aspose FOSS
module paths are already all-lowercase, so this is a defensive pass-through
for the common case rather than a full implementation of the escaping rule).

A 200 response with a non-empty body (at least one version line) means
published; a 404/410 (module never existed or was withdrawn) means not
published; anything else is ambiguous.
"""

from __future__ import annotations

from . import CheckResult, default_fetch


def check_published(candidate: dict, *, fetch=None) -> CheckResult:
    fetch = fetch or default_fetch
    module_path = candidate["module_path"]
    url = f"https://proxy.golang.org/{module_path}/@v/list"
    resp = fetch(url)

    if resp is None:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="go-proxy-api")

    if resp.status_code in (404, 410):
        return CheckResult(published=False, ambiguous=False, evidence_url=url, method="go-proxy-api")

    if resp.status_code != 200:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="go-proxy-api")

    if not resp.body.strip():
        # 200 with an empty version list is not a documented proxy behavior;
        # treat conservatively as ambiguous rather than assuming published.
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="go-proxy-api")

    return CheckResult(published=True, ambiguous=False, evidence_url=url, method="go-proxy-api")

"""go.py — Go Modules publish-verification adapter.

Public API endpoint: https://proxy.golang.org/{module-path}/@v/list
(unauthenticated GET; module path must be case-encoded per the Go module
proxy protocol -- every uppercase letter is escaped as '!' + its lowercase
form, e.g. "GitHub.com" -> "!git!hub.com").

A 200 response with a non-empty body (at least one version line) means
published; a 404/410 (module never existed or was withdrawn) means not
published; anything else is ambiguous.

No search() function here (unlike pypi/npm/nuget/cargo, Mission MT018-2026-08-01):
proxy.golang.org has no free-text search API, and Go module paths are already
fully-qualified by repo (github.com/{org}/{repo}), making the non-conforming-name
ambiguity search guards against structurally much less likely than for the other
4 registries' short, unqualified package names.
"""

from __future__ import annotations

import json

from . import CheckResult, default_fetch


def _fetch_latest_version(escaped_path: str, *, fetch) -> "str | None":
    """Query the module proxy's @latest endpoint for the authoritative latest
    version -- deliberately NOT computed by sorting @v/list's own output
    (that list isn't guaranteed semver-sorted and Go's own module-resolution
    rules, e.g. major-version-suffix handling and pseudo-version exclusion,
    are already correctly implemented behind @latest; reimplementing that
    logic here would risk getting it wrong for one extra fetch). Never
    raises -- returns None on any failure, same fail-closed posture as the
    rest of this module; a failure here must never break published
    detection, which @v/list alone already established."""
    url = f"https://proxy.golang.org/{escaped_path}/@latest"
    resp = fetch(url)
    if resp is None or resp.status_code != 200:
        return None
    try:
        return json.loads(resp.body).get("Version")
    except (json.JSONDecodeError, AttributeError):
        return None


def _escape_module_path(module_path: str) -> str:
    """Go module proxy case-encoding: each uppercase letter becomes '!' +
    its lowercase form. Real bug found 2026-08-01 (Mission MT018,
    TC-MT018-06): cells/go's real module path
    (github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26) has mixed
    case and returned a false-negative 404 before this was implemented --
    the module IS live (v26.7.0/v26.7.1), just at the escaped path."""
    return "".join(f"!{c.lower()}" if c.isupper() else c for c in module_path)


def check_published(candidate: dict, *, fetch=None) -> CheckResult:
    fetch = fetch or default_fetch
    module_path = candidate["module_path"]
    escaped_path = _escape_module_path(module_path)
    url = f"https://proxy.golang.org/{escaped_path}/@v/list"
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

    # A Go module path is already a fully-qualified repo location (e.g.
    # "github.com/aspose-cells-foss/...") -- it IS the project URL, so the
    # foss-substring-or-corroboration identity rule (Mission MT018) applies
    # directly against module_path itself; no separate metadata fetch needed.
    version = _fetch_latest_version(escaped_path, fetch=fetch)
    return CheckResult(
        published=True, ambiguous=False, evidence_url=url, method="go-proxy-api",
        project_url=f"https://{module_path}", candidate_name=module_path,
        version=version,
    )

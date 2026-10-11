"""maven.py — Maven Central publish-verification adapter, CheckResult-shaped.

MT075-T6 (plan Revision 2 SR2.5): a thin interface SHIM around the same
maven-metadata.xml approach `commands.ops.publish_watcher.default_live_checker`
already uses (unchanged in substance -- same endpoint, same XML fields), so
`registry_watch.py` can iterate all 6 registries through one uniform
`check_published(candidate, *, fetch=None) -> CheckResult` contract instead
of special-casing Maven's bespoke `str | None` return shape everywhere a
cross-registry feature (like this one) needs to treat it like the other 5.
`publish_watcher.py` itself is untouched -- its own Maven-specific debounce/
stuck-release logic keeps working exactly as before; this is an additional,
independent adapter, not a replacement.
"""

from __future__ import annotations

import json
from xml.etree import ElementTree

from . import CheckResult, default_fetch


def check_published(candidate: dict, *, fetch=None) -> CheckResult:
    fetch = fetch or default_fetch
    group_id = candidate.get("group_id", "")
    artifact_id = candidate.get("artifact_id", "")
    group_path = group_id.replace(".", "/")
    url = f"https://repo1.maven.org/maven2/{group_path}/{artifact_id}/maven-metadata.xml"
    resp = fetch(url)

    if resp is None:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="maven-metadata-xml")

    if resp.status_code == 404:
        return CheckResult(published=False, ambiguous=False, evidence_url=url, method="maven-metadata-xml")

    if resp.status_code != 200:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="maven-metadata-xml")

    try:
        root = ElementTree.fromstring(resp.body)
    except ElementTree.ParseError:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="maven-metadata-xml")

    version = root.findtext("versioning/release") or root.findtext("versioning/latest")
    if not version:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="maven-metadata-xml")

    return CheckResult(
        published=True,
        ambiguous=False,
        evidence_url=url,
        method="maven-metadata-xml",
        candidate_name=artifact_id,
        version=version,
    )


def search(family: str, *, fetch=None) -> list[CheckResult]:
    """Maven Central's search REST API, `org.aspose` group scoped -- mirrors
    nuget.search()'s shape (family-scoped discovery), for the same reverse-
    discovery use case (registry_watch.py's future discovery pass)."""
    fetch = fetch or default_fetch
    query_url = f"https://search.maven.org/solrsearch/select?q=g:org.aspose+AND+a:*{family}*&rows=20&wt=json"
    resp = fetch(query_url)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = json.loads(resp.body)
        docs = data.get("response", {}).get("docs", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    results = []
    for doc in docs:
        artifact_id = doc.get("a", "")
        group_id = doc.get("g", "")
        if "aspose" not in artifact_id.lower():
            continue
        result = check_published({"group_id": group_id, "artifact_id": artifact_id}, fetch=fetch)
        if result.published and not result.ambiguous:
            results.append(result)
    return results

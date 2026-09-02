"""Tests for lib/publication_probe.py (readme-refresh-publication-state-hardening-2026-09-02).

The real registry adapters run against an injected `fetch` -- the only network boundary --
with response bodies shaped like the real PyPI JSON for aspose-3d-foss 26.1.0 (captured
2026-09-02 in reports/plan_state/readme-refresh-publication-state-hardening-2026-09-02/
evidence/investigation/pypi.aspose-3d-foss.json).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import publication_probe as pp  # noqa: E402
from package_registries import FetchResponse  # noqa: E402

REPO = "https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-Python.git"
RECORD_UNPUBLISHED = {
    "registry_type": "pypi", "candidate": {"name": "aspose-3d-foss"},
    "published": False, "record_verified_at": "2026-08-01",
}


def _pypi_body(*, version="26.1.0", home="https://github.com/aspose-3d/Aspose.3D-for-Python",
               license_text="", kinds=("bdist_wheel",)):
    files = [{"packagetype": k, "upload_time_iso_8601": "2026-08-29T04:13:26.858892Z"} for k in kinds]
    return json.dumps({
        "info": {"name": "aspose-3d-foss", "version": version, "author": "Aspose",
                 "requires_python": ">=3.7", "license": license_text, "home_page": home,
                 "project_urls": {"Homepage": home}, "summary": "Aspose.3D FOSS for Python"},
        "releases": {version: files}, "urls": files,
    }).encode()


def _fetch_with(responses: dict):
    calls = []

    def fetch(url, **_kw):
        calls.append(url)
        r = responses.get(url, "404")
        if r is None:
            return None
        if r == "404":
            return FetchResponse(404, b"")
        return FetchResponse(200, r)
    fetch.calls = calls
    return fetch


def test_live_published_pypi_overrides_a_stale_unpublished_record_and_reports_drift():
    fetch = _fetch_with({"https://pypi.org/pypi/aspose-3d-foss/json": _pypi_body()})
    r = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch, resolve_url=lambda u: None)
    assert r["source"] == "live_probe"
    assert r["effective_published"] is True and r["drift"] is True
    assert r["record"] == {"published": False, "verified_at": "2026-08-01"}
    live = r["live"]
    assert live["published"] is True and live["details_supported"] is True
    assert live["latest_version"] == "26.1.0" and live["released_at"].startswith("2026-08-29")
    assert live["artifact_kinds"] == ["bdist_wheel"] and live["requires_python"] == ">=3.7"
    assert live["repo_url_corroborated"] is False
    assert sorted(f["kind"] for f in r["metadata_findings"]) == [
        "no_license_metadata", "no_sdist", "project_url_not_this_repository",
    ]
    line = pp.format_publication_line(r)
    assert line.startswith("PUBLISHED aspose-3d-foss 26.1.0 on pypi (2026-08-29) [bdist_wheel]".join(["PUBLICATION: ", ""]))
    assert "DRIFT: data/package_registry.json says unpublished" in line
    assert "never README" in line


def test_live_404_confirms_unpublished_without_drift_and_without_metadata_findings():
    fetch = _fetch_with({})
    r = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch)
    assert r["source"] == "live_probe" and r["effective_published"] is False and r["drift"] is False
    assert r["live"]["published"] is False and r["metadata_findings"] == []
    assert pp.format_publication_line(r) == (
        "PUBLICATION: NOT PUBLISHED aspose-3d-foss on pypi -- live probe "
        "https://pypi.org/pypi/aspose-3d-foss/json (404)"
    )


def test_ambiguous_probe_falls_back_to_the_record_and_names_the_fallback():
    fetch = _fetch_with({"https://pypi.org/pypi/aspose-3d-foss/json": None})  # network down
    r = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch)
    assert r["effective_published"] is False and r["drift"] is False
    assert r["source"].startswith("package_registry.json (probe ambiguous: pypi-json-api")
    assert r["live"]["ambiguous"] is True and r["live"]["published"] is None
    assert "FROM RECORD ONLY" in pp.format_publication_line(r)
    # A published record with an ambiguous probe stays published -- a fallback never flips.
    r2 = pp.probe_publication({**RECORD_UNPUBLISHED, "published": True}, repo_url=REPO, fetch=fetch)
    assert r2["effective_published"] is True and r2["drift"] is False


def test_offline_flag_skips_the_network_entirely():
    fetch = _fetch_with({"https://pypi.org/pypi/aspose-3d-foss/json": _pypi_body()})
    r = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch, offline=True)
    assert fetch.calls == []
    assert r["source"] == "package_registry.json (offline)" and r["effective_published"] is False


def test_probe_only_ever_uses_the_declared_name_never_a_family_guess():
    # PyPI `aspose-3d` is the commercial product; a probe that guessed from the family would
    # "confirm" the wrong package. The only URL fetched is the declared candidate's.
    fetch = _fetch_with({
        "https://pypi.org/pypi/aspose-3d/json": _pypi_body(version="26.8.0"),
        "https://pypi.org/pypi/aspose-3d-foss/json": "404",
    })
    r = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch)
    assert fetch.calls == ["https://pypi.org/pypi/aspose-3d-foss/json"]
    assert r["effective_published"] is False
    r_none = pp.probe_publication({"registry_type": "pypi", "candidate": {}, "published": False}, fetch=fetch)
    assert r_none["source"].startswith("package_registry.json (no probe")


def test_renamed_repository_is_corroborated_through_its_redirect_not_flagged():
    # Real case (cells/python, 2026-09-02): PyPI project URLs name the repo's OLD name, which
    # GitHub 301-redirects to the current one. The probe follows GitHub URLs once, via the
    # injectable resolve_url boundary -- never a network call in this test.
    old_name = "https://github.com/aspose-3d-foss/old-name"
    fetch = _fetch_with({"https://pypi.org/pypi/aspose-3d-foss/json": _pypi_body(home=old_name, license_text="MIT", kinds=("sdist", "bdist_wheel"))})
    resolved = []

    def resolve_url(url):
        resolved.append(url)
        return "https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-Python" if url == old_name else None
    r = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch, resolve_url=resolve_url)
    assert resolved == [old_name]
    assert r["live"]["repo_url_corroborated"] is True
    assert r["live"]["repo_url_corroborated_via_redirect"].endswith("/Aspose.3D-FOSS-for-Python")
    assert r["metadata_findings"] == []
    # A redirect that lands somewhere else is still a finding.
    r2 = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch, resolve_url=lambda u: "https://github.com/other/place")
    assert [f["kind"] for f in r2["metadata_findings"]] == ["project_url_not_this_repository"]


def test_go_modules_identity_is_the_module_path():
    url = "https://proxy.golang.org/github.com/aspose-pdf-foss/aspose-pdf-foss-for-go/@v/list"
    fetch = _fetch_with({url: b"v1.0.0"})
    r = pp.probe_publication(
        {"registry_type": "go_modules", "candidate": {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
         "published": True}, repo_url="https://github.com/aspose-pdf-foss/aspose-pdf-foss-for-go", fetch=fetch,
    )
    assert r["name"] == "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"
    assert r["source"] == "live_probe" and r["effective_published"] is True


def test_corroborated_repo_url_and_full_metadata_yield_no_findings():
    good = _pypi_body(home="https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-Python",
                      license_text="MIT", kinds=("sdist", "bdist_wheel"))
    fetch = _fetch_with({"https://pypi.org/pypi/aspose-3d-foss/json": good})
    r = pp.probe_publication(RECORD_UNPUBLISHED, repo_url=REPO, fetch=fetch)
    assert r["live"]["repo_url_corroborated"] is True
    assert r["live"]["artifact_kinds"] == ["bdist_wheel", "sdist"]
    assert r["metadata_findings"] == []


def test_non_pypi_registries_get_the_boolean_without_fabricated_details():
    nuget_index = "https://api.nuget.org/v3-flatcontainer/aspose.words.foss/index.json"
    fetch = _fetch_with({nuget_index: json.dumps({"versions": ["26.2.0"]}).encode()})
    r = pp.probe_publication(
        {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"}, "published": False},
        repo_url="https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-NET", fetch=fetch,
    )
    assert r["source"] == "live_probe" and r["effective_published"] is True and r["drift"] is True
    assert r["live"]["details_supported"] is False and "latest_version" not in r["live"]
    assert r["metadata_findings"] == []  # no details -> no metadata claims
    assert "[artifacts unparsed]" in pp.format_publication_line(r)


def test_maven_probe_uses_maven_metadata_xml_for_the_declared_coordinates():
    url = "https://repo1.maven.org/maven2/com/aspose/aspose-cells-foss/maven-metadata.xml"
    fetch = _fetch_with({url: b"<metadata><versioning><latest>26.5.0</latest></versioning></metadata>"})
    r = pp.probe_publication(
        {"registry_type": "maven", "candidate": {"group_id": "com.aspose", "artifact_id": "aspose-cells-foss"},
         "published": True}, fetch=fetch,
    )
    assert fetch.calls == [url]
    assert r["name"] == "com.aspose:aspose-cells-foss"
    assert r["effective_published"] is True and r["drift"] is False and r["source"] == "live_probe"

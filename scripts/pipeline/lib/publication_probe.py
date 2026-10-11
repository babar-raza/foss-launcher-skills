"""publication_probe.py -- live package-publication fact for /readme-refresh (S-120).

Mission readme-refresh-publication-state-hardening-2026-09-02 (FINDINGS.md under
reports/plan_state/). Found live: 3d/python's `aspose-3d-foss` 26.1.0 had been on PyPI since
2026-08-29 while `data/package_registry.json` still said `published: false` (backfilled
2026-08-01) and the readme-refresh skill read nothing else -- so a regenerated README would keep
saying "has not yet been published", offer no PyPI badges, and verify its examples against an
editable clone instead of the real published artifact. The daily package_publish_watch HAD
detected it (proposal issues #67/#70/#72/#74, all open) -- the system knew, the skill did not.

This module makes publication state a live-probed, evidenced FACT with the checked-in record
as a named fallback:

    probe_publication(install_info, repo_url=..., fetch=...) -> {
        "registry_type", "name", "probed_at",
        "record":   {"published": bool, "verified_at": str|None},      # data/package_registry.json
        "live":     {"published": bool|None, "ambiguous": bool, "evidence_url", "method",
                     "latest_version", "released_at", "artifact_kinds", "requires_python",
                     "license", "project_urls", "repo_url_corroborated": bool|None,
                     "details_supported": bool},
        "effective_published": bool,        # live when unambiguous, else the record
        "source": "live_probe" | "package_registry.json (probe ambiguous: ...)" | "package_registry.json (offline)",
        "drift": bool,                      # live unambiguous AND live != record
        "metadata_findings": [{"kind", "detail"}],   # registry-metadata defects -> upstream issues
    }

Rules that are load-bearing, not style:
- NEVER guess a package name from the family. Only the manifest-declared `candidate.name`
  (or Maven group/artifact) from install_info is probed. Real trap: PyPI `aspose-3d` is the
  commercial Aspose.3D for Python via .NET (49 releases); `aspose-3d-foss` is the FOSS one.
- An ambiguous probe (network down, non-200/404 status, unparsable body) never flips anything:
  `effective_published` falls back to the record and `source` says so, so every downstream
  consumer can tell a fact from a fallback.
- Details (version/date/artifacts/metadata) are parsed for PyPI from the same JSON the identity
  check already fetched; other registries get the boolean from their adapter and
  `details_supported: False` -- an honest "not parsed", never a fabricated version.
- This module never writes `data/package_registry.json`: the watcher's human-approved
  `apply_proposal` stays the only write path; S-120 surfaces `drift` for the operator.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from package_registries import CheckResult, default_fetch
from package_registries import cargo as _cargo
from package_registries import go as _go
from package_registries import npm as _npm
from package_registries import nuget as _nuget
from package_registries import pypi as _pypi

_ADAPTERS: dict[str, Callable[..., CheckResult]] = {
    "pypi": _pypi.check_published,
    "nuget": _nuget.check_published,
    "npm": _npm.check_published,
    "cargo": _cargo.check_published,
    "go_modules": _go.check_published,
}

_MAVEN_METADATA_URL = "https://repo1.maven.org/maven2/{group_path}/{artifact_id}/maven-metadata.xml"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_resolve_url(url: str, *, timeout: float = 10.0) -> "str | None":
    """Final URL after redirects (HEAD, same User-Agent as default_fetch) -- so a registry
    project URL that names a repository's OLD name (GitHub keeps a 301 after a rename; real case:
    cells/python's PyPI record points at `aspose-cells-foss/aspose-cells-python`, which redirects
    to `Aspose.Cells-FOSS-for-Python`) still corroborates. None on any failure."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "aspose-org-package-registry-watch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None


def _repo_fragment(repo_url: "str | None") -> str:
    """`https://github.com/org/Repo.git` -> `org/repo` (lowercase, no .git) -- the fragment a
    registry's project URL must contain to corroborate that the package is THIS repository."""
    if not repo_url:
        return ""
    frag = repo_url.strip().rstrip("/")
    if frag.endswith(".git"):
        frag = frag[:-4]
    parts = frag.split("github.com/")
    return parts[1].lower() if len(parts) == 2 else ""


def _maven_check(candidate: dict, *, fetch) -> CheckResult:
    group_id, artifact_id = candidate.get("group_id"), candidate.get("artifact_id")
    url = _MAVEN_METADATA_URL.format(group_path=str(group_id or "").replace(".", "/"), artifact_id=artifact_id)
    if not group_id or not artifact_id:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="maven-metadata-xml")
    resp = fetch(url)
    if resp is None:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="maven-metadata-xml")
    if resp.status_code == 404:
        return CheckResult(published=False, ambiguous=False, evidence_url=url, method="maven-metadata-xml")
    if resp.status_code != 200:
        return CheckResult(published=False, ambiguous=True, evidence_url=url, method="maven-metadata-xml")
    return CheckResult(published=True, ambiguous=False, evidence_url=url, method="maven-metadata-xml",
                       candidate_name=f"{group_id}:{artifact_id}")


def _pypi_details(name: str, *, fetch) -> dict:
    """Second read of the same public JSON the adapter used (kept separate so the adapter's
    contract stays untouched). Returns {} when anything is missing -- never invents a version."""
    resp = fetch(f"https://pypi.org/pypi/{name}/json")
    if resp is None or resp.status_code != 200:
        return {}
    try:
        data = json.loads(resp.body)
    except (json.JSONDecodeError, ValueError):
        return {}
    info = data.get("info") or {}
    version = info.get("version")
    files = (data.get("releases") or {}).get(version) or data.get("urls") or []
    kinds = sorted({f.get("packagetype") for f in files if f.get("packagetype")})
    uploads = sorted(f.get("upload_time_iso_8601") or f.get("upload_time") or "" for f in files)
    license_text = (info.get("license") or "").strip() or None
    license_expr = (info.get("license_expression") or "").strip() or None
    return {
        "latest_version": version,
        "released_at": uploads[-1] if uploads and uploads[-1] else None,
        "artifact_kinds": kinds,
        "requires_python": info.get("requires_python") or None,
        "license": license_expr or license_text,
        "project_urls": dict(info.get("project_urls") or {}),
        "home_page": info.get("home_page") or None,
        "summary": info.get("summary") or None,
        "release_count": len(data.get("releases") or {}),
    }


def _metadata_findings(registry_type: str, live: dict, repo_url: "str | None") -> list[dict]:
    """Registry-metadata defects a reader of the package page would hit. These are UPSTREAM
    ISSUES (the composition contract's transient-defect rule) -- never README content."""
    findings: list[dict] = []
    if not live.get("published") or not live.get("details_supported"):
        return findings
    urls = {**(live.get("project_urls") or {})}
    if live.get("home_page"):
        urls.setdefault("home_page", live["home_page"])
    if _repo_fragment(repo_url) and urls and live.get("repo_url_corroborated") is False:
        findings.append({
            "kind": "project_url_not_this_repository",
            "detail": f"registry project URLs {sorted(set(urls.values()))} do not point at {repo_url} "
                      f"(redirects followed)",
        })
    if not urls:
        findings.append({"kind": "no_project_url", "detail": "the registry record carries no project/homepage URL"})
    if not live.get("license"):
        findings.append({"kind": "no_license_metadata", "detail": "the registry record carries no license metadata"})
    if registry_type == "pypi" and live.get("artifact_kinds") and "sdist" not in live["artifact_kinds"]:
        findings.append({
            "kind": "no_sdist",
            "detail": f"latest release ships {live['artifact_kinds']} only -- no source distribution",
        })
    return findings


def probe_publication(install_info: dict, *, repo_url: "str | None" = None, fetch=None,
                      resolve_url=None, offline: bool = False) -> dict:
    fetch = fetch or default_fetch
    resolve_url = resolve_url or default_resolve_url
    registry_type = (install_info or {}).get("registry_type")
    candidate = (install_info or {}).get("candidate") or {}
    name = candidate.get("name") or candidate.get("module_path") or (
        f"{candidate.get('group_id')}:{candidate.get('artifact_id')}"
        if candidate.get("group_id") and candidate.get("artifact_id") else None
    )
    record = {
        "published": bool((install_info or {}).get("published", False)),
        "verified_at": (install_info or {}).get("record_verified_at"),
    }
    base = {
        "registry_type": registry_type, "name": name, "probed_at": _utc(), "record": record,
        "live": {"published": None, "ambiguous": True, "evidence_url": None, "method": None,
                 "details_supported": False},
        "effective_published": record["published"], "drift": False, "metadata_findings": [],
    }
    if offline:
        base["source"] = "package_registry.json (offline)"
        return base
    if not registry_type or not name or (registry_type not in _ADAPTERS and registry_type != "maven"):
        base["source"] = "package_registry.json (no probe: unknown registry or no declared package identity)"
        return base

    check = _maven_check(candidate, fetch=fetch) if registry_type == "maven" else _ADAPTERS[registry_type](candidate, fetch=fetch)
    live: dict[str, Any] = {
        "published": None if check.ambiguous else bool(check.published),
        "ambiguous": bool(check.ambiguous),
        "evidence_url": check.evidence_url, "method": check.method,
        "verified_owner": check.verified_owner, "project_url": check.project_url,
        "details_supported": False,
    }
    if not check.ambiguous and check.published and registry_type == "pypi":
        details = _pypi_details(name, fetch=fetch)
        if details:
            live.update(details)
            live["details_supported"] = True
    frag = _repo_fragment(repo_url)
    urls = [u for u in [live.get("project_url"), live.get("home_page")] + list((live.get("project_urls") or {}).values()) if u]
    corroborated: "bool | None" = None
    if frag and urls:
        corroborated = any(frag in str(u).lower() for u in urls)
        if not corroborated:
            # A renamed repository keeps a 301 from its old name; follow GitHub URLs once
            # before calling the registry record wrong (cells/python, live 2026-09-02).
            for u in sorted({str(u) for u in urls if "github.com/" in str(u).lower()}):
                final = resolve_url(u)
                if final and frag in final.lower():
                    corroborated = True
                    live["repo_url_corroborated_via_redirect"] = final
                    break
    live["repo_url_corroborated"] = corroborated

    base["live"] = live
    if check.ambiguous:
        base["source"] = f"package_registry.json (probe ambiguous: {check.method} {check.evidence_url})"
        return base
    base["effective_published"] = bool(check.published)
    base["source"] = "live_probe"
    base["drift"] = bool(check.published) != record["published"]
    base["metadata_findings"] = _metadata_findings(registry_type, live, repo_url)
    return base


def format_publication_line(publication: dict) -> str:
    """One human line for `plan` stdout / the composing agent -- the fact, its source, and any
    drift, so a stale checked-in flag can never again be mistaken for the current state."""
    if not publication:
        return "PUBLICATION: unknown (no probe result)"
    live = publication.get("live") or {}
    name = publication.get("name") or "?"
    rtype = publication.get("registry_type") or "?"
    if publication.get("source") == "live_probe":
        if publication.get("effective_published"):
            ver = live.get("latest_version")
            when = (live.get("released_at") or "")[:10]
            kinds = ",".join(live.get("artifact_kinds") or []) or "artifacts unparsed"
            head = f"PUBLISHED {name}{' ' + ver if ver else ''} on {rtype}{' (' + when + ')' if when else ''} [{kinds}] -- live probe {live.get('evidence_url')}"
        else:
            head = f"NOT PUBLISHED {name} on {rtype} -- live probe {live.get('evidence_url')} (404)"
    else:
        head = (f"{'PUBLISHED' if publication.get('effective_published') else 'NOT PUBLISHED'} {name} on {rtype} "
                f"-- FROM RECORD ONLY: {publication.get('source')}")
    tail = ""
    if publication.get("drift"):
        rec = "published" if (publication.get("record") or {}).get("published") else "unpublished"
        tail += (f"; DRIFT: data/package_registry.json says {rec} -- apply the package_publish_watch "
                 f"proposal (apply_proposal) after independent verification; S-120 never writes it")
    mf = publication.get("metadata_findings") or []
    if mf:
        tail += f"; registry metadata defects ({len(mf)}): " + ", ".join(f["kind"] for f in mf) + " -> upstream-issues.md, never README"
    return "PUBLICATION: " + head + tail

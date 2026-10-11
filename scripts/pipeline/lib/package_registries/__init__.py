"""package_registries — per-registry publish-verification adapters.

Mission MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-04. Each sibling module
(pypi.py, nuget.py, npm.py, go.py) exposes one function:

    check_published(candidate: dict, *, fetch=None) -> CheckResult

`candidate` is the registry-appropriate coordinate shape from a
data/package_registry.json entry (see data/schemas/package-registry-schema.json).
`fetch` is an injected `(url: str) -> FetchResponse | None` callable (None on
connection error/timeout) -- dependency injection instead of monkeypatching
`urllib`/`requests` (a T3 IO-boundary mock under AGENTS.md 16) so tests stay
fixture-based with zero live network calls and zero monkeypatch-lint concerns.

A CheckResult never asserts more than one real HTTP round trip determined --
callers must not flip `data/package_registry.json`'s `verification.published`
directly off one CheckResult. Use `apply_debounce()` below, which requires 2
consecutive agreeing "published" results (the mission's documented rerun-
consistency requirement: a single transient API error or ambiguous response
must never flip live-published state).
"""

from __future__ import annotations

from typing import NamedTuple


class FetchResponse(NamedTuple):
    status_code: int
    body: bytes


class CheckResult(NamedTuple):
    published: bool
    ambiguous: bool  # True if the check could not conclusively determine state (network error, unexpected status)
    evidence_url: str
    method: str
    verified_owner: str | None = None
    project_url: str | None = None  # project/homepage/repository URL from the registry's own API response
    candidate_name: str | None = None  # the actual name this result was checked against (set by search())
    version: str | None = None  # live latest version observed this check (Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION,
    # Phase 1) -- distinct from data/package_registry.json's candidate.version, which is the last
    # *recorded* value; callers compare the two to detect drift (mirrors publish_watcher.py's
    # existing Maven-only check_published_families_for_new_version() pattern, generalized here).
    # None when the registry has nothing to report (404/ambiguous) or the check didn't ask for it.
    yanked: bool = False  # True when the reported `version` is specifically marked yanked/withdrawn by
    # the registry (currently only crates.io populates this) -- distinct from published=False: a
    # yanked version is discouraged, not gone, and must not be treated as a removal signal.


REQUIRED_CONSECUTIVE_CHECKS = 2


_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_FETCH_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 1.0


def _classify_fetch_exception(exc: BaseException) -> None:
    """Map a transport-level fault to the adapters' 'ambiguous' signal (None).

    Beyond the OSError family (timeouts, DNS, refused, TLS), a malformed or
    truncated HTTP exchange raises http.client.HTTPException subclasses
    (IncompleteRead, BadStatusLine, LineTooLong, ...) which are NOT OSErrors.
    Before this they escaped default_fetch and aborted the whole watcher run, so
    one bad response from one registry hid every other package's result. Anything
    that is not a network fault (a bug in the caller) still propagates."""
    import http.client
    import urllib.error

    if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException)):
        return None
    raise exc


def _fetch_once(url: str, *, timeout: float = 10.0) -> FetchResponse | None:
    """One unauthenticated GET via stdlib urllib (no `requests` dependency --
    confirmed not installed in this repo's venv). None on any transport fault."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "aspose-org-package-registry-watch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return FetchResponse(status_code=resp.status, body=resp.read())
    except urllib.error.HTTPError as exc:
        return FetchResponse(status_code=exc.code, body=b"")
    except Exception as exc:  # noqa: BLE001 -- narrowed by _classify_fetch_exception, which re-raises non-network faults
        return _classify_fetch_exception(exc)


def _fetch_with_retry(url, fetch_once, *, attempts: int = DEFAULT_FETCH_ATTEMPTS, sleep=None) -> FetchResponse | None:
    """Retry policy over a single-attempt fetch. Retries ONLY a transport fault
    (None) or a transient status (429/5xx); a definitive answer -- 200, 404, 410,
    any other 4xx -- is returned immediately, since retrying cannot change a
    correct result. After the last attempt the last outcome is returned as-is
    (None or the transient response): the caller's adapter still maps it to
    `ambiguous`, so retrying can only turn a false 'ambiguous' into the truth,
    never fabricate a success. Measured motivation: api.nuget.org stalls at TCP
    connect on ~2-3 of 50 calls; without a retry each stall delays the
    2-consecutive-check debounce by a full scheduled day."""
    import time

    sleep = sleep if sleep is not None else time.sleep
    resp = None
    for attempt in range(max(1, attempts)):
        resp = fetch_once(url)
        if resp is not None and resp.status_code not in _TRANSIENT_STATUS_CODES:
            return resp
        if attempt + 1 < max(1, attempts):
            sleep(_RETRY_BACKOFF_SECONDS)
    return resp


def default_fetch(url: str, *, timeout: float = 10.0) -> FetchResponse | None:
    """Default `fetch` implementation: single-attempt GET wrapped in the bounded
    retry policy above. Returns None on any transport fault rather than raising,
    so adapters can treat that uniformly as `ambiguous` alongside unexpected HTTP
    statuses."""
    return _fetch_with_retry(url, lambda u: _fetch_once(u, timeout=timeout))


def platform_compatible(registry_type: str, platform: str, name: str) -> bool:
    """Whether a registry package `name` can belong to `platform`.

    NuGet is the only registry shared by two platforms (net and cpp), so a
    family-level search ("aspose slides") returns both indiscriminately. Real
    cases: email/cpp's search fell back to the .NET `Aspose.Email.Foss` (contains
    "foss", so it passed corroboration) purely because no cpp package existed yet;
    the mirror hazard is a net entry adopting `Aspose.<Fam>.Cpp.FOSS`. Every real
    cpp NuGet ID observed embeds "Cpp" (Aspose.Cells.Cpp.FOSS,
    Aspose.Slides.Cpp.FOSS). Single definition, used by registry_backfill AND the
    watcher's identity re-resolution, so the two can never disagree."""
    if registry_type != "nuget":
        return True
    has_cpp_marker = "cpp" in name.lower()
    return has_cpp_marker if platform == "cpp" else not has_cpp_marker


def is_corroborated_match(candidate_name: str, project_url: "str | None", expected_repo_fragment: str) -> bool:
    """Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE identity-verification rule
    (user-mandated): a live registry hit only confirms the FOSS product if the
    candidate name contains "foss" in some form, OR corroborating metadata
    (the registry's own project/homepage URL) exactly references the product's
    known FOSS GitHub org/repo.

    Real case this guards against in both directions:
      - False negative: PyPI's `aspose-note` has no "foss" in its name but IS the
        genuine FOSS package -- its project_urls point exactly to
        github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python. A purely
        mechanical "reject if no foss substring" rule would wrongly discard this.
      - False positive: PyPI's `aspose-page` (no "foss") is a genuinely unrelated
        *commercial* package with no FOSS connection at all -- accepting any
        name match without corroboration would have produced this exact
        collision (found 2026-08-01 during the full-repo audit).

    `expected_repo_fragment` is the identifying substring of the product's real
    FOSS GitHub org/repo (e.g. "aspose-note-foss" or "Aspose.Note-FOSS") -- callers
    supply this from the family's known repo_url, never guessed here.
    """
    if "foss" in candidate_name.lower():
        return True
    # Guard added Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2:
    # an empty expected_repo_fragment is not a real fragment to match against --
    # without this guard, `"" in project_url.lower()` is always True in Python
    # (an empty string is a substring of everything), which would make ANY
    # truthy project_url accepted as "corroborated" the moment a caller could not
    # resolve a real expected fragment (e.g. a family missing from
    # data/products.json) -- silently defeating the entire safeguard this
    # function exists to provide.
    if project_url and expected_repo_fragment and expected_repo_fragment.lower() in project_url.lower():
        return True
    return False


def apply_debounce(current_consecutive: int, result: CheckResult) -> tuple[int, bool]:
    """Given the current consecutive-agreeing-checks counter and a new
    CheckResult, return (new_counter, should_flip_to_published).

    Rules:
      - An ambiguous result never advances the counter and never flips state
        (fail closed -- a false "published" is worse than staying "not yet
        published" one cycle longer).
      - A published=False result resets the counter to 0 (no premature credit
        toward a future flip if the package genuinely isn't there yet).
      - A published=True result increments the counter; once it reaches
        REQUIRED_CONSECUTIVE_CHECKS, the caller should flip state to
        published and may reset the counter.
    """
    if result.ambiguous:
        return current_consecutive, False
    if not result.published:
        return 0, False
    new_counter = current_consecutive + 1
    return new_counter, new_counter >= REQUIRED_CONSECUTIVE_CHECKS

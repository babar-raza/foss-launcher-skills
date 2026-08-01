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


REQUIRED_CONSECUTIVE_CHECKS = 2


def default_fetch(url: str, *, timeout: float = 10.0) -> FetchResponse | None:
    """Default `fetch` implementation: a plain unauthenticated GET via stdlib
    urllib (no `requests` dependency -- confirmed not installed in this repo's
    venv this session). Returns None on any connection-level failure
    (timeout, DNS, refused) rather than raising, so adapters can treat that
    uniformly as `ambiguous` alongside unexpected HTTP statuses.
    """
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "aspose-org-package-registry-watch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return FetchResponse(status_code=resp.status, body=resp.read())
    except urllib.error.HTTPError as exc:
        return FetchResponse(status_code=exc.code, body=b"")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


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
    if project_url and expected_repo_fragment.lower() in project_url.lower():
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

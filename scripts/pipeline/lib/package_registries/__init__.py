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

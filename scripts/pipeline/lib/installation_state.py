"""installation_state.py — the installation-state state machine (Mission
MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2, plan section F).

Two pure functions, deliberately with no I/O and no side effects:

  classify_entry(entry) -> one of the STATES below
  desired_source(state) -> "package_manager" | "github" | "unchanged"

`classify_entry()` derives state from a data/package_registry.json entry's
own fields -- it never reads a cache of the state itself (the plan's own
Data-model section explicitly rejected persisting `reconciliation_state` as
a cached field in that Hugo-consumed file; this module is what "compute it
on demand" means in practice).

`desired_source()` is Stage D from the plan's target architecture: the single
choke point every later stage (page inventory, change proposal) reads to
decide whether a page should show package-manager or GitHub install
instructions -- so that decision is made in exactly one place, not
re-derived differently by each consumer.
"""

from __future__ import annotations

from typing import Any

UNKNOWN = "UNKNOWN"
GITHUB_ONLY = "GITHUB_ONLY"
CANDIDATE_UNCORROBORATED = "CANDIDATE_UNCORROBORATED"
PACKAGE_MANAGER_VERIFIED = "PACKAGE_MANAGER_VERIFIED"
DRIFT_SUSPECTED = "DRIFT_SUSPECTED"
IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
RETIRED_EXCLUDED = "RETIRED_EXCLUDED"

STATES = frozenset({
    UNKNOWN, GITHUB_ONLY, CANDIDATE_UNCORROBORATED, PACKAGE_MANAGER_VERIFIED,
    DRIFT_SUSPECTED, IDENTITY_CONFLICT, RETIRED_EXCLUDED,
})

SOURCE_PACKAGE_MANAGER = "package_manager"
SOURCE_GITHUB = "github"
SOURCE_UNCHANGED = "unchanged"


def classify_entry(entry: "dict[str, Any] | None", *, drift_suspected: bool = False) -> str:
    """Classify a single data/package_registry.json entry into its current
    installation state, per plan section F.

    `drift_suspected` is passed in by the caller (the watcher already tracks
    `consecutive_checks_absent` internally and knows when that threshold is
    reached) rather than recomputed here -- this function has no access to
    debounce counters' meaning, only to the entry's own recorded fields, and
    must not guess at a threshold value that belongs to the watcher's own
    debounce module.

    RETIRED_EXCLUDED is intentionally never derived here (this module never
    reads data/registry_exclusions.json -- callers that already know an entry
    is excluded should not call this function for it at all; classify_entry's
    job is the states derivable from the entry's own recorded shape).
    """
    if not entry:
        return UNKNOWN

    conflict = entry.get("conflict")
    if conflict:
        return IDENTITY_CONFLICT

    verification = entry.get("verification") or {}
    published = verification.get("published")

    if published:
        return DRIFT_SUSPECTED if drift_suspected else PACKAGE_MANAGER_VERIFIED

    candidate = entry.get("candidate")
    if not candidate:
        return UNKNOWN

    # CANDIDATE_UNCORROBORATED is intentionally never produced here: whether a
    # given check found an uncorroborated hit is transient watcher-run output
    # (see package_publish_watch.check_unpublished_entries's own uncorroborated
    # findings list), not a fact persisted in data/package_registry.json --
    # and desired_source() treats it identically to GITHUB_ONLY regardless, so
    # nothing downstream needs classify_entry() to distinguish the two from the
    # persisted entry alone.
    return GITHUB_ONLY


def desired_source(state: str) -> str:
    """Stage D (plan section C/F): the single, pure mapping from state to
    desired installation-instruction source. Every later stage (page
    inventory, change proposal) reads this instead of re-deriving its own
    notion of "should this page show package-manager or GitHub content"."""
    if state not in STATES:
        raise ValueError(f"desired_source: unrecognized state {state!r}")
    if state == PACKAGE_MANAGER_VERIFIED:
        return SOURCE_PACKAGE_MANAGER
    if state in (GITHUB_ONLY, CANDIDATE_UNCORROBORATED):
        return SOURCE_GITHUB
    # DRIFT_SUSPECTED, IDENTITY_CONFLICT, RETIRED_EXCLUDED, UNKNOWN: never
    # auto-change rendered content pending human resolution -- matches the
    # existing, already-justified "never auto-revert published back to false"
    # invariant (plan section F) and the requirement not to destroy a
    # known-good install method on a single unreliable observation.
    return SOURCE_UNCHANGED

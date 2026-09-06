"""SEO-EXECUTION-INVARIANTS (Contract J): the exact, named 14-invariant
registry that must hold before this mission's pipeline is allowed to write
anything for a given (family, mechanism, run) -- design authority is
`check-keywords-this-data-curious-feather.md` §4k (line 2218), which is the
literal, numbered source for the 14 checks below; do not re-derive or
re-number them independently of that list.

``check_invariants(context)`` is a pure decision function: it never reaches
out to any subsystem itself. Every invariant's truth value is a field on
``context`` (an ``InvariantContext``), supplied by the caller. This keeps
the 14-invariant policy engine itself fully unit-testable (one negative
test per invariant, forcing exactly one field to its failing value with
every other field held at a realistic passing baseline) without needing to
mock seven different subsystems' internals.

A context field left ``None`` means "not evaluated at this call site" --
this is a real, honest signal, not "assumed to pass": a caller that hasn't
computed a particular invariant's input yet (for example, an invariant
that is inherently per-candidate rather than per-run, evaluated at a call
site that only runs once per batch) reports that invariant as ``SKIPPED``,
not ``PASS``. ``InvariantReport.passed`` is True only when every
NON-skipped invariant passed; a report can be "passed" while several
invariants remain SKIPPED, and callers that need a stronger guarantee
should check ``report.skipped`` themselves.

Wired for real (this card) into ``apply.py``'s and ``recommend.py``'s own
top-level entry points:
- invariant 13 (recommendation-memory store integrity) -- new, explicit
  code in BOTH `apply.py` (Governance gate 0.5) and `recommend.py`
  (`run_recommendations()`'s own top).
- invariant 14 (no unresolved suspension) -- new, explicit code in
  `recommend.py` only (per-family: an opportunity for a SUSPENDED family
  is skipped, not the whole run refused), using `no_unresolved_suspension()`
  below. `apply.py` gets this invariant for free as a side effect of its
  own PRE-EXISTING per-patch autonomy-eligibility gate (a SUSPENDED family
  is never `AUTONOMOUSLY_ELIGIBLE`) -- no new code was added there for
  invariant 14 specifically, since `recommend.py` (which had ZERO
  autonomy-state awareness of any kind before this card) was the real gap:
  without this, a SUSPENDED family's pages kept generating fresh LLM
  proposals and populating recommendation-memory, directly against
  Contract J's stop-the-line intent, even though `apply.py` would
  correctly refuse to ever WRITE them.

Invariants 9-11 (change budget, cross-mechanism budget, autonomy
eligibility) are already enforced by `apply.py`'s own pre-existing,
independently-reviewed gates (Contract G's `_preflight_change_budget()`,
Contract I's per-patch autonomy check) -- this card deliberately does NOT
duplicate or refactor that already-tested logic into a second, parallel
code path, which would be a real regression risk for no safety gain.
Invariant 12 (workflow-drift freshness) is disclosed, not wired: today's
`check_workflow_drift.check_workflow_drift()` makes a live `gh api` network
call on every invocation with no persisted "last known state" to consult
instead, so wiring it into every apply.py/recommend.py run would add a new
hard network dependency to two production entry points that have never
had one -- filed as `SEO-EXECUTION-INVARIANTS-DRIFT-CHECK-WIRING-RESOLVER-1`
rather than added unreviewed. Invariants 1-8 are per-candidate checks whose
real data lives in composer modules (`title_clause_composer.py`,
`description_composer.py`, `metadata_consistency.py`) that are outside
this card's own `allowed_paths` -- correctly implemented and covered by
their own negative test here, wired into production by whichever future
card owns that composer's per-candidate loop.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

try:
    from seo.pipeline import autonomy_state, recommendation_memory
except ImportError:
    from pipeline import autonomy_state, recommendation_memory

log = logging.getLogger(__name__)


@dataclass
class InvariantContext:
    """One optional field per named Contract J invariant. `None` means
    "not evaluated here" (SKIPPED), never a silent pass."""

    # 1-8: per-candidate invariants (real data lives in composer modules).
    schema_classification_ok: "bool | None" = None
    keyword_provenance_present: "bool | None" = None
    page_mapping_unambiguous: "bool | None" = None
    page_intent_resolvable: "bool | None" = None
    grounding_evidence_nonempty: "bool | None" = None
    intent_platform_matches_structural_platform: "bool | None" = None
    naturalness_status: "str | None" = None  # "pass" | "warn" | "fail"
    naturalness_warn_cleared: "bool | None" = None  # paired with the above (mirrors 8)
    metadata_consistency_open_warn: "bool | None" = None
    requires_human_review: "bool | None" = None  # paired with the above

    # 9-14: run-scoped invariants.
    change_budget_ok: "bool | None" = None
    cross_mechanism_budget_ok: "bool | None" = None
    dry_run: bool = False
    autonomy_eligible: "bool | None" = None
    workflow_drift_in_sync: "bool | None" = None
    recommendation_memory_ok: "bool | None" = None
    no_unresolved_suspension: "bool | None" = None


@dataclass
class InvariantResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIPPED"
    detail: str


@dataclass
class InvariantReport:
    family: "str | None"
    mechanism: "str | None"
    results: "list[InvariantResult]" = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.status != "FAIL" for r in self.results)

    @property
    def skipped(self) -> "list[str]":
        return [r.name for r in self.results if r.status == "SKIPPED"]

    @property
    def failed(self) -> "list[InvariantResult]":
        return [r for r in self.results if r.status == "FAIL"]


def _result(name: str, value: "bool | None", pass_detail: str, fail_detail: str) -> InvariantResult:
    if value is None:
        return InvariantResult(name, "SKIPPED", "not evaluated at this call site")
    return InvariantResult(name, "PASS" if value else "FAIL", pass_detail if value else fail_detail)


def check_invariants(context: InvariantContext, *, family: "str | None" = None,
                      mechanism: "str | None" = None) -> InvariantReport:
    """Evaluate the exact, numbered 14 Contract J invariants against
    `context`. Never raises -- an invariant whose context field is missing
    is SKIPPED, not assumed to pass or fail."""
    results: "list[InvariantResult]" = [
        _result(
            "1_schema_classification_succeeds", context.schema_classification_ok,
            "target file classified successfully", "target file failed schema classification",
        ),
        _result(
            "2_keyword_provenance_present", context.keyword_provenance_present,
            "keyword_source marker present", "keyword_source marker missing",
        ),
        _result(
            "3_page_mapping_unambiguous", context.page_mapping_unambiguous,
            "map_url.py resolved exactly one content path", "page mapping ambiguous or unresolved",
        ),
        _result(
            "4_page_intent_resolvable", context.page_intent_resolvable,
            "family/platform known", "family and/or platform unknown",
        ),
        _result(
            "5_grounding_evidence_nonempty", context.grounding_evidence_nonempty,
            "claims/apis/formats/gsc_query grounding present", "no grounding evidence for this candidate",
        ),
        _result(
            "6_intent_platform_matches_page_structural_platform",
            context.intent_platform_matches_structural_platform,
            "intent platform matches the page's own structural platform",
            "intent platform mismatches the page's own structural platform (Finding #84)",
        ),
        _naturalness_result(context.naturalness_status, context.naturalness_warn_cleared),
        _metadata_consistency_result(context.metadata_consistency_open_warn, context.requires_human_review),
        _result(
            "9_change_budget_not_exceeded", context.change_budget_ok,
            "this run's own mechanism budget not exceeded", "this run's own mechanism budget exceeded",
        ),
        _result(
            "10_cross_mechanism_change_budget_not_exceeded", context.cross_mechanism_budget_ok,
            "cross-mechanism weekly budget not exceeded", "cross-mechanism weekly budget exceeded (Finding #80)",
        ),
        _autonomy_result(context.dry_run, context.autonomy_eligible),
        _result(
            "12_workflow_drift_state_in_sync_and_fresh", context.workflow_drift_in_sync,
            "workflow-YAML drift state is IN_SYNC", "workflow-YAML drift state is not IN_SYNC (or stale/unknown)",
        ),
        _result(
            "13_recommendation_memory_readable_and_schema_matched", context.recommendation_memory_ok,
            "recommendation-memory store is readable and schema-version-matched",
            "recommendation-memory store is unreadable or schema-version-mismatched",
        ),
        _result(
            "14_no_unresolved_suspension_for_family_mechanism", context.no_unresolved_suspension,
            "no unresolved SUSPENDED/rollback-candidate state for this (family, mechanism)",
            "an unresolved SUSPENDED/rollback-candidate state exists for this (family, mechanism)",
        ),
    ]
    return InvariantReport(family=family, mechanism=mechanism, results=results)


def _naturalness_result(status: "str | None", warn_cleared: "bool | None") -> InvariantResult:
    """Design text (§4k #7): 'PASS or WARN-with-clearance, never FAIL' --
    a bare, uncleared WARN is NOT sufficient, mirroring invariant 8's own
    open-warn-needs-review pairing and matching the one real production
    caller of this exact pattern today, title_clause_composer.py, which
    treats an uncleared WARN the same as FAIL (no clearance queue exists
    for it to route to)."""
    name = "7_naturalness_not_fail"
    if status is None:
        return InvariantResult(name, "SKIPPED", "not evaluated at this call site")
    if status == "fail":
        return InvariantResult(name, "FAIL", "naturalness evaluator returned FAIL")
    if status == "pass":
        return InvariantResult(name, "PASS", "naturalness evaluator returned PASS")
    if status == "warn":
        if warn_cleared:
            return InvariantResult(name, "PASS", "naturalness evaluator returned WARN, with clearance")
        return InvariantResult(
            name, "FAIL",
            "naturalness evaluator returned WARN without clearance -- an uncleared WARN "
            "is not sufficient (Finding #79)",
        )
    return InvariantResult(name, "FAIL", f"unrecognized naturalness status {status!r}")


def _metadata_consistency_result(open_warn: "bool | None", requires_human_review: "bool | None") -> InvariantResult:
    name = "8_no_open_metadata_consistency_warn_without_review"
    if open_warn is None:
        return InvariantResult(name, "SKIPPED", "not evaluated at this call site")
    if not open_warn:
        return InvariantResult(name, "PASS", "no open Contract E WARN")
    if requires_human_review:
        return InvariantResult(name, "PASS", "open Contract E WARN, but requires_human_review is already True")
    return InvariantResult(
        name, "FAIL",
        "open Contract E WARN with requires_human_review not True (Finding #79)",
    )


def recommendation_memory_is_ok() -> bool:
    """Real data source for invariant 13: the store is readable (never
    raises even on a corrupt file -- load_memory() itself fails open to an
    empty, valid shape) and its schema_version matches this module's own
    known-supported version. Never raises."""
    try:
        state = recommendation_memory.load_memory()
        return state.get("schema_version") == recommendation_memory.SCHEMA_VERSION
    except Exception:
        log.warning("execution_invariants.py: recommendation_memory_is_ok() failed", exc_info=True)
        return False


def no_unresolved_suspension(families: "list[str]", mechanism: str) -> bool:
    """Real data source for invariant 14: none of `families` is currently
    SUSPENDED for `mechanism`. Read-only -- never mutates autonomy state.
    Fails closed (returns False, i.e. "an unresolved suspension exists")
    on any internal error, since silently treating an unreadable autonomy
    state as "nothing suspended" would be the unsafe default for a
    stop-the-line check."""
    try:
        state = autonomy_state.load_state()
        for family in families:
            if autonomy_state.get_status(family, mechanism, state) == autonomy_state.STATUS_SUSPENDED:
                return False
        return True
    except Exception:
        log.warning("execution_invariants.py: no_unresolved_suspension() failed", exc_info=True)
        return False


def _autonomy_result(dry_run: bool, autonomy_eligible: "bool | None") -> InvariantResult:
    name = "11_autonomy_state_eligible_or_dry_run"
    if dry_run:
        return InvariantResult(name, "PASS", "action is apply.py --dry-run")
    if autonomy_eligible is None:
        return InvariantResult(name, "SKIPPED", "not evaluated at this call site")
    if autonomy_eligible:
        return InvariantResult(name, "PASS", "autonomy state is AUTONOMOUSLY_ELIGIBLE")
    return InvariantResult(name, "FAIL", "autonomy state is not AUTONOMOUSLY_ELIGIBLE and this is not --dry-run")

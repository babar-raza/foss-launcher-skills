"""CONTRACT: 12 named adversarial probes for S-123 (forensic-heal-sprint), Wave 5 of
MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: the pasted mission spec's Phase 17 asks for an independent adversarial review that
actively tries to disprove readiness across a fixed list of failure modes, with every
finding either disproven-with-evidence, repaired, or recorded as a blocker. This module is
that list made mechanical: 12 pure functions, each a deterministic PASS/FAIL check over a
well-defined evidence dict (never "did it feel okay") -- no probe here calls an LLM to
judge itself. Each probe returns DISPROVEN_WITH_EVIDENCE or BLOCKER; the REPAIRED
disposition is not something a single probe run can produce (a fix requires a SECOND run
after remediation) -- run_adversarial_review()'s prior_dispositions parameter is what turns
a probe that flips BLOCKER -> DISPROVEN_WITH_EVIDENCE across two runs into REPAIRED.

Independence enforcement: run_adversarial_review() takes sealing_session_id and
reviewer_session_id and refuses (raises) if they match -- the S-116 "fresh context"
requirement made mechanical rather than advisory, per the plan's design.
"""
from __future__ import annotations

import sprint_state

PROBE_IDS: "tuple[str, ...]" = tuple(f"A-{i:02d}" for i in range(1, 13))
DISPOSITIONS: "tuple[str, ...]" = ("DISPROVEN_WITH_EVIDENCE", "REPAIRED", "BLOCKER")


class AdversarialReviewError(RuntimeError):
    """Raised when the review itself cannot proceed safely (e.g. independence violated)."""


def _result(probe_id: str, passed: bool, detail: str) -> dict:
    return {
        "probe_id": probe_id,
        "disposition": "DISPROVEN_WITH_EVIDENCE" if passed else "BLOCKER",
        "detail": detail,
    }


def probe_a01_unaided_review_incomplete(evidence: dict) -> dict:
    """Every scoped product must have both an unaided-repo summary and unaided-content
    findings -- a scoped product with neither means the unaided pass never really covered it."""
    scoped = set(evidence.get("products_scoped", []))
    with_repo = set(evidence.get("products_with_unaided_repo_summary", []))
    with_content = set(evidence.get("products_with_unaided_content_findings", []))
    missing = sorted((scoped - with_repo) | (scoped - with_content))
    return _result("A-01", not missing, f"products missing unaided coverage: {missing}" if missing else "all scoped products covered")


def probe_a02_system_used_too_early(evidence: dict) -> dict:
    """Re-verifies the unaided-first verdict independently. A properly-overridden violation
    is not a fresh adversarial failure -- the override IS the governed path for this case,
    already recorded as a limitation elsewhere; only an UN-overridden violation blocks here."""
    verdict = evidence.get("unaided_first_verdict")
    override_present = bool(evidence.get("override_present"))
    passed = verdict == "UNAIDED_FIRST_CLEAN" or override_present
    detail = f"verdict={verdict!r}, override_present={override_present}"
    return _result("A-02", passed, detail)


def probe_a03_blind_spot_matrix_incomplete(evidence: dict) -> dict:
    """Orphan finding IDs (unaccounted for in the comparison matrix) must be zero."""
    orphans = evidence.get("orphan_finding_ids", [])
    return _result("A-03", not orphans, f"orphan finding_ids: {orphans}" if orphans else "zero orphans")


def probe_a04_root_cause_not_traced(evidence: dict) -> dict:
    """Every root cause needs a layer AND a file_ref with a resolvable line reference
    (contains ':' followed by a line number) -- 'somewhere in the codebase' is not a trace."""
    bad = []
    for rc in evidence.get("root_causes", []):
        file_ref = rc.get("file_ref", "")
        has_line = ":" in file_ref and file_ref.rsplit(":", 1)[-1].isdigit()
        if not rc.get("layer") or not has_line:
            bad.append(rc.get("root_cause_id"))
    return _result("A-04", not bad, f"root causes without a resolvable layer+line: {bad}" if bad else "all root causes traced")


def probe_a05_solution_options_missing(evidence: dict) -> dict:
    """Every fix-plan item needs >=2 options, each fully scored on all 6 axes."""
    axes = {"correctness", "scope", "maintainability", "risk", "repeatability", "verification_cost"}
    bad = []
    for item in evidence.get("fix_plan_items", []):
        options = item.get("options", [])
        if len(options) < 2 or any(not axes.issubset(opt.keys()) for opt in options):
            bad.append(item.get("root_cause_id"))
    return _result("A-05", not bad, f"fix-plan items with insufficient options: {bad}" if bad else "all items have >=2 fully-scored options")


def probe_a06_taskcards_too_vague(evidence: dict) -> dict:
    """Every taskcard needs non-empty allowed_paths, verification_commands, and rollback."""
    bad = []
    for card in evidence.get("taskcards", []):
        if not card.get("allowed_paths") or not card.get("verification_commands") or not card.get("rollback", "").strip():
            bad.append(card.get("task_id"))
    return _result("A-06", not bad, f"under-specified taskcards: {bad}" if bad else "all taskcards fully specified")


def probe_a07_fix_did_not_address_root_cause(evidence: dict) -> dict:
    """Every CLOSED taskcard's root_cause_id must resolve to a known root cause."""
    known = set(evidence.get("root_cause_ids", []))
    bad = [
        c.get("task_id") for c in evidence.get("taskcards", [])
        if c.get("status") == "CLOSED" and c.get("root_cause_id") not in known
    ]
    return _result("A-07", not bad, f"CLOSED taskcards with an unresolved root_cause_id: {bad}" if bad else "every CLOSED taskcard traces to a known root cause")


def probe_a08_content_hand_patched(evidence: dict) -> dict:
    """Every changed content/** path must attribute to a recorded pipeline command."""
    changed = set(evidence.get("changed_content_paths", []))
    attributed = set(evidence.get("attributed_content_paths", []))
    unattributed = sorted(changed - attributed)
    return _result("A-08", not unattributed, f"unattributed content changes: {unattributed}" if unattributed else "every content change is attributed")


def probe_a09_wrong_order(evidence: dict) -> dict:
    """For every taskcard with regeneration_required, its content-regen evidence timestamp
    must be strictly after its system-heal evidence timestamp -- content regenerated at or
    before the system fix landed means the system wasn't actually healed first.

    RC-tex-python-01 (MT037 Batch 1 adversarial review): a taskcard whose root cause is
    layer='data' is exempt, mirroring sprint_state.SYSTEM_LAYERS/check_system_before_content_
    gate's own established rule that a data-layer root cause (e.g. a stale JSON config or a
    one-off content mistake) never gates content regeneration on a system-layer fix -- there
    is no system fix for this class of root cause to precede. A taskcard with no layer at all
    fails open (not treated as system-layer), the same convention check_system_before_content_
    gate already uses for a missing/unrecognized layer. Before this fix, A-09 applied the
    ordering requirement uniformly regardless of layer, incorrectly flagging legitimate
    content-only fixes (e.g. TC-tex-python-05, root cause RC-tex-python-06, layer=data) the
    same way as a genuine unaddressed script-layer gap (e.g. TC-BSA-01, RC-tex-python-01,
    layer=script, which A-09 correctly continues to flag -- that fix-plan deliberately chose
    a content-only remediation over fixing the script layer, so the system-layer gap really is
    still open)."""
    bad = []
    for card in evidence.get("taskcards", []):
        if not card.get("regeneration_required"):
            continue
        if card.get("layer") not in sprint_state.SYSTEM_LAYERS:
            continue
        heal_at = card.get("system_heal_evidence_at")
        regen_at = card.get("content_regen_evidence_at")
        if not heal_at or not regen_at or regen_at <= heal_at:
            bad.append(card.get("task_id"))
    return _result("A-09", not bad, f"taskcards with content regenerated before/without a system fix: {bad}" if bad else "system-before-content ordering holds for every card")


def probe_a10_verification_shallow(evidence: dict) -> dict:
    """For every taskcard with regeneration_required, before/after hashes must both be
    present and different -- identical hashes despite a claimed regen means nothing
    verifiably changed."""
    bad = []
    for card in evidence.get("taskcards", []):
        if not card.get("regeneration_required"):
            continue
        before, after = card.get("before_hash"), card.get("after_hash")
        if not before or not after or before == after:
            bad.append(card.get("task_id"))
    return _result("A-10", not bad, f"taskcards with no verifiable before/after change: {bad}" if bad else "every regenerated taskcard has a verified before/after diff")


def probe_a11_hardening_cosmetic(evidence: dict) -> dict:
    """Every hardening item must cite a check that provably fails against a synthetic
    regression fixture -- a 'strengthened' check that can't be shown to catch anything is
    cosmetic, not hardening."""
    bad = [
        item.get("check_name") for item in evidence.get("hardening_items", [])
        if not item.get("fails_on_regression_fixture")
    ]
    return _result("A-11", not bad, f"hardening items with no proven regression catch: {bad}" if bad else "every hardening item proven against a regression fixture")


def probe_a12_pilot_not_end_to_end(evidence: dict) -> dict:
    """All 7 pilot-chain links must resolve."""
    links = evidence.get("pilot_chain_links", [])
    passed = len(links) == 7 and all(links)
    return _result("A-12", passed, f"pilot chain links: {links}" if not passed else "all 7 pilot-chain links resolved")


PROBES = {
    "A-01": probe_a01_unaided_review_incomplete,
    "A-02": probe_a02_system_used_too_early,
    "A-03": probe_a03_blind_spot_matrix_incomplete,
    "A-04": probe_a04_root_cause_not_traced,
    "A-05": probe_a05_solution_options_missing,
    "A-06": probe_a06_taskcards_too_vague,
    "A-07": probe_a07_fix_did_not_address_root_cause,
    "A-08": probe_a08_content_hand_patched,
    "A-09": probe_a09_wrong_order,
    "A-10": probe_a10_verification_shallow,
    "A-11": probe_a11_hardening_cosmetic,
    "A-12": probe_a12_pilot_not_end_to_end,
}


def run_adversarial_review(
    evidence_bundle: dict, *, sealing_session_id: str, reviewer_session_id: str,
    prior_dispositions: "dict[str, str] | None" = None,
) -> dict:
    """Run all 12 probes against evidence_bundle (one key per probe_id -- see each probe's
    docstring for its evidence shape). Raises AdversarialReviewError if
    reviewer_session_id == sealing_session_id (independence enforced, not requested).

    If prior_dispositions is given (a probe_id -> disposition map from an earlier,
    pre-remediation run), any probe that was BLOCKER before and passes now is reported
    REPAIRED instead of DISPROVEN_WITH_EVIDENCE -- a probe that was already clean stays
    DISPROVEN_WITH_EVIDENCE either way.

    Returns {"dispositions": {probe_id: {...probe result..., "disposition": ...}},
             "any_blocker": bool, "independence_verified": True}.
    """
    if reviewer_session_id == sealing_session_id:
        raise AdversarialReviewError(
            "adversarial review requires a reviewer session distinct from the sealing "
            "session -- independence is enforced, not requested"
        )

    dispositions = {}
    for probe_id in PROBE_IDS:
        result = PROBES[probe_id](evidence_bundle.get(probe_id, {}))
        if (
            prior_dispositions
            and prior_dispositions.get(probe_id) == "BLOCKER"
            and result["disposition"] == "DISPROVEN_WITH_EVIDENCE"
        ):
            result = {**result, "disposition": "REPAIRED"}
        dispositions[probe_id] = result

    any_blocker = any(r["disposition"] == "BLOCKER" for r in dispositions.values())
    return {"dispositions": dispositions, "any_blocker": any_blocker, "independence_verified": True}

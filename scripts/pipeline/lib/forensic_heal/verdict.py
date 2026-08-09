"""CONTRACT: computed (never asserted) dual verdicts for S-123 (forensic-heal-sprint),
Wave 5 of MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: the strongest anti-overclaim control in the whole design. Neither the
human_readiness_verdict nor the agentic_consumption_verdict nor the final_verdict is a
field an agent fills in by hand -- all three are DERIVED, deterministically, from the same
evidence every other Wave 5 module already produced (sprint state, the unaided-first
verdict, the pilot chain, the adversarial dispositions). An agent cannot claim
SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH by asserting it; it can only be true if every input
that would make it true actually is.
"""
from __future__ import annotations

HUMAN_READINESS_VERDICTS: "tuple[str, ...]" = ("READY", "READY_WITH_LIMITATIONS", "NOT_READY")
AGENTIC_CONSUMPTION_VERDICTS: "tuple[str, ...]" = ("CONSUMABLE", "CONSUMABLE_WITH_LIMITATIONS", "NOT_CONSUMABLE")
FINAL_VERDICTS: "tuple[str, ...]" = (
    "SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH", "SYSTEM_HEALED_WITH_LIMITATIONS",
    "SYSTEM_NOT_READY_REWORK_REQUIRED", "BLOCKED_EXTERNAL",
)


def compute_verdict(
    *, sprint_state: dict, gate_passed: bool, pilot_chain_resolved: bool,
    adversarial_review: dict, unaided_first_override: "dict | None" = None,
) -> dict:
    """Compute the final verdict plus both sub-verdicts.

    Args mirror the real outputs of this mission's other modules directly:
      sprint_state          -- sprint_state.compute_sprint_state()'s return value
      gate_passed           -- sprint_state.check_system_before_content_gate()'s "passed"
      pilot_chain_resolved  -- True only if all 7 pilot-chain links resolved
      adversarial_review    -- adversarial_probes.run_adversarial_review()'s return value
      unaided_first_override -- S-122's manifest["unaided_first_override"], or None

    Returns {"final_verdict", "human_readiness_verdict", "agentic_consumption_verdict",
             "limitations": [...]}. `limitations` is always non-empty when either verdict
    is *_WITH_LIMITATIONS, and always empty for the top-tier or BLOCKED_EXTERNAL outcomes.
    """
    exceptions = sprint_state.get("exception_task_ids", {})

    if "BLOCKED_EXTERNAL" in exceptions:
        return {
            "final_verdict": "BLOCKED_EXTERNAL",
            "human_readiness_verdict": "NOT_READY",
            "agentic_consumption_verdict": "NOT_CONSUMABLE",
            "limitations": [f"BLOCKED_EXTERNAL taskcard(s): {exceptions['BLOCKED_EXTERNAL']}"],
        }

    rework_reasons: "list[str]" = []
    if exceptions.get("BLOCKED_LOCAL"):
        rework_reasons.append(f"BLOCKED_LOCAL taskcard(s): {exceptions['BLOCKED_LOCAL']}")
    if exceptions.get("REWORK_REQUIRED"):
        rework_reasons.append(f"REWORK_REQUIRED taskcard(s): {exceptions['REWORK_REQUIRED']}")
    if not gate_passed:
        rework_reasons.append("system-before-content gate has not passed")
    blocker_probes = [pid for pid, r in adversarial_review.get("dispositions", {}).items() if r["disposition"] == "BLOCKER"]
    if blocker_probes:
        rework_reasons.append(f"unresolved adversarial BLOCKER probe(s): {blocker_probes}")

    if rework_reasons:
        return {
            "final_verdict": "SYSTEM_NOT_READY_REWORK_REQUIRED",
            "human_readiness_verdict": "NOT_READY",
            "agentic_consumption_verdict": "NOT_CONSUMABLE",
            "limitations": rework_reasons,
        }

    limitations: "list[str]" = []
    if unaided_first_override:
        limitations.append(f"unaided-first gate overridden: {unaided_first_override.get('reason')}")
    if not pilot_chain_resolved:
        limitations.append("pilot chain did not fully resolve")
    repaired_probes = [pid for pid, r in adversarial_review.get("dispositions", {}).items() if r["disposition"] == "REPAIRED"]
    if repaired_probes:
        limitations.append(f"adversarial probe(s) required repair before passing: {repaired_probes}")
    if sprint_state.get("aggregate_status") != "CLOSED":
        limitations.append(f"sprint aggregate status is {sprint_state.get('aggregate_status')!r}, not CLOSED")

    if limitations:
        return {
            "final_verdict": "SYSTEM_HEALED_WITH_LIMITATIONS",
            "human_readiness_verdict": "READY_WITH_LIMITATIONS",
            "agentic_consumption_verdict": "CONSUMABLE_WITH_LIMITATIONS",
            "limitations": limitations,
        }

    return {
        "final_verdict": "SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH",
        "human_readiness_verdict": "READY",
        "agentic_consumption_verdict": "CONSUMABLE",
        "limitations": [],
    }

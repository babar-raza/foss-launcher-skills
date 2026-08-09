from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import verdict  # noqa: E402


def _sprint_state(status="CLOSED", exceptions=None):
    return {"aggregate_status": status, "exception_task_ids": exceptions or {}}


def _clean_adversarial():
    return {"dispositions": {f"A-{i:02d}": {"disposition": "DISPROVEN_WITH_EVIDENCE"} for i in range(1, 13)}, "any_blocker": False}


def test_top_tier_verdict_requires_everything_clean():
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=True, pilot_chain_resolved=True,
        adversarial_review=_clean_adversarial(), unaided_first_override=None,
    )
    assert result["final_verdict"] == "SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH"
    assert result["human_readiness_verdict"] == "READY"
    assert result["agentic_consumption_verdict"] == "CONSUMABLE"
    assert result["limitations"] == []


def test_blocked_external_taskcard_forces_blocked_external_verdict():
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(exceptions={"BLOCKED_EXTERNAL": ["TC-1"]}),
        gate_passed=True, pilot_chain_resolved=True, adversarial_review=_clean_adversarial(),
    )
    assert result["final_verdict"] == "BLOCKED_EXTERNAL"
    assert result["human_readiness_verdict"] == "NOT_READY"


def test_blocked_external_outranks_a_clean_everything_else():
    # Even with a perfectly clean gate/pilot/adversarial state, one BLOCKED_EXTERNAL card
    # must still force BLOCKED_EXTERNAL -- it is never overridden by other good signals.
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(status="CLOSED", exceptions={"BLOCKED_EXTERNAL": ["TC-1"]}),
        gate_passed=True, pilot_chain_resolved=True, adversarial_review=_clean_adversarial(),
    )
    assert result["final_verdict"] == "BLOCKED_EXTERNAL"


def test_gate_not_passed_forces_rework_required():
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=False, pilot_chain_resolved=True,
        adversarial_review=_clean_adversarial(),
    )
    assert result["final_verdict"] == "SYSTEM_NOT_READY_REWORK_REQUIRED"


def test_adversarial_blocker_forces_rework_required():
    adversarial = _clean_adversarial()
    adversarial["dispositions"]["A-03"]["disposition"] = "BLOCKER"
    adversarial["any_blocker"] = True
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=True, pilot_chain_resolved=True,
        adversarial_review=adversarial,
    )
    assert result["final_verdict"] == "SYSTEM_NOT_READY_REWORK_REQUIRED"
    assert "A-03" in result["limitations"][0]


def test_rework_required_cards_force_rework_required_verdict():
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(exceptions={"REWORK_REQUIRED": ["TC-2"]}),
        gate_passed=True, pilot_chain_resolved=True, adversarial_review=_clean_adversarial(),
    )
    assert result["final_verdict"] == "SYSTEM_NOT_READY_REWORK_REQUIRED"


def test_unaided_first_override_caps_at_with_limitations():
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=True, pilot_chain_resolved=True,
        adversarial_review=_clean_adversarial(),
        unaided_first_override={"reason": "ledger tooling unavailable"},
    )
    assert result["final_verdict"] == "SYSTEM_HEALED_WITH_LIMITATIONS"
    assert result["human_readiness_verdict"] == "READY_WITH_LIMITATIONS"
    assert any("ledger tooling unavailable" in lim for lim in result["limitations"])


def test_unresolved_pilot_chain_caps_at_with_limitations():
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=True, pilot_chain_resolved=False,
        adversarial_review=_clean_adversarial(),
    )
    assert result["final_verdict"] == "SYSTEM_HEALED_WITH_LIMITATIONS"


def test_repaired_adversarial_probe_caps_at_with_limitations():
    adversarial = _clean_adversarial()
    adversarial["dispositions"]["A-03"]["disposition"] = "REPAIRED"
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=True, pilot_chain_resolved=True,
        adversarial_review=adversarial,
    )
    assert result["final_verdict"] == "SYSTEM_HEALED_WITH_LIMITATIONS"


def test_non_closed_aggregate_caps_at_with_limitations_even_if_everything_else_clean():
    result = verdict.compute_verdict(
        sprint_state=_sprint_state(status="INTEGRATION_VERIFIED"), gate_passed=True,
        pilot_chain_resolved=True, adversarial_review=_clean_adversarial(),
    )
    assert result["final_verdict"] == "SYSTEM_HEALED_WITH_LIMITATIONS"


def test_verdict_is_never_asserted_only_computed_from_inputs():
    # Same function, same shape of inputs, differing only in one boolean -- proves the
    # verdict is a pure function of its inputs, not something set independently.
    clean = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=True, pilot_chain_resolved=True,
        adversarial_review=_clean_adversarial(),
    )
    dirty = verdict.compute_verdict(
        sprint_state=_sprint_state(), gate_passed=True, pilot_chain_resolved=True,
        adversarial_review=_clean_adversarial(), unaided_first_override={"reason": "x"},
    )
    assert clean["final_verdict"] != dirty["final_verdict"]

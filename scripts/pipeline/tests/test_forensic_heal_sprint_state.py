from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import sprint_state  # noqa: E402


def _card(status, layer="script"):
    return {"status": status, "layer": layer}


# ---------------------------------------------------------------------------
# compute_sprint_state
# ---------------------------------------------------------------------------


def test_aggregate_is_the_minimum_progress_across_cards():
    cards = {
        "TC-1": _card("IMPLEMENTED"),
        "TC-2": _card("CLOSED"),
        "TC-3": _card("READY"),
    }
    result = sprint_state.compute_sprint_state(cards)
    assert result["aggregate_status"] == "READY"
    assert result["in_scope_task_ids"] == ["TC-1", "TC-2", "TC-3"]


def test_aggregate_is_closed_when_every_card_closed():
    cards = {"TC-1": _card("CLOSED"), "TC-2": _card("CLOSED")}
    result = sprint_state.compute_sprint_state(cards)
    assert result["aggregate_status"] == "CLOSED"


def test_superseded_and_out_of_scope_cards_are_excluded_not_counted():
    cards = {
        "TC-1": _card("CLOSED"),
        "TC-2": _card("SUPERSEDED"),
        "TC-3": _card("OUT_OF_SCOPE"),
    }
    result = sprint_state.compute_sprint_state(cards)
    assert result["aggregate_status"] == "CLOSED"
    assert result["excluded_task_ids"] == ["TC-2", "TC-3"]
    assert result["in_scope_task_ids"] == ["TC-1"]


def test_any_exception_status_forces_the_aggregate_to_it():
    cards = {"TC-1": _card("IMPLEMENTED"), "TC-2": _card("REWORK_REQUIRED")}
    result = sprint_state.compute_sprint_state(cards)
    assert result["aggregate_status"] == "REWORK_REQUIRED"
    assert result["exception_task_ids"] == {"REWORK_REQUIRED": ["TC-2"]}


def test_blocked_external_outranks_blocked_local_and_rework_required():
    cards = {
        "TC-1": _card("REWORK_REQUIRED"),
        "TC-2": _card("BLOCKED_LOCAL"),
        "TC-3": _card("BLOCKED_EXTERNAL"),
    }
    result = sprint_state.compute_sprint_state(cards)
    assert result["aggregate_status"] == "BLOCKED_EXTERNAL"


def test_paused_card_is_reported_not_a_keyerror_crash():
    """Regression: PAUSED is a real schema-5f status (added for the
    context-switch-declaration mechanism) but was missing from every
    classification bucket in this module, so compute_sprint_state crashed
    with a bare KeyError on any mission carrying a paused taskcard --
    reproduced live on MT037's real taskcard store (TC-tex-python-04)."""
    cards = {"TC-1": _card("IMPLEMENTED"), "TC-2": _card("PAUSED")}
    result = sprint_state.compute_sprint_state(cards)
    assert result["aggregate_status"] == "PAUSED"
    assert result["exception_task_ids"] == {"PAUSED": ["TC-2"]}


def test_paused_ranks_below_the_other_exception_statuses():
    cards = {"TC-1": _card("PAUSED"), "TC-2": _card("REWORK_REQUIRED")}
    result = sprint_state.compute_sprint_state(cards)
    assert result["aggregate_status"] == "REWORK_REQUIRED"


def test_empty_in_scope_set_raises():
    with pytest.raises(ValueError, match="no in-scope"):
        sprint_state.compute_sprint_state({})


def test_all_excluded_raises_not_a_silent_default():
    cards = {"TC-1": _card("SUPERSEDED")}
    with pytest.raises(ValueError, match="no in-scope"):
        sprint_state.compute_sprint_state(cards)


def test_unknown_task_id_in_explicit_selection_raises():
    cards = {"TC-1": _card("CLOSED")}
    with pytest.raises(ValueError, match="not found"):
        sprint_state.compute_sprint_state(cards, task_ids=["TC-999"])


def test_explicit_task_ids_narrows_scope():
    cards = {"TC-1": _card("CLOSED"), "TC-2": _card("TODO")}
    result = sprint_state.compute_sprint_state(cards, task_ids=["TC-1"])
    assert result["aggregate_status"] == "CLOSED"


# ---------------------------------------------------------------------------
# check_system_before_content_gate
# ---------------------------------------------------------------------------


def test_gate_passes_when_every_system_layer_card_is_implemented_or_later():
    cards = {
        "TC-1": _card("IMPLEMENTED", layer="script"),
        "TC-2": _card("CLOSED", layer="governance_doc"),
        "TC-3": _card("TODO", layer="data"),  # data layer never blocks
    }
    result = sprint_state.check_system_before_content_gate(cards)
    assert result["passed"] is True
    assert result["blocking_cards"] == []


def test_gate_blocks_on_a_system_layer_card_below_implemented():
    cards = {
        "TC-1": _card("IN_PROGRESS", layer="script"),
        "TC-2": _card("CLOSED", layer="prompt"),
    }
    result = sprint_state.check_system_before_content_gate(cards)
    assert result["passed"] is False
    assert result["blocking_cards"] == [{"task_id": "TC-1", "layer": "script", "status": "IN_PROGRESS"}]


def test_gate_blocks_on_exception_status_even_if_rank_would_pass():
    # A card can't be BLOCKED_LOCAL and simultaneously "done enough" -- exception status
    # always blocks regardless of any prior rank.
    cards = {"TC-1": _card("BLOCKED_LOCAL", layer="script")}
    result = sprint_state.check_system_before_content_gate(cards)
    assert result["passed"] is False
    assert result["blocking_cards"][0]["status"] == "BLOCKED_LOCAL"


def test_gate_ignores_excluded_cards():
    cards = {"TC-1": _card("SUPERSEDED", layer="script")}
    result = sprint_state.check_system_before_content_gate(cards)
    assert result["passed"] is True


def test_gate_missing_layer_does_not_block_fails_open_by_design():
    cards = {"TC-1": {"status": "TODO"}}  # no "layer" key at all
    result = sprint_state.check_system_before_content_gate(cards)
    assert result["passed"] is True


def test_gate_blocks_on_a_paused_system_layer_card():
    """PAUSED must keep blocking system-before-content the same way
    BLOCKED_LOCAL/BLOCKED_EXTERNAL/REWORK_REQUIRED already do -- the gate's
    defensive _PROGRESS_RANK.get(status, -1) fallback already handled this
    correctly even before the compute_sprint_state KeyError fix above."""
    cards = {"TC-1": _card("PAUSED", layer="script")}
    result = sprint_state.check_system_before_content_gate(cards)
    assert result["passed"] is False
    assert result["blocking_cards"][0]["status"] == "PAUSED"


def test_gate_scoped_to_explicit_task_ids_only():
    cards = {
        "TC-1": _card("TODO", layer="script"),  # would block, but not selected
        "TC-2": _card("CLOSED", layer="script"),
    }
    result = sprint_state.check_system_before_content_gate(cards, task_ids=["TC-2"])
    assert result["passed"] is True

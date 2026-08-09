from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import pilot_chain  # noqa: E402

_FULL_CHAIN = {
    "unaided_finding_id": "FND-1", "root_cause_id": "RC-1", "task_id": "TC-1",
    "system_fix_diff_ref": "commit:abc123", "regen_command": "batch_reference.py font python",
    "verification_before_hash": "hash-before", "verification_after_hash": "hash-after",
    "agentic_consumption_recheck_passed": True,
}


def test_full_chain_resolves():
    result = pilot_chain.resolve_pilot_chain(_FULL_CHAIN)
    assert result["resolved"] is True
    assert all(result["links"].values())


def test_missing_unaided_finding_breaks_the_chain():
    chain = {**_FULL_CHAIN, "unaided_finding_id": None}
    result = pilot_chain.resolve_pilot_chain(chain)
    assert result["resolved"] is False
    assert result["links"]["unaided_finding"] is False


def test_identical_before_after_hash_does_not_count_as_verified():
    chain = {**_FULL_CHAIN, "verification_after_hash": _FULL_CHAIN["verification_before_hash"]}
    result = pilot_chain.resolve_pilot_chain(chain)
    assert result["links"]["verification_artifact_pair"] is False
    assert result["resolved"] is False


def test_missing_after_hash_breaks_verification_link():
    chain = {**_FULL_CHAIN, "verification_after_hash": None}
    result = pilot_chain.resolve_pilot_chain(chain)
    assert result["links"]["verification_artifact_pair"] is False


def test_agentic_recheck_must_be_exactly_true_not_truthy():
    chain = {**_FULL_CHAIN, "agentic_consumption_recheck_passed": "yes"}
    result = pilot_chain.resolve_pilot_chain(chain)
    assert result["links"]["agentic_consumption_recheck"] is False


def test_empty_chain_resolves_nothing():
    result = pilot_chain.resolve_pilot_chain({})
    assert result["resolved"] is False
    assert not any(result["links"].values())

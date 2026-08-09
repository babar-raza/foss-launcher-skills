"""Each of the 12 adversarial probes needs a passing AND a failing fixture (per plan
typed-snuggling-peach.md) -- a probe that can never fail is not adversarial, it's decorative.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import adversarial_probes as ap  # noqa: E402


# ---------------------------------------------------------------------------
# A-01
# ---------------------------------------------------------------------------


def test_a01_passes_when_every_scoped_product_covered():
    evidence = {
        "products_scoped": ["font/python"],
        "products_with_unaided_repo_summary": ["font/python"],
        "products_with_unaided_content_findings": ["font/python"],
    }
    assert ap.probe_a01_unaided_review_incomplete(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a01_blocks_when_a_scoped_product_has_no_content_findings():
    evidence = {
        "products_scoped": ["font/python", "pdf/net"],
        "products_with_unaided_repo_summary": ["font/python", "pdf/net"],
        "products_with_unaided_content_findings": ["font/python"],
    }
    assert ap.probe_a01_unaided_review_incomplete(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-02
# ---------------------------------------------------------------------------


def test_a02_passes_when_clean():
    assert ap.probe_a02_system_used_too_early({"unaided_first_verdict": "UNAIDED_FIRST_CLEAN", "override_present": False})["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a02_passes_when_violated_but_properly_overridden():
    assert ap.probe_a02_system_used_too_early({"unaided_first_verdict": "VIOLATED", "override_present": True})["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a02_blocks_when_violated_without_override():
    assert ap.probe_a02_system_used_too_early({"unaided_first_verdict": "VIOLATED", "override_present": False})["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-03
# ---------------------------------------------------------------------------


def test_a03_passes_with_zero_orphans():
    assert ap.probe_a03_blind_spot_matrix_incomplete({"orphan_finding_ids": []})["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a03_blocks_on_orphans():
    assert ap.probe_a03_blind_spot_matrix_incomplete({"orphan_finding_ids": ["FND-9"]})["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-04
# ---------------------------------------------------------------------------


def test_a04_passes_with_layer_and_line_reference():
    evidence = {"root_causes": [{"root_cause_id": "RC-1", "layer": "script", "file_ref": "x.py:42"}]}
    assert ap.probe_a04_root_cause_not_traced(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a04_blocks_without_line_number():
    evidence = {"root_causes": [{"root_cause_id": "RC-1", "layer": "script", "file_ref": "x.py"}]}
    assert ap.probe_a04_root_cause_not_traced(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-05
# ---------------------------------------------------------------------------

_AXES = {"correctness": "x", "scope": "x", "maintainability": "x", "risk": "x", "repeatability": "x", "verification_cost": "x"}


def test_a05_passes_with_two_fully_scored_options():
    evidence = {"fix_plan_items": [{"root_cause_id": "RC-1", "options": [dict(_AXES), dict(_AXES)]}]}
    assert ap.probe_a05_solution_options_missing(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a05_blocks_with_only_one_option():
    evidence = {"fix_plan_items": [{"root_cause_id": "RC-1", "options": [dict(_AXES)]}]}
    assert ap.probe_a05_solution_options_missing(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-06
# ---------------------------------------------------------------------------


def test_a06_passes_with_fully_specified_taskcard():
    evidence = {"taskcards": [{"task_id": "TC-1", "allowed_paths": ["x.py"], "verification_commands": ["pytest x"], "rollback": "git checkout x"}]}
    assert ap.probe_a06_taskcards_too_vague(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a06_blocks_with_empty_rollback():
    evidence = {"taskcards": [{"task_id": "TC-1", "allowed_paths": ["x.py"], "verification_commands": ["pytest x"], "rollback": "  "}]}
    assert ap.probe_a06_taskcards_too_vague(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-07
# ---------------------------------------------------------------------------


def test_a07_passes_when_closed_card_traces_to_a_known_root_cause():
    evidence = {"taskcards": [{"task_id": "TC-1", "status": "CLOSED", "root_cause_id": "RC-1"}], "root_cause_ids": ["RC-1"]}
    assert ap.probe_a07_fix_did_not_address_root_cause(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a07_blocks_when_closed_card_references_unknown_root_cause():
    evidence = {"taskcards": [{"task_id": "TC-1", "status": "CLOSED", "root_cause_id": "RC-999"}], "root_cause_ids": ["RC-1"]}
    assert ap.probe_a07_fix_did_not_address_root_cause(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-08
# ---------------------------------------------------------------------------


def test_a08_passes_when_every_change_is_attributed():
    evidence = {"changed_content_paths": ["content/a.md"], "attributed_content_paths": ["content/a.md"]}
    assert ap.probe_a08_content_hand_patched(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a08_blocks_on_unattributed_content_change():
    evidence = {"changed_content_paths": ["content/a.md", "content/b.md"], "attributed_content_paths": ["content/a.md"]}
    assert ap.probe_a08_content_hand_patched(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-09
# ---------------------------------------------------------------------------


def test_a09_passes_when_regen_happens_after_system_heal():
    evidence = {"taskcards": [{"task_id": "TC-1", "regeneration_required": True, "system_heal_evidence_at": "2026-08-01T00:00:00Z", "content_regen_evidence_at": "2026-08-02T00:00:00Z"}]}
    assert ap.probe_a09_wrong_order(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a09_blocks_when_regen_happens_before_system_heal():
    evidence = {"taskcards": [{"task_id": "TC-1", "regeneration_required": True, "system_heal_evidence_at": "2026-08-02T00:00:00Z", "content_regen_evidence_at": "2026-08-01T00:00:00Z"}]}
    assert ap.probe_a09_wrong_order(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-10
# ---------------------------------------------------------------------------


def test_a10_passes_with_differing_before_after_hashes():
    evidence = {"taskcards": [{"task_id": "TC-1", "regeneration_required": True, "before_hash": "a", "after_hash": "b"}]}
    assert ap.probe_a10_verification_shallow(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a10_blocks_on_identical_before_after_hashes():
    evidence = {"taskcards": [{"task_id": "TC-1", "regeneration_required": True, "before_hash": "a", "after_hash": "a"}]}
    assert ap.probe_a10_verification_shallow(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-11
# ---------------------------------------------------------------------------


def test_a11_passes_when_hardening_proven_against_regression_fixture():
    evidence = {"hardening_items": [{"check_name": "check_x", "fails_on_regression_fixture": True}]}
    assert ap.probe_a11_hardening_cosmetic(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a11_blocks_when_hardening_unproven():
    evidence = {"hardening_items": [{"check_name": "check_x", "fails_on_regression_fixture": False}]}
    assert ap.probe_a11_hardening_cosmetic(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# A-12
# ---------------------------------------------------------------------------


def test_a12_passes_with_all_seven_links_resolved():
    evidence = {"pilot_chain_links": [True] * 7}
    assert ap.probe_a12_pilot_not_end_to_end(evidence)["disposition"] == "DISPROVEN_WITH_EVIDENCE"


def test_a12_blocks_with_a_broken_link():
    evidence = {"pilot_chain_links": [True] * 6 + [False]}
    assert ap.probe_a12_pilot_not_end_to_end(evidence)["disposition"] == "BLOCKER"


# ---------------------------------------------------------------------------
# run_adversarial_review orchestration
# ---------------------------------------------------------------------------


def _clean_bundle() -> dict:
    return {
        "A-01": {"products_scoped": [], "products_with_unaided_repo_summary": [], "products_with_unaided_content_findings": []},
        "A-02": {"unaided_first_verdict": "UNAIDED_FIRST_CLEAN", "override_present": False},
        "A-03": {"orphan_finding_ids": []},
        "A-04": {"root_causes": []},
        "A-05": {"fix_plan_items": []},
        "A-06": {"taskcards": []},
        "A-07": {"taskcards": [], "root_cause_ids": []},
        "A-08": {"changed_content_paths": [], "attributed_content_paths": []},
        "A-09": {"taskcards": []},
        "A-10": {"taskcards": []},
        "A-11": {"hardening_items": []},
        "A-12": {"pilot_chain_links": [True] * 7},
    }


def test_run_adversarial_review_requires_independent_sessions():
    with pytest.raises(ap.AdversarialReviewError, match="distinct"):
        ap.run_adversarial_review(_clean_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-a")


def test_run_adversarial_review_all_clean_bundle_has_no_blockers():
    result = ap.run_adversarial_review(_clean_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-b")
    assert result["any_blocker"] is False
    assert result["independence_verified"] is True
    assert len(result["dispositions"]) == 12


def test_run_adversarial_review_flags_a_real_blocker():
    bundle = _clean_bundle()
    bundle["A-03"] = {"orphan_finding_ids": ["FND-9"]}
    result = ap.run_adversarial_review(bundle, sealing_session_id="sess-a", reviewer_session_id="sess-b")
    assert result["any_blocker"] is True
    assert result["dispositions"]["A-03"]["disposition"] == "BLOCKER"


def test_run_adversarial_review_marks_repaired_when_a_prior_blocker_now_passes():
    bundle = _clean_bundle()  # A-03 now clean
    prior = {"A-03": "BLOCKER"}
    result = ap.run_adversarial_review(bundle, sealing_session_id="sess-a", reviewer_session_id="sess-b", prior_dispositions=prior)
    assert result["dispositions"]["A-03"]["disposition"] == "REPAIRED"
    assert result["any_blocker"] is False


def test_run_adversarial_review_probe_that_was_already_clean_stays_disproven_not_repaired():
    bundle = _clean_bundle()
    prior = {"A-03": "DISPROVEN_WITH_EVIDENCE"}
    result = ap.run_adversarial_review(bundle, sealing_session_id="sess-a", reviewer_session_id="sess-b", prior_dispositions=prior)
    assert result["dispositions"]["A-03"]["disposition"] == "DISPROVEN_WITH_EVIDENCE"

"""Tests for forensic_heal_sprint_run.py (S-123, Wave 4) against a real scratch
TaskcardStore (never the actual repo's reports/plan_state/). Proves: (1) status/gate read
real taskcards through sprint_state.py's pure functions, (2) advance-taskcard is genuinely
CAS-protected (a stale expected_status is refused, not silently overwritten), (3) the
system-before-content gate blocks a real content-layer taskcard until its system-layer
sibling reaches IMPLEMENTED.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "governance"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import forensic_heal_sprint_run as fhsr  # noqa: E402
from taskcard_store import TaskcardStore  # noqa: E402

_MISSION_ID = "MT-TEST-S123"


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    fhsr.configure()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_card(repo: Path, task_id: str, *, status: str, layer: str = "script") -> None:
    store = TaskcardStore(_MISSION_ID, repo_root=repo)
    # Statuses past IMPLEMENTED require non-empty evidence_refs (schema 5f) -- real
    # validation, not mocked, so the seed helper must satisfy it like any real caller would.
    evidence_refs = [] if status in ("TODO", "READY", "IN_PROGRESS", "IMPLEMENTED") else ["seed-evidence.txt"]
    store.append({
        "task_id": task_id, "mission_id": _MISSION_ID, "status": status,
        "recorded_at": _now(), "recorded_by": "test-session", "evidence_refs": evidence_refs,
        "layer": layer, "title": f"seed {task_id}",
    })


def test_status_reads_real_taskcards(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="CLOSED")
    _seed_card(tmp_path, "TC-2", status="TODO")

    result = fhsr.status(_MISSION_ID)
    assert result["aggregate_status"] == "TODO"
    assert result["in_scope_task_ids"] == ["TC-1", "TC-2"]


def test_status_raises_when_mission_has_no_taskcards(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    with pytest.raises(fhsr.ForensicHealSprintRunError, match="No taskcards"):
        fhsr.status("MT-NONEXISTENT")


def test_gate_blocks_until_system_layer_card_implemented(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-SYS", status="IN_PROGRESS", layer="script")
    _seed_card(tmp_path, "TC-CONTENT", status="TODO", layer="data")

    result = fhsr.gate(_MISSION_ID)
    assert result["passed"] is False
    assert result["blocking_cards"][0]["task_id"] == "TC-SYS"


def test_gate_passes_once_system_layer_card_reaches_implemented(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-SYS", status="IN_PROGRESS", layer="script")

    fhsr.advance_taskcard(
        _MISSION_ID, "TC-SYS", expected_status="IN_PROGRESS", new_status="IMPLEMENTED",
        evidence_refs=["scripts/pipeline/commands/content/batch_reference.py"],
        session_id="test-session",
    )

    result = fhsr.gate(_MISSION_ID)
    assert result["passed"] is True


def test_advance_taskcard_is_cas_protected(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="TODO", layer="script")

    fhsr.advance_taskcard(
        _MISSION_ID, "TC-1", expected_status="TODO", new_status="READY",
        evidence_refs=[], session_id="test-session",
    )

    # A second caller racing with a now-stale expected_status ("TODO") must be refused, not
    # silently overwrite the winner's advance to READY.
    with pytest.raises(fhsr.ForensicHealSprintRunError, match="CAS refusal"):
        fhsr.advance_taskcard(
            _MISSION_ID, "TC-1", expected_status="TODO", new_status="IN_PROGRESS",
            evidence_refs=[], session_id="test-session-2",
        )
    assert fhsr.status(_MISSION_ID)["aggregate_status"] == "READY"


def test_advance_taskcard_unknown_task_id_raises(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="TODO")
    with pytest.raises(fhsr.ForensicHealSprintRunError):
        fhsr.advance_taskcard(
            _MISSION_ID, "TC-999", expected_status="TODO", new_status="READY",
            evidence_refs=[], session_id="test-session",
        )


def test_advance_taskcard_requires_session_identity(tmp_path, monkeypatch):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="TODO")
    for var in ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(fhsr.ForensicHealSprintRunError, match="session identity"):
        fhsr.advance_taskcard(
            _MISSION_ID, "TC-1", expected_status="TODO", new_status="READY", evidence_refs=[],
        )


# ---------------------------------------------------------------------------
# Wave 5: pilot-check / adversarial-review / compute-verdict / close
# ---------------------------------------------------------------------------

_FULL_CHAIN = {
    "unaided_finding_id": "FND-1", "root_cause_id": "RC-1", "task_id": "TC-1",
    "system_fix_diff_ref": "commit:abc", "regen_command": "batch_reference.py",
    "verification_before_hash": "a", "verification_after_hash": "b",
    "agentic_consumption_recheck_passed": True,
}


def _clean_adversarial_bundle() -> dict:
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


def test_pilot_check_resolves_a_complete_chain(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    result = fhsr.pilot_check(_FULL_CHAIN)
    assert result["resolved"] is True


def test_adversarial_review_requires_distinct_sessions(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    with pytest.raises(fhsr.ForensicHealSprintRunError, match="distinct"):
        fhsr.adversarial_review(
            _clean_adversarial_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-a",
        )


def test_adversarial_review_clean_bundle_has_no_blocker(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    result = fhsr.adversarial_review(
        _clean_adversarial_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-b",
    )
    assert result["any_blocker"] is False


def test_compute_verdict_reads_real_sprint_state_and_computes_top_tier(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="CLOSED")
    adversarial = fhsr.adversarial_review(
        _clean_adversarial_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-b",
    )
    result = fhsr.compute_verdict(
        _MISSION_ID, gate_passed=True, pilot_chain_resolved=True,
        adversarial_review_result=adversarial,
    )
    assert result["final_verdict"] == "SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH"


def test_close_appends_a_real_row_to_the_tracked_history_ledger(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="CLOSED")
    adversarial = fhsr.adversarial_review(
        _clean_adversarial_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-b",
    )
    result = fhsr.close(
        _MISSION_ID, products=["font/python"], gate_passed=True, pilot_chain_resolved=True,
        adversarial_review_result=adversarial, unaided_first_verdict="UNAIDED_FIRST_CLEAN",
        system_recall=0.6,
    )
    assert result["verdict"]["final_verdict"] == "SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH"

    ledger_path = tmp_path / "docs" / "governance" / "forensic-heal-history.md"
    assert ledger_path.is_file()
    text = ledger_path.read_text(encoding="utf-8")
    assert "# Forensic Heal Sprint History" in text
    assert _MISSION_ID in text
    assert "1/1" in text  # 1 taskcard closed / 1 total
    assert "60%" in text
    assert "SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH" in text


def test_close_never_hides_a_failing_verdict_from_the_ledger(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="TODO")  # not closed, not implemented
    adversarial = fhsr.adversarial_review(
        _clean_adversarial_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-b",
    )
    result = fhsr.close(
        _MISSION_ID, products=["font/python"], gate_passed=False, pilot_chain_resolved=False,
        adversarial_review_result=adversarial, unaided_first_verdict="UNAIDED_FIRST_CLEAN",
        system_recall=None,
    )
    assert result["verdict"]["final_verdict"] == "SYSTEM_NOT_READY_REWORK_REQUIRED"

    text = (tmp_path / "docs" / "governance" / "forensic-heal-history.md").read_text(encoding="utf-8")
    assert "SYSTEM_NOT_READY_REWORK_REQUIRED" in text
    assert "n/a" in text  # system_recall=None rendered honestly, not as 0% or blank


def test_history_ledger_is_append_only_across_two_closes(tmp_path):
    fhsr.configure(repo_root=tmp_path)
    _seed_card(tmp_path, "TC-1", status="CLOSED")
    adversarial = fhsr.adversarial_review(
        _clean_adversarial_bundle(), sealing_session_id="sess-a", reviewer_session_id="sess-b",
    )
    fhsr.close(
        _MISSION_ID, products=["font/python"], gate_passed=True, pilot_chain_resolved=True,
        adversarial_review_result=adversarial, unaided_first_verdict="UNAIDED_FIRST_CLEAN",
        system_recall=1.0,
    )
    ledger_path = tmp_path / "docs" / "governance" / "forensic-heal-history.md"
    row_count_after_first = len(ledger_path.read_text(encoding="utf-8").splitlines())

    fhsr.close(
        _MISSION_ID, products=["font/python"], gate_passed=True, pilot_chain_resolved=True,
        adversarial_review_result=adversarial, unaided_first_verdict="UNAIDED_FIRST_CLEAN",
        system_recall=1.0,
    )
    row_count_after_second = len(ledger_path.read_text(encoding="utf-8").splitlines())
    assert row_count_after_second == row_count_after_first + 1

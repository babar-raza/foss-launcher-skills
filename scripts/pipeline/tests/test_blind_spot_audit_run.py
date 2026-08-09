"""Round-trip state-machine test for blind_spot_audit_run.py (S-122), against a scratch
fixture repo (real git, never the actual aspose.org repo). Proves the load-bearing safety
properties from the plan (C:\\Users\\prora\\.claude\\plans\\typed-snuggling-peach.md):
(1) PHASE_CONTRACTS ordering cannot be skipped or re-entered, (2) a POST-window phase
cannot be entered before SEALED (L1 of unaided-first enforcement), (3) `seal` performs real
L2+L3 enforcement and blocks on a genuine violation or an unreadable ledger rather than
silently passing (Wave 2), (4) single-owner ACTIVE.json locking refuses a second concurrent
run, (5) ABANDONED and the terminal state both clear ACTIVE.json. The pure L2/L3 mechanics
themselves (negative controls for each violation class) live in
test_forensic_heal_unaided_first.py -- this file proves the state machine wires them in
correctly, not that the underlying detection logic is correct.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "diagnostics"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "governance"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import blind_spot_audit_run as bsa  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    bsa.configure()


def _run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _build_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init", "-q"], cwd=repo)
    _run_git(["config", "user.email", "test@example.com"], cwd=repo)
    _run_git(["config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
    _run_git(["add", "-A"], cwd=repo)
    _run_git(["commit", "-q", "-m", "initial"], cwd=repo)
    return repo


def _configure(repo: Path) -> None:
    bsa.configure(repo_root=repo, reports_root=repo / "reports")


# ---------------------------------------------------------------------------
# Happy path through the INSIDE window (Wave 1's honest reachable surface)
# ---------------------------------------------------------------------------


def test_open_lands_on_first_phase(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)

    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    assert manifest["state"] == "INTAKE_PINNED"
    assert manifest["phase_history"][-1]["phase"] == "intake"
    assert manifest["products"] == ["font/python"]
    assert manifest["pinned_inputs"]["git_head_sha"]


def test_advance_walks_pre_and_inside_phases_in_order(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]

    manifest = bsa.advance(run_id, phase="scope", session_id="test-session-1")
    assert manifest["state"] == "SCOPED"

    manifest = bsa.advance(run_id, phase="unaided-repo", session_id="test-session-1")
    assert manifest["state"] == "UNAIDED_REPO_REVIEWED"

    manifest = bsa.advance(run_id, phase="unaided-content", session_id="test-session-1")
    assert manifest["state"] == "UNAIDED_CONTENT_REVIEWED"

    manifest = bsa.advance(run_id, phase="agentic-consumption", session_id="test-session-1")
    assert manifest["state"] == "AGENTIC_CONSUMPTION_REVIEWED"

    for phase in ("intake", "scope", "unaided-repo", "unaided-content", "agentic-consumption"):
        assert bsa._evidence_path(run_id, phase).is_file()


# ---------------------------------------------------------------------------
# Ordering cannot be skipped or re-entered
# ---------------------------------------------------------------------------


def test_advance_refuses_to_skip_a_phase(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]

    with pytest.raises(bsa.BlindSpotAuditRunError, match="Illegal advance"):
        bsa.advance(run_id, phase="unaided-repo", session_id="test-session-1")  # skips "scope"


def test_advance_refuses_to_re_enter_a_completed_phase(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    bsa.advance(run_id, phase="scope", session_id="test-session-1")

    with pytest.raises(bsa.BlindSpotAuditRunError, match="Illegal advance"):
        bsa.advance(run_id, phase="intake", session_id="test-session-1")


# ---------------------------------------------------------------------------
# L1: POST-window phases refused before SEALED
# ---------------------------------------------------------------------------


def test_advance_refuses_post_phase_before_sealed(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    for phase in ("scope", "unaided-repo", "unaided-content", "agentic-consumption"):
        bsa.advance(run_id, phase=phase, session_id="test-session-1")

    with pytest.raises(bsa.BlindSpotAuditRunError, match="not SEALED"):
        bsa.advance(run_id, phase="system-review", session_id="test-session-1")


def test_advance_refuses_seal_as_a_generic_phase_target(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]

    with pytest.raises(bsa.BlindSpotAuditRunError, match="dedicated verb"):
        bsa.advance(run_id, phase="seal", session_id="test-session-1")


# ---------------------------------------------------------------------------
# seal(): real unaided-first enforcement (Wave 2)
# ---------------------------------------------------------------------------


def _advance_to_agentic_consumption_reviewed(run_id: str) -> None:
    for phase in ("scope", "unaided-repo", "unaided-content", "agentic-consumption"):
        bsa.advance(run_id, phase=phase, session_id="test-session-1")


def test_seal_blocks_when_ledger_is_entirely_absent_unprovable(tmp_path):
    # A scratch fixture repo has no reports/skill-context or reports/skill-runs at all --
    # UNPROVABLE, not a silent CLEAN.
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    _advance_to_agentic_consumption_reviewed(run_id)

    with pytest.raises(bsa.BlindSpotAuditRunError, match="UNPROVABLE"):
        bsa.seal(run_id, session_id="test-session-1")

    assert bsa.status(run_id)["state"] == "BLOCKED_UNAIDED_FIRST"


def test_seal_succeeds_when_ledger_present_and_nothing_ran(tmp_path):
    repo = _build_repo(tmp_path)
    (repo / "reports" / "skill-context" / "history").mkdir(parents=True)
    (repo / "reports" / "skill-runs").mkdir(parents=True)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    _advance_to_agentic_consumption_reviewed(run_id)

    manifest = bsa.seal(run_id, session_id="test-session-1")
    assert manifest["state"] == "SEALED"
    assert manifest["unaided_first_verdict"] == "UNAIDED_FIRST_CLEAN"
    assert "unaided_first_override" not in manifest

    seal_evidence = json.loads((bsa._run_root(run_id) / "evidence-manual-seal.json").read_text(encoding="utf-8"))
    assert "evidence-unaided-repo.json" in seal_evidence["file_hashes"]
    assert "evidence-unaided-content.json" in seal_evidence["file_hashes"]
    assert "evidence-agentic-consumption.json" in seal_evidence["file_hashes"]


def test_seal_blocks_on_real_l3_violation_a_system_artifact_appeared_in_window(tmp_path):
    repo = _build_repo(tmp_path)
    (repo / "reports" / "skill-context" / "history").mkdir(parents=True)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    bsa.advance(run_id, phase="scope", session_id="test-session-1")
    bsa.advance(run_id, phase="unaided-repo", session_id="test-session-1")
    # Simulate a system-tooling side effect landing during the unaided window.
    sneaky = repo / "reports" / "audit" / "sneaky-run.json"
    sneaky.parent.mkdir(parents=True, exist_ok=True)
    sneaky.write_text("{}", encoding="utf-8")
    bsa.advance(run_id, phase="unaided-content", session_id="test-session-1")
    bsa.advance(run_id, phase="agentic-consumption", session_id="test-session-1")

    with pytest.raises(bsa.BlindSpotAuditRunError, match="VIOLATED"):
        bsa.seal(run_id, session_id="test-session-1")
    assert bsa.status(run_id)["state"] == "BLOCKED_UNAIDED_FIRST"


def test_seal_override_proceeds_and_records_the_violation(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)  # no ledger dirs -> UNPROVABLE
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    _advance_to_agentic_consumption_reviewed(run_id)

    with pytest.raises(bsa.BlindSpotAuditRunError):
        bsa.seal(run_id, session_id="test-session-1")
    assert bsa.status(run_id)["state"] == "BLOCKED_UNAIDED_FIRST"

    manifest = bsa.seal(run_id, session_id="test-session-1", override_reason="ledger tooling unavailable in this environment")
    assert manifest["state"] == "SEALED"
    assert manifest["unaided_first_override"]["verdict"] == "UNPROVABLE"
    assert manifest["unaided_first_override"]["reason"]


def test_advance_to_post_phase_succeeds_after_real_seal(tmp_path):
    repo = _build_repo(tmp_path)
    (repo / "reports" / "skill-context" / "history").mkdir(parents=True)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    _advance_to_agentic_consumption_reviewed(run_id)
    bsa.seal(run_id, session_id="test-session-1")

    manifest = bsa.advance(run_id, phase="system-review", session_id="test-session-1")
    assert manifest["state"] == "SYSTEM_REVIEWED"


# ---------------------------------------------------------------------------
# Single-owner locking
# ---------------------------------------------------------------------------


def test_open_refuses_second_concurrent_run(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")

    with pytest.raises(bsa.BlindSpotAuditRunError, match="already has active run"):
        bsa.open_run(products=["pdf/net"], mission_id="MT-TEST", session_id="test-session-2")


def test_open_allows_new_run_after_prior_abandoned(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    bsa.abandon(manifest["run_id"], reason="test abandon")

    manifest2 = bsa.open_run(products=["pdf/net"], mission_id="MT-TEST", session_id="test-session-2")
    assert manifest2["state"] == "INTAKE_PINNED"


# ---------------------------------------------------------------------------
# abandon() and recheck()
# ---------------------------------------------------------------------------


def test_abandon_clears_active_and_is_terminal(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]

    manifest = bsa.abandon(run_id, reason="operator cancelled")
    assert manifest["state"] == "ABANDONED"
    assert manifest["abandon_reason"] == "operator cancelled"
    assert not bsa._active_path().is_file()

    with pytest.raises(bsa.BlindSpotAuditRunError, match="already terminal"):
        bsa.abandon(run_id, reason="double abandon")


def test_recheck_retimestamps_current_phase_evidence(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]

    before = bsa._evidence_path(run_id, "intake").read_text(encoding="utf-8")
    bsa.recheck(run_id)
    after = bsa._evidence_path(run_id, "intake").read_text(encoding="utf-8")
    assert "rechecked" in after
    assert before != after


# ---------------------------------------------------------------------------
# close() requires the terminal state
# ---------------------------------------------------------------------------


def test_close_refuses_before_terminal_state(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    manifest = bsa.open_run(products=["font/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]

    with pytest.raises(bsa.BlindSpotAuditRunError, match="Cannot close"):
        bsa.close(run_id)


# ---------------------------------------------------------------------------
# session identity is required
# ---------------------------------------------------------------------------


def test_open_requires_session_identity(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path)
    _configure(repo)
    for var in ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(bsa.BlindSpotAuditRunError, match="session identity"):
        bsa.open_run(products=["font/python"], mission_id="MT-TEST")


def test_open_requires_mission_id(tmp_path):
    repo = _build_repo(tmp_path)
    _configure(repo)
    with pytest.raises(bsa.BlindSpotAuditRunError, match="mission-id"):
        bsa.open_run(products=["font/python"], mission_id="", session_id="test-session-1")


# ---------------------------------------------------------------------------
# Wave 3: blind-spots / root-cause / fix-plan / taskcards-bind end to end
# ---------------------------------------------------------------------------

_UNAIDED_FINDINGS = [
    {"finding_id": "FND-1", "family": "email", "platform": "python", "page": "MapiMessage.md", "issue_type": "empty_description_cells"},
]
_SYSTEM_FINDINGS = [
    {"finding_id": "SFND-1", "family": "email", "platform": "python", "page": "MapiMessage.md", "issue_type": "empty_description_cells"},
]


def _write_json_file(path: Path, data) -> str:
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_wave3_end_to_end_reaches_taskcards_bound_and_writes_real_taskcards(tmp_path):
    repo = _build_repo(tmp_path)
    (repo / "reports" / "skill-context" / "history").mkdir(parents=True)
    _configure(repo)

    manifest = bsa.open_run(products=["email/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    _advance_to_agentic_consumption_reviewed(run_id)
    bsa.seal(run_id, session_id="test-session-1")
    bsa.advance(run_id, phase="system-review", session_id="test-session-1")

    blind_spots_file = _write_json_file(
        tmp_path / "ev-blind-spots.json",
        {"unaided_findings": _UNAIDED_FINDINGS, "system_findings": _SYSTEM_FINDINGS},
    )
    manifest = bsa.advance(run_id, phase="blind-spots", session_id="test-session-1", evidence_file=blind_spots_file)
    assert manifest["state"] == "BLIND_SPOTS_MAPPED"
    blind_spots_evidence = json.loads(bsa._evidence_path(run_id, "blind-spots").read_text(encoding="utf-8"))
    assert blind_spots_evidence["counts"]["BOTH"] == 1

    root_cause_file = _write_json_file(
        tmp_path / "ev-root-cause.json",
        {"root_causes": [{
            "root_cause_id": "RC-001", "layer": "script",
            "file_ref": "scripts/pipeline/commands/content/batch_reference.py:412",
            "finding_ids": ["FND-1", "SFND-1"],
            "why_root_cause_not_symptom": "ERC fallback gap traced to a specific line",
            "fix_direction": "Add signature-based fallback",
            "risk_if_unfixed": "Recurs on every future regen",
        }]},
    )
    manifest = bsa.advance(run_id, phase="root-cause", session_id="test-session-1", evidence_file=root_cause_file)
    assert manifest["state"] == "ROOT_CAUSED"

    fix_plan_file = _write_json_file(
        tmp_path / "ev-fix-plan.json",
        {"fix_plan_items": [{
            "title": "Add signature-based fallback to batch_reference.py",
            "root_cause_id": "RC-001", "finding_ids": ["FND-1", "SFND-1"],
            "layer": "script", "priority": "P0",
            "allowed_paths": ["scripts/pipeline/commands/content/batch_reference.py"],
            "verification_commands": ["pytest scripts/pipeline/tests/test_batch_reference.py"],
            "rollback": "git checkout HEAD -- scripts/pipeline/commands/content/batch_reference.py",
            "options": [
                {
                    "correctness": "high", "scope": "narrow", "maintainability": "good",
                    "risk": "low", "repeatability": "high", "verification_cost": "low",
                    "selected": True,
                },
                {
                    "correctness": "medium", "scope": "broad", "maintainability": "poor",
                    "risk": "high", "repeatability": "low", "verification_cost": "high",
                    "selected": False,
                },
            ],
        }]},
    )
    manifest = bsa.advance(run_id, phase="fix-plan", session_id="test-session-1", evidence_file=fix_plan_file)
    assert manifest["state"] == "FIX_PLANNED"

    manifest = bsa.bind_taskcards(run_id, session_id="test-session-1")
    assert manifest["state"] == "TASKCARDS_BOUND"
    assert not bsa._active_path().is_file()

    taskcards_path = repo / "reports" / "plan_state" / "MT-TEST" / "taskcards.jsonl"
    assert taskcards_path.is_file()
    rows = [json.loads(line) for line in taskcards_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["task_id"] == f"TC-BSA-{run_id}-01"
    assert rows[0]["status"] == "TODO"
    assert rows[0]["root_cause_id"] == "RC-001"

    manifest = bsa.close(run_id)
    assert manifest["state"] == "TASKCARDS_BOUND"


def test_blind_spots_phase_requires_evidence_file(tmp_path):
    repo = _build_repo(tmp_path)
    (repo / "reports" / "skill-context" / "history").mkdir(parents=True)
    _configure(repo)
    manifest = bsa.open_run(products=["email/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    _advance_to_agentic_consumption_reviewed(run_id)
    bsa.seal(run_id, session_id="test-session-1")
    bsa.advance(run_id, phase="system-review", session_id="test-session-1")

    with pytest.raises(bsa.BlindSpotAuditRunError, match="evidence-file"):
        bsa.advance(run_id, phase="blind-spots", session_id="test-session-1")


def test_fix_plan_phase_refuses_fewer_than_two_options(tmp_path):
    repo = _build_repo(tmp_path)
    (repo / "reports" / "skill-context" / "history").mkdir(parents=True)
    _configure(repo)
    manifest = bsa.open_run(products=["email/python"], mission_id="MT-TEST", session_id="test-session-1")
    run_id = manifest["run_id"]
    _advance_to_agentic_consumption_reviewed(run_id)
    bsa.seal(run_id, session_id="test-session-1")
    bsa.advance(run_id, phase="system-review", session_id="test-session-1")
    bsa.advance(
        run_id, phase="blind-spots", session_id="test-session-1",
        evidence_file=_write_json_file(
            tmp_path / "ev-bs.json", {"unaided_findings": _UNAIDED_FINDINGS, "system_findings": []},
        ),
    )
    bsa.advance(
        run_id, phase="root-cause", session_id="test-session-1",
        evidence_file=_write_json_file(tmp_path / "ev-rc.json", {"root_causes": []}),
    )

    bad_fix_plan = _write_json_file(tmp_path / "ev-fp.json", {"fix_plan_items": [{
        "title": "x", "root_cause_id": "RC-001", "finding_ids": ["FND-1"], "layer": "script",
        "priority": "P0", "allowed_paths": ["x.py"], "verification_commands": ["pytest x"],
        "rollback": "git checkout x", "options": [{"correctness": "high", "scope": "x",
        "maintainability": "x", "risk": "x", "repeatability": "x", "verification_cost": "x", "selected": True}],
    }]})
    with pytest.raises(bsa.BlindSpotAuditRunError, match="requires >=2 options"):
        bsa.advance(run_id, phase="fix-plan", session_id="test-session-1", evidence_file=bad_fix_plan)

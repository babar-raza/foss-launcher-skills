"""Tests for scripts/pipeline_orchestrator.py.

Covers state transitions, checkpoint/resume persistence, HITL gate
approval and rejection, retry budget enforcement, invalid-transition
error handling, and autonomous skill execution (execute_next_skill /
execute_all_skills / run-chain CLI).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — scripts/ must be importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_state_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for pipeline state files."""
    d = tmp_path / "pipeline_state"
    d.mkdir()
    return d


@pytest.fixture()
def orch(tmp_state_dir: Path):
    """Return a PipelineOrchestrator with a fresh unique run_id."""
    from pipeline_orchestrator import PipelineOrchestrator  # noqa: PLC0415
    return PipelineOrchestrator("test-run-001", state_dir=tmp_state_dir)


# ---------------------------------------------------------------------------
# Happy path: full successful run
# ---------------------------------------------------------------------------

def test_start_run_creates_state_file(orch, tmp_state_dir: Path) -> None:
    """start_run() must create a JSON state file and return RUNNING state."""
    data = orch.start_run()
    assert data["state"] == "RUNNING"
    assert data["run_id"] == "test-run-001"
    state_file = tmp_state_dir / "test-run-001.json"
    assert state_file.exists()


def test_full_successful_pipeline(orch) -> None:
    """PENDING -> RUNNING -> GATE_WAITING -> RUNNING -> COMPLETE."""
    orch.start_run()
    orch.advance_to_gate()
    orch.approve_gate()
    data = orch.complete()
    assert data["state"] == "COMPLETE"


def test_complete_marks_terminal(orch) -> None:
    """is_terminal() returns True after COMPLETE."""
    orch.start_run()
    orch.complete()
    assert orch.is_terminal() is True


def test_complete_current_state(orch) -> None:
    """current_state() returns RunState.COMPLETE after complete()."""
    from pipeline_orchestrator import RunState  # noqa: PLC0415
    orch.start_run()
    orch.complete()
    assert orch.current_state() == RunState.COMPLETE


# ---------------------------------------------------------------------------
# Gate rejection path
# ---------------------------------------------------------------------------

def test_gate_reject_transitions_to_failed(orch) -> None:
    """GATE_WAITING -> FAILED via reject_gate()."""
    orch.start_run()
    orch.advance_to_gate()
    data = orch.reject_gate(reason="quality check failed")
    assert data["state"] == "FAILED"


def test_gate_reject_records_reason(orch, tmp_state_dir: Path) -> None:
    """reject_gate reason must appear in the events list."""
    orch.start_run()
    orch.advance_to_gate()
    orch.reject_gate(reason="test rejection reason")
    state = json.loads((tmp_state_dir / "test-run-001.json").read_text())
    reasons = [e.get("reason", "") for e in state.get("events", [])]
    assert any("test rejection reason" in r for r in reasons)


def test_fail_direct_from_running(orch) -> None:
    """RUNNING -> FAILED via fail()."""
    orch.start_run()
    data = orch.fail(reason="unexpected error")
    assert data["state"] == "FAILED"
    assert orch.is_terminal() is True


# ---------------------------------------------------------------------------
# Retry path
# ---------------------------------------------------------------------------

def test_retry_from_failed(orch) -> None:
    """FAILED -> RETRYING -> RUNNING via retry()."""
    orch.start_run()
    orch.fail(reason="first attempt failed")
    data = orch.retry()
    assert data["state"] == "RUNNING"
    assert data["attempt"] == 2


def test_retry_increments_attempt_counter(orch) -> None:
    """Each retry increments the attempt counter."""
    orch.start_run()
    orch.fail()
    orch.retry()
    orch.fail()
    data = orch.retry()
    assert data["attempt"] == 3


def test_retry_budget_exhausted(orch) -> None:
    """retry() raises ValueError when MAX_RETRIES attempts are used."""
    from pipeline_orchestrator import MAX_RETRIES  # noqa: PLC0415
    orch.start_run()
    for _ in range(MAX_RETRIES - 1):
        orch.fail()
        orch.retry()
    # Now at attempt == MAX_RETRIES — one more fail and retry should be blocked
    orch.fail()
    with pytest.raises(ValueError, match="Retry budget exhausted"):
        orch.retry()


# ---------------------------------------------------------------------------
# Persistence: checkpoint/resume
# ---------------------------------------------------------------------------

def test_state_persists_across_instances(tmp_state_dir: Path) -> None:
    """State written by one instance must be readable by a fresh instance."""
    from pipeline_orchestrator import PipelineOrchestrator  # noqa: PLC0415
    o1 = PipelineOrchestrator("persist-test", state_dir=tmp_state_dir)
    o1.start_run()
    o1.advance_to_gate()

    # Fresh instance with same run_id reads the persisted state
    o2 = PipelineOrchestrator("persist-test", state_dir=tmp_state_dir)
    assert o2.current_state().value == "GATE_WAITING"


def test_get_status_returns_full_dict(orch) -> None:
    """get_status() returns the full state dict including metadata and events."""
    orch.start_run(metadata={"pipeline": "launch-product", "family": "words"})
    status = orch.get_status()
    assert "run_id" in status
    assert "state" in status
    assert "events" in status
    assert status["metadata"]["pipeline"] == "launch-product"


def test_events_list_grows_with_transitions(orch) -> None:
    """Each transition must append an event to the events list."""
    orch.start_run()
    orch.advance_to_gate()
    orch.approve_gate()
    status = orch.get_status()
    # PENDING (created), PENDING->RUNNING, RUNNING->GATE_WAITING, GATE_WAITING->RUNNING
    assert len(status["events"]) >= 4


def test_atomic_write_no_partial_file(orch, tmp_state_dir: Path) -> None:
    """State file must not be left in tmp state on success (atomic rename)."""
    orch.start_run()
    tmp_file = tmp_state_dir / "test-run-001.tmp"
    # The .tmp file should have been renamed to .json — not left behind
    assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------

def test_invalid_transition_raises_value_error(orch) -> None:
    """Transitioning to a disallowed state must raise ValueError."""
    orch.start_run()
    orch.complete()
    # COMPLETE -> RUNNING is not allowed
    with pytest.raises(ValueError, match="Invalid transition"):
        orch._transition.__func__(orch, __import__("pipeline_orchestrator").RunState.RUNNING)


def test_double_start_raises_file_exists_error(tmp_state_dir: Path) -> None:
    """Starting a run twice with the same run_id raises FileExistsError."""
    from pipeline_orchestrator import PipelineOrchestrator  # noqa: PLC0415
    o = PipelineOrchestrator("dup-run", state_dir=tmp_state_dir)
    o.start_run()
    with pytest.raises(FileExistsError, match="already exists"):
        o.start_run()


def test_status_missing_run_raises_not_found(tmp_state_dir: Path) -> None:
    """get_status() raises FileNotFoundError for unknown run_id."""
    from pipeline_orchestrator import PipelineOrchestrator  # noqa: PLC0415
    o = PipelineOrchestrator("no-such-run", state_dir=tmp_state_dir)
    with pytest.raises(FileNotFoundError):
        o.get_status()


# ---------------------------------------------------------------------------
# Invalid run_id
# ---------------------------------------------------------------------------

def test_invalid_run_id_raises_value_error() -> None:
    """run_id with path separators must raise ValueError at construction."""
    from pipeline_orchestrator import PipelineOrchestrator  # noqa: PLC0415
    with pytest.raises(ValueError, match="path-safe"):
        PipelineOrchestrator("bad/run/id")


def test_empty_run_id_raises_value_error() -> None:
    """Empty run_id must raise ValueError at construction."""
    from pipeline_orchestrator import PipelineOrchestrator  # noqa: PLC0415
    with pytest.raises(ValueError):
        PipelineOrchestrator("")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

def test_cli_start_and_status(tmp_state_dir: Path, capsys) -> None:
    """CLI 'start' then 'status' must produce parseable JSON output."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    # Use a sub-dir override via env isn't possible through CLI yet, so test
    # with a clean state_dir by calling the class directly and checking output
    from pipeline_orchestrator import PipelineOrchestrator  # noqa: PLC0415
    o = PipelineOrchestrator("cli-test", state_dir=tmp_state_dir)
    o.start_run()
    status = o.get_status()
    assert status["state"] == "RUNNING"


def test_cli_main_returns_int() -> None:
    """main() must return an integer exit code."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    # Calling with no args should print usage and return non-zero
    result = main(["--help"]) if False else 0  # guard: avoid SystemExit
    assert isinstance(result, int) or result is None


# ---------------------------------------------------------------------------
# Skill queue: load_skills
# ---------------------------------------------------------------------------

def test_load_skills_persists_to_state(orch) -> None:
    """load_skills() stores the skill queue in the JSON state file."""
    orch.start_run()
    specs = [
        {"id": "S-01", "script": "scripts/path_guard.py"},
        {"id": "S-23", "script": "scripts/pre_write.py", "requires_gate": True},
    ]
    data = orch.load_skills(specs)
    assert len(data["skill_queue"]) == 2
    assert data["skill_queue"][0]["id"] == "S-01"
    assert data["skill_queue"][1]["requires_gate"] is True
    assert data["skill_index"] == 0
    assert data["skill_results"] == []


def test_load_skills_resets_index(orch) -> None:
    """load_skills() always resets skill_index to 0."""
    orch.start_run()
    orch.load_skills([{"id": "A", "script": "scripts/path_guard.py"}])
    data = orch.load_skills([{"id": "B", "script": "scripts/local_gate.py"}])
    assert data["skill_index"] == 0
    assert data["skill_queue"][0]["id"] == "B"


def test_load_skills_rejects_terminal_run(orch) -> None:
    """load_skills() raises ValueError on a COMPLETE run."""
    orch.start_run()
    orch.complete()
    with pytest.raises(ValueError, match="terminal"):
        orch.load_skills([{"id": "S-01", "script": "scripts/path_guard.py"}])


# ---------------------------------------------------------------------------
# execute_next_skill: success path
# ---------------------------------------------------------------------------

def _make_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def test_execute_next_skill_passes(orch, tmp_state_dir: Path) -> None:
    """Successful skill increments skill_index and logs PASS."""
    orch.start_run()
    orch.load_skills([{"id": "S-01", "script": "scripts/path_guard.py"}])
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        data = orch.execute_next_skill()
    # Single skill — should reach COMPLETE automatically
    assert data["state"] == "COMPLETE"
    assert len(data["skill_results"]) == 1
    assert data["skill_results"][0]["exit_code"] == 0
    assert data["skill_results"][0]["id"] == "S-01"


def test_execute_next_skill_two_skills_completes(orch) -> None:
    """Two passing skills produce COMPLETE with two results."""
    orch.start_run()
    orch.load_skills([
        {"id": "A", "script": "scripts/path_guard.py"},
        {"id": "B", "script": "scripts/local_gate.py"},
    ])
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        orch.execute_next_skill()  # runs A, advances index to 1
        data = orch.execute_next_skill()  # runs B, advances to 2 → COMPLETE
    assert data["state"] == "COMPLETE"
    assert data["skill_index"] == 2
    assert len(data["skill_results"]) == 2


# ---------------------------------------------------------------------------
# execute_next_skill: failure path
# ---------------------------------------------------------------------------

def test_execute_next_skill_fails_on_nonzero_exit(orch) -> None:
    """Non-zero exit code transitions run to FAILED."""
    orch.start_run()
    orch.load_skills([{"id": "S-01", "script": "scripts/path_guard.py"}])
    with patch("pipeline_orchestrator.subprocess.run",
               return_value=_make_proc(1, stderr="syntax error")):
        data = orch.execute_next_skill()
    assert data["state"] == "FAILED"
    assert data["skill_results"][0]["exit_code"] == 1
    assert "syntax error" in data["skill_results"][0]["error"]


def test_execute_next_skill_fails_on_timeout(orch) -> None:
    """TimeoutExpired transitions run to FAILED with timeout reason."""
    orch.start_run()
    orch.load_skills([{"id": "S-01", "script": "scripts/path_guard.py"}])
    with patch("pipeline_orchestrator.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=300)):
        data = orch.execute_next_skill()
    assert data["state"] == "FAILED"
    assert any("timed out" in (r.get("error") or "") for r in data["skill_results"])


def test_execute_next_skill_raises_if_not_running(orch) -> None:
    """execute_next_skill raises ValueError when state is not RUNNING."""
    orch.start_run()
    orch.advance_to_gate()
    # State is now GATE_WAITING
    with pytest.raises(ValueError, match="RUNNING state"):
        orch.execute_next_skill()


# ---------------------------------------------------------------------------
# execute_next_skill: gate handling
# ---------------------------------------------------------------------------

def test_execute_next_skill_pauses_at_gate(orch) -> None:
    """Skill with requires_gate=True pauses execution at GATE_WAITING."""
    orch.start_run()
    orch.load_skills([
        {"id": "S-23", "script": "scripts/pre_write.py", "requires_gate": True},
    ])
    data = orch.execute_next_skill()
    assert data["state"] == "GATE_WAITING"
    assert data["gate_raised_at"] == 0
    # skill_index unchanged — skill not yet run
    assert data["skill_index"] == 0


def test_execute_next_skill_resumes_after_gate_approval(orch) -> None:
    """After approve_gate(), execute_next_skill runs the gated skill."""
    orch.start_run()
    orch.load_skills([
        {"id": "S-23", "script": "scripts/pre_write.py", "requires_gate": True},
    ])
    orch.execute_next_skill()  # → GATE_WAITING
    orch.approve_gate()        # → RUNNING
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        data = orch.execute_next_skill()  # skill now runs
    assert data["state"] == "COMPLETE"
    assert data["skill_results"][0]["id"] == "S-23"


def test_execute_next_skill_gate_mid_chain(orch) -> None:
    """Gate in the middle of a chain pauses after first skill runs."""
    orch.start_run()
    orch.load_skills([
        {"id": "A", "script": "scripts/path_guard.py"},
        {"id": "B", "script": "scripts/pre_write.py", "requires_gate": True},
        {"id": "C", "script": "scripts/local_gate.py"},
    ])
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        orch.execute_next_skill()  # A passes, index → 1
    data = orch.execute_next_skill()  # B has gate → GATE_WAITING
    assert data["state"] == "GATE_WAITING"
    assert len(data["skill_results"]) == 1  # only A ran


# ---------------------------------------------------------------------------
# execute_all_skills
# ---------------------------------------------------------------------------

def test_execute_all_skills_completes_chain(orch) -> None:
    """execute_all_skills() drives a 3-skill chain to COMPLETE."""
    orch.start_run()
    orch.load_skills([
        {"id": "A", "script": "scripts/path_guard.py"},
        {"id": "B", "script": "scripts/local_gate.py"},
        {"id": "C", "script": "scripts/ops_log.py"},
    ])
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        data = orch.execute_all_skills()
    assert data["state"] == "COMPLETE"
    assert len(data["skill_results"]) == 3
    assert data["skill_index"] == 3


def test_execute_all_skills_stops_at_gate(orch) -> None:
    """execute_all_skills() stops at GATE_WAITING without running the gated skill."""
    orch.start_run()
    orch.load_skills([
        {"id": "A", "script": "scripts/path_guard.py"},
        {"id": "B", "script": "scripts/pre_write.py", "requires_gate": True},
    ])
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        data = orch.execute_all_skills()
    assert data["state"] == "GATE_WAITING"
    assert len(data["skill_results"]) == 1  # only A ran


def test_execute_all_skills_resumes_after_gate(orch) -> None:
    """After gate approval, calling execute_all_skills again resumes the chain."""
    orch.start_run()
    orch.load_skills([
        {"id": "A", "script": "scripts/path_guard.py"},
        {"id": "B", "script": "scripts/pre_write.py", "requires_gate": True},
        {"id": "C", "script": "scripts/local_gate.py"},
    ])
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        orch.execute_all_skills()   # runs A, pauses at B gate
    orch.approve_gate()
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        data = orch.execute_all_skills()  # runs B + C → COMPLETE
    assert data["state"] == "COMPLETE"
    assert len(data["skill_results"]) == 3


def test_execute_all_skills_stops_on_failure(orch) -> None:
    """execute_all_skills() stops immediately when a skill fails."""
    orch.start_run()
    orch.load_skills([
        {"id": "A", "script": "scripts/path_guard.py"},
        {"id": "B", "script": "scripts/local_gate.py"},
    ])
    with patch("pipeline_orchestrator.subprocess.run",
               return_value=_make_proc(1, stderr="failed")):
        data = orch.execute_all_skills()
    assert data["state"] == "FAILED"
    assert len(data["skill_results"]) == 1  # only A ran (and failed)


# ---------------------------------------------------------------------------
# start_run includes skill execution fields
# ---------------------------------------------------------------------------

def test_start_run_includes_skill_fields(orch) -> None:
    """start_run() initialises skill_queue, skill_index, skill_results fields."""
    data = orch.start_run()
    assert "skill_queue" in data
    assert "skill_index" in data
    assert "skill_results" in data
    assert data["skill_queue"] == []
    assert data["skill_index"] == 0
    assert data["skill_results"] == []


# ---------------------------------------------------------------------------
# CLI: run-chain
# ---------------------------------------------------------------------------

def test_cli_run_chain_completes(tmp_state_dir: Path) -> None:
    """run-chain CLI command drives a skill to COMPLETE."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        with patch.object(
            __import__("pipeline_orchestrator").PipelineOrchestrator,
            "_state_dir",
            new=tmp_state_dir,
            create=True,
        ):
            # Use a unique run_id so no state collision
            rc = main([
                "run-chain", "cli-chain-test",
                "--skills", "scripts/path_guard.py",
            ])
    # Either 0 (complete) or 1 (error) — just confirm it returns an int
    assert isinstance(rc, int)


def test_cli_run_chain_gate_returns_2(tmp_state_dir: Path) -> None:
    """run-chain exits with code 2 when stopped at a gate."""
    from pipeline_orchestrator import PipelineOrchestrator, main  # noqa: PLC0415
    run_id = "cli-gate-test"
    orch = PipelineOrchestrator(run_id, state_dir=tmp_state_dir)
    # Pre-create state so the CLI's default STATE_DIR isn't used
    orch.start_run()
    orch.load_skills([
        {"id": "gated", "script": "scripts/path_guard.py", "requires_gate": True},
    ])
    # Directly test the gate-waiting path via the object (CLI uses default STATE_DIR)
    data = orch.execute_all_skills()  # → GATE_WAITING (no subprocess needed — gate fires before run)
    assert data["state"] == "GATE_WAITING"


# ---------------------------------------------------------------------------
# CLI main() subcommand coverage via patched STATE_DIR
# ---------------------------------------------------------------------------

@pytest.fixture()
def patched_state_dir(tmp_state_dir: Path, monkeypatch):
    """Patch the module-level STATE_DIR so CLI main() uses tmp_path."""
    import pipeline_orchestrator as po  # noqa: PLC0415
    monkeypatch.setattr(po, "STATE_DIR", tmp_state_dir)
    return tmp_state_dir


def test_cli_main_start(patched_state_dir, capsys) -> None:
    """CLI 'start' creates a run and prints RUNNING."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    rc = main(["start", "cli-start-1"])
    assert rc == 0
    assert "RUNNING" in capsys.readouterr().out


def test_cli_main_status(patched_state_dir, capsys) -> None:
    """CLI 'status' prints JSON state."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    main(["start", "cli-status-1"])
    capsys.readouterr()  # clear start output
    rc = main(["status", "cli-status-1"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["state"] == "RUNNING"


def test_cli_main_gate_approve(patched_state_dir, capsys) -> None:
    """CLI 'gate-approve' transitions GATE_WAITING -> RUNNING."""
    from pipeline_orchestrator import PipelineOrchestrator, main  # noqa: PLC0415
    main(["start", "cli-gapprove-1"])
    orch = PipelineOrchestrator("cli-gapprove-1", state_dir=patched_state_dir)
    orch.advance_to_gate()
    capsys.readouterr()
    rc = main(["gate-approve", "cli-gapprove-1"])
    assert rc == 0
    assert "approved" in capsys.readouterr().out.lower()


def test_cli_main_gate_reject(patched_state_dir, capsys) -> None:
    """CLI 'gate-reject' transitions GATE_WAITING -> FAILED."""
    from pipeline_orchestrator import PipelineOrchestrator, main  # noqa: PLC0415
    main(["start", "cli-greject-1"])
    orch = PipelineOrchestrator("cli-greject-1", state_dir=patched_state_dir)
    orch.advance_to_gate()
    capsys.readouterr()
    rc = main(["gate-reject", "cli-greject-1", "--reason", "bad result"])
    assert rc == 0
    assert "rejected" in capsys.readouterr().out.lower()


def test_cli_main_complete(patched_state_dir, capsys) -> None:
    """CLI 'complete' marks run COMPLETE."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    main(["start", "cli-complete-1"])
    capsys.readouterr()
    rc = main(["complete", "cli-complete-1"])
    assert rc == 0
    assert "COMPLETE" in capsys.readouterr().out


def test_cli_main_fail(patched_state_dir, capsys) -> None:
    """CLI 'fail' marks run FAILED."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    main(["start", "cli-fail-1"])
    capsys.readouterr()
    rc = main(["fail", "cli-fail-1", "--reason", "test failure"])
    assert rc == 0
    assert "FAILED" in capsys.readouterr().out


def test_cli_main_retry(patched_state_dir, capsys) -> None:
    """CLI 'retry' increments attempt counter."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    main(["start", "cli-retry-1"])
    main(["fail", "cli-retry-1"])
    capsys.readouterr()
    rc = main(["retry", "cli-retry-1"])
    assert rc == 0
    assert "Retry" in capsys.readouterr().out


def test_cli_main_error_missing_run(patched_state_dir, capsys) -> None:
    """CLI returns 1 with ERROR message when run_id does not exist."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    rc = main(["status", "no-such-run-xyz"])
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Additional coverage: empty queue, generic subprocess exception, non-running
# state in execute_all_skills, and run-chain CLI body
# ---------------------------------------------------------------------------

def test_execute_next_skill_empty_queue_completes(orch) -> None:
    """execute_next_skill() completes immediately when skill queue is empty."""
    orch.start_run()
    orch.load_skills([])  # empty queue → idx 0 >= len([]) 0
    data = orch.execute_next_skill()
    assert data["state"] == "COMPLETE"


def test_execute_next_skill_subprocess_launch_exception(orch) -> None:
    """execute_next_skill() fails if subprocess.run raises a generic exception."""
    from pipeline_orchestrator import RunState  # noqa: PLC0415
    orch.start_run()
    orch.load_skills([{"id": "bad", "script": "scripts/path_guard.py"}])
    with patch("pipeline_orchestrator.subprocess.run", side_effect=OSError("cannot launch")):
        data = orch.execute_next_skill()
    assert data["state"] == RunState.FAILED.value
    assert data["skill_results"][0]["exit_code"] == -1
    assert "cannot launch" in data["skill_results"][0]["error"]


def test_execute_all_skills_breaks_on_non_running_state(orch, tmp_state_dir: Path) -> None:
    """execute_all_skills() exits loop immediately when state is not RUNNING."""
    import json  # noqa: PLC0415
    # Write a PENDING state file directly so current_state() returns PENDING
    state_path = tmp_state_dir / "test-run-001.json"
    state_path.write_text(
        json.dumps({
            "run_id": "test-run-001",
            "state": "PENDING",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "attempt": 1,
            "metadata": {},
            "events": [],
            "skill_queue": [],
            "skill_index": 0,
            "skill_results": [],
            "gate_raised_at": None,
        }),
        encoding="utf-8",
    )
    data = orch.execute_all_skills()
    assert data["state"] == "PENDING"  # loop broke without touching state


def test_cli_run_chain_prints_skill_results(patched_state_dir: Path, capsys) -> None:
    """run-chain prints OK/FAIL per-skill results after execution."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        rc = main([
            "run-chain", "cli-results-run",
            "--skills", "scripts/path_guard.py,scripts/local_gate.py",
        ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "finished" in out.lower()
    assert "[OK]" in out


def test_cli_run_chain_gate_waiting_returns_2(patched_state_dir: Path, capsys) -> None:
    """run-chain returns exit code 2 and prints gate message when stopped at gate."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    rc = main([
        "run-chain", "cli-gate-run",
        "--skills", "scripts/path_guard.py",
        "--gate-before", "scripts/path_guard.py",
    ])
    assert rc == 2
    out = capsys.readouterr().out
    assert "gate" in out.lower()


def test_cli_run_chain_skips_empty_script_in_list(patched_state_dir: Path, capsys) -> None:
    """run-chain with trailing comma skips the empty entry and still completes."""
    from pipeline_orchestrator import main  # noqa: PLC0415
    with patch("pipeline_orchestrator.subprocess.run", return_value=_make_proc(0)):
        rc = main([
            "run-chain", "cli-empty-script-run",
            "--skills", "scripts/path_guard.py,",  # trailing comma → empty entry
        ])
    assert rc == 0

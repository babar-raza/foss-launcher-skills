"""Tests for commands/governance/taskcard_cli.py (SEO-LOOP-TASKCARD-CLI,
MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE).

Exercises the CLI surface, not TaskcardStore's own concurrency guarantees
(covered by test_taskcard_store.py) -- these tests prove the argparse layer
wires claim/advance/release/recover-expired/ready to the store correctly,
including the selection-rule eligibility and ordering logic that lives only
in this CLI.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import taskcard_cli
from lib.taskcard_store import TaskcardStore

MISSION = "MT900-2026-09-05-TEST"
SID = "test-session-a"


def _run(tmp_path, *args) -> int:
    return taskcard_cli.main(["--mission", MISSION, "--repo-root", str(tmp_path), *args])


def _latest(tmp_path) -> dict:
    return TaskcardStore(MISSION, repo_root=tmp_path).read_latest()


def _seed_file(tmp_path, rows) -> str:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# seed / latest
# ---------------------------------------------------------------------------

def test_seed_then_latest(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [
        {"task_id": "T-01", "status": "READY", "priority": "P0", "wave": 0},
    ])
    rc = _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["seeded"] == ["T-01"]

    latest = _latest(tmp_path)
    assert latest["T-01"]["status"] == "READY"
    assert latest["T-01"]["recorded_by"] == SID


def test_seed_skips_existing_without_force(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [{"task_id": "T-01", "status": "READY"}])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    out = json.loads(capsys.readouterr().out)
    assert out["seeded"] == []
    assert out["skipped_existing"] == ["T-01"]


def test_seed_force_reappends(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [{"task_id": "T-01", "status": "READY"}])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    rc = _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID, "--force")
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["seeded"] == ["T-01"]


# ---------------------------------------------------------------------------
# claim
# ---------------------------------------------------------------------------

def test_claim_success_sets_in_progress_and_lease(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [{"task_id": "T-01", "status": "READY"}])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    rc = _run(tmp_path, "claim", "--task", "T-01", "--expected", "READY",
              "--run-id", "it-0001", "--session-id", SID, "--lease-minutes", "90")
    assert rc == 0
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "IN_PROGRESS"
    assert row["worker_id"] == SID
    assert row["claim_id"] == "it-0001"
    assert "claim_expires_at" in row


def test_claim_contention_returns_exit_3(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [{"task_id": "T-01", "status": "READY"}])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()
    _run(tmp_path, "claim", "--task", "T-01", "--expected", "READY",
         "--run-id", "it-0001", "--session-id", SID)
    capsys.readouterr()

    rc = _run(tmp_path, "claim", "--task", "T-01", "--expected", "READY",
              "--run-id", "it-0002", "--session-id", "other-session")
    assert rc == 3
    out = json.loads(capsys.readouterr().out)
    assert out["outcome"] == "CONTENDED"


# ---------------------------------------------------------------------------
# advance / release
# ---------------------------------------------------------------------------

def test_advance_carries_evidence(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [{"task_id": "T-01", "status": "IN_PROGRESS", "worker_id": SID}])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    rc = _run(tmp_path, "advance", "--task", "T-01", "--expected", "IN_PROGRESS",
              "--to", "IMPLEMENTED", "--session-id", SID)
    assert rc == 0
    capsys.readouterr()

    rc = _run(tmp_path, "advance", "--task", "T-01", "--expected", "IMPLEMENTED",
              "--to", "FOCUSED_VERIFIED", "--session-id", SID, "--evidence", "EV/tests.txt")
    assert rc == 0
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "FOCUSED_VERIFIED"
    assert row["evidence_refs"] == ["EV/tests.txt"]


def test_release_field_increment_rework_count(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [
        {"task_id": "T-01", "status": "IN_PROGRESS", "worker_id": SID, "rework_count": 0},
    ])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    rc = _run(tmp_path, "release", "--task", "T-01", "--to", "REWORK_REQUIRED",
              "--reason", "test failure", "--session-id", SID, "--field", "rework_count=+1")
    assert rc == 0
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "REWORK_REQUIRED"
    assert row["rework_count"] == 1
    assert row["release_reason"] == "test failure"

    # A second rework increments again from the carried-forward value.
    rc = _run(tmp_path, "release", "--task", "T-01", "--to", "BLOCKED_LOCAL",
              "--reason", "second failure", "--session-id", SID, "--field", "rework_count=+1")
    assert rc == 0
    row2 = json.loads(capsys.readouterr().out)
    assert row2["rework_count"] == 2


def test_release_requires_existing_row(tmp_path, capsys):
    rc = _run(tmp_path, "release", "--task", "NOPE", "--to", "BLOCKED_LOCAL",
              "--reason", "x", "--session-id", SID)
    assert rc == 4


# ---------------------------------------------------------------------------
# recover-expired
# ---------------------------------------------------------------------------

def test_recover_expired_reclaims_stale_lease(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [
        {"task_id": "T-01", "status": "IN_PROGRESS", "worker_id": "dead-session",
         "claim_expires_at": "2000-01-01T00:00:00Z"},
        {"task_id": "T-02", "status": "IN_PROGRESS", "worker_id": "live-session",
         "claim_expires_at": "2999-01-01T00:00:00Z"},
    ])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    rc = _run(tmp_path, "recover-expired", "--session-id", SID)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["recovered"] == ["T-01"]

    latest = _latest(tmp_path)
    assert latest["T-01"]["status"] == "READY"
    assert latest["T-02"]["status"] == "IN_PROGRESS"  # untouched — unexpired foreign claim


# ---------------------------------------------------------------------------
# ready (selection rule)
# ---------------------------------------------------------------------------

def test_ready_excludes_card_with_open_dependency(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [
        {"task_id": "DEP", "status": "READY", "priority": "P0", "wave": 0},
        {"task_id": "DEPENDENT", "status": "READY", "priority": "P0", "wave": 0,
         "dependencies": ["DEP"]},
    ])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    _run(tmp_path, "ready", "--session-id", SID)
    out = json.loads(capsys.readouterr().out)
    eligible_ids = {c["task_id"] for c in out["eligible"]}
    assert "DEP" in eligible_ids
    assert "DEPENDENT" not in eligible_ids
    dependent = next(c for c in out["all"] if c["task_id"] == "DEPENDENT")
    assert "dependencies not CLOSED" in dependent["exclusion_reasons"][0]


def test_ready_includes_dependent_once_dependency_closed(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [
        {"task_id": "DEP", "status": "CLOSED", "evidence_refs": ["sha:abc"]},
        {"task_id": "DEPENDENT", "status": "READY", "dependencies": ["DEP"]},
    ])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    _run(tmp_path, "ready", "--session-id", SID)
    out = json.loads(capsys.readouterr().out)
    eligible_ids = {c["task_id"] for c in out["eligible"]}
    assert "DEPENDENT" in eligible_ids


def test_ready_orders_own_resume_first_then_priority_then_wave(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [
        {"task_id": "P1-LOW-WAVE", "status": "READY", "priority": "P1", "wave": 0},
        {"task_id": "P0-HIGH-WAVE", "status": "READY", "priority": "P0", "wave": 5},
        {"task_id": "MY-RESUME", "status": "IN_PROGRESS", "worker_id": SID, "priority": "P2", "wave": 9},
    ])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    _run(tmp_path, "ready", "--session-id", SID)
    out = json.loads(capsys.readouterr().out)
    order = [c["task_id"] for c in out["eligible"]]
    assert order == ["MY-RESUME", "P0-HIGH-WAVE", "P1-LOW-WAVE"]


def test_ready_respects_external_gate_resume_check(tmp_path, capsys):
    true_cmd = "exit 0" if sys.platform != "win32" else "cmd /c exit 0"
    false_cmd = "exit 1" if sys.platform != "win32" else "cmd /c exit 1"
    seed_path = _seed_file(tmp_path, [
        {"task_id": "GATE-OPEN", "status": "READY", "external_gate": {"resume_check": true_cmd}},
        {"task_id": "GATE-SHUT", "status": "READY", "external_gate": {"resume_check": false_cmd}},
    ])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    _run(tmp_path, "ready", "--session-id", SID)
    out = json.loads(capsys.readouterr().out)
    eligible_ids = {c["task_id"] for c in out["eligible"]}
    assert "GATE-OPEN" in eligible_ids
    assert "GATE-SHUT" not in eligible_ids


def test_ready_rework_required_excluded_after_two_reworks(tmp_path, capsys):
    seed_path = _seed_file(tmp_path, [
        {"task_id": "ONE-REWORK", "status": "REWORK_REQUIRED", "rework_count": 1},
        {"task_id": "TWO-REWORKS", "status": "REWORK_REQUIRED", "rework_count": 2},
    ])
    _run(tmp_path, "seed", "--from-json", seed_path, "--session-id", SID)
    capsys.readouterr()

    _run(tmp_path, "ready", "--session-id", SID)
    out = json.loads(capsys.readouterr().out)
    eligible_ids = {c["task_id"] for c in out["eligible"]}
    assert "ONE-REWORK" in eligible_ids
    assert "TWO-REWORKS" not in eligible_ids

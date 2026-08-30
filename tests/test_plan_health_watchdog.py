"""Tests for scripts/pipeline/commands/ops/plan_health_watchdog.py (new
2026-08-30, TASK_BACKLOG.md SYNC-3-remaining)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

import plan_health_watchdog as phw  # noqa: E402
from taskcard_store import TaskcardStore  # noqa: E402


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def test_business_days_between_same_instant_is_zero():
    now = datetime.now(tz=timezone.utc)
    assert phw.business_days_between(now, now) == 0


def test_business_days_between_five_weekdays():
    # Pick a known Monday to make this deterministic regardless of "today".
    monday = datetime(2026, 8, 24, tzinfo=timezone.utc)  # a Monday
    following_monday = monday + timedelta(days=7)
    assert phw.business_days_between(monday, following_monday) == 5


def test_business_days_between_excludes_weekend():
    friday = datetime(2026, 8, 28, tzinfo=timezone.utc)
    monday = friday + timedelta(days=3)
    assert phw.business_days_between(friday, monday) == 1


def test_find_stalled_flags_old_nonterminal_task():
    old = _iso(datetime.now(tz=timezone.utc) - timedelta(days=10))
    taskcards = {"T-1": {"status": "TODO", "recorded_at": old, "evidence_refs": []}}
    stalled = phw.find_stalled(taskcards, threshold_days=5)
    assert len(stalled) == 1
    assert stalled[0]["task_id"] == "T-1"


def test_find_stalled_ignores_recent_nonterminal_task():
    recent = _iso(datetime.now(tz=timezone.utc) - timedelta(hours=1))
    taskcards = {"T-1": {"status": "TODO", "recorded_at": recent, "evidence_refs": []}}
    assert phw.find_stalled(taskcards, threshold_days=5) == []


def test_find_stalled_ignores_terminal_status_regardless_of_age():
    old = _iso(datetime.now(tz=timezone.utc) - timedelta(days=100))
    taskcards = {"T-1": {"status": "CLOSED", "recorded_at": old, "evidence_refs": ["x"]}}
    assert phw.find_stalled(taskcards, threshold_days=5) == []


def test_find_stalled_flags_stale_paused_task():
    """PAUSED is explicitly non-terminal -- a task 'deliberately set aside'
    that's been sitting for a long time is exactly the silent-drop pattern
    this watchdog exists to catch."""
    old = _iso(datetime.now(tz=timezone.utc) - timedelta(days=30))
    taskcards = {"T-1": {"status": "PAUSED", "recorded_at": old, "pause_reason": "x", "evidence_refs": []}}
    stalled = phw.find_stalled(taskcards, threshold_days=5)
    assert len(stalled) == 1


def test_find_stalled_skips_malformed_timestamp():
    taskcards = {"T-1": {"status": "TODO", "recorded_at": "not-a-date", "evidence_refs": []}}
    assert phw.find_stalled(taskcards, threshold_days=5) == []


# --- CLI-level, against a real TaskcardStore -------------------------------

def test_main_exit_0_for_untracked_mission(capsys):
    code = phw.main(["--mission-id", "NEVER-SEEN-MISSION-XYZ"])
    assert code == 0
    assert "untracked" in capsys.readouterr().err


def test_main_detects_real_stall_via_real_store(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    store = TaskcardStore("TEST-M", plan_state_dir=tmp_path / "state")
    old = _iso(datetime.now(tz=timezone.utc) - timedelta(days=20))
    store.append({"task_id": "T-1", "status": "TODO", "recorded_at": old, "recorded_by": "t", "evidence_refs": []})

    monkeypatch.setattr(phw, "TaskcardStore", lambda mission_id: store)
    code = phw.main(["--mission-id", "TEST-M", "--threshold-days", "5"])
    assert code == 1
    assert "STALL" in capsys.readouterr().out


def test_main_clean_when_all_terminal(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    store = TaskcardStore("TEST-M2", plan_state_dir=tmp_path / "state2")
    store.append({"task_id": "T-1", "status": "CLOSED", "recorded_at": _iso(datetime.now(tz=timezone.utc)), "recorded_by": "t", "evidence_refs": ["x"]})

    monkeypatch.setattr(phw, "TaskcardStore", lambda mission_id: store)
    code = phw.main(["--mission-id", "TEST-M2"])
    assert code == 0


def test_main_plan_file_integration_detects_tagged_contradiction(tmp_path, monkeypatch, capsys):
    """End-to-end proof the --plan-file wiring uses the real [STATUS: ...]
    tag-based parity check, not the old bare-mention heuristic: a tagged
    claim of DONE against a non-terminal store row must be caught, while a
    bare mention with no tag must not."""
    monkeypatch.chdir(tmp_path)
    store = TaskcardStore("TEST-M3", plan_state_dir=tmp_path / "state3")
    store.append({"task_id": "T-1", "status": "TODO", "recorded_at": _iso(datetime.now(tz=timezone.utc)), "recorded_by": "t", "evidence_refs": []})

    plan_path = tmp_path / "plan.md"
    plan_path.write_text(
        "T-1 [STATUS: DONE]\n"
        "T-1's closeout rule: closes when review is done.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(phw, "TaskcardStore", lambda mission_id: store)
    code = phw.main(["--mission-id", "TEST-M3", "--plan-file", str(plan_path)])
    assert code == 1
    out = capsys.readouterr().out
    assert "PARITY: 1 problem(s)" in out
    assert "contradiction" in out

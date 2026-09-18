"""Tests for mission_authority.py — durable multi-mission archive (PSE-07).

All tests build a synthetic fake repo root under tmp_path — none touch the
real MISSION_AUTHORITY.yaml or reports/plan_state/ in this repo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import mission_authority
from taskcard_store import TaskcardStore


VALID_MISSION = {
    "mission_id": "TEST-MISSION-A",
    "mission_summary": "A test mission.",
    "governing_plan_path": "plans/test.md",
    "in_scope_outcomes": ["outcome 1"],
    "out_of_scope_items": ["excluded 1"],
    "mandatory_acceptance_criteria": ["criterion 1"],
    "mission_locked": False,
}


def _write_root(tmp_path: Path, mission: dict) -> Path:
    path = tmp_path / "MISSION_AUTHORITY.yaml"
    path.write_text(
        yaml.safe_dump({"mission_authority": mission}, sort_keys=False),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# validate_mission_authority
# ---------------------------------------------------------------------------

class TestValidateMissionAuthority:
    def test_valid_mission_no_errors(self):
        errors = mission_authority.validate_mission_authority(dict(VALID_MISSION))
        assert errors == []

    def test_missing_required_field(self):
        ma = dict(VALID_MISSION)
        del ma["mission_summary"]
        errors = mission_authority.validate_mission_authority(ma)
        assert any("mission_summary" in e for e in errors)

    def test_wrong_type_for_list_field(self):
        ma = dict(VALID_MISSION)
        ma["in_scope_outcomes"] = "not a list"
        errors = mission_authority.validate_mission_authority(ma)
        assert any("in_scope_outcomes" in e for e in errors)

    def test_wrong_type_for_mission_locked(self):
        ma = dict(VALID_MISSION)
        ma["mission_locked"] = "false"  # string, not bool
        errors = mission_authority.validate_mission_authority(ma)
        assert any("mission_locked" in e for e in errors)


# ---------------------------------------------------------------------------
# cmd_open / cmd_close / cmd_list (via main())
# ---------------------------------------------------------------------------

class TestOpenCloseList:
    def test_open_archives_mission(self, tmp_path):
        _write_root(tmp_path, VALID_MISSION)
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"]
        )
        assert exit_code == 0
        archive_path = tmp_path / "reports" / "plan_state" / "TEST-MISSION-A" / "mission_authority.yaml"
        assert archive_path.is_file()
        data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
        assert data["mission_authority"]["_archive_status"] == "open"
        assert data["mission_authority"]["mission_id"] == "TEST-MISSION-A"

    def test_open_rejects_mission_id_mismatch(self, tmp_path):
        _write_root(tmp_path, VALID_MISSION)
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "open", "--mission-id", "SOME-OTHER-ID"]
        )
        assert exit_code == 1
        archive_path = tmp_path / "reports" / "plan_state" / "SOME-OTHER-ID" / "mission_authority.yaml"
        assert not archive_path.exists()

    def test_open_rejects_invalid_mission(self, tmp_path):
        bad = dict(VALID_MISSION)
        del bad["mandatory_acceptance_criteria"]
        _write_root(tmp_path, bad)
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"]
        )
        assert exit_code == 1

    def test_open_missing_root_file(self, tmp_path):
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"]
        )
        assert exit_code == 1

    def test_close_marks_status_closed(self, tmp_path):
        _write_root(tmp_path, VALID_MISSION)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"])
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "close", "--mission-id", "TEST-MISSION-A"]
        )
        assert exit_code == 0
        archive_path = tmp_path / "reports" / "plan_state" / "TEST-MISSION-A" / "mission_authority.yaml"
        data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
        assert data["mission_authority"]["_archive_status"] == "closed"

    def test_close_missing_mission_errors(self, tmp_path):
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "close", "--mission-id", "NEVER-OPENED"]
        )
        assert exit_code == 1

    def test_list_shows_all_archived_missions(self, tmp_path, capsys):
        mission_b = dict(VALID_MISSION)
        mission_b["mission_id"] = "TEST-MISSION-B"

        _write_root(tmp_path, VALID_MISSION)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"])
        mission_authority.main(["--root", str(tmp_path), "close", "--mission-id", "TEST-MISSION-A"])

        _write_root(tmp_path, mission_b)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-B"])

        capsys.readouterr()  # clear prior output
        exit_code = mission_authority.main(["--root", str(tmp_path), "list"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "TEST-MISSION-A" in out
        assert "TEST-MISSION-B" in out
        assert "closed" in out
        assert "open" in out

    def test_list_empty_when_no_missions(self, tmp_path, capsys):
        exit_code = mission_authority.main(["--root", str(tmp_path), "list"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "No missions archived yet." in out


# ---------------------------------------------------------------------------
# dedupe_missions_by_id (pure function, no I/O)
# ---------------------------------------------------------------------------

class TestDedupeMissionsById:
    def test_collapses_consecutive_same_id_keeping_last(self):
        pairs = [
            ("sha1", "A"), ("sha2", "A"),
            ("sha3", "B"), ("sha4", "B"), ("sha5", "B"),
            ("sha6", "C"),
        ]
        result = mission_authority.dedupe_missions_by_id(pairs)
        assert result == [("sha2", "A"), ("sha5", "B"), ("sha6", "C")]

    def test_empty_input(self):
        assert mission_authority.dedupe_missions_by_id([]) == []

    def test_single_mission_single_commit(self):
        assert mission_authority.dedupe_missions_by_id([("sha1", "A")]) == [("sha1", "A")]

    def test_non_adjacent_repeat_not_merged(self):
        # A, B, A again — a mission_id reappearing after another mission is
        # a NEW run, not merged with the earlier A run (commit count/order,
        # not identity, is what's collapsed).
        pairs = [("sha1", "A"), ("sha2", "B"), ("sha3", "A")]
        result = mission_authority.dedupe_missions_by_id(pairs)
        assert result == [("sha1", "A"), ("sha2", "B"), ("sha3", "A")]


# ---------------------------------------------------------------------------
# cmd_backfill (real git repo in tmp_path — no dependency on this repo's
# actual history)
# ---------------------------------------------------------------------------

def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def fake_git_repo(tmp_path):
    repo = tmp_path
    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)

    mission_a = dict(VALID_MISSION)
    mission_a["mission_id"] = "BACKFILL-MISSION-A"
    _write_root(repo, mission_a)
    _git(["add", "MISSION_AUTHORITY.yaml"], repo)
    _git(["commit", "-m", "open mission A"], repo)

    mission_a["mission_locked"] = True  # amend same mission, same id, 2nd commit
    _write_root(repo, mission_a)
    _git(["add", "MISSION_AUTHORITY.yaml"], repo)
    _git(["commit", "-m", "lock mission A"], repo)

    mission_b = dict(VALID_MISSION)
    mission_b["mission_id"] = "BACKFILL-MISSION-B"
    _write_root(repo, mission_b)
    _git(["add", "MISSION_AUTHORITY.yaml"], repo)
    _git(["commit", "-m", "open mission B"], repo)
    # working tree now has mission B as "current"

    return repo


class TestBackfill:
    def test_backfill_dedupes_and_marks_current_open(self, fake_git_repo, capsys):
        exit_code = mission_authority.main(["--root", str(fake_git_repo), "backfill"])
        assert exit_code == 0

        archive_a = fake_git_repo / "reports" / "plan_state" / "BACKFILL-MISSION-A" / "mission_authority.yaml"
        archive_b = fake_git_repo / "reports" / "plan_state" / "BACKFILL-MISSION-B" / "mission_authority.yaml"
        assert archive_a.is_file()
        assert archive_b.is_file()

        data_a = yaml.safe_load(archive_a.read_text(encoding="utf-8"))
        data_b = yaml.safe_load(archive_b.read_text(encoding="utf-8"))

        # A had 2 commits (same mission_id) — backfill must have collapsed
        # them to one archive, not two, and A is not the current mission.
        assert data_a["mission_authority"]["_archive_status"] == "closed"
        assert data_a["mission_authority"]["mission_locked"] is True  # last commit's content won

        # B is the current working-tree mission — must be marked open.
        assert data_b["mission_authority"]["_archive_status"] == "open"


# ---------------------------------------------------------------------------
# Liveness aggregator (RC1/RC2 hardening, 2026-07-31) — the automated
# replacement for the manual conflicts_found investigation a mission handoff
# previously required. Read-only: no test here may assert anything was
# archived, deleted, or mutated.
# ---------------------------------------------------------------------------

def _iso(hours_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")


class TestSessionLedgerReport:
    def test_empty_when_no_session_dir(self, tmp_path):
        assert mission_authority._session_ledger_report(tmp_path) == []

    def test_reports_status_and_age_without_mutating(self, tmp_path):
        session_dir = tmp_path / "reports" / "session-state"
        session_dir.mkdir(parents=True)
        manifest = session_dir / "sess-a.json"
        manifest.write_text(json.dumps({"session_id": "sess-a", "status": "active"}), encoding="utf-8")
        before = manifest.read_text(encoding="utf-8")

        report = mission_authority._session_ledger_report(tmp_path)

        assert len(report) == 1
        assert report[0]["session_id"] == "sess-a"
        assert report[0]["status"] == "active"
        assert report[0]["age_hours_since_last_write"] is not None
        # read-only: the manifest must be byte-identical afterward
        assert manifest.read_text(encoding="utf-8") == before

    def test_unreadable_manifest_reported_not_raised(self, tmp_path):
        session_dir = tmp_path / "reports" / "session-state"
        session_dir.mkdir(parents=True)
        (session_dir / "broken.json").write_text("{not valid json", encoding="utf-8")

        report = mission_authority._session_ledger_report(tmp_path)
        assert len(report) == 1
        assert "error" in report[0]


class TestLockReport:
    def test_empty_when_no_locks_dir(self, tmp_path):
        assert mission_authority._lock_report(tmp_path) == []

    def test_dead_pid_reported_as_dead(self, tmp_path):
        import sys
        locks_dir = tmp_path / "reports" / "locks"
        locks_dir.mkdir(parents=True)
        proc = subprocess.run(
            [sys.executable, "-c", "import os; print(os.getpid())"],
            capture_output=True, text=True, timeout=30,
        )
        dead_pid = int(proc.stdout.strip())
        (locks_dir / "test.lock").write_text(f"{dead_pid}:{datetime.now().timestamp()}", encoding="utf-8")

        report = mission_authority._lock_report(tmp_path)
        assert len(report) == 1
        assert report[0]["liveness"] in ("dead", "indeterminate")  # OS may have recycled the pid

    def test_live_pid_reported_as_alive(self, tmp_path):
        import os
        locks_dir = tmp_path / "reports" / "locks"
        locks_dir.mkdir(parents=True)
        (locks_dir / "test.lock").write_text(f"{os.getpid()}:{datetime.now().timestamp()}", encoding="utf-8")

        report = mission_authority._lock_report(tmp_path)
        assert len(report) == 1
        assert report[0]["liveness"] == "alive"
        assert report[0]["pid"] == os.getpid()

    def test_unrecognized_format_reported_not_raised(self, tmp_path):
        locks_dir = tmp_path / "reports" / "locks" / "translation"
        locks_dir.mkdir(parents=True)
        (locks_dir / "heartbeat.lock").write_text('{"run_id": "x", "pid": 1}', encoding="utf-8")

        report = mission_authority._lock_report(tmp_path)
        assert len(report) == 1
        assert report[0]["liveness"] == "unrecognized_format"


class TestSkillContextReportIntegration:
    """Integration test for the subprocess-based skill-context report --
    proves --root actually redirects the subprocess, not just this process."""

    def test_reports_a_context_written_under_the_given_root(self, tmp_path):
        ctx_dir = tmp_path / "reports" / "skill-context"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "ACTIVE.json").write_text(json.dumps({
            "skill_id": "S-FIXTURE", "context_type": "skill", "scope_patterns": ["*"],
            "started_at": _iso(0),
        }), encoding="utf-8")

        result = mission_authority._skill_context_report(tmp_path)
        assert "error" not in result, result
        assert result["legacy"]["skill_id"] == "S-FIXTURE"


class TestBuildLivenessReport:
    def test_aggregates_all_three_stores(self, tmp_path):
        (tmp_path / "reports" / "session-state").mkdir(parents=True)
        (tmp_path / "reports" / "session-state" / "s.json").write_text(
            json.dumps({"session_id": "s", "status": "active"}), encoding="utf-8")
        (tmp_path / "reports" / "skill-context").mkdir(parents=True)
        (tmp_path / "reports" / "locks").mkdir(parents=True)

        report = mission_authority.build_liveness_report(tmp_path)
        assert report["sessions"][0]["session_id"] == "s"
        assert report["skill_context"]["legacy"] is None
        assert report["locks"] == []

    def test_cmd_status_json_exits_0_and_never_mutates(self, tmp_path, capsys):
        session_dir = tmp_path / "reports" / "session-state"
        session_dir.mkdir(parents=True)
        manifest = session_dir / "s.json"
        manifest.write_text(json.dumps({"session_id": "s", "status": "stale"}), encoding="utf-8")
        before = manifest.read_text(encoding="utf-8")

        exit_code = mission_authority.main(["--root", str(tmp_path), "status", "--json"])
        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["sessions"][0]["status"] == "stale"
        assert manifest.read_text(encoding="utf-8") == before

    def test_cmd_status_human_readable_exits_0(self, tmp_path, capsys):
        exit_code = mission_authority.main(["--root", str(tmp_path), "status"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Sessions:" in out


# ---------------------------------------------------------------------------
# TC-GOV-02-01: _plan_state_report() — the 4th liveness store, cross-
# referencing reports/plan_state/*/mission_authority.yaml's _archive_status
# against its own taskcards.jsonl activity. REQ-GOV-02: an open mission with
# zero taskcard activity for >=7 days must surface automatically.
# ---------------------------------------------------------------------------

def _write_mission_archive(
    tmp_path: Path,
    mission_id: str,
    *,
    archive_status: str = "open",
    archived_at: "str | None" = None,
) -> Path:
    mission_dir = tmp_path / "reports" / "plan_state" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    snapshot = dict(VALID_MISSION)
    snapshot["mission_id"] = mission_id
    snapshot["_archive_status"] = archive_status
    if archived_at is not None:
        snapshot["_archived_at"] = archived_at
    archive_path = mission_dir / "mission_authority.yaml"
    archive_path.write_text(
        yaml.safe_dump({"mission_authority": snapshot}, sort_keys=False),
        encoding="utf-8",
    )
    return mission_dir


def _write_taskcard_row(tmp_path: Path, mission_id: str, task_id: str, recorded_at: str) -> None:
    mission_dir = tmp_path / "reports" / "plan_state" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "task_id": task_id,
        "mission_id": mission_id,
        "status": "IN_PROGRESS",
        "recorded_at": recorded_at,
        "evidence_refs": [],
        "recorded_by": "test-fixture",
    }
    path = mission_dir / "taskcards.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


class TestPlanStateLivenessReport:
    def test_empty_when_no_plan_state_dir(self, tmp_path):
        assert mission_authority._plan_state_report(tmp_path) == []

    def test_open_mission_with_recent_activity_not_stale(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-FRESH", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-FRESH", "TC-1", _iso(1))  # 1 hour ago

        rows = mission_authority._plan_state_report(tmp_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["mission_id"] == "MT-FRESH"
        assert row["archive_status"] == "open"
        assert row["last_activity_source"] == "taskcards"
        assert row["stale"] is False
        assert row["age_days_since_last_activity"] < 1

    def test_open_mission_with_old_activity_is_stale(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-STALE", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-STALE", "TC-1", _iso(24 * 10))  # 10 days ago

        rows = mission_authority._plan_state_report(tmp_path)
        row = rows[0]
        assert row["stale"] is True
        assert row["age_days_since_last_activity"] >= 7

    def test_open_mission_uses_max_recorded_at_not_first(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-MULTI", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-MULTI", "TC-1", _iso(24 * 20))
        _write_taskcard_row(tmp_path, "MT-MULTI", "TC-2", _iso(1))  # most recent

        rows = mission_authority._plan_state_report(tmp_path)
        row = rows[0]
        assert row["stale"] is False  # driven by the most recent row, not the oldest

    def test_closed_mission_never_flagged_stale_even_if_old(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-CLOSED", archive_status="closed")
        _write_taskcard_row(tmp_path, "MT-CLOSED", "TC-1", _iso(24 * 400))

        rows = mission_authority._plan_state_report(tmp_path)
        row = rows[0]
        assert row["archive_status"] == "closed"
        assert row["stale"] is False

    def test_open_mission_with_no_taskcards_falls_back_to_archived_at(self, tmp_path):
        _write_mission_archive(
            tmp_path, "MT-NEVER-TOUCHED", archive_status="open", archived_at=_iso(24 * 10),
        )
        # No taskcards.jsonl written at all for this mission.

        rows = mission_authority._plan_state_report(tmp_path)
        row = rows[0]
        assert row["last_activity_source"] == "archived_at"
        assert row["stale"] is True

    def test_open_mission_with_recent_archived_at_and_no_taskcards_not_stale(self, tmp_path):
        _write_mission_archive(
            tmp_path, "MT-JUST-OPENED", archive_status="open", archived_at=_iso(1),
        )

        rows = mission_authority._plan_state_report(tmp_path)
        row = rows[0]
        assert row["last_activity_source"] == "archived_at"
        assert row["stale"] is False

    def test_open_mission_with_zero_signal_at_all_flagged_stale(self, tmp_path):
        # No _archived_at, no taskcards.jsonl -- absence of any liveness
        # signal for an open mission must fail toward "stale", not be
        # silently skipped.
        _write_mission_archive(tmp_path, "MT-NO-SIGNAL", archive_status="open")

        rows = mission_authority._plan_state_report(tmp_path)
        row = rows[0]
        assert row["last_activity_source"] == "unknown"
        assert row["last_activity_at"] is None
        assert row["stale"] is True

    def test_unreadable_archive_reported_not_raised(self, tmp_path):
        mission_dir = tmp_path / "reports" / "plan_state" / "MT-BROKEN"
        mission_dir.mkdir(parents=True)
        (mission_dir / "mission_authority.yaml").write_text("{not: valid: yaml:", encoding="utf-8")

        rows = mission_authority._plan_state_report(tmp_path)
        assert len(rows) == 1
        assert "error" in rows[0]

    def test_non_mission_file_directly_under_plan_state_root_skipped(self, tmp_path):
        plan_state_root = tmp_path / "reports" / "plan_state"
        plan_state_root.mkdir(parents=True)
        (plan_state_root / "mission_activation_log.jsonl").write_text("{}\n", encoding="utf-8")
        _write_mission_archive(tmp_path, "MT-REAL", archive_status="open", archived_at=_iso(1))

        rows = mission_authority._plan_state_report(tmp_path)
        assert len(rows) == 1
        assert rows[0]["mission_id"] == "MT-REAL"

    def test_build_liveness_report_aggregates_plan_state_and_stale_open_missions(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-A-STALE", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-A-STALE", "TC-1", _iso(24 * 30))
        _write_mission_archive(tmp_path, "MT-B-FRESH", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-B-FRESH", "TC-1", _iso(1))
        _write_mission_archive(tmp_path, "MT-C-CLOSED", archive_status="closed")
        _write_taskcard_row(tmp_path, "MT-C-CLOSED", "TC-1", _iso(24 * 30))

        report = mission_authority.build_liveness_report(tmp_path)
        assert len(report["plan_state"]) == 3
        assert report["stale_open_missions"] == ["MT-A-STALE"]

    def test_cmd_status_json_includes_stale_open_missions_key(self, tmp_path, capsys):
        _write_mission_archive(tmp_path, "MT-STALE-CLI", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-STALE-CLI", "TC-1", _iso(24 * 30))

        exit_code = mission_authority.main(["--root", str(tmp_path), "status", "--json"])
        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["stale_open_missions"] == ["MT-STALE-CLI"]

    def test_cmd_status_human_readable_shows_stale_missions(self, tmp_path, capsys):
        _write_mission_archive(tmp_path, "MT-STALE-HUMAN", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-STALE-HUMAN", "TC-1", _iso(24 * 30))

        exit_code = mission_authority.main(["--root", str(tmp_path), "status"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Stale open missions" in out
        assert "MT-STALE-HUMAN" in out

    def test_plan_state_report_never_mutates_taskcards_file(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-READONLY", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-READONLY", "TC-1", _iso(1))
        taskcards_path = tmp_path / "reports" / "plan_state" / "MT-READONLY" / "taskcards.jsonl"
        before = taskcards_path.read_text(encoding="utf-8")

        mission_authority._plan_state_report(tmp_path)

        assert taskcards_path.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# TC-GOV-02-01-FIX: per-mission failure isolation for _plan_state_report().
#
# The independent review of TC-GOV-02-01 reproduced that ONE malformed mission
# under reports/plan_state/ raised out of _plan_state_report() and therefore
# out of `mission_authority.py status --json`, blinding the stale-open-mission
# detector for every other mission (exit 0 before the 4th store existed, exit 1
# with a traceback after it). Every fixture below is built in tmp_path -- never
# the real ledger -- and rows that the schema permits are written through the
# REAL TaskcardStore.append() (validate_taskcard_record checks that
# `recorded_at` is present, not what type it is).
# ---------------------------------------------------------------------------

_HEALTHY = "MT-HEALTHY-STALE"
_FIXED_NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)


def _z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_raw_archive(tmp_path: Path, mission_id: str, text: str) -> Path:
    mission_dir = tmp_path / "reports" / "plan_state" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    (mission_dir / "mission_authority.yaml").write_bytes(text.encode("utf-8"))
    return mission_dir


def _append_via_store(tmp_path: Path, mission_id: str, task_id: str, recorded_at) -> None:
    """Write one row through the sanctioned writer (schema-validated append)."""
    TaskcardStore(mission_id, repo_root=tmp_path).append({
        "task_id": task_id,
        "mission_id": mission_id,
        "status": "IN_PROGRESS",
        "recorded_at": recorded_at,
        "evidence_refs": [],
        "recorded_by": "test-fixture",
    })


def _row_for(rows: list, mission_id: str) -> dict:
    matches = [r for r in rows if r["mission_id"] == mission_id]
    assert len(matches) == 1, f"expected exactly one row for {mission_id}, got {rows}"
    return matches[0]


def _seed_healthy_stale(tmp_path: Path) -> None:
    _write_mission_archive(tmp_path, _HEALTHY, archive_status="open")
    _write_taskcard_row(tmp_path, _HEALTHY, "TC-1", _iso(24 * 20))


def _assert_error_row(row: dict, mission_id: str, error_classes: tuple) -> None:
    assert row["mission_id"] == mission_id
    assert row["error"].split(":", 1)[0] in error_classes, row["error"]
    assert "\n" not in row["error"] and "Traceback" not in row["error"]
    assert row["error"].isascii()
    # An errored mission's staleness is unknowable -- it must not claim either way.
    assert "stale" not in row


def _snapshot_tree(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _seed_every_crash_class(tmp_path: Path) -> None:
    """One healthy stale mission plus one mission per crash class."""
    _seed_healthy_stale(tmp_path)
    # (a) schema-valid row whose recorded_at is not a string, via the real writer
    _write_mission_archive(tmp_path, "MT-BAD-A-TYPED", archive_status="open")
    _append_via_store(tmp_path, "MT-BAD-A-TYPED", "TC-1", _iso(24 * 20))
    _append_via_store(tmp_path, "MT-BAD-A-TYPED", "TC-2", 1757000000)
    # (b) valid-JSON lines that are not objects
    mission_dir = _write_mission_archive(tmp_path, "MT-BAD-B-NONDICT", archive_status="open")
    (mission_dir / "taskcards.jsonl").write_text('[1, 2]\n"oops"\nnull\n42\n', encoding="utf-8")
    # (c) invalid UTF-8 in the ledger
    mission_dir = _write_mission_archive(tmp_path, "MT-BAD-C-UTF8", archive_status="open")
    (mission_dir / "taskcards.jsonl").write_bytes(b'\xff\xfe{"task_id": "TC-1"}\n')
    # (d) mission_authority: null
    _write_raw_archive(tmp_path, "MT-BAD-D-NULL", "mission_authority:\n")
    # (g) a YAML syntax error whose message quotes non-ASCII source text
    _write_raw_archive(tmp_path, "MT-BAD-E-UNICODE", "mission_authority: {a: 日本語: [\n")


class TestPlanStateLivenessIsolation:
    # -- (a) non-string recorded_at ------------------------------------------

    @pytest.mark.parametrize(
        "value",
        [None, "", 0, 1757000000, 1.5, True, False, {}, {"a": 1}, [], [1],
         datetime(2026, 9, 17, tzinfo=timezone.utc), datetime(2026, 9, 17).date(),
         "not-a-timestamp"],
        ids=["none", "empty", "zero", "int", "float", "true", "false", "empty-dict",
             "dict", "empty-list", "list", "datetime", "date", "garbage-str"],
    )
    def test_parse_iso_timestamp_returns_none_for_non_string_or_garbage(self, value):
        assert mission_authority._parse_iso_timestamp(value) is None

    @pytest.mark.parametrize(
        "bad_value", [1757000000, {"a": 1}, [1], True], ids=["int", "dict", "list", "bool"],
    )
    def test_non_string_recorded_at_accepted_by_real_store_does_not_crash_report(
        self, tmp_path, bad_value,
    ):
        _seed_healthy_stale(tmp_path)
        _write_mission_archive(tmp_path, "MT-BAD-TS", archive_status="open")
        _append_via_store(tmp_path, "MT-BAD-TS", "TC-1", _iso(24 * 20))
        _append_via_store(tmp_path, "MT-BAD-TS", "TC-2", bad_value)
        # Precondition, not an assumption: the real writer accepted the bad row.
        assert len(TaskcardStore("MT-BAD-TS", repo_root=tmp_path).read_history()) == 2

        rows = mission_authority._plan_state_report(tmp_path)

        bad = _row_for(rows, "MT-BAD-TS")
        assert "error" not in bad
        assert bad["last_activity_source"] == "taskcards"  # the valid old row still counts
        assert bad["stale"] is True
        assert _row_for(rows, _HEALTHY)["stale"] is True

    def test_bad_typed_row_does_not_poison_a_good_recent_row(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-MIXED", archive_status="open")
        _append_via_store(tmp_path, "MT-MIXED", "TC-1", _iso(1))
        _append_via_store(tmp_path, "MT-MIXED", "TC-2", {"a": 1})

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert row["last_activity_source"] == "taskcards"
        assert row["stale"] is False

    def test_only_row_with_non_string_recorded_at_is_no_signal_so_mission_is_stale(
        self, tmp_path,
    ):
        _write_mission_archive(tmp_path, "MT-ONLY-BAD", archive_status="open")
        _append_via_store(tmp_path, "MT-ONLY-BAD", "TC-1", 1757000000)

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert "error" not in row
        assert row["last_activity_source"] == "unknown"
        assert row["stale"] is True  # fails toward surfacing, same as zero-signal

    # -- (b) valid-JSON non-dict lines ---------------------------------------

    @pytest.mark.parametrize(
        "line", ["[1, 2]", '"oops"', "null", "42"], ids=["list", "string", "null", "number"],
    )
    def test_non_dict_taskcard_lines_are_skipped_not_raised(self, tmp_path, line):
        _seed_healthy_stale(tmp_path)
        mission_dir = _write_mission_archive(tmp_path, "MT-BAD-LINES", archive_status="open")
        good = json.dumps({
            "task_id": "TC-1", "mission_id": "MT-BAD-LINES", "status": "IN_PROGRESS",
            "recorded_at": _iso(1), "evidence_refs": [], "recorded_by": "test-fixture",
        })
        (mission_dir / "taskcards.jsonl").write_text(f"{line}\n{good}\n{line}\n", encoding="utf-8")

        rows = mission_authority._plan_state_report(tmp_path)

        bad = _row_for(rows, "MT-BAD-LINES")
        assert "error" not in bad
        assert bad["last_activity_source"] == "taskcards"
        assert bad["stale"] is False
        assert _row_for(rows, _HEALTHY)["stale"] is True

    def test_only_non_dict_taskcard_lines_is_no_signal_so_mission_is_stale(self, tmp_path):
        mission_dir = _write_mission_archive(tmp_path, "MT-ALL-JUNK", archive_status="open")
        (mission_dir / "taskcards.jsonl").write_text("[1, 2]\nnull\n", encoding="utf-8")

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert "error" not in row
        assert row["last_activity_source"] == "unknown"
        assert row["stale"] is True

    # -- (c) undecodable / unreadable taskcards.jsonl ------------------------

    def test_invalid_utf8_taskcards_becomes_error_row_for_that_mission_only(self, tmp_path):
        _seed_healthy_stale(tmp_path)
        mission_dir = _write_mission_archive(tmp_path, "MT-BAD-UTF8", archive_status="open")
        (mission_dir / "taskcards.jsonl").write_bytes(b'\xff\xfe{"task_id": "TC-1"}\n')

        rows = mission_authority._plan_state_report(tmp_path)

        assert len(rows) == 2
        _assert_error_row(_row_for(rows, "MT-BAD-UTF8"), "MT-BAD-UTF8", ("UnicodeDecodeError",))
        assert _row_for(rows, _HEALTHY)["stale"] is True

    def test_unreadable_taskcards_path_becomes_error_row_for_that_mission_only(self, tmp_path):
        _seed_healthy_stale(tmp_path)
        mission_dir = _write_mission_archive(tmp_path, "MT-BAD-IO", archive_status="open")
        (mission_dir / "taskcards.jsonl").mkdir()  # exists, but cannot be read as a file

        rows = mission_authority._plan_state_report(tmp_path)

        _assert_error_row(
            _row_for(rows, "MT-BAD-IO"), "MT-BAD-IO",
            ("PermissionError", "IsADirectoryError", "OSError"),
        )
        assert _row_for(rows, _HEALTHY)["stale"] is True

    # -- (d) mission_authority: key that is not a mapping --------------------

    @pytest.mark.parametrize(
        "body",
        ["mission_authority:\n", "mission_authority:\n  - a\n  - b\n",
         "mission_authority: just-a-string\n", "- a\n- b\n", ""],
        ids=["null", "list", "string", "top-level-list", "empty-file"],
    )
    def test_mission_authority_key_not_a_mapping_becomes_error_row(self, tmp_path, body):
        _seed_healthy_stale(tmp_path)
        _write_raw_archive(tmp_path, "MT-BAD-MA", body)

        rows = mission_authority._plan_state_report(tmp_path)

        assert len(rows) == 2
        _assert_error_row(
            _row_for(rows, "MT-BAD-MA"), "MT-BAD-MA", ("ValueError", "TypeError", "KeyError"),
        )
        assert _row_for(rows, _HEALTHY)["stale"] is True

    # -- other non-string archive fields (same defect class) -----------------

    def test_date_typed_mission_id_falls_back_to_directory_name_and_json_serialises(
        self, tmp_path, capsys,
    ):
        # An unquoted `mission_id: 2026-09-17` loads as datetime.date, which
        # json.dumps cannot serialise -- it used to kill `status --json`.
        _write_raw_archive(
            tmp_path, "MT-BAD-DATE",
            "mission_authority:\n  mission_id: 2026-09-17\n  _archive_status: open\n",
        )

        report = mission_authority.build_liveness_report(tmp_path)
        json.dumps(report)  # must not raise

        assert report["plan_state"][0]["mission_id"] == "MT-BAD-DATE"
        assert mission_authority.main(["--root", str(tmp_path), "status", "--json"]) == 0
        json.loads(capsys.readouterr().out)

    def test_non_string_archive_status_is_unknown_and_never_stale(self, tmp_path):
        _write_raw_archive(
            tmp_path, "MT-BAD-STATUS",
            "mission_authority:\n  mission_id: MT-BAD-STATUS\n  _archive_status: [open]\n",
        )

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert row["archive_status"] == "unknown"
        assert row["stale"] is False
        json.dumps(row)

    def test_datetime_typed_archived_at_is_no_signal_by_explicit_decision(self, tmp_path):
        # An UNQUOTED `_archived_at: 2026-09-17T00:00:00Z` loads as a datetime.
        # Decision (TC-GOV-02-01-FIX): a non-string timestamp is "no signal",
        # never silently accepted -- so the open mission fails toward stale.
        _write_raw_archive(
            tmp_path, "MT-DT-ARCHIVED",
            "mission_authority:\n  mission_id: MT-DT-ARCHIVED\n  _archive_status: open\n"
            "  _archived_at: 2026-09-17T00:00:00Z\n",
        )

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert row["last_activity_source"] == "unknown"
        assert row["last_activity_at"] is None
        assert row["stale"] is True

    def test_error_text_is_single_line_ascii_and_bounded(self):
        exc = ValueError("first line\nsecond line 日本語 " + "x" * 5000)

        text = mission_authority._plan_state_error_text(exc)

        assert text.startswith("ValueError: ")
        assert "\n" not in text
        assert text.isascii()
        assert len(text) <= 260

    def test_error_text_survives_a_yaml_error_quoting_non_ascii_source(self, tmp_path):
        _write_raw_archive(tmp_path, "MT-BAD-UNICODE", "mission_authority: {a: 日本語: [\n")

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert "error" in row
        assert row["error"].isascii()

    # -- isolation + surfacing ------------------------------------------------

    def test_one_malformed_mission_does_not_blind_the_detector_for_the_others(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-A-HEALTHY-STALE", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-A-HEALTHY-STALE", "TC-1", _iso(24 * 20))
        _write_raw_archive(tmp_path, "MT-B-MALFORMED", "mission_authority:\n")
        _write_mission_archive(tmp_path, "MT-C-HEALTHY-FRESH", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-C-HEALTHY-FRESH", "TC-1", _iso(1))
        _write_mission_archive(tmp_path, "MT-D-CLOSED-OLD", archive_status="closed")
        _write_taskcard_row(tmp_path, "MT-D-CLOSED-OLD", "TC-1", _iso(24 * 400))

        report = mission_authority.build_liveness_report(tmp_path)

        rows = report["plan_state"]
        assert [r["mission_id"] for r in rows] == [
            "MT-A-HEALTHY-STALE", "MT-B-MALFORMED", "MT-C-HEALTHY-FRESH", "MT-D-CLOSED-OLD",
        ]
        assert "error" in _row_for(rows, "MT-B-MALFORMED")
        assert _row_for(rows, "MT-A-HEALTHY-STALE")["stale"] is True
        assert _row_for(rows, "MT-C-HEALTHY-FRESH")["stale"] is False
        assert _row_for(rows, "MT-D-CLOSED-OLD")["stale"] is False
        assert report["stale_open_missions"] == ["MT-A-HEALTHY-STALE"]

    def test_plan_state_errors_key_lists_errored_missions_and_keeps_them_out_of_stale(
        self, tmp_path,
    ):
        _seed_every_crash_class(tmp_path)

        report = mission_authority.build_liveness_report(tmp_path)

        assert sorted(report["plan_state_errors"]) == [
            "MT-BAD-C-UTF8", "MT-BAD-D-NULL", "MT-BAD-E-UNICODE",
        ]
        assert set(report["stale_open_missions"]) == {
            _HEALTHY, "MT-BAD-A-TYPED", "MT-BAD-B-NONDICT",
        }

    def test_malformed_ledger_is_never_mutated_by_the_report(self, tmp_path):
        _seed_every_crash_class(tmp_path)
        before = _snapshot_tree(tmp_path / "reports" / "plan_state")

        mission_authority.build_liveness_report(tmp_path)

        assert _snapshot_tree(tmp_path / "reports" / "plan_state") == before
        assert not list((tmp_path / "reports" / "plan_state").rglob("*.lock"))

    # -- CLI: status --json must never exit non-zero on plan_state contents --

    def test_cmd_status_json_exits_0_with_every_crash_class_present(self, tmp_path, capsys):
        _seed_every_crash_class(tmp_path)

        exit_code = mission_authority.main(["--root", str(tmp_path), "status", "--json"])

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert _HEALTHY in out["stale_open_missions"]
        assert len(out["plan_state"]) == 6

    def test_cmd_status_human_readable_surfaces_unreadable_missions(self, tmp_path, capsys):
        _seed_healthy_stale(tmp_path)
        mission_dir = _write_mission_archive(tmp_path, "MT-BAD-UTF8", archive_status="open")
        (mission_dir / "taskcards.jsonl").write_bytes(b'\xff\xfe{"task_id": "TC-1"}\n')

        exit_code = mission_authority.main(["--root", str(tmp_path), "status"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Unreadable plan_state missions" in out
        assert "MT-BAD-UTF8" in out
        assert "UnicodeDecodeError" in out
        assert _HEALTHY in out  # the healthy stale mission is still listed

    def test_real_cli_process_exits_0_on_malformed_ledger_under_a_cp1252_console(
        self, tmp_path,
    ):
        # Real process, real exit code, and a console encoding that cannot
        # represent the CJK text quoted by the YAML error in the fixture.
        _seed_every_crash_class(tmp_path)
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "cp1252"

        proc = subprocess.run(
            [sys.executable, mission_authority.__file__, "--root", str(tmp_path),
             "status", "--json"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=120, env=env,
        )

        assert proc.returncode == 0, proc.stderr[-400:]
        out = json.loads(proc.stdout)
        assert _HEALTHY in out["stale_open_missions"]


class TestPlanStateLivenessTimestampPolicy:
    """Future-dated / boundary / naive-timestamp policy (TC-GOV-02-01-FIX).

    DECISION: a `recorded_at` or `_archived_at` more than 1 day in the future is
    "no signal", never activity. A future stamp used to make an abandoned
    mission look permanently live (a row ~10 years ahead gave age_days=-3650
    and stale=False). 1 day of slack covers clock skew and the worst real
    source of a legitimately-future-looking stamp, a local time mislabelled
    `Z` (max UTC offset +14h), while bounding any masking to under a day.
    """

    def test_far_future_recorded_at_cannot_mask_staleness(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-MASKED", archive_status="open")
        old = _iso(24 * 20)
        _append_via_store(tmp_path, "MT-MASKED", "TC-1", old)
        _append_via_store(tmp_path, "MT-MASKED", "TC-2", _iso(-24 * 3650))  # ~10y ahead

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert row["stale"] is True
        assert row["last_activity_at"] == old
        assert row["age_days_since_last_activity"] >= 19.9

    def test_far_future_only_row_is_no_signal(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-FUTURE-ONLY", archive_status="open")
        _append_via_store(tmp_path, "MT-FUTURE-ONLY", "TC-1", _iso(-24 * 30))

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert row["last_activity_source"] == "unknown"
        assert row["last_activity_at"] is None
        assert row["stale"] is True

    def test_far_future_archived_at_is_ignored_too(self, tmp_path):
        _write_mission_archive(
            tmp_path, "MT-FUTURE-ARCHIVED", archive_status="open", archived_at=_iso(-24 * 30),
        )

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert row["last_activity_source"] == "unknown"
        assert row["stale"] is True

    def test_slightly_future_within_tolerance_counts_and_age_is_clamped_to_zero(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-SKEW", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-SKEW", "TC-1", _z(_FIXED_NOW + timedelta(hours=2)))

        row = mission_authority._plan_state_report(tmp_path, now=_FIXED_NOW)[0]

        assert row["last_activity_source"] == "taskcards"
        assert row["age_days_since_last_activity"] == 0.0
        assert row["stale"] is False

    def test_future_tolerance_boundary_is_one_day_inclusive(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-EDGE-IN", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-EDGE-IN", "TC-1", _z(_FIXED_NOW + timedelta(days=1)))
        _write_mission_archive(tmp_path, "MT-EDGE-OUT", archive_status="open")
        _write_taskcard_row(
            tmp_path, "MT-EDGE-OUT", "TC-1", _z(_FIXED_NOW + timedelta(days=1, seconds=1)),
        )

        rows = mission_authority._plan_state_report(tmp_path, now=_FIXED_NOW)

        assert _row_for(rows, "MT-EDGE-IN")["last_activity_source"] == "taskcards"
        assert _row_for(rows, "MT-EDGE-OUT")["last_activity_source"] == "unknown"

    def test_exactly_seven_days_is_stale_and_just_under_is_not(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-EXACT-7D", archive_status="open")
        _write_taskcard_row(tmp_path, "MT-EXACT-7D", "TC-1", _z(_FIXED_NOW - timedelta(days=7)))
        _write_mission_archive(tmp_path, "MT-JUST-UNDER", archive_status="open")
        _write_taskcard_row(
            tmp_path, "MT-JUST-UNDER", "TC-1",
            _z(_FIXED_NOW - timedelta(days=6, hours=23, minutes=59, seconds=59)),
        )

        rows = mission_authority._plan_state_report(tmp_path, now=_FIXED_NOW)

        assert _row_for(rows, "MT-EXACT-7D")["stale"] is True  # `>=`, matches the plan
        assert _row_for(rows, "MT-JUST-UNDER")["stale"] is False

    def test_naive_timestamp_is_treated_as_utc(self, tmp_path):
        _write_mission_archive(tmp_path, "MT-NAIVE", archive_status="open")
        naive = (_FIXED_NOW - timedelta(days=7)).replace(tzinfo=None).isoformat()
        _write_taskcard_row(tmp_path, "MT-NAIVE", "TC-1", naive)

        row = mission_authority._plan_state_report(tmp_path, now=_FIXED_NOW)[0]

        assert row["last_activity_source"] == "taskcards"
        assert row["age_days_since_last_activity"] == 7.0
        assert row["stale"] is True

    def test_absent_archive_status_is_unknown_and_never_stale(self, tmp_path):
        _write_raw_archive(tmp_path, "MT-NO-STATUS", "mission_authority:\n  mission_id: MT-NO-STATUS\n")
        _write_taskcard_row(tmp_path, "MT-NO-STATUS", "TC-1", _iso(24 * 400))

        row = mission_authority._plan_state_report(tmp_path)[0]

        assert row["archive_status"] == "unknown"
        assert row["stale"] is False


# ---------------------------------------------------------------------------
# ST-157: archive_mission() collision guard
# ---------------------------------------------------------------------------

class TestArchiveMissionCollisionGuard:
    def test_reopen_of_same_unchanged_mission_is_not_a_collision(self, tmp_path):
        """Idempotent re-open of the SAME mission with unchanged content must
        still succeed -- the guard only fires on a genuine content mismatch."""
        _write_root(tmp_path, VALID_MISSION)
        first = mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"])
        second = mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"])
        assert first == 0
        assert second == 0

    def test_two_different_missions_sharing_an_id_is_refused(self, tmp_path, capsys):
        """The literal MT018 scenario: two DIFFERENT missions' content trying
        to archive under the SAME mission_id. Must be refused, not silently
        overwritten (the pre-fix behavior)."""
        _write_root(tmp_path, VALID_MISSION)
        exit_code_1 = mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"])
        assert exit_code_1 == 0

        colliding = dict(VALID_MISSION)
        colliding["mission_id"] = "TEST-MISSION-A"
        colliding["mission_summary"] = "A completely different, unrelated mission that happens to reuse this id."
        _write_root(tmp_path, colliding)
        capsys.readouterr()
        exit_code_2 = mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "TEST-MISSION-A"])
        assert exit_code_2 == 1
        assert "already in use" in capsys.readouterr().out

        # The ORIGINAL archive must be untouched -- proving no silent overwrite occurred.
        archive_path = tmp_path / "reports" / "plan_state" / "TEST-MISSION-A" / "mission_authority.yaml"
        data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
        assert data["mission_authority"]["mission_summary"] == VALID_MISSION["mission_summary"]

    def test_archive_mission_raises_directly_when_called_as_a_library(self, tmp_path):
        mission_authority.archive_mission("X", dict(VALID_MISSION, mission_id="X"), status="open", root=tmp_path)
        colliding = dict(VALID_MISSION, mission_id="X", mission_summary="different")
        with pytest.raises(mission_authority.MissionIdCollisionError):
            mission_authority.archive_mission("X", colliding, status="open", root=tmp_path)


# ---------------------------------------------------------------------------
# H1: cmd_activate — pre-flight consent gate for the root mission slot
# (reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md)
# ---------------------------------------------------------------------------

class TestActivate:
    def test_activate_over_locked_open_incumbent_without_force_refuses(self, tmp_path, capsys):
        """Replays the real 2026-09-11 incident: an incumbent mission held
        the root slot, mission_locked: true, _archive_status: open (still
        active). A challenger must be refused without --force, and the root
        file must be untouched (activate never writes it)."""
        incumbent = dict(VALID_MISSION, mission_id="MT066-INCUMBENT", mission_locked=True)
        _write_root(tmp_path, incumbent)
        assert mission_authority.main(
            ["--root", str(tmp_path), "open", "--mission-id", "MT066-INCUMBENT"]
        ) == 0
        root_before = (tmp_path / "MISSION_AUTHORITY.yaml").read_text(encoding="utf-8")

        capsys.readouterr()
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "activate", "--mission-id", "MT068-CHALLENGER"]
        )
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "MT066-INCUMBENT" in out
        assert "Refusing" in out
        assert (tmp_path / "MISSION_AUTHORITY.yaml").read_text(encoding="utf-8") == root_before

    def test_activate_over_locked_open_incumbent_with_valid_force_succeeds(self, tmp_path, capsys):
        incumbent = dict(VALID_MISSION, mission_id="MT066-INCUMBENT", mission_locked=True)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT066-INCUMBENT"])

        capsys.readouterr()
        exit_code = mission_authority.main([
            "--root", str(tmp_path), "activate", "--mission-id", "MT068-CHALLENGER",
            "--force", "see reports/skill-gaps/2026-09-11-example.md for justification",
            "--disposition", "will-close-after-current-task",
        ])
        assert exit_code == 0
        assert "may take over" in capsys.readouterr().out

        log_path = tmp_path / "reports" / "plan_state" / mission_authority.ACTIVATION_LOG_NAME
        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        takeover = [e for e in entries if e["action"] == "takeover"][0]
        assert takeover["previous_mission_id"] == "MT066-INCUMBENT"
        assert takeover["incumbent_locked_open"] is True
        assert takeover["force_reason"]
        assert takeover["disposition"] == "will-close-after-current-task"

    def test_activate_force_reason_too_short_is_rejected(self, tmp_path, capsys):
        incumbent = dict(VALID_MISSION, mission_id="MT066-INCUMBENT", mission_locked=True)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT066-INCUMBENT"])

        capsys.readouterr()
        exit_code = mission_authority.main([
            "--root", str(tmp_path), "activate", "--mission-id", "MT068-CHALLENGER", "--force", "because",
        ])
        assert exit_code == 1
        assert "too short" in capsys.readouterr().out

    def test_activate_force_without_disposition_is_rejected(self, tmp_path, capsys):
        """TC-GOV-03-01: the root cause this taskcard closes -- --force used to
        validate only the reason string's length, never recording what happens
        to the incumbent's remaining work. A real (long-enough) reason must no
        longer be sufficient on its own; --disposition is now required too, and
        the root file must stay untouched (activate never writes it)."""
        incumbent = dict(VALID_MISSION, mission_id="MT066-INCUMBENT", mission_locked=True)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT066-INCUMBENT"])
        root_before = (tmp_path / "MISSION_AUTHORITY.yaml").read_text(encoding="utf-8")

        capsys.readouterr()
        exit_code = mission_authority.main([
            "--root", str(tmp_path), "activate", "--mission-id", "MT068-CHALLENGER",
            "--force", "see reports/skill-gaps/2026-09-11-example.md for justification",
        ])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "--disposition" in out
        assert (tmp_path / "MISSION_AUTHORITY.yaml").read_text(encoding="utf-8") == root_before

        log_path = tmp_path / "reports" / "plan_state" / mission_authority.ACTIVATION_LOG_NAME
        assert not log_path.exists() or "MT068-CHALLENGER" not in log_path.read_text(encoding="utf-8")

    def test_activate_force_with_malformed_disposition_is_rejected(self, tmp_path, capsys):
        incumbent = dict(VALID_MISSION, mission_id="MT066-INCUMBENT", mission_locked=True)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT066-INCUMBENT"])

        capsys.readouterr()
        exit_code = mission_authority.main([
            "--root", str(tmp_path), "activate", "--mission-id", "MT068-CHALLENGER",
            "--force", "see reports/skill-gaps/2026-09-11-example.md for justification",
            "--disposition", "not-a-real-disposition-shape",
        ])
        assert exit_code == 1
        assert "not a recognized" in capsys.readouterr().out

    def test_activate_force_with_disposition_prefix_forms_succeed(self, tmp_path, capsys):
        """parking-with-reason:<text> and handing-off-to:<mission-id> both
        require real, non-empty text after the prefix -- a bare prefix is the
        same "narrative filler" failure mode the reason-length check already
        guards against, one layer up."""
        incumbent = dict(VALID_MISSION, mission_id="MT066-INCUMBENT", mission_locked=True)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT066-INCUMBENT"])

        capsys.readouterr()
        exit_code = mission_authority.main([
            "--root", str(tmp_path), "activate", "--mission-id", "MT068-CHALLENGER",
            "--force", "see reports/skill-gaps/2026-09-11-example.md for justification",
            "--disposition", "handing-off-to:MT070-SOMEONE-ELSE",
        ])
        assert exit_code == 0

        log_path = tmp_path / "reports" / "plan_state" / mission_authority.ACTIVATION_LOG_NAME
        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        takeover = [e for e in entries if e["action"] == "takeover"][-1]
        assert takeover["disposition"] == "handing-off-to:MT070-SOMEONE-ELSE"

    def test_activate_force_with_bare_prefix_disposition_is_rejected(self, tmp_path, capsys):
        incumbent = dict(VALID_MISSION, mission_id="MT066-INCUMBENT", mission_locked=True)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT066-INCUMBENT"])

        capsys.readouterr()
        exit_code = mission_authority.main([
            "--root", str(tmp_path), "activate", "--mission-id", "MT068-CHALLENGER",
            "--force", "see reports/skill-gaps/2026-09-11-example.md for justification",
            "--disposition", "parking-with-reason:   ",
        ])
        assert exit_code == 1
        assert "missing required text" in capsys.readouterr().out

    def test_activate_over_unlocked_or_closed_incumbent_needs_no_force(self, tmp_path, capsys):
        incumbent = dict(VALID_MISSION, mission_id="MT-DONE", mission_locked=False)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT-DONE"])

        capsys.readouterr()
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "activate", "--mission-id", "MT-NEXT"]
        )
        assert exit_code == 0
        assert "may take over" in capsys.readouterr().out

    def test_activate_same_mission_id_resumption_never_checks_incumbent(self, tmp_path, capsys):
        """The test that would catch a naive lock-shaped design wrongly
        blocking legitimate same-mission-later-session resumption (this
        mission's own 2026-09-11 situation): resuming the mission that
        already holds the root slot must be an ungated fast path, even when
        that mission's own archived snapshot is mission_locked: true and
        _archive_status: open -- exactly the state that DOES refuse a
        takeover from a DIFFERENT mission_id (see
        test_activate_over_locked_open_incumbent_without_force_refuses
        above). A black-box proof, not a mock of internal call counts (a
        monkeypatch on module internals is a banned T2 pattern per
        AGENTS.md §16): if the same-mission-id fast path were missing, this
        exact locked+open state would fall through to the takeover-refusal
        branch and return 1 with an ERROR, not 0 with 'Resuming'."""
        mission = dict(VALID_MISSION, mission_id="MT068-SELF", mission_locked=True)
        _write_root(tmp_path, mission)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT068-SELF"])

        capsys.readouterr()
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "activate", "--mission-id", "MT068-SELF"]
        )
        assert exit_code == 0
        assert "Resuming" in capsys.readouterr().out

    def test_activate_no_incumbent_at_all_proceeds(self, tmp_path, capsys):
        """First-ever mission: no root file exists yet."""
        exit_code = mission_authority.main(
            ["--root", str(tmp_path), "activate", "--mission-id", "MT-FIRST"]
        )
        assert exit_code == 0
        assert "No incumbent" in capsys.readouterr().out

    def test_activate_appends_durable_log_not_just_console_output(self, tmp_path):
        incumbent = dict(VALID_MISSION, mission_id="MT-A", mission_locked=False)
        _write_root(tmp_path, incumbent)
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT-A"])
        mission_authority.main(["--root", str(tmp_path), "activate", "--mission-id", "MT-B"])

        log_path = tmp_path / "reports" / "plan_state" / mission_authority.ACTIVATION_LOG_NAME
        assert log_path.is_file()
        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        assert entries[-1]["mission_id"] == "MT-B"
        assert entries[-1]["previous_mission_id"] == "MT-A"


# ---------------------------------------------------------------------------
# ST-157: mission-id ledger seed + allocate
# ---------------------------------------------------------------------------

def _init_git_repo_with_root_history(tmp_path: Path, missions: list[dict]) -> None:
    """Build a real git repo whose MISSION_AUTHORITY.yaml history contains one
    commit per mission in `missions`, oldest first -- exercises the real
    _git_history_mission_ids() git subprocess path, not a mock."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)
    for mission in missions:
        _write_root(tmp_path, mission)
        subprocess.run(["git", "add", "MISSION_AUTHORITY.yaml"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"open {mission['mission_id']}"], cwd=str(tmp_path), check=True)


class TestSeedLedgerAndAllocate:
    def test_seed_ledger_from_git_history(self, tmp_path):
        _init_git_repo_with_root_history(tmp_path, [
            dict(VALID_MISSION, mission_id="MT001-2026-01-01-FIRST"),
            dict(VALID_MISSION, mission_id="MT002-2026-01-02-SECOND"),
        ])
        exit_code = mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        assert exit_code == 0

        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        assert ledger.has_id("MT001-2026-01-01-FIRST")
        assert ledger.has_id("MT002-2026-01-02-SECOND")
        assert ledger.highest_number() == 2

    def test_seed_ledger_from_local_plan_state_directory_names(self, tmp_path):
        """The real fix for the live 2026-09-01 finding: a mission with a
        reports/plan_state/{id}/ directory but NO mission_authority.yaml
        inside it (e.g. only taskcards.jsonl) must still be captured, because
        the directory NAME -- not its contents -- is read."""
        mission_dir = tmp_path / "reports" / "plan_state" / "MT005-2026-01-05-NO-YAML-INSIDE"
        mission_dir.mkdir(parents=True)
        (mission_dir / "taskcards.jsonl").write_text("", encoding="utf-8")

        exit_code = mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        assert exit_code == 0
        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        assert ledger.has_id("MT005-2026-01-05-NO-YAML-INSIDE")

    def test_seed_ledger_records_both_sides_of_a_real_number_collision(self, tmp_path):
        """The literal MT018 scenario, end to end through the real CLI: two
        DIFFERENT missions recorded via two DIFFERENT sources (plans/missions/
        vs. a local plan_state directory) sharing one number must both survive
        in the ledger as disclosed history, and highest_number() must reflect
        the true max so a future allocate() never re-mints either."""
        (tmp_path / "reports" / "plan_state" / "MT018-A").mkdir(parents=True)
        missions_dir = tmp_path / "plans" / "missions"
        missions_dir.mkdir(parents=True)
        (missions_dir / "MT018-B.md").write_text("# mission B\n", encoding="utf-8")

        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        assert ledger.has_id("MT018-A")
        assert ledger.has_id("MT018-B")
        numbers = [e["number"] for e in ledger.history()]
        assert numbers.count(18) == 2
        assert ledger.highest_number() == 18

    def test_seed_ledger_is_idempotent(self, tmp_path):
        (tmp_path / "reports" / "plan_state" / "MT003-ONCE").mkdir(parents=True)
        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        count_after_first = len(ledger.history())
        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        assert len(ledger.history()) == count_after_first

    def test_seed_ledger_reserves_track_b_bare_numbers_without_fabricating_history(self, tmp_path):
        """Regression test for the exact bug caught live 2026-09-01: Track B's
        table only ever has a bare "MT0NN" (no date/slug), which the
        _MT_ID_RE-shaped sources reject outright -- an earlier version of this
        function silently dropped every Track B row into 'non-numeric skipped'
        with no error, leaving those numbers completely unprotected. The fix
        must reserve the NUMBER via a clearly-labeled placeholder id."""
        doc_dir = tmp_path / "docs" / "readme-refresh"
        doc_dir.mkdir(parents=True)
        (doc_dir / "plan-system-forensic-reconciliation.md").write_text(
            "| MT041 | 2026-08-14 | some incident |\n"
            "| MT042 | 2026-08-14 | another incident |\n",
            encoding="utf-8",
        )
        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        assert ledger.highest_number() == 42
        numbers = {e["number"] for e in ledger.history()}
        assert {41, 42} <= numbers
        placeholder = next(e for e in ledger.history() if e["number"] == 41)
        assert placeholder["track"] == "readme-refresh"
        assert "PLACEHOLDER" in placeholder["mission_id"]

    def test_track_b_numbers_handles_trailing_text_and_combined_cells(self, tmp_path):
        """Regression test for a second ST-194 (2026-09-11) find, caught by
        independent verification: the prior regex required the number to sit
        immediately before the closing pipe, silently dropping any row whose
        first cell carries trailing text (e.g. real table rows "MT034 (+
        Phase 2)", "MT015 (dependency)") or names more than one number in one
        cell (e.g. real row "MT043/MT044") -- the exact same false-green
        failure shape as the bare-vs-dated-slug bug this function's docstring
        already describes, a second independent instance of it. Also proves
        a Notes-column mention of an unrelated number in a DIFFERENT row
        (e.g. "restored by MT056") is never picked up -- extraction is
        scoped to the first cell only."""
        doc_dir = tmp_path / "docs" / "readme-refresh"
        doc_dir.mkdir(parents=True)
        (doc_dir / "plan-system-forensic-reconciliation.md").write_text(
            "| MT034 (+ Phase 2) | 2026-08-12 | some incident |\n"
            "| MT015 (dependency) | 2026-07-30 | some incident |\n"
            "| MT043/MT044 | 2026-08-14 | some incident |\n"
            "| MT040 | 2026-08-14 | unrelated note mentioning MT056 elsewhere |\n",
            encoding="utf-8",
        )
        numbers = mission_authority._track_b_numbers(tmp_path)
        assert sorted(numbers) == [15, 34, 40, 43, 44]

    def test_seed_ledger_discloses_track_b_collision_even_when_number_already_claimed(self, tmp_path):
        """Regression test for the ST-194 (2026-09-11) disclosure gap: a prior
        version of the Track B seed loop skipped reserving a number whenever
        ANY entry already claimed it, which correctly avoided a redundant
        reservation but ALSO silently swallowed a genuine main-vs-Track-B
        collision (the exact defect class ST-157 exists to make visible).
        Real-world instance this fix uncovered: MT038/MT039/MT040 among
        others. Here: a main-track mission and a Track B row both claim
        number 38 -- both must survive in the ledger."""
        (tmp_path / "reports" / "plan_state" / "MT038-2026-08-27-CI-HARDENING").mkdir(parents=True)
        doc_dir = tmp_path / "docs" / "readme-refresh"
        doc_dir.mkdir(parents=True)
        (doc_dir / "plan-system-forensic-reconciliation.md").write_text(
            "| MT038 | 2026-08-14 | some readme-refresh incident |\n",
            encoding="utf-8",
        )

        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        assert ledger.has_id("MT038-2026-08-27-CI-HARDENING")
        assert ledger.has_id("MT038-README-REFRESH-TRACK-B-PLACEHOLDER")
        numbers = [e["number"] for e in ledger.history()]
        assert numbers.count(38) == 2

    def test_seed_ledger_backfills_known_off_the_books_missions(self, tmp_path):
        """Regression test for the ST-194 Mechanism-3 backfill: MT021's second,
        real instance ('Discovery health gate enforcement', commit
        a30d6a0ae9) has no dated-slug id anywhere in the repo -- no
        plans/missions/*.md file, no reports/plan_state/ dir -- so it is
        invisible to every other source scan. The explicit, cited
        _KNOWN_OFF_THE_BOOKS_MISSIONS list must still record it (when its
        citation evidence exists under root), and must be idempotent like
        every other seed source."""
        gaps_dir = tmp_path / "reports" / "skill-gaps"
        gaps_dir.mkdir(parents=True)
        (gaps_dir / "2026-08-05-discovery-health-gate-enforcement.md").write_text(
            "# SKILL GAP ESCALATION -- Discovery health gate enforcement (MT021, successor to MT020)\n",
            encoding="utf-8",
        )

        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        assert ledger.has_id("MT021-2026-08-05-DISCOVERY-HEALTH-GATE-ENFORCEMENT-OFF-THE-BOOKS-PLACEHOLDER")
        count_after_first = len(ledger.history())

        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        assert len(ledger.history()) == count_after_first

    def test_seed_ledger_skips_off_the_books_entry_without_its_citation_evidence(self, tmp_path):
        """The filter in _known_off_the_books_missions() must key off real
        on-disk evidence, not fire unconditionally -- otherwise every
        unrelated tmp_path test fixture in this suite would silently gain a
        phantom MT021 entry it never asked for (caught live while building
        this fix: it broke 3 unrelated seed-ledger/allocate tests)."""
        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        from mission_id_ledger import MissionIdLedger
        ledger = MissionIdLedger(repo_root=tmp_path)
        assert not ledger.has_id("MT021-2026-08-05-DISCOVERY-HEALTH-GATE-ENFORCEMENT-OFF-THE-BOOKS-PLACEHOLDER")

    def test_allocate_cli_mints_next_free_id_and_prints_it(self, tmp_path, capsys):
        (tmp_path / "reports" / "plan_state" / "MT005-EXISTING").mkdir(parents=True)
        mission_authority.main(["--root", str(tmp_path), "seed-ledger"])
        capsys.readouterr()

        exit_code = mission_authority.main([
            "--root", str(tmp_path), "allocate", "--track", "main", "--slug", "NEW-WORK", "--date", "2026-09-01",
        ])
        assert exit_code == 0
        printed = capsys.readouterr().out.strip()
        assert printed == "MT006-2026-09-01-NEW-WORK"

    def test_list_flags_mt0nn_mission_not_covered_by_the_ledger(self, tmp_path, capsys):
        """cmd_list's new coverage cross-check: a plans/missions/*.md file
        whose id never went through allocate/seed-ledger must be flagged."""
        missions_dir = tmp_path / "plans" / "missions"
        missions_dir.mkdir(parents=True)
        (missions_dir / "MT099-2026-09-01-NEVER-SEEDED.md").write_text("# x\n", encoding="utf-8")
        (tmp_path / "reports" / "plan_state" / "MT099-2026-09-01-NEVER-SEEDED").mkdir(parents=True)
        _write_root(tmp_path, dict(VALID_MISSION, mission_id="MT099-2026-09-01-NEVER-SEEDED"))
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "MT099-2026-09-01-NEVER-SEEDED"])

        capsys.readouterr()
        exit_code = mission_authority.main(["--root", str(tmp_path), "list"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "LEDGER COVERAGE WARNING" in out
        assert "MT099-2026-09-01-NEVER-SEEDED" in out

    def test_list_does_not_flag_free_text_slug_missions(self, tmp_path, capsys):
        """Non-numeric mission ids are explicitly out of scope and must never
        appear in the coverage warning."""
        _write_root(tmp_path, dict(VALID_MISSION, mission_id="free-text-slug-mission"))
        mission_authority.main(["--root", str(tmp_path), "open", "--mission-id", "free-text-slug-mission"])
        capsys.readouterr()
        mission_authority.main(["--root", str(tmp_path), "list"])
        out = capsys.readouterr().out
        assert "LEDGER COVERAGE WARNING" not in out

"""Tests for mission_authority.py — durable multi-mission archive (PSE-07).

All tests build a synthetic fake repo root under tmp_path — none touch the
real MISSION_AUTHORITY.yaml or reports/plan_state/ in this repo.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import mission_authority


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

"""Tests for mission_authority.py — durable multi-mission archive (PSE-07).

All tests build a synthetic fake repo root under tmp_path — none touch the
real MISSION_AUTHORITY.yaml or reports/plan_state/ in this repo.
"""
from __future__ import annotations

import subprocess
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

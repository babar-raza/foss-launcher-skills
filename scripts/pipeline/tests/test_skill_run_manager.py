"""Unit tests for skill_run_manager.py using temp directories."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import skill_run_manager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_run_id(runs_dir: Path) -> str:
    """Return the stem of the single .json file in runs_dir."""
    files = list(runs_dir.glob("*.json"))
    assert len(files) == 1, f"Expected 1 run record, found {len(files)}"
    return files[0].stem


def _load_record(runs_dir: Path) -> dict:
    files = list(runs_dir.glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _isolate_runs_dir(tmp_path):
    """Redirect _RUNS_DIR to tmp_path for all tests; reset after each."""
    skill_run_manager.configure(runs_dir=tmp_path)
    yield
    skill_run_manager.configure()


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_writes_required_fields(self, tmp_path):
        rc = skill_run_manager.main(["create", "--skills", "S-48"])
        assert rc == 0
        record = _load_record(tmp_path)
        assert "run_id" in record
        assert "S-48" in record["skills_invoked"]
        assert record["outcome"] == "pending"
        assert record["commit_sha"] is None
        assert record["completed_at"] is None

    def test_create_retroactive_flag(self, tmp_path):
        rc = skill_run_manager.main(["create", "--skills", "S-48", "--retroactive"])
        assert rc == 0
        record = _load_record(tmp_path)
        assert record["retroactive"] is True
        assert _get_run_id(tmp_path).startswith("retroactive-")

    def test_create_comma_separated_skills_split(self, tmp_path):
        """--skills S-73,S-62 must store two ids, not one literal (TC-W3H-008)."""
        rc = skill_run_manager.main(["create", "--skills", "S-73,S-62"])
        assert rc == 0
        record = _load_record(tmp_path)
        assert record["skills_invoked"] == ["S-73", "S-62"]

    def test_create_mixed_comma_and_space_skills(self, tmp_path):
        rc = skill_run_manager.main(["create", "--skills", "S-73,S-62", "S-76"])
        assert rc == 0
        record = _load_record(tmp_path)
        assert record["skills_invoked"] == ["S-73", "S-62", "S-76"]


# ---------------------------------------------------------------------------
# TestRecordStep
# ---------------------------------------------------------------------------

class TestRecordStep:
    def test_record_step_appends_to_skill_details(self, tmp_path):
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        rc = skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-48", "--type", "full",
        ])
        assert rc == 0
        record = _load_record(tmp_path)
        assert len(record["skill_details"]) == 1
        assert record["skill_details"][0]["skill_id"] == "S-48"
        assert record["skill_details"][0]["invocation_type"] == "full"

    def test_record_step_missing_record_returns_2(self, tmp_path):
        rc = skill_run_manager.main([
            "record-step", "--run-id", "nonexistent-id",
            "--skill", "S-48", "--type", "full",
        ])
        assert rc == 2


# ---------------------------------------------------------------------------
# TestGetDeclaredSkills
# ---------------------------------------------------------------------------

class TestGetDeclaredSkills:
    def test_returns_all_invoked_skills(self, tmp_path, capsys):
        skill_run_manager.main(["create", "--skills", "S-48", "S-23"])
        run_id = _get_run_id(tmp_path)

        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-48", "--type", "full",
        ])
        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-23", "--type", "partial",
        ])

        capsys.readouterr()  # clear stdout
        rc = skill_run_manager.main(["get-declared-skills", "--run-id", run_id])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert "S-48" in out
        assert "S-23" in out

    def test_inline_reasoning_type_rejected(self, tmp_path):
        """inline_reasoning is no longer a valid invocation type."""
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        with pytest.raises(SystemExit):
            skill_run_manager.main([
                "record-step", "--run-id", run_id,
                "--skill", "S-48", "--type", "inline_reasoning",
            ])

    def test_gap_approved_requires_report(self, tmp_path):
        """gap_approved type requires --gap-report argument."""
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        rc = skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-48", "--type", "gap_approved",
        ])
        assert rc == 1  # Should fail without --gap-report


# ---------------------------------------------------------------------------
# TestValidate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_matching_declaration_exits_0(self, tmp_path):
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-48",
        ])
        assert rc == 0

    def test_extra_declared_skill_exits_1(self, tmp_path):
        """Declaring S-99 when record only has S-48 is a false positive."""
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-48, S-99",
        ])
        assert rc == 1

    def test_full_and_partial_both_declared(self, tmp_path):
        """Both full and partial invocation types are valid for declaration."""
        skill_run_manager.main(["create", "--skills", "S-73", "S-01"])
        run_id = _get_run_id(tmp_path)

        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-73", "--type", "full",
        ])
        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-01", "--type", "partial",
        ])

        # Declaring both should pass
        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-73, S-01",
        ])
        assert rc == 0

    def test_undeclared_skill_fails(self, tmp_path):
        """Not declaring a recorded skill is a false negative."""
        skill_run_manager.main(["create", "--skills", "S-73", "S-01"])
        run_id = _get_run_id(tmp_path)

        # Declaring only S-73 when record has both → should fail (S-01 missing)
        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-73",
        ])
        assert rc == 1

    def test_no_record_at_all_exits_1(self, tmp_path):
        """Declaring a skill with no record entry at all is invalid."""
        skill_run_manager.main(["create", "--skills", "S-73"])
        run_id = _get_run_id(tmp_path)

        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-73", "--type", "full",
        ])

        # Declaring S-99 which has no record → should fail
        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-73, S-99",
        ])
        assert rc == 1


# ---------------------------------------------------------------------------
# TestFinalize
# ---------------------------------------------------------------------------

class TestFinalize:
    def test_finalize_sets_outcome_and_sha(self, tmp_path):
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        rc = skill_run_manager.main([
            "finalize", "--run-id", run_id,
            "--outcome", "success", "--commit-sha", "abc123def",
        ])
        assert rc == 0
        record = _load_record(tmp_path)
        assert record["outcome"] == "success"
        assert record["commit_sha"] == "abc123def"
        assert record["completed_at"] is not None


# ---------------------------------------------------------------------------
# TestPathUtils — proves repo_rel() renders safely in and out of repo root
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TestFindPending
# ---------------------------------------------------------------------------

class TestFindPending:
    def _write_pending(self, runs_dir: Path, run_id: str, started_at: str) -> None:
        """Write a minimal pending run record with the given started_at."""
        record = {
            "run_id": run_id,
            "skills_invoked": ["S-48"],
            "skill_details": [],
            "plans_referenced": [],
            "pre_conditions_verified": False,
            "outcome": "pending",
            "started_at": started_at,
            "completed_at": None,
            "commit_sha": None,
            "retroactive": False,
        }
        path = runs_dir / f"{run_id}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def test_fresh_record_is_returned(self, tmp_path, capsys):
        """A pending record with a recent started_at is returned by find-pending."""
        now = datetime.now(tz=timezone.utc)
        run_id = "20260501-120000-s48"
        self._write_pending(tmp_path, run_id, now.isoformat().replace("+00:00", "Z"))

        capsys.readouterr()
        rc = skill_run_manager.main(["find-pending", "--max-age-hours", "48"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert out == run_id

    def test_stale_record_is_skipped(self, tmp_path, capsys):
        """A pending record older than max-age-hours is skipped (exit 2)."""
        stale_time = datetime.now(tz=timezone.utc) - timedelta(hours=72)
        run_id = "20260429-000000-s48"
        self._write_pending(tmp_path, run_id, stale_time.isoformat().replace("+00:00", "Z"))

        capsys.readouterr()
        rc = skill_run_manager.main(["find-pending", "--max-age-hours", "48"])
        assert rc == 2  # no active pending record found

    def test_stale_skipped_fresh_returned(self, tmp_path, capsys):
        """With a stale and a fresh record, only the fresh one is returned."""
        stale_time = datetime.now(tz=timezone.utc) - timedelta(hours=72)
        fresh_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        # Stale record sorts AFTER fresh (lexicographic, older timestamp)
        stale_id = "20260429-000000-s48-stale"
        fresh_id = "20260501-110000-s48-fresh"
        self._write_pending(tmp_path, stale_id, stale_time.isoformat().replace("+00:00", "Z"))
        self._write_pending(tmp_path, fresh_id, fresh_time.isoformat().replace("+00:00", "Z"))

        capsys.readouterr()
        rc = skill_run_manager.main(["find-pending", "--max-age-hours", "48"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert out == fresh_id

    def test_finalized_record_not_returned(self, tmp_path, capsys):
        """A finalized (non-pending) record is not returned even if recent."""
        run_id = "20260501-120000-s48-done"
        record = {
            "run_id": run_id,
            "skills_invoked": ["S-48"],
            "skill_details": [],
            "plans_referenced": [],
            "pre_conditions_verified": False,
            "outcome": "success",
            "started_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "completed_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "commit_sha": "abc123",
            "retroactive": False,
        }
        (tmp_path / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")

        capsys.readouterr()
        rc = skill_run_manager.main(["find-pending"])
        assert rc == 2


import path_utils  # noqa: E402


class TestPathUtils:
    def test_in_repo_returns_relative(self):
        """A path under _REPO_ROOT is rendered as a relative string."""
        root = path_utils._REPO_ROOT
        target = root / "scripts" / "pipeline" / "skill_run_manager.py"
        result = path_utils.repo_rel(target)
        expected = str(target.relative_to(root))
        assert result == expected

    def test_out_of_repo_returns_absolute(self, tmp_path):
        """A path outside _REPO_ROOT (e.g. tmp_path) never raises and returns an absolute path."""
        target = tmp_path / "some" / "nested" / "file.json"
        result = path_utils.repo_rel(target)
        # Must not crash; must equal the absolute path string
        assert result == str(target)

    def test_explicit_root_in_repo(self, tmp_path):
        """When an explicit root is given and path is under it, result is relative."""
        root = tmp_path / "myroot"
        target = root / "sub" / "file.txt"
        result = path_utils.repo_rel(target, root=root)
        assert result == str(Path("sub") / "file.txt")

    def test_explicit_root_outside(self, tmp_path):
        """When an explicit root is given and path is NOT under it, result is absolute."""
        root = tmp_path / "myroot"
        target = tmp_path / "elsewhere" / "file.txt"
        result = path_utils.repo_rel(target, root=root)
        assert result == str(target)

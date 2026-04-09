"""Unit tests for skill_run_manager.py using temp directories."""

from __future__ import annotations

import json
import sys
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


def _patch_dirs(tmp_path: Path, monkeypatch) -> None:
    """Patch _RUNS_DIR so file I/O goes to tmp_path instead of the real reports/ directory."""
    monkeypatch.setattr(skill_run_manager, "_RUNS_DIR", tmp_path)


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_writes_required_fields(self, tmp_path, monkeypatch):
        _patch_dirs(tmp_path, monkeypatch)
        rc = skill_run_manager.main(["create", "--skills", "S-48"])
        assert rc == 0
        record = _load_record(tmp_path)
        assert "run_id" in record
        assert "S-48" in record["skills_invoked"]
        assert record["outcome"] == "pending"
        assert record["commit_sha"] is None
        assert record["completed_at"] is None

    def test_create_retroactive_flag(self, tmp_path, monkeypatch):
        _patch_dirs(tmp_path, monkeypatch)
        rc = skill_run_manager.main(["create", "--skills", "S-48", "--retroactive"])
        assert rc == 0
        record = _load_record(tmp_path)
        assert record["retroactive"] is True
        assert _get_run_id(tmp_path).startswith("retroactive-")


# ---------------------------------------------------------------------------
# TestRecordStep
# ---------------------------------------------------------------------------

class TestRecordStep:
    def test_record_step_appends_to_skill_details(self, tmp_path, monkeypatch):
        _patch_dirs(tmp_path, monkeypatch)
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

    def test_record_step_missing_record_returns_2(self, tmp_path, monkeypatch):
        _patch_dirs(tmp_path, monkeypatch)
        rc = skill_run_manager.main([
            "record-step", "--run-id", "nonexistent-id",
            "--skill", "S-48", "--type", "full",
        ])
        assert rc == 2


# ---------------------------------------------------------------------------
# TestGetDeclaredSkills
# ---------------------------------------------------------------------------

class TestGetDeclaredSkills:
    def test_excludes_inline_reasoning(self, tmp_path, monkeypatch, capsys):
        _patch_dirs(tmp_path, monkeypatch)
        skill_run_manager.main(["create", "--skills", "S-48", "S-23"])
        run_id = _get_run_id(tmp_path)

        # Mark S-23 as inline_reasoning
        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-23", "--type", "inline_reasoning",
        ])

        capsys.readouterr()  # clear stdout
        rc = skill_run_manager.main(["get-declared-skills", "--run-id", run_id])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert "S-48" in out
        assert "S-23" not in out


# ---------------------------------------------------------------------------
# TestValidate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_matching_declaration_exits_0(self, tmp_path, monkeypatch):
        _patch_dirs(tmp_path, monkeypatch)
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-48",
        ])
        assert rc == 0

    def test_extra_declared_skill_exits_1(self, tmp_path, monkeypatch):
        """Declaring S-99 when record only has S-48 is a false positive."""
        _patch_dirs(tmp_path, monkeypatch)
        skill_run_manager.main(["create", "--skills", "S-48"])
        run_id = _get_run_id(tmp_path)

        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-48, S-99",
        ])
        assert rc == 1

    def test_inline_declared_is_allowed(self, tmp_path, monkeypatch):
        """Declaring an inline_reasoning skill is now valid (has a record)."""
        _patch_dirs(tmp_path, monkeypatch)
        skill_run_manager.main(["create", "--skills", "S-73", "S-01"])
        run_id = _get_run_id(tmp_path)

        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-73", "--type", "full",
        ])
        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-01", "--type", "inline_reasoning",
        ])

        # Declaring both (full + inline) should pass
        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-73, S-01",
        ])
        assert rc == 0

    def test_inline_undeclared_is_allowed(self, tmp_path, monkeypatch):
        """NOT declaring an inline_reasoning skill is valid (it's optional)."""
        _patch_dirs(tmp_path, monkeypatch)
        skill_run_manager.main(["create", "--skills", "S-73", "S-01"])
        run_id = _get_run_id(tmp_path)

        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-73", "--type", "full",
        ])
        skill_run_manager.main([
            "record-step", "--run-id", run_id,
            "--skill", "S-01", "--type", "inline_reasoning",
        ])

        # Declaring only the full skill should pass
        rc = skill_run_manager.main([
            "validate", "--run-id", run_id, "--declared", "S-73",
        ])
        assert rc == 0

    def test_no_record_at_all_exits_1(self, tmp_path, monkeypatch):
        """Declaring a skill with no record entry at all is invalid."""
        _patch_dirs(tmp_path, monkeypatch)
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
    def test_finalize_sets_outcome_and_sha(self, tmp_path, monkeypatch):
        _patch_dirs(tmp_path, monkeypatch)
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

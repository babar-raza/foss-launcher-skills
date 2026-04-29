"""Unit tests for check_skill_run_records.py using temp directories and monkeypatching."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks" 
_PIPELINE_ROOT = _CI_ROOT.parent / "pipeline"
for _p in (str(_CI_ROOT), str(_PIPELINE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_skill_run_records  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(runs_dir: Path, run_id: str, skills: list[str], commit_sha: str) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id,
        "skills_invoked": skills,
        "skill_details": [],
        "outcome": "success",
        "commit_sha": commit_sha,
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")


# ---------------------------------------------------------------------------
# TestParseSkills (unit — no I/O)
# ---------------------------------------------------------------------------

class TestParseSkills:
    def test_parses_bracketed_form(self):
        msg = "feat: stuff\n\nSkills invoked: [S-48, S-23]\n"
        result = check_skill_run_records._parse_declared_skills(msg)
        assert result == ["S-48", "S-23"]

    def test_parses_unbracketed_form(self):
        msg = "feat: stuff\n\nSkills invoked: S-48\n"
        result = check_skill_run_records._parse_declared_skills(msg)
        assert result == ["S-48"]

    def test_no_declaration_returns_none(self):
        msg = "docs: just documentation, no skills"
        assert check_skill_run_records._parse_declared_skills(msg) is None


# ---------------------------------------------------------------------------
# TestMain
# ---------------------------------------------------------------------------

class TestMain:
    def test_matching_record_exits_0(self, tmp_path, monkeypatch):
        _make_record(tmp_path, "test-run", ["S-48"], "abc12345")
        check_skill_run_records.configure(runs_dir=tmp_path)
        monkeypatch.setattr(
            check_skill_run_records, "_get_commit_message",
            lambda sha: "feat: stuff\n\nSkills invoked: [S-48]\n",
        )
        assert check_skill_run_records.main(["--commits", "abc12345"]) == 0

    def test_extra_declared_skill_exits_1(self, tmp_path, monkeypatch):
        """Record has S-48 but message declares S-48 + S-99 — mismatch."""
        _make_record(tmp_path, "test-run", ["S-48"], "abc12345")
        check_skill_run_records.configure(runs_dir=tmp_path)
        monkeypatch.setattr(
            check_skill_run_records, "_get_commit_message",
            lambda sha: "feat: stuff\n\nSkills invoked: [S-48, S-99]\n",
        )
        assert check_skill_run_records.main(["--commits", "abc12345"]) == 1

    def test_no_skills_declaration_exits_0(self, tmp_path, monkeypatch):
        """Commit with no 'Skills invoked:' line is not a mismatch — just skipped."""
        check_skill_run_records.configure(runs_dir=tmp_path)
        monkeypatch.setattr(
            check_skill_run_records, "_get_commit_message",
            lambda sha: "docs: no skills here",
        )
        assert check_skill_run_records.main(["--commits", "abc12345"]) == 0

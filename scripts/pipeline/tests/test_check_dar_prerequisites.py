"""Tests for check_dar_prerequisites.py — DAR prerequisite enforcement."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure the pipeline package is importable
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import check_dar_prerequisites as cdp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DAR_AGENTS_MD = """\
## §6a Downstream Activation Rules (DAR)

| Downstream skill | Required upstream | Trigger condition |
|-----------------|------------------|------------------|
| `/page-draft` (S-19) | `/knowledge-bootstrap` | Always |
| `/page-draft` (S-19) | `/page-plan` (S-18) | Plan not in session context |
| `/page-enhance` (S-21) | S-25 `/eval-page` or S-17 `/rubric-align` (either satisfies -- choice of [S-25, S-17]) | Eval not in session context |
| `/content-check` (S-23) | `/knowledge-bootstrap` | Always |

Some other section
"""


def _make_run_record(tmp_path: Path, skills: list[str], run_id: str = "test-run") -> Path:
    record = {
        "run_id": run_id,
        "skills_invoked": skills,
        "skill_details": [],
        "outcome": "pending",
    }
    f = tmp_path / f"{run_id}.json"
    f.write_text(json.dumps(record), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# _parse_dar_table
# ---------------------------------------------------------------------------

class TestParseDarTable:
    def test_parses_rows(self):
        rows = cdp._parse_dar_table(_DAR_AGENTS_MD)
        assert len(rows) == 4

    def test_stops_at_section_boundary(self):
        rows = cdp._parse_dar_table(_DAR_AGENTS_MD)
        # All rows should come from the table
        for downstream, upstream, trigger in rows:
            assert downstream  # no empty cells

    def test_empty_text_returns_empty(self):
        assert cdp._parse_dar_table("") == []

    def test_no_table_returns_empty(self):
        assert cdp._parse_dar_table("# AGENTS.md\n\nSome content\n") == []


# ---------------------------------------------------------------------------
# _extract_identifiers
# ---------------------------------------------------------------------------

class TestExtractIdentifiers:
    def test_extracts_s_id_and_slug(self):
        ids = cdp._extract_identifiers("`/page-plan` (S-18)")
        assert "S-18" in ids
        assert "page-plan" in ids

    def test_extracts_multiple_options(self):
        cell = "S-25 `/eval-page` or S-17 `/rubric-align`"
        ids = cdp._extract_identifiers(cell)
        assert "S-25" in ids
        assert "S-17" in ids
        assert "eval-page" in ids
        assert "rubric-align" in ids

    def test_slug_only(self):
        ids = cdp._extract_identifiers("`/knowledge-bootstrap`")
        assert "knowledge-bootstrap" in ids
        assert not any(x.startswith("S-") for x in ids)


# ---------------------------------------------------------------------------
# _get_prerequisites
# ---------------------------------------------------------------------------

class TestGetPrerequisites:
    def setup_method(self):
        self.rows = cdp._parse_dar_table(_DAR_AGENTS_MD)

    def test_page_draft_has_two_prerequisite_groups(self):
        groups = cdp._get_prerequisites(self.rows, "page-draft")
        assert len(groups) == 2

    def test_page_draft_by_s_id(self):
        groups = cdp._get_prerequisites(self.rows, "S-19")
        assert len(groups) == 2

    def test_page_enhance_has_one_group_with_two_options(self):
        groups = cdp._get_prerequisites(self.rows, "page-enhance")
        assert len(groups) == 1
        alts = groups[0]
        # Either S-25 or S-17 (or their slugs) should be present
        assert any(x in ("S-25", "eval-page", "S-17", "rubric-align") for x in alts)

    def test_unknown_skill_returns_empty(self):
        groups = cdp._get_prerequisites(self.rows, "nonexistent-skill")
        assert groups == []

    def test_skill_with_no_dar_entry_returns_empty(self):
        groups = cdp._get_prerequisites(self.rows, "commit")
        assert groups == []


# ---------------------------------------------------------------------------
# _get_session_skills
# ---------------------------------------------------------------------------

class TestGetSessionSkills:
    def test_empty_dir_returns_empty(self, tmp_path):
        assert cdp._get_session_skills(tmp_path) == set()

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        assert cdp._get_session_skills(tmp_path / "does-not-exist") == set()

    def test_collects_skills_invoked(self, tmp_path):
        _make_run_record(tmp_path, ["S-01", "S-23"])
        found = cdp._get_session_skills(tmp_path)
        assert "S-01" in found
        assert "S-23" in found

    def test_collects_from_multiple_records(self, tmp_path):
        _make_run_record(tmp_path, ["S-01"], run_id="run-1")
        _make_run_record(tmp_path, ["S-18"], run_id="run-2")
        found = cdp._get_session_skills(tmp_path)
        assert "S-01" in found
        assert "S-18" in found

    def test_ignores_corrupt_json(self, tmp_path):
        (tmp_path / "corrupt.json").write_text("not-json", encoding="utf-8")
        _make_run_record(tmp_path, ["S-01"])
        found = cdp._get_session_skills(tmp_path)
        assert "S-01" in found

    def test_collects_from_skill_details(self, tmp_path):
        record = {
            "run_id": "test",
            "skills_invoked": [],
            "skill_details": [{"skill_id": "S-99"}],
            "outcome": "pending",
        }
        (tmp_path / "test.json").write_text(json.dumps(record), encoding="utf-8")
        found = cdp._get_session_skills(tmp_path)
        assert "S-99" in found


# ---------------------------------------------------------------------------
# check() integration — acceptance criteria
# ---------------------------------------------------------------------------

class TestCheck:
    def setup_method(self):
        # Write a real AGENTS.md fragment to a temp file
        self._orig_agents = cdp._DAR_TABLE
        self._orig_runs = cdp._RUNS_DIR

    def teardown_method(self):
        cdp._DAR_TABLE = self._orig_agents
        cdp._RUNS_DIR = self._orig_runs

    def _configure(self, tmp_path: Path, agents_content: str = _DAR_AGENTS_MD):
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text(agents_content, encoding="utf-8")
        runs_dir = tmp_path / "skill-runs"
        runs_dir.mkdir()
        cdp.configure(dar_table=agents_file, runs_dir=runs_dir)
        return runs_dir

    # --- Acceptance criterion 1: exits 1 when no prerequisite run record ---

    def test_page_draft_exits_1_when_no_kb_run(self, tmp_path):
        self._configure(tmp_path)
        result = cdp.check("page-draft")
        assert result == 1

    def test_page_draft_exits_1_when_no_page_plan_run(self, tmp_path):
        # knowledge-bootstrap present but page-plan missing
        runs_dir = self._configure(tmp_path)
        _make_run_record(runs_dir, ["knowledge-bootstrap"], run_id="run-kb")
        result = cdp.check("page-draft")
        assert result == 1

    # --- Acceptance criterion 2: exits 0 after prerequisite run records exist ---

    def test_page_draft_exits_0_when_all_prerequisites_present(self, tmp_path):
        runs_dir = self._configure(tmp_path)
        _make_run_record(runs_dir, ["knowledge-bootstrap"], run_id="run-kb")
        _make_run_record(runs_dir, ["S-18"], run_id="run-plan")
        result = cdp.check("page-draft")
        assert result == 0

    def test_page_draft_exits_0_with_s_id_match(self, tmp_path):
        # S-19 as skill arg; prerequisites in records by slug
        runs_dir = self._configure(tmp_path)
        _make_run_record(runs_dir, ["knowledge-bootstrap", "page-plan"], run_id="run-all")
        result = cdp.check("S-19")
        assert result == 0

    def test_page_enhance_exits_0_when_either_option_present(self, tmp_path):
        # S-25 OR S-17 satisfies the page-enhance requirement
        runs_dir = self._configure(tmp_path)
        _make_run_record(runs_dir, ["S-17"], run_id="run-rubric")
        result = cdp.check("page-enhance")
        assert result == 0

    def test_page_enhance_exits_1_when_neither_option_present(self, tmp_path):
        self._configure(tmp_path)
        result = cdp.check("page-enhance")
        assert result == 1

    # --- No DAR entry → exits 0 (skill not in table) ---

    def test_skill_with_no_dar_entry_exits_0(self, tmp_path):
        self._configure(tmp_path)
        result = cdp.check("commit")
        assert result == 0

    # --- Fail-open: missing AGENTS.md → exits 0 ---

    def test_missing_agents_md_exits_0_fail_open(self, tmp_path):
        runs_dir = tmp_path / "skill-runs"
        runs_dir.mkdir()
        cdp.configure(dar_table=tmp_path / "NONEXISTENT.md", runs_dir=runs_dir)
        result = cdp.check("page-draft")
        assert result == 0

    # --- Fail-open: empty DAR table → exits 0 ---

    def test_empty_dar_table_exits_0_fail_open(self, tmp_path):
        self._configure(tmp_path, agents_content="# AGENTS.md\n\nNo DAR table here.\n")
        result = cdp.check("page-draft")
        assert result == 0


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------

class TestMain:
    def setup_method(self):
        self._orig_agents = cdp._DAR_TABLE
        self._orig_runs = cdp._RUNS_DIR

    def teardown_method(self):
        cdp._DAR_TABLE = self._orig_agents
        cdp._RUNS_DIR = self._orig_runs

    def test_main_exits_1_on_missing_prereq(self, tmp_path):
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text(_DAR_AGENTS_MD, encoding="utf-8")
        runs_dir = tmp_path / "skill-runs"
        runs_dir.mkdir()
        cdp.configure(dar_table=agents_file, runs_dir=runs_dir)
        result = cdp.main(["--skill", "page-draft"])
        assert result == 1

    def test_main_exits_0_on_no_dar_entry(self, tmp_path):
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text(_DAR_AGENTS_MD, encoding="utf-8")
        runs_dir = tmp_path / "skill-runs"
        runs_dir.mkdir()
        cdp.configure(dar_table=agents_file, runs_dir=runs_dir)
        result = cdp.main(["--skill", "commit"])
        assert result == 0

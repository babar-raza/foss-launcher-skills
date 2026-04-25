"""Tests for skill_chain.py — DAR-driven prerequisite chain resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import skill_chain  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixture — minimal AGENTS.md with DAR table
# ---------------------------------------------------------------------------

_DAR_MD = """\
## §6a

| Downstream skill | Required upstream | Trigger condition |
|-----------------|------------------|------------------|
| `/page-enhance` (S-21) | S-25 `/eval-page` | Eval not in session |
| `/heal-page` (S-26) | S-25 `/eval-page` | Eval not in session |
| `/page-draft` (S-19) | `/knowledge-bootstrap` | Always |
| `/page-draft` (S-19) | S-18 `/page-plan` | Plan not in session |
| `/page-plan` (S-18) | `/knowledge-bootstrap` | Always |
| `/truth-merge` (S-35) | S-34 `/repo-scout` | Scout output absent |
| `/multi-req` (S-99) | S-25 `/eval-page` or S-17 `/rubric-align` | Either satisfies |
"""


@pytest.fixture()
def dar_md_file(tmp_path):
    f = tmp_path / "AGENTS.md"
    f.write_text(_DAR_MD, encoding="utf-8")
    return f


@pytest.fixture()
def runs_dir(tmp_path):
    d = tmp_path / "skill-runs"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _configure(dar_md_file, runs_dir):
    skill_chain.configure(agents_md=dar_md_file, runs_dir=runs_dir)
    yield
    # Reset to defaults after each test
    skill_chain._AGENTS_MD = _PIPELINE_DIR.parent.parent / "AGENTS.md"
    skill_chain._RUNS_DIR = _PIPELINE_DIR.parent.parent / "reports" / "skill-runs"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write_run_record(runs_dir: Path, skills: list[str]) -> None:
    record = {
        "skills_invoked": skills,
        "skill_details": [{"skill_id": s} for s in skills],
    }
    (runs_dir / "test-record.json").write_text(json.dumps(record), encoding="utf-8")


# ---------------------------------------------------------------------------
# TestResolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_no_prereqs_returns_empty_chain(self):
        code, chain = skill_chain.resolve("repo-scout")
        assert code == 0
        assert chain == []

    def test_single_prereq(self):
        code, chain = skill_chain.resolve("S-21")
        assert code == 0
        # S-21 requires S-25/eval-page
        assert len(chain) == 1
        assert "S-25" in chain[0] or "eval-page" in chain[0]

    def test_transitive_prereqs(self):
        # page-draft (S-19) requires knowledge-bootstrap AND page-plan (S-18)
        # page-plan (S-18) requires knowledge-bootstrap
        # So chain should include knowledge-bootstrap (from S-18) then S-18 then knowledge-bootstrap again (direct)
        # After dedup: knowledge-bootstrap, S-18
        code, chain = skill_chain.resolve("S-19")
        assert code == 0
        # Should have at least 2 steps: knowledge-bootstrap and page-plan
        identifiers_in_chain = [id_ for group in chain for id_ in group]
        assert any("knowledge-bootstrap" in id_ for id_ in identifiers_in_chain)
        assert any("S-18" in id_ or "page-plan" in id_ for id_ in identifiers_in_chain)

    def test_alternative_prereqs(self):
        # S-99 requires S-25 OR S-17 (either satisfies)
        code, chain = skill_chain.resolve("S-99")
        assert code == 0
        assert len(chain) == 1
        assert "S-25" in chain[0] or "S-17" in chain[0]

    def test_unknown_skill_returns_empty_chain(self):
        code, chain = skill_chain.resolve("nonexistent-skill")
        assert code == 0
        assert chain == []

    def test_missing_agents_md_returns_exit_2(self, tmp_path):
        skill_chain.configure(agents_md=tmp_path / "missing.md")
        code, chain = skill_chain.resolve("S-21")
        assert code == 2
        assert chain == []

    def test_empty_agents_md_returns_exit_2(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("# No DAR table here\n", encoding="utf-8")
        skill_chain.configure(agents_md=f)
        code, chain = skill_chain.resolve("S-21")
        assert code == 2


# ---------------------------------------------------------------------------
# TestMain — without --check-session
# ---------------------------------------------------------------------------

class TestMainNoSession:
    def test_no_prereqs_exits_0(self):
        result = skill_chain.main(["--skill", "repo-scout"])
        assert result == 0

    def test_skill_with_prereqs_exits_0(self):
        result = skill_chain.main(["--skill", "S-21"])
        assert result == 0

    def test_json_output_is_valid_json(self, capsys):
        result = skill_chain.main(["--skill", "S-21", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["target"] == "S-21"
        assert "prerequisites" in data

    def test_json_output_has_step_numbers(self, capsys):
        skill_chain.main(["--skill", "S-21", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for i, prereq in enumerate(data["prerequisites"]):
            assert prereq["step"] == i + 1

    def test_json_satisfied_is_none_without_check_session(self, capsys):
        skill_chain.main(["--skill", "S-21", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for prereq in data["prerequisites"]:
            assert prereq["satisfied"] is None

    def test_fail_open_on_missing_agents_md_exits_2(self, tmp_path):
        skill_chain.configure(agents_md=tmp_path / "missing.md")
        result = skill_chain.main(["--skill", "S-21"])
        assert result == 2


# ---------------------------------------------------------------------------
# TestMain — with --check-session
# ---------------------------------------------------------------------------

class TestMainCheckSession:
    def test_satisfied_prereqs_exits_0(self, runs_dir):
        _write_run_record(runs_dir, ["S-25", "eval-page"])
        result = skill_chain.main(["--skill", "S-21", "--check-session"])
        assert result == 0

    def test_missing_prereqs_exits_1(self, runs_dir):
        # No run records — S-25/eval-page not satisfied
        result = skill_chain.main(["--skill", "S-21", "--check-session"])
        assert result == 1

    def test_alternative_satisfied_exits_0(self, runs_dir):
        # S-99 needs S-25 OR S-17 — providing S-17 should satisfy
        _write_run_record(runs_dir, ["S-17"])
        result = skill_chain.main(["--skill", "S-99", "--check-session"])
        assert result == 0

    def test_no_prereqs_exits_0_with_check_session(self, runs_dir):
        result = skill_chain.main(["--skill", "repo-scout", "--check-session"])
        assert result == 0

    def test_json_satisfied_fields_populated(self, runs_dir, capsys):
        _write_run_record(runs_dir, ["S-25"])
        skill_chain.main(["--skill", "S-21", "--check-session", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for prereq in data["prerequisites"]:
            assert prereq["satisfied"] is not None

    def test_json_satisfied_true_when_met(self, runs_dir, capsys):
        _write_run_record(runs_dir, ["S-25", "eval-page"])
        skill_chain.main(["--skill", "S-21", "--check-session", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for prereq in data["prerequisites"]:
            assert prereq["satisfied"] is True

    def test_json_satisfied_false_when_missing(self, runs_dir, capsys):
        skill_chain.main(["--skill", "S-21", "--check-session", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for prereq in data["prerequisites"]:
            assert prereq["satisfied"] is False

"""Tests for check_onboarding_integrity.py, focused on the C7-TOC-ANCHORS slug algorithm.

No test file existed for this check before. Added while diagnosing a real false positive
(found live 2026-08-08): the slug algorithm collapsed whitespace runs into a single hyphen,
disagreeing with GitHub's real anchor algorithm (which converts each space individually,
producing a double hyphen when two spaces occur in a row -- e.g. after a lone "&" is
stripped out of "Mission & Taskcard"). This blocked any commit staging both RUNBOOK.md and
OPERATOR_GUIDE.md (the only two-file trigger combination that exercises this check locally),
regardless of what the commit actually changed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))

import check_onboarding_integrity as coi  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_state():
    yield
    coi.configure()
    coi._failures.clear()
    coi._passed_labels.clear()


# ---------------------------------------------------------------------------
# _github_heading_slug — the real bug
# ---------------------------------------------------------------------------


def test_slug_ampersand_produces_double_hyphen():
    """Regression test for the real defect: a lone '&' surrounded by spaces leaves two
    consecutive spaces after stripping, which GitHub renders as a double hyphen, not one."""
    heading = "17. Planning Discipline (Mission & Taskcard Methodology)"
    assert coi._github_heading_slug(heading) == "17-planning-discipline-mission--taskcard-methodology"


def test_slug_simple_heading_no_double_hyphen():
    assert coi._github_heading_slug("Purpose") == "purpose"


def test_slug_strips_punctuation():
    assert coi._github_heading_slug("2a. Source-of-Truth Hierarchy") == "2a-source-of-truth-hierarchy"


def test_slug_multiple_ampersands():
    assert coi._github_heading_slug("A & B & C") == "a--b--c"


def test_slug_leading_trailing_whitespace_stripped():
    assert coi._github_heading_slug("  Padded Heading  ") == "padded-heading"


# ---------------------------------------------------------------------------
# check_toc_anchors — end-to-end against a fixture repo
# ---------------------------------------------------------------------------


def _write_agents_md(tmp_path: Path, text: str) -> None:
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")


def test_toc_anchors_passes_for_ampersand_heading(tmp_path):
    _write_agents_md(
        tmp_path,
        "# AGENTS.md\n\n"
        "| §17 | [Planning Discipline](#17-planning-discipline-mission--taskcard-methodology) |\n\n"
        "## 17. Planning Discipline (Mission & Taskcard Methodology)\n",
    )
    coi.configure(repo_root=tmp_path)
    coi.check_toc_anchors()
    assert coi._failures == []


def test_toc_anchors_fails_for_genuinely_dangling_anchor(tmp_path):
    _write_agents_md(
        tmp_path,
        "# AGENTS.md\n\n"
        "| §99 | [Nonexistent](#99-does-not-exist) |\n\n"
        "## 1. Purpose\n",
    )
    coi.configure(repo_root=tmp_path)
    coi.check_toc_anchors()
    assert len(coi._failures) == 1
    assert "99-does-not-exist" in coi._failures[0]

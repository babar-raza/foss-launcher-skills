"""Tests for PageRoleEvaluator._check_faq — Rule 3: faq.list-vs-body H3 cross-check.

Root-cause context:
    content/kb.aspose.org/en/cells/net/faq.md was generated with 12 FAQ entries stored
    exclusively in frontmatter `faq.list`. Hugo renders `.Content` (body only) and never
    iterates frontmatter arrays, so all entries were invisible to users. The existing
    _check_faq rule counted any H2 headings; 4 structural headings satisfied the >=3
    threshold and the page received grade A, masking the defect.

Rule 3 (added to _check_faq):
    If `faq.list` is a non-empty list in frontmatter AND no H3 headings exist in the body,
    emit FAIL RV. Only fires when faq.list is explicitly present.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from content_eval.evaluators.page_role import PageRoleEvaluator
from content_eval.models import Finding, Heading, Page


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_EVALUATOR = PageRoleEvaluator()

_FAQ_ENTRIES = [
    {"question": "How do I install Aspose.Cells FOSS for .NET?",
     "answer": "Run `dotnet add package Aspose.Cells_FOSS`"},
    {"question": "How do I create a new Excel workbook?",
     "answer": "Instantiate `new Workbook()`"},
]


def _faq_page(
    faq_list: list[dict] | None = None,
    headings: list[Heading] | None = None,
    type_field: str = "topic",
) -> Page:
    """Build a minimal FAQ Page fixture without touching the filesystem."""
    fm: dict = {"type": type_field}
    if faq_list is not None:
        fm["faq"] = {"list": faq_list}
    return Page(
        filepath=Path("content/kb.aspose.org/en/cells/net/faq.md"),
        raw_text="",
        frontmatter=fm,
        body="",
        headings=headings or [],
        page_role="faq",
    )


def _rule3_fails(findings: list[Finding]) -> list[Finding]:
    """Return only Rule-3 FAIL findings (contain 'faq.list' in message)."""
    return [f for f in findings if f.level == "FAIL" and "faq.list" in f.message]


# ---------------------------------------------------------------------------
# Rule 3 — happy path (defect class)
# ---------------------------------------------------------------------------

class TestFaqListNoH3EmitsFail:
    """Rule 3 must fire when faq.list is populated but body has no H3 headings."""

    def test_cells_net_defect_pattern(self):
        """Reproduces the exact cells/net defect: faq.list + 4 structural H2s, 0 H3s."""
        page = _faq_page(
            faq_list=_FAQ_ENTRIES,
            headings=[
                Heading(level=2, text="Overview", line_no=10),
                Heading(level=2, text="Installation", line_no=20),
                Heading(level=2, text="Quick Start", line_no=30),
                Heading(level=2, text="Common Topics", line_no=40),
            ],
        )
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert fails, (
            "FAIL not emitted for faq.list + H2-only body. "
            f"All findings: {[f.message for f in findings]}"
        )

    def test_fail_level_is_fail_not_warn(self):
        """Severity must be FAIL — zero visible FAQ content is critical."""
        page = _faq_page(faq_list=_FAQ_ENTRIES, headings=[])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert fails, "Expected at least one FAIL finding"
        assert all(f.level == "FAIL" for f in fails)

    def test_fail_category_is_rv(self):
        """Category must be RV (role-violation)."""
        page = _faq_page(faq_list=_FAQ_ENTRIES, headings=[])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert fails
        assert all(f.category == "RV" for f in fails)

    def test_fail_message_contains_invisible_phrase(self):
        """Message must mention Hugo renderer invisibility."""
        page = _faq_page(faq_list=_FAQ_ENTRIES, headings=[])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert fails
        assert "invisible to the Hugo renderer" in fails[0].message

    def test_fail_message_contains_entry_count(self):
        """Message must include the count of trapped entries for diagnostic clarity."""
        entries = [{"question": f"Q{i}", "answer": f"A{i}"} for i in range(7)]
        page = _faq_page(faq_list=entries, headings=[])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert fails
        assert "7" in fails[0].message, (
            f"Expected count '7' in message; got: {fails[0].message}"
        )

    def test_suggestion_mentions_new_kb_faq(self):
        """Suggestion must reference the /new-kb-faq skill."""
        page = _faq_page(faq_list=_FAQ_ENTRIES, headings=[])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert fails
        assert "/new-kb-faq" in fails[0].suggestion, (
            f"Suggestion should reference /new-kb-faq; got: {fails[0].suggestion}"
        )


# ---------------------------------------------------------------------------
# Rule 3 — passing path (faq.list + H3 headings present → no Rule 3 FAIL)
# ---------------------------------------------------------------------------

class TestFaqListWithH3DoesNotFail:
    """Rule 3 must NOT fire when faq.list is present AND H3 headings exist in body."""

    def test_faq_list_plus_h3_headings(self):
        """Valid state: frontmatter list + matching ### question headings in body."""
        page = _faq_page(
            faq_list=_FAQ_ENTRIES,
            headings=[
                Heading(level=2, text="Frequently Asked Questions", line_no=5),
                Heading(level=3, text="How do I install Aspose.Cells FOSS for .NET?", line_no=10),
                Heading(level=3, text="How do I create a new Excel workbook?", line_no=20),
            ],
        )
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert not fails, (
            f"Rule 3 must not fire when H3 headings are present; got: {[f.message for f in fails]}"
        )

    def test_single_h3_heading_is_sufficient(self):
        """Even one H3 heading suppresses Rule 3 (content is at least partially visible)."""
        page = _faq_page(
            faq_list=_FAQ_ENTRIES,
            headings=[Heading(level=3, text="How do I install?", line_no=10)],
        )
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert not fails


# ---------------------------------------------------------------------------
# Rule 3 — regression (no faq.list → rule must not fire regardless of headings)
# ---------------------------------------------------------------------------

class TestNoFaqListNoRule3:
    """Pages without faq.list must never trigger Rule 3, regardless of heading structure."""

    def test_no_faq_list_no_headings(self):
        """Pure body-only FAQ (slides/net style) — no faq.list, no H3s → Rule 3 silent."""
        page = _faq_page(faq_list=None, headings=[])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert not fails

    def test_no_faq_list_with_h2_headings(self):
        """Slides/net pattern: no faq.list, H2 section + H3 questions → Rule 3 silent."""
        page = _faq_page(
            faq_list=None,
            headings=[
                Heading(level=2, text="Frequently Asked Questions", line_no=5),
                Heading(level=3, text="How do I install?", line_no=10),
                Heading(level=3, text="How do I save as XLSX?", line_no=20),
            ],
        )
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert not fails

    def test_empty_faq_list_no_rule3(self):
        """Edge case: faq.list key exists but list is empty → Rule 3 does not fire."""
        page = _faq_page(faq_list=[], headings=[])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        fails = _rule3_fails(findings)
        assert not fails, "Empty faq.list must not trigger Rule 3"


# ---------------------------------------------------------------------------
# Pre-existing rules still work (non-regression)
# ---------------------------------------------------------------------------

class TestExistingRulesUnchanged:
    """Confirm Rule 1 (type:topic) and Rule 2 (h2_count) still fire as before."""

    def test_rule1_type_topic_fail_still_fires(self):
        """Rule 1: type != topic → FAIL (pre-existing; must not regress)."""
        page = _faq_page(faq_list=None, headings=[], type_field="docs")
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        type_fails = [f for f in findings if "type: topic" in f.message and f.level == "FAIL"]
        assert type_fails, "Rule 1 (type:topic FAIL) must still fire"

    def test_rule2_h2_count_warn_still_fires(self):
        """Rule 2: h2_count < 3 → WARN (pre-existing; must not regress)."""
        page = _faq_page(faq_list=None, headings=[Heading(level=2, text="FAQ", line_no=5)])
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        h2_warns = [f for f in findings if "question headings" in f.message and f.level == "WARN"]
        assert h2_warns, "Rule 2 (h2_count WARN) must still fire"

    def test_rule2_h2_count_suppressed_when_enough(self):
        """Rule 2 must NOT fire when h2_count >= 3."""
        page = _faq_page(
            faq_list=None,
            headings=[
                Heading(level=2, text="A", line_no=1),
                Heading(level=2, text="B", line_no=2),
                Heading(level=2, text="C", line_no=3),
            ],
        )
        findings = _EVALUATOR.evaluate(page, knowledge=None)
        h2_warns = [f for f in findings if "question headings" in f.message and f.level == "WARN"]
        assert not h2_warns, "Rule 2 must not fire when h2_count >= 3"

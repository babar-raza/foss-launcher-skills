"""Integration tests for grading system wiring.

Tests the interaction between grade_writer, no_downgrade_guard decision matrix,
and content_eval.models grade computation.
"""

import textwrap
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from content_eval.models import compute_grade, compute_grade_with_criticality, Finding
from grade_writer import read_grade, write_grade
from no_downgrade_guard import _decision, DECISION_ALLOW, DECISION_WARN, DECISION_BLOCK


# ---------------------------------------------------------------------------
# Decision matrix — exhaustive
# ---------------------------------------------------------------------------

class TestDecisionMatrix:
    """Verify the decision matrix from the plan (Part 8.2)."""

    @pytest.mark.parametrize("existing,proposed,expected", [
        # A/B blocks D/F
        ("A", "D", DECISION_BLOCK),
        ("A", "F", DECISION_BLOCK),
        ("B", "D", DECISION_BLOCK),
        ("B", "F", DECISION_BLOCK),
        # A/B warns on C
        ("A", "C", DECISION_WARN),
        ("B", "C", DECISION_WARN),
        # A/B allows A/B
        ("A", "A", DECISION_ALLOW),
        ("A", "B", DECISION_ALLOW),
        ("B", "A", DECISION_ALLOW),
        ("B", "B", DECISION_ALLOW),
        # C blocks D/F
        ("C", "D", DECISION_BLOCK),
        ("C", "F", DECISION_BLOCK),
        # C allows A/B/C (lateral or better)
        ("C", "A", DECISION_ALLOW),
        ("C", "B", DECISION_ALLOW),
        ("C", "C", DECISION_ALLOW),
        # D/F allows anything
        ("D", "A", DECISION_ALLOW),
        ("D", "F", DECISION_ALLOW),
        ("F", "A", DECISION_ALLOW),
        ("F", "F", DECISION_ALLOW),
    ])
    def test_decision(self, existing, proposed, expected):
        assert _decision(existing, proposed, target_exists=True) == expected

    def test_new_file_always_allows(self):
        for grade in ("A", "B", "C", "D", "F"):
            assert _decision(None, grade, target_exists=False) == DECISION_ALLOW

    def test_no_stored_grade_always_allows(self):
        for grade in ("A", "B", "C", "D", "F"):
            assert _decision(None, grade, target_exists=True) == DECISION_ALLOW


# ---------------------------------------------------------------------------
# Grade write → read → decision pipeline
# ---------------------------------------------------------------------------

class TestGradeWriteReadDecision:
    """End-to-end: write a grade, read it back, feed to decision matrix."""

    def test_a_grade_blocks_f_proposed(self):
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "A", model_sha="sha1", evaluator_tier="full")
            stored = read_grade(p)
            assert stored["grade"] == "A"
            decision = _decision(stored["grade"], "F", target_exists=True)
            assert decision == DECISION_BLOCK
        finally:
            p.unlink(missing_ok=True)

    def test_d_grade_allows_b_proposed(self):
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "D", model_sha="sha1", evaluator_tier="full")
            stored = read_grade(p)
            decision = _decision(stored["grade"], "B", target_exists=True)
            assert decision == DECISION_ALLOW
        finally:
            p.unlink(missing_ok=True)

    def test_grade_upgrade_replaces_and_unblocks(self):
        """Page graded D, then upgraded to B. New B should block F."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "D", model_sha="sha1")
            # D allows anything
            assert _decision(read_grade(p)["grade"], "F", True) == DECISION_ALLOW
            # Upgrade to B
            write_grade(p, "B", model_sha="sha2")
            # B blocks F
            assert _decision(read_grade(p)["grade"], "F", True) == DECISION_BLOCK
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# EvalReport.grade property
# ---------------------------------------------------------------------------

class TestEvalReportGrade:
    def test_report_grade_reflects_findings(self):
        from content_eval.models import EvalReport
        report = EvalReport(findings=[
            Finding("FAIL", "AA", "a.md", 1, "bad api"),
            Finding("WARN", "ST", "a.md", 2, "struct issue"),
        ])
        # 1 FAIL → C
        assert report.grade == "C"

    def test_report_grade_a_on_clean(self):
        from content_eval.models import EvalReport
        report = EvalReport(findings=[
            Finding("INFO", "RL", "a.md", 1, "fyi"),
        ])
        assert report.grade == "A"


# ---------------------------------------------------------------------------
# Zero-finding grade write (regression test for by_file() miss)
# ---------------------------------------------------------------------------

class TestZeroFindingGradeWrite:
    """Ensures pages with zero findings still get grade A written.

    This is a regression test for the bug where --write-grade iterated
    report.by_file() (which only contains files with findings), causing
    zero-finding pages to be silently skipped.
    """

    def test_zero_finding_page_gets_grade_a(self):
        """Simulate the fixed CLI path: iterate pages list, not by_file()."""
        from content_eval.models import EvalReport
        p = _tmp_file("---\ntitle: Clean Page\n---\nBody.\n")
        try:
            # Report with no findings for this page (mimics zero-finding case)
            report = EvalReport(findings=[])
            by_file = report.by_file()
            # The page's filepath is NOT in by_file (zero findings)
            assert str(p) not in by_file

            # The fix: grade from page_findings (empty list) → grade A
            page_findings = by_file.get(str(p), [])
            grade = compute_grade_with_criticality(page_findings)
            assert grade == "A"

            # Write it
            write_grade(p, grade, model_sha="test_sha", evaluator_tier="full")
            stored = read_grade(p)
            assert stored is not None
            assert stored["grade"] == "A"
        finally:
            p.unlink(missing_ok=True)

    def test_mixed_findings_and_zero_finding_pages(self):
        """Pages with findings and without should all get grades."""
        from content_eval.models import EvalReport
        p_clean = _tmp_file("---\ntitle: Clean\n---\nBody.\n")
        p_dirty = _tmp_file("---\ntitle: Dirty\n---\nBody.\n")
        try:
            report = EvalReport(findings=[
                Finding("FAIL", "AA", str(p_dirty), 1, "bad api"),
            ])
            by_file = report.by_file()

            # Simulate iterating over both pages (the fix)
            for p in [p_clean, p_dirty]:
                page_findings = by_file.get(str(p), [])
                grade = compute_grade_with_criticality(page_findings)
                write_grade(p, grade, model_sha="sha1", evaluator_tier="full")

            assert read_grade(p_clean)["grade"] == "A"
            assert read_grade(p_dirty)["grade"] == "C"  # 1 FAIL
        finally:
            p_clean.unlink(missing_ok=True)
            p_dirty.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_file(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    )
    f.write(content)
    f.close()
    return Path(f.name)

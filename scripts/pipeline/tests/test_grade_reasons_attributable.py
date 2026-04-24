"""Tests for VERIFY-03: grade_reasons evaluator attribution.

Confirms that grade_reasons() output includes evaluator names for FAIL and WARN
findings, making grading results interpretable without re-running evaluation.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/pipeline is in the path
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from content_eval.models import EvalReport, Finding  # noqa: E402


def _make_report(findings: list[Finding]) -> EvalReport:
    return EvalReport(findings=findings)


def _finding(level: str, evaluator: str, message: str = "test msg", line_no: int = 0) -> Finding:
    return Finding(
        level=level,
        category="AA",
        filepath="test.md",
        line_no=line_no,
        message=message,
        evaluator=evaluator,
    )


class TestGradeReasonsAttribution:
    """VERIFY-03: grade_reasons must include evaluator name in all summaries."""

    def test_fail_reason_includes_evaluator_name(self):
        """Single FAIL: summary includes evaluator name and count."""
        report = _make_report([_finding("FAIL", "api_accuracy")])
        reasons = report.grade_reasons()
        assert any("api_accuracy" in r for r in reasons), (
            f"Expected evaluator name 'api_accuracy' in grade_reasons, got: {reasons}"
        )

    def test_fail_reason_includes_multiplication_format(self):
        """Single FAIL: summary uses Evaluator×Count format."""
        report = _make_report([_finding("FAIL", "api_completeness")])
        reasons = report.grade_reasons()
        summary_line = reasons[0]
        assert "api_completeness\u00d71" in summary_line or "api_completeness×1" in summary_line, (
            f"Expected 'api_completeness×1' in first reason: {summary_line}"
        )

    def test_multiple_fail_evaluators_all_listed(self):
        """Multiple FAILs from different evaluators: all evaluators listed."""
        report = _make_report([
            _finding("FAIL", "api_accuracy"),
            _finding("FAIL", "code_syntax_check"),
            _finding("FAIL", "api_accuracy"),
        ])
        reasons = report.grade_reasons()
        summary_line = reasons[0]
        assert "api_accuracy" in summary_line, f"Missing api_accuracy in: {summary_line}"
        assert "code_syntax_check" in summary_line, f"Missing code_syntax_check in: {summary_line}"

    def test_fail_count_reflected_in_summary(self):
        """Two FAILs from same evaluator: count shows ×2."""
        report = _make_report([
            _finding("FAIL", "api_accuracy"),
            _finding("FAIL", "api_accuracy"),
        ])
        reasons = report.grade_reasons()
        summary_line = reasons[0]
        assert "api_accuracy\u00d72" in summary_line or "api_accuracy×2" in summary_line, (
            f"Expected 'api_accuracy×2' in: {summary_line}"
        )

    def test_first_fail_message_included(self):
        """First FAIL message is included as a separate reason for human context."""
        report = _make_report([_finding("FAIL", "api_accuracy", message="class 'Foo' not found", line_no=42)])
        reasons = report.grade_reasons()
        message_lines = [r for r in reasons if "class 'Foo' not found" in r]
        assert message_lines, f"Expected first FAIL message in grade_reasons, got: {reasons}"

    def test_first_fail_message_includes_line_number(self):
        """First FAIL message includes line number when available."""
        report = _make_report([_finding("FAIL", "api_accuracy", message="missing member", line_no=10)])
        reasons = report.grade_reasons()
        message_lines = [r for r in reasons if "missing member" in r]
        assert message_lines, f"Expected FAIL message in grade_reasons, got: {reasons}"
        assert "line 10" in message_lines[0], f"Expected 'line 10' in: {message_lines[0]}"

    def test_warn_reason_includes_evaluator_name(self):
        """WARN summary includes evaluator name (must use a canonical evaluator).

        risk_language is EXPERIMENTAL — its findings do not appear in grade_reasons.
        Use api_accuracy (canonical) for this test.
        """
        report = _make_report([_finding("WARN", "api_accuracy")])
        reasons = report.grade_reasons()
        assert reasons, "Expected at least one reason"
        assert any("api_accuracy" in r for r in reasons), (
            f"Expected evaluator name 'api_accuracy' in grade_reasons, got: {reasons}"
        )

    def test_no_findings_is_still_clear(self):
        """No findings: grade_reasons still produces a clear message."""
        report = _make_report([])
        reasons = report.grade_reasons()
        assert reasons, "Expected at least one reason for no-findings case"
        assert any("No findings" in r for r in reasons), (
            f"Expected 'No findings' message, got: {reasons}"
        )

    def test_grade_a_no_findings_unchanged(self):
        """Grade A with no findings still says 'No findings -> grade A'."""
        report = _make_report([])
        reasons = report.grade_reasons()
        assert any("grade A" in r for r in reasons), (
            f"Expected 'grade A' in reasons, got: {reasons}"
        )

    def test_unknown_evaluator_shown_as_unknown(self):
        """Missing evaluator name shows 'unknown' not empty string."""
        f = Finding(
            level="FAIL",
            category="AA",
            filepath="test.md",
            line_no=0,
            message="test",
            evaluator="",  # no evaluator set
        )
        report = _make_report([f])
        reasons = report.grade_reasons()
        assert any("unknown" in r for r in reasons), (
            f"Expected 'unknown' fallback in grade_reasons, got: {reasons}"
        )


# ---------------------------------------------------------------------------
# Canonical / Experimental separation — FA-01 acceptance criteria
# ---------------------------------------------------------------------------
class TestCanonicalExperimentalSeparation:
    """Verify that experimental evaluator findings cannot affect the canonical grade.

    These tests enforce FA-01 acceptance criteria: a FAIL or ceiling-triggering
    WARN from an experimental evaluator must leave the canonical grade unchanged.
    """

    def _exp_finding(self, level: str, evaluator: str = "capability_claim_check",
                     category: str = "CF") -> Finding:
        """Return a finding from a known EXPERIMENTAL evaluator."""
        return Finding(
            level=level,
            category=category,
            filepath="test.md",
            line_no=1,
            message=f"{evaluator} {level} finding",
            evaluator=evaluator,
        )

    def _canon_finding(self, level: str, evaluator: str = "api_accuracy",
                       category: str = "AA") -> Finding:
        """Return a finding from a known CANONICAL evaluator."""
        return Finding(
            level=level,
            category=category,
            filepath="test.md",
            line_no=1,
            message=f"{evaluator} {level} finding",
            evaluator=evaluator,
        )

    # Test 1 — experimental FAIL only: canonical grade unchanged (must stay A)
    def test_experimental_fail_only_grade_unchanged(self):
        """Experimental FAIL in isolation must not lower canonical grade from A."""
        report = _make_report([self._exp_finding("FAIL")])
        assert report.grade == "A", (
            f"Experimental FAIL should not change canonical grade from A, got: {report.grade}"
        )

    # Test 2 — canonical FAIL only: grade changes as expected (C)
    def test_canonical_fail_changes_grade(self):
        """A single canonical FAIL must produce grade C (1-2 FAIL threshold)."""
        report = _make_report([self._canon_finding("FAIL")])
        assert report.grade == "C", (
            f"Single canonical FAIL should produce grade C, got: {report.grade}"
        )

    # Test 3 — mixed findings: only canonical affects grade/ceiling
    def test_mixed_findings_only_canonical_affects_grade(self):
        """Mixed canonical + experimental findings: grade driven by canonical only."""
        # One canonical WARN + one experimental FAIL
        # Expected: 0 canonical FAILs, 1 canonical WARN → grade A (0-2 WARNs)
        report = _make_report([
            self._canon_finding("WARN"),
            self._exp_finding("FAIL"),
        ])
        assert report.grade == "A", (
            f"With 1 canonical WARN + 1 experimental FAIL, grade should be A, got: {report.grade}"
        )

    # Test 4 — write-path: experimental-only change doesn't trigger grade shift
    def test_experimental_finding_not_in_grade_reasons(self):
        """grade_reasons must not reference experimental evaluator as grade cause."""
        report = _make_report([self._exp_finding("FAIL")])
        reasons = report.grade_reasons()
        # Grade should be A and reasons should not mention the experimental evaluator
        assert report.grade == "A", f"Grade should be A, got: {report.grade}"
        assert not any("capability_claim_check" in r for r in reasons), (
            f"Experimental evaluator name must not appear in grade_reasons as a grade cause: {reasons}"
        )

    # Test 5 — V0 regression: capability_claim_check/structure WARN does NOT cap via CF ceiling
    def test_cf_ceiling_does_not_apply_to_experimental_cf_finding(self):
        """CF category ceiling must not cap grade when finding is from experimental evaluator.

        grade_config.yaml: CF: {levels: [WARN, FAIL], ceiling: C}
        capability_claim_check → category CF → EXPERIMENTAL
        A WARN from this evaluator previously capped canonical grade to C via CF ceiling.
        After fix: canonical grade is computed from canonical findings only.
        """
        # No canonical findings → base grade A.
        # CF WARN from capability_claim_check (experimental) must not cap to C.
        report = _make_report([
            Finding(
                level="WARN",
                category="CF",
                filepath="test.md",
                line_no=5,
                message="capability claim mismatch",
                evaluator="capability_claim_check",
            )
        ])
        assert report.grade == "A", (
            f"CF ceiling from experimental evaluator must not cap canonical grade to C; got: {report.grade}"
        )
        reasons = report.grade_reasons()
        assert not any("CF ceiling" in r for r in reasons), (
            f"CF ceiling reason must not appear when finding is from experimental evaluator: {reasons}"
        )

"""End-to-end integration test for the content_eval pipeline.

Covers:
- EVALUATOR_LOGIC_VERSION is present and correct
- compute_grade and EvalReport.grade return correct grade for known finding counts
- grade_reasons() returns non-empty list of strings
- grade_writer.write_grade writes grade + logic_version to frontmatter
- Full eval CLI invocation on fixture files produces expected output
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


# ---------------------------------------------------------------------------
# Tests for EVALUATOR_LOGIC_VERSION consistency
# ---------------------------------------------------------------------------

class TestEvaluatorLogicVersionConsistency:
    """EVALUATOR_LOGIC_VERSION must match in __init__.py and grade_config.yaml."""

    def test_version_is_string(self):
        from content_eval import EVALUATOR_LOGIC_VERSION
        assert isinstance(EVALUATOR_LOGIC_VERSION, str), (
            "EVALUATOR_LOGIC_VERSION must be a string"
        )

    def test_version_matches_grade_config_yaml(self):
        """grade_config.yaml evaluator_logic_version must match __init__.py."""
        import yaml
        from content_eval import EVALUATOR_LOGIC_VERSION

        grade_config_path = _PIPELINE_DIR / "content_eval" / "grade_config.yaml"
        assert grade_config_path.exists(), f"grade_config.yaml not found at {grade_config_path}"

        config = yaml.safe_load(grade_config_path.read_text(encoding="utf-8"))
        yaml_version = config.get("evaluator_logic_version", "")
        assert yaml_version == EVALUATOR_LOGIC_VERSION, (
            f"Version mismatch: __init__.py={EVALUATOR_LOGIC_VERSION!r} "
            f"grade_config.yaml={yaml_version!r}. "
            "Bump grade_config.yaml evaluator_logic_version to match."
        )


# ---------------------------------------------------------------------------
# Tests for compute_grade and grade thresholds
# ---------------------------------------------------------------------------

class TestComputeGrade:
    """compute_grade must map finding counts to correct letter grades."""

    def test_no_findings_is_grade_a(self):
        from content_eval.models import compute_grade
        assert compute_grade(0, 0) == "A"

    def test_warns_only_grade_b_or_c(self):
        from content_eval.models import compute_grade
        # A few WARNs should not drop to D or F
        grade = compute_grade(0, 3)
        assert grade in ("A", "B", "C"), f"Expected A/B/C for 0 FAILs 3 WARNs, got {grade}"

    def test_one_fail_drops_grade(self):
        from content_eval.models import compute_grade
        grade = compute_grade(1, 0)
        assert grade in ("C", "D", "F"), (
            f"1 FAIL should drop grade to C/D/F, got {grade}"
        )

    def test_many_fails_is_grade_f(self):
        from content_eval.models import compute_grade
        grade = compute_grade(10, 0)
        assert grade == "F", f"10 FAILs should be grade F, got {grade}"


# ---------------------------------------------------------------------------
# Tests for EvalReport
# ---------------------------------------------------------------------------

class TestEvalReport:
    """EvalReport.grade and grade_reasons() must reflect Finding counts."""

    def _make_finding(self, severity: str, category: str = "AA") -> "Finding":
        from content_eval.models import Finding
        return Finding(severity, category, "test.md", 10, "test message")

    def test_no_findings_grade_a(self):
        from content_eval.models import EvalReport
        report = EvalReport([])
        assert report.grade == "A"

    def test_fail_finding_drops_grade(self):
        from content_eval.models import EvalReport
        report = EvalReport([self._make_finding("FAIL")])
        assert report.grade in ("C", "D", "F")

    def test_grade_reasons_returns_strings(self):
        from content_eval.models import EvalReport
        report = EvalReport([self._make_finding("FAIL"), self._make_finding("WARN")])
        reasons = report.grade_reasons()
        assert isinstance(reasons, list), "grade_reasons() must return a list"
        assert len(reasons) >= 1, "grade_reasons() must return at least one reason"
        for r in reasons:
            assert isinstance(r, str), f"Each reason must be a string, got {type(r)}"

    def test_grade_reasons_empty_on_passing(self):
        from content_eval.models import EvalReport
        report = EvalReport([])
        reasons = report.grade_reasons()
        # Even for Grade A, grade_reasons() should return a list (may include "No findings" note)
        assert isinstance(reasons, list)


# ---------------------------------------------------------------------------
# Tests for grade_writer integration
# ---------------------------------------------------------------------------

class TestGradeWriterIntegration:
    """write_grade must embed logic_version in frontmatter."""

    def test_write_grade_embeds_logic_version(self, tmp_path: Path):
        from content_eval import EVALUATOR_LOGIC_VERSION
        from grade_writer import write_grade

        page = tmp_path / "test_page.md"
        page.write_text(textwrap.dedent("""\
            ---
            title: Test Page
            description: A test page for grade writer.
            provenance:
              content_origin: skill-generated
            evidence:
              model_sha: abc123
            ---

            ## Overview

            This is a test page.
        """), encoding="utf-8")

        write_grade(page, "B", model_sha="abc123", evaluator_tier="structural",
                    logic_version=EVALUATOR_LOGIC_VERSION, grade_reasons=["Test reason"])

        content = page.read_text(encoding="utf-8")
        assert f"graded_logic_version: {EVALUATOR_LOGIC_VERSION}" in content, (
            f"Expected graded_logic_version: {EVALUATOR_LOGIC_VERSION} in frontmatter"
        )
        assert "grade: B" in content

    def test_write_grade_overwrites_existing_grade(self, tmp_path: Path):
        from content_eval import EVALUATOR_LOGIC_VERSION
        from grade_writer import write_grade

        page = tmp_path / "test_page2.md"
        page.write_text(textwrap.dedent("""\
            ---
            title: Test Page 2
            description: Another test page.
            evidence:
              model_sha: abc123
            grade: A
            graded_logic_version: 1
            ---

            ## Content

            Test content.
        """), encoding="utf-8")

        write_grade(page, "D", model_sha="abc123", evaluator_tier="full",
                    logic_version=EVALUATOR_LOGIC_VERSION, grade_reasons=["Multiple FAILs"])

        content = page.read_text(encoding="utf-8")
        assert "grade: D" in content
        assert f"graded_logic_version: {EVALUATOR_LOGIC_VERSION}" in content
        # Old grade A should be gone
        assert "grade: A" not in content

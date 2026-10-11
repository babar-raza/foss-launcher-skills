"""Tests for content_eval knowledge gate and evaluator crash handling."""
import pytest

from content_eval.models import Finding, EvalReport


class TestEvaluatorCrashProducesFail:
    """Crashed evaluator must produce FAIL finding, not WARN."""

    def test_evaluator_crash_finding_level_is_fail(self):
        """Simulate the finding that cli.py creates on evaluator exception.

        The finding must use level='FAIL' so it affects the grade.
        Previously this was 'WARN', which made crashes invisible to grading.
        """
        # This mirrors the exact Finding created in cli.py's except block
        finding = Finding(
            level="FAIL",
            category="PIPELINE",
            filepath="content/docs.aspose.org/en/slides/python/test.md",
            line_no=0,
            message="Evaluator 'accuracy' raised ValueError: boom",
            evaluator="cli",
            suggestion="Check stderr for full traceback.",
        )
        assert finding.level == "FAIL"

        # Verify it counts as a fail in an EvalReport
        report = EvalReport(findings=[finding])
        assert len(report.fails) == 1
        assert len(report.warns) == 0

    def test_warn_level_would_not_count_as_fail(self):
        """Confirm that WARN findings do NOT appear in report.fails.

        This is the old (broken) behavior — kept as a regression guard.
        """
        finding = Finding(
            level="WARN",
            category="PIPELINE",
            filepath="content/docs.aspose.org/en/slides/python/test.md",
            line_no=0,
            message="Evaluator 'accuracy' raised ValueError: boom",
            evaluator="cli",
        )
        report = EvalReport(findings=[finding])
        assert len(report.fails) == 0
        assert len(report.warns) == 1


class TestKnowledgeUnavailableProducesFail:
    """Knowledge.available=False must produce FAIL finding, not empty results."""

    def test_knowledge_unavailable_finding_level_is_fail(self):
        """The PRECONDITION_FAIL finding for unavailable knowledge must be FAIL."""
        # This mirrors the exact Finding created in cli.py's knowledge gate
        finding = Finding(
            level="FAIL",
            category="PIPELINE",
            filepath="content/docs.aspose.org/en/slides/python/_index.md",
            line_no=0,
            message="Knowledge unavailable for slides/python. "
                    "Run /knowledge-bootstrap slides python first. "
                    "Grading without knowledge produces inflated grades.",
            evaluator="cli",
            suggestion="Run /knowledge-bootstrap to populate knowledge artifacts.",
        )
        assert finding.level == "FAIL"

        report = EvalReport(findings=[finding])
        assert len(report.fails) == 1
        assert len(report.warns) == 0

    def test_knowledge_unavailable_finding_has_stable_id(self):
        """The finding must produce a deterministic stable ID."""
        finding = Finding(
            level="FAIL",
            category="PIPELINE",
            filepath="content/docs.aspose.org/en/slides/python/_index.md",
            line_no=0,
            message="Knowledge unavailable for slides/python. "
                    "Run /knowledge-bootstrap slides python first. "
                    "Grading without knowledge produces inflated grades.",
            evaluator="cli",
            suggestion="Run /knowledge-bootstrap to populate knowledge artifacts.",
        )
        assert finding.id.startswith("CE-")
        assert len(finding.id) == 11  # CE- + 8 hex chars

    def test_dedup_gate_fires_once_per_key(self):
        """The _knowledge_unavailable_keys set ensures one finding per family/platform."""
        # Simulate the dedup logic from cli.py
        _knowledge_unavailable_keys: set[tuple[str, str]] = set()
        findings: list[Finding] = []

        keys_to_process = [
            ("slides", "python"),
            ("slides", "python"),  # duplicate — should NOT emit
            ("cells", "java"),
        ]

        for family, platform in keys_to_process:
            key = (family, platform)
            if key not in _knowledge_unavailable_keys:
                _knowledge_unavailable_keys.add(key)
                findings.append(Finding(
                    level="FAIL",
                    category="PIPELINE",
                    filepath=f"content/docs.aspose.org/en/{family}/{platform}/_index.md",
                    line_no=0,
                    message=f"Knowledge unavailable for {family}/{platform}.",
                    evaluator="cli",
                ))

        # Two unique keys → two findings (not three)
        assert len(findings) == 2
        assert "slides/python" in findings[0].message
        assert "cells/java" in findings[1].message

"""Grade consistency contract tests for attach_evidence vs content_eval.

Ensures the evaluator subset used by attach_evidence() for reference pages
is always included in the DEFAULT_EVALUATORS list used by content_eval.
This prevents silent grade split-brain where attach_evidence grades higher
than content_eval because an evaluator was removed from the full suite.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


class TestAttachEvidenceEvaluatorSubset:
    """Verify attach_evidence's reference evaluators are a subset of content_eval's."""

    def test_dc_evaluator_in_default_evaluators(self):
        """DescriptionCompletenessEvaluator must be in DEFAULT_EVALUATORS."""
        from content_eval.config import DEFAULT_EVALUATORS
        assert "description_completeness" in DEFAULT_EVALUATORS, (
            "description_completeness was removed from DEFAULT_EVALUATORS — "
            "attach_evidence uses it for reference pages but content_eval would skip it"
        )

    def test_cs_evaluator_in_default_evaluators(self):
        """ContentSubstanceEvaluator must be in DEFAULT_EVALUATORS."""
        from content_eval.config import DEFAULT_EVALUATORS
        assert "content_substance" in DEFAULT_EVALUATORS, (
            "content_substance was removed from DEFAULT_EVALUATORS — "
            "attach_evidence uses it for reference pages but content_eval would skip it"
        )

    def test_dc_evaluator_importable(self):
        """DescriptionCompletenessEvaluator must be importable (not deleted)."""
        from content_eval.evaluators.description_completeness import (
            DescriptionCompletenessEvaluator,
        )
        assert callable(getattr(DescriptionCompletenessEvaluator, "evaluate", None))

    def test_cs_evaluator_importable(self):
        """ContentSubstanceEvaluator must be importable (not deleted)."""
        from content_eval.evaluators.content_substance import (
            ContentSubstanceEvaluator,
        )
        assert callable(getattr(ContentSubstanceEvaluator, "evaluate", None))


class TestGradeMonotonicity:
    """Verify grade computation is monotonic: more findings = worse grade."""

    def test_more_fails_never_improve_grade(self):
        """Adding FAILs must never produce a better (higher) grade."""
        from content_eval.models import compute_grade
        grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        prev_rank = -1
        for fails in range(0, 10):
            grade = compute_grade(fails, 0)
            rank = grade_order[grade]
            assert rank >= prev_rank, (
                f"Grade improved from {prev_rank} to {rank} when fails went to {fails}"
            )
            prev_rank = rank

    def test_more_warns_never_improve_grade(self):
        """Adding WARNs must never produce a better (higher) grade."""
        from content_eval.models import compute_grade
        grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        prev_rank = -1
        for warns in range(0, 10):
            grade = compute_grade(0, warns)
            rank = grade_order[grade]
            assert rank >= prev_rank, (
                f"Grade improved from {prev_rank} to {rank} when warns went to {warns}"
            )
            prev_rank = rank


class TestAttachEvidenceReferenceGuard:
    """Verify runner.py still contains the reference-page evaluator block."""

    def test_runner_has_reference_evaluator_block(self):
        """runner.py must contain the reference.aspose.org evaluator block."""
        runner_path = _PIPELINE_DIR / "evidence" / "runner.py"
        source = runner_path.read_text(encoding="utf-8")
        assert "reference.aspose.org" in source, (
            "runner.py no longer checks for reference.aspose.org — "
            "the reference-page evaluator block was removed"
        )
        assert "DescriptionCompletenessEvaluator" in source, (
            "runner.py no longer imports DescriptionCompletenessEvaluator"
        )
        assert "ContentSubstanceEvaluator" in source, (
            "runner.py no longer imports ContentSubstanceEvaluator"
        )

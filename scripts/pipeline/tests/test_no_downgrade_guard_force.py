"""Tests for no_downgrade_guard.py --force-regenerate flag (ST-022)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from no_downgrade_guard import (
    compare_content,
    DECISION_ALLOW,
    DECISION_BLOCK,
)


def _mock_evaluate(grade="D", fail_count=10, warn_count=5):
    """Return a mock _evaluate_file result with the given grade."""
    return {
        "fail_count": fail_count,
        "warn_count": warn_count,
        "grade": grade,
        "findings": [
            {"level": "FAIL", "message": "mock fail", "line": 1, "category": "test"}
        ] * fail_count,
    }


# Patch targets — all in the no_downgrade_guard module namespace.
_PATCH_EVALUATE = "no_downgrade_guard._evaluate_file"
_PATCH_INFER = "no_downgrade_guard.infer_product"
_PATCH_READ_GRADE = "no_downgrade_guard.read_grade"


class TestForceRegenerateFlag:
    """ST-022: --force-regenerate bypasses downgrade guards."""

    def _make_existing_page(self, tmp_path: Path, words=200, headings=5, code_blocks=2, grade="A") -> Path:
        """Write a synthetic existing page and return its path."""
        lines = ["---", f"title: Test Page", f"grade: {grade}", "---", ""]
        for h in range(headings):
            lines.append(f"## Section {h + 1}")
            words_per_section = max(1, words // max(headings, 1))
            lines.append(" ".join(f"word{i}" for i in range(words_per_section)))
            if code_blocks > 0 and h < code_blocks:
                lines.append("```python")
                lines.append(f"print('section {h}')")
                lines.append("```")
        page = tmp_path / "test-page.md"
        page.write_text("\n".join(lines), encoding="utf-8")
        return page

    @patch(_PATCH_READ_GRADE, return_value=None)
    @patch(_PATCH_EVALUATE)
    @patch(_PATCH_INFER, return_value=("slides", "net"))
    def test_force_allows_grade_downgrade(self, mock_infer, mock_eval, mock_read_grade, tmp_path):
        """force_regenerate=True returns ALLOW even for A->D downgrade."""
        target = self._make_existing_page(tmp_path, grade="A")
        proposed = "# Rewritten\nShort new content that would grade D."

        # First call evaluates existing (A), second evaluates proposed (D).
        mock_eval.side_effect = [
            _mock_evaluate(grade="A", fail_count=0, warn_count=0),
            _mock_evaluate(grade="D", fail_count=10, warn_count=5),
        ]

        result = compare_content(target, proposed, force_regenerate=True)

        assert result["decision"] == DECISION_ALLOW
        assert "force-regenerate" in result["reason"]

    @patch(_PATCH_READ_GRADE, return_value=None)
    @patch(_PATCH_EVALUATE)
    @patch(_PATCH_INFER, return_value=("slides", "net"))
    def test_force_skips_structural_regression(self, mock_infer, mock_eval, mock_read_grade, tmp_path):
        """force_regenerate=True returns ALLOW even with structural regression (word count drop)."""
        target = self._make_existing_page(tmp_path, words=500, headings=8, code_blocks=3)
        proposed = "# Stub\nTiny."  # Would normally trigger structural BLOCK.

        mock_eval.side_effect = [
            _mock_evaluate(grade="A", fail_count=0, warn_count=0),
            _mock_evaluate(grade="D", fail_count=10, warn_count=5),
        ]

        result = compare_content(target, proposed, force_regenerate=True)

        assert result["decision"] == DECISION_ALLOW
        assert "force-regenerate" in result["reason"]
        # Structural check was skipped, so we should have grade info from _evaluate_file.
        assert result["proposed"]["grade"] == "D"

    @patch(_PATCH_READ_GRADE, return_value=None)
    @patch(_PATCH_EVALUATE)
    @patch(_PATCH_INFER, return_value=("slides", "net"))
    def test_force_flag_in_return_dict(self, mock_infer, mock_eval, mock_read_grade, tmp_path):
        """force_regenerate=True includes the flag in the return dict for audit trail."""
        target = self._make_existing_page(tmp_path)
        proposed = "# New content\nSome words here."

        mock_eval.side_effect = [
            _mock_evaluate(grade="A", fail_count=0, warn_count=0),
            _mock_evaluate(grade="B", fail_count=1, warn_count=0),
        ]

        result = compare_content(target, proposed, force_regenerate=True)

        assert result.get("force_regenerate") is True

    @patch(_PATCH_READ_GRADE, return_value=None)
    @patch(_PATCH_EVALUATE)
    @patch(_PATCH_INFER, return_value=("slides", "net"))
    def test_default_preserves_existing_behavior(self, mock_infer, mock_eval, mock_read_grade, tmp_path):
        """force_regenerate=False (default) still blocks A->D downgrade."""
        target = self._make_existing_page(tmp_path, words=60, headings=0, code_blocks=0)
        # Proposed content that won't trigger structural checks but will trigger grade block.
        proposed = " ".join(f"word{i}" for i in range(60)) + "\n"

        mock_eval.side_effect = [
            _mock_evaluate(grade="A", fail_count=0, warn_count=0),
            _mock_evaluate(grade="D", fail_count=10, warn_count=5),
        ]

        result = compare_content(target, proposed, force_regenerate=False)

        assert result["decision"] == DECISION_BLOCK
        assert "force_regenerate" not in result

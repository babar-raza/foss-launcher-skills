"""Tests for verify.py — healing verification with regression detection."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verify import (
    HealingReport,
    VerifyResult,
    _compare_findings,
    _findings_from_dicts,
    _regression_severity,
    verify_healing,
)
from content_eval.models import Finding


def _make_finding(
    level: str = "FAIL",
    category: str = "AA",
    filepath: str = "test.md",
    line_no: int = 1,
    message: str = "test finding",
    evaluator: str = "test_eval",
) -> Finding:
    return Finding(
        level=level,
        category=category,
        filepath=filepath,
        line_no=line_no,
        message=message,
        suggestion="",
        evaluator=evaluator,
        cause_class="",
    )


class TestCompareFindings:
    """Test the _compare_findings() diff logic."""

    def test_no_change(self):
        f1 = _make_finding(message="same finding")
        new_f, new_w, res_f, res_w = _compare_findings([f1], [f1])
        assert new_f == []
        assert new_w == []
        assert res_f == []
        assert res_w == []

    def test_new_fail_detected(self):
        before = [_make_finding(message="existing")]
        after = [
            _make_finding(message="existing"),
            _make_finding(message="new problem", line_no=10),
        ]
        new_f, new_w, res_f, res_w = _compare_findings(before, after)
        assert len(new_f) == 1
        assert new_f[0].message == "new problem"
        assert res_f == []

    def test_resolved_fail_detected(self):
        before = [
            _make_finding(message="will be fixed"),
            _make_finding(message="stays"),
        ]
        after = [_make_finding(message="stays")]
        new_f, new_w, res_f, res_w = _compare_findings(before, after)
        assert new_f == []
        assert len(res_f) == 1
        assert res_f[0].message == "will be fixed"

    def test_warn_tracking(self):
        before = [_make_finding(level="WARN", message="old warn")]
        after = [_make_finding(level="WARN", message="new warn")]
        new_f, new_w, res_f, res_w = _compare_findings(before, after)
        assert len(new_w) == 1
        assert len(res_w) == 1

    def test_empty_before_after(self):
        new_f, new_w, res_f, res_w = _compare_findings([], [])
        assert new_f == new_w == res_f == res_w == []

    def test_all_resolved(self):
        before = [_make_finding(message="gone1"), _make_finding(message="gone2", line_no=5)]
        new_f, new_w, res_f, res_w = _compare_findings(before, [])
        assert len(res_f) == 2
        assert new_f == []


class TestVerifyHealing:
    """Test the main verify_healing() function."""

    def test_no_regression(self):
        before = [_make_finding(filepath="page.md", message="fixed issue")]
        after = []  # All findings resolved
        report = verify_healing(
            healed_files=["page.md"],
            before_findings=before,
            after_findings=after,
        )
        assert report.regression_detected is False
        assert report.pages_verified == 1
        assert report.total_resolved_fails == 1
        assert report.total_new_fails == 0

    def test_regression_detected(self):
        before = [_make_finding(filepath="page.md", message="old")]
        after = [
            _make_finding(filepath="page.md", message="old"),
            _make_finding(filepath="page.md", message="NEW regression", line_no=50),
        ]
        report = verify_healing(
            healed_files=["page.md"],
            before_findings=before,
            after_findings=after,
        )
        assert report.regression_detected is True
        assert report.total_new_fails == 1

    def test_multiple_files(self):
        before = [
            _make_finding(filepath="a.md", message="a-finding"),
            _make_finding(filepath="b.md", message="b-finding"),
        ]
        after = [
            _make_finding(filepath="b.md", message="b-finding"),  # b unchanged
        ]
        report = verify_healing(
            healed_files=["a.md", "b.md"],
            before_findings=before,
            after_findings=after,
        )
        assert report.pages_verified == 2
        assert report.total_resolved_fails == 1  # a.md finding resolved
        assert report.regression_detected is False

    def test_grade_computation(self):
        before = [_make_finding(filepath="page.md", message=f"fail-{i}") for i in range(5)]
        after = [_make_finding(filepath="page.md", message="fail-0")]  # 4 resolved
        report = verify_healing(
            healed_files=["page.md"],
            before_findings=before,
            after_findings=after,
        )
        pr = report.page_results[0]
        # Before: 5 FAILs = F grade; After: 1 FAIL = D grade
        assert pr.before_grade in {"D", "F"}
        assert pr.improved is True

    def test_from_json_reports(self, tmp_path):
        before_data = {
            "findings": [
                {"level": "FAIL", "category": "AA", "filepath": "page.md",
                 "line_no": 1, "message": "api error", "evaluator": "api_accuracy",
                 "suggestion": "", "cause_class": ""},
            ]
        }
        after_data = {"findings": []}

        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"
        before_path.write_text(json.dumps(before_data), encoding="utf-8")
        after_path.write_text(json.dumps(after_data), encoding="utf-8")

        report = verify_healing(
            healed_files=["page.md"],
            before_report_path=before_path,
            after_report_path=after_path,
        )
        assert report.regression_detected is False
        assert report.total_resolved_fails == 1

    def test_to_dict(self):
        report = verify_healing(
            healed_files=["page.md"],
            before_findings=[_make_finding(filepath="page.md", message="fixed")],
            after_findings=[],
        )
        d = report.to_dict()
        assert d["pages_verified"] == 1
        assert d["regression_detected"] is False
        assert len(d["pages"]) == 1
        assert d["pages"][0]["improved"] is True


class TestVerifyResult:
    """Test VerifyResult properties."""

    def test_regression_property(self):
        r = VerifyResult(
            filepath="test.md",
            before_grade="B", after_grade="D",
            before_fail_count=1, after_fail_count=3,
            before_warn_count=0, after_warn_count=0,
            new_fails=[{"id": "x", "level": "FAIL", "category": "AA", "message": "new"}],
        )
        assert r.regression_detected is True

    def test_improved_property(self):
        r = VerifyResult(
            filepath="test.md",
            before_grade="D", after_grade="B",
            before_fail_count=5, after_fail_count=1,
            before_warn_count=2, after_warn_count=2,
        )
        assert r.improved is True
        assert r.regression_detected is False


class TestRegressionSeverity:
    """Test the _regression_severity() classification."""

    def test_no_new_fails_is_none(self):
        assert _regression_severity(0, 0, "B", "B") == "none"

    def test_grade_decrease_is_critical(self):
        assert _regression_severity(2, 0, "B", "D") == "critical"

    def test_net_improvement_is_minor(self):
        # 1 new fail but 3 resolved — net improvement
        assert _regression_severity(1, 3, "D", "C") == "minor"

    def test_no_net_improvement_same_grade_is_moderate(self):
        assert _regression_severity(2, 1, "D", "D") == "moderate"

    def test_new_fails_grade_improved_is_minor(self):
        # Grade went up despite new fails (more resolved than new)
        assert _regression_severity(1, 5, "D", "B") == "minor"

    def test_verify_result_severity_property(self):
        r = VerifyResult(
            filepath="test.md",
            before_grade="B", after_grade="D",
            before_fail_count=1, after_fail_count=3,
            before_warn_count=0, after_warn_count=0,
            new_fails=[{"id": "x"}],
            resolved_fails=[],
        )
        assert r.regression_severity == "critical"

    def test_verify_result_no_regression_severity(self):
        r = VerifyResult(
            filepath="test.md",
            before_grade="D", after_grade="B",
            before_fail_count=5, after_fail_count=1,
            before_warn_count=0, after_warn_count=0,
        )
        assert r.regression_severity == "none"

    def test_healing_report_aggregate_severity(self):
        before = [
            _make_finding(filepath="a.md", message="old-a"),
            _make_finding(filepath="b.md", message="old-b"),
        ]
        after = [
            _make_finding(filepath="a.md", message="old-a"),
            # b.md: old finding gone but new one appeared
            _make_finding(filepath="b.md", message="new-regression", line_no=50),
        ]
        report = verify_healing(
            healed_files=["a.md", "b.md"],
            before_findings=before,
            after_findings=after,
        )
        assert report.regression_detected is True
        assert report.regression_severity in ("minor", "moderate", "critical")

    def test_healing_report_no_regression_severity_none(self):
        report = verify_healing(
            healed_files=["a.md"],
            before_findings=[_make_finding(filepath="a.md", message="fixed")],
            after_findings=[],
        )
        assert report.regression_severity == "none"

    def test_to_dict_includes_severity(self):
        report = verify_healing(
            healed_files=["a.md"],
            before_findings=[_make_finding(filepath="a.md", message="fixed")],
            after_findings=[],
        )
        d = report.to_dict()
        assert "regression_severity" in d
        assert d["regression_severity"] == "none"


class TestFindingsFromDicts:
    """Test reconstruction of Finding objects from dicts."""

    def test_basic_reconstruction(self):
        dicts = [
            {"level": "FAIL", "category": "PT", "filepath": "f.md",
             "line_no": 10, "message": "prose issue", "evaluator": "prose_truth"},
        ]
        findings = _findings_from_dicts(dicts)
        assert len(findings) == 1
        assert findings[0].level == "FAIL"
        assert findings[0].category == "PT"

    def test_missing_fields_use_defaults(self):
        dicts = [{"level": "WARN", "message": "partial"}]
        findings = _findings_from_dicts(dicts)
        assert len(findings) == 1
        assert findings[0].category == ""
        assert findings[0].filepath == ""

    def test_line_field_fallback(self):
        """Support both 'line_no' and 'line' field names."""
        dicts = [{"level": "FAIL", "line": 42, "message": "test"}]
        findings = _findings_from_dicts(dicts)
        assert findings[0].line_no == 42

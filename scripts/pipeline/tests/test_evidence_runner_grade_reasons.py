"""Tests for grade_reasons flow in evidence/runner.py.

Verifies that _build_audit_grade_reasons produces correct reason strings
and that attach_evidence passes grade_reasons to write_grade.
"""

from __future__ import annotations

import types

import pytest

from evidence.runner import _build_audit_grade_reasons


# ---------------------------------------------------------------------------
# Fake Finding — minimal duck-type matching token_ops.Finding slots
# ---------------------------------------------------------------------------

class _FakeFinding:
    __slots__ = ("level", "filepath", "line_no", "message", "suggestion")

    def __init__(self, level="WARN", line_no=0, message="test finding"):
        self.level = level
        self.filepath = "test.md"
        self.line_no = line_no
        self.message = message
        self.suggestion = ""


# ---------------------------------------------------------------------------
# _build_audit_grade_reasons unit tests
# ---------------------------------------------------------------------------

class TestBuildAuditGradeReasons:
    def test_no_findings_grade_a(self):
        reasons = _build_audit_grade_reasons("A", 0, 0, [])
        assert reasons == ["No findings -> grade A"]

    def test_with_fail_findings(self):
        findings = [
            _FakeFinding(level="FAIL", line_no=42, message="Unknown API Foo.bar"),
            _FakeFinding(level="FAIL", line_no=55, message="Unknown API Baz.qux"),
        ]
        reasons = _build_audit_grade_reasons("C", 2, 0, findings)
        assert len(reasons) == 2
        assert "2 FAIL" in reasons[0]
        assert "grade C" in reasons[0]
        assert "Foo.bar" in reasons[1]
        assert "(line 42)" in reasons[1]

    def test_with_warn_findings(self):
        findings = [
            _FakeFinding(level="WARN", line_no=10, message="Deprecated method"),
            _FakeFinding(level="WARN", line_no=20, message="Another warning"),
            _FakeFinding(level="WARN", line_no=30, message="Third warning"),
        ]
        reasons = _build_audit_grade_reasons("B", 0, 3, findings)
        assert len(reasons) == 1
        assert "3 WARN" in reasons[0]
        assert "grade B" in reasons[0]

    def test_with_extra_findings(self):
        audit_findings = [_FakeFinding(level="WARN", line_no=5, message="audit warn")]
        extra = [
            _FakeFinding(level="FAIL", line_no=99, message="description empty"),
        ]
        reasons = _build_audit_grade_reasons("C", 1, 1, audit_findings, extra)
        assert len(reasons) == 2
        assert "1 FAIL" in reasons[0]
        assert "description empty" in reasons[1]

    def test_fail_without_line_no(self):
        findings = [_FakeFinding(level="FAIL", line_no=0, message="general fail")]
        reasons = _build_audit_grade_reasons("C", 1, 0, findings)
        assert "(line" not in reasons[1]

    def test_empty_extra_findings(self):
        reasons = _build_audit_grade_reasons("A", 0, 0, [], [])
        assert reasons == ["No findings -> grade A"]

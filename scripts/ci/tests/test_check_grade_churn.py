"""test_check_grade_churn.py — Regression tests for check_grade_churn.py

Covers edge cases in _GRADE_FIELD_RE and _GRADE_CONTINUATION_RE patterns.
"""
import sys
from pathlib import Path

import pytest

# Bootstrap: add scripts/ci/checks/ to sys.path
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks.check_grade_churn import (
    _GRADE_FIELD_RE,
    _GRADE_CONTINUATION_RE,
    _BULK_ANNOTATION_RE,
    _is_grade_only_change,
)


# ---------------------------------------------------------------------------
# _GRADE_FIELD_RE tests
# ---------------------------------------------------------------------------


def test_grade_field_graded_at_detected():
    """A +graded_at diff line is classified as a grade field."""
    assert _GRADE_FIELD_RE.match("+graded_at: 2026-05-04")


def test_grade_field_grade_detected():
    """A +grade diff line is classified as a grade field."""
    assert _GRADE_FIELD_RE.match("+grade: A")


def test_grade_field_graded_evaluators_detected():
    """A +graded_evaluators diff line is classified as a grade field."""
    assert _GRADE_FIELD_RE.match("+graded_evaluators: full")


def test_grade_field_non_grade_not_detected():
    """A non-grade diff line (e.g. title change) is NOT a grade field."""
    assert not _GRADE_FIELD_RE.match("+title: New Product Page Title")


def test_grade_field_evidence_line_not_detected():
    """An evidence claim line is NOT a grade field."""
    assert not _GRADE_FIELD_RE.match("+  - ERC-cells-java-01298e56")


def test_grade_field_body_text_not_detected():
    """A body prose line is NOT a grade field."""
    assert not _GRADE_FIELD_RE.match("+This product supports many file formats.")


# ---------------------------------------------------------------------------
# _GRADE_CONTINUATION_RE tests
# ---------------------------------------------------------------------------


def test_continuation_bare_list_marker_matched():
    """Bare list marker '+  -' alone IS matched as grade continuation (documented edge case)."""
    # This is a harmless edge case: a bare '-' under a grade field list.
    # The regex matches it, but it's rare in practice.
    assert _GRADE_CONTINUATION_RE.match("+  -")


def test_continuation_list_item_with_colon_not_matched():
    """List item with a colon after the dash is NOT continuation (new field assignment)."""
    # e.g. '+  - member_id: abc' should NOT be classified as continuation
    # because it contains a colon, making it a new key-value pair.
    assert not _GRADE_CONTINUATION_RE.match("+  - member_id: abc")


def test_continuation_evidence_api_line_not_matched():
    """Evidence API reference lines with colons are NOT grade continuation."""
    # Evidence lines like '+  claims:' have colons and should NOT be continuation.
    assert not _GRADE_CONTINUATION_RE.match("+  claims: []")


def test_continuation_indented_scalar_without_colon():
    """An indented scalar value without a colon IS matched as continuation."""
    # e.g. a grade_reasons list item like '+  audit_fail' (no colon)
    assert _GRADE_CONTINUATION_RE.match("+  audit_fail")


# ---------------------------------------------------------------------------
# _BULK_ANNOTATION_RE tests
# ---------------------------------------------------------------------------


def test_bulk_annotation_match():
    """BULK-GRADE-MIGRATION annotation is detected case-insensitively."""
    text = "BULK-GRADE-MIGRATION: approved by admin on 2026-05-04, reason: policy change"
    assert _BULK_ANNOTATION_RE.search(text)


def test_bulk_annotation_lowercase_match():
    """Lowercase bulk-grade-migration annotation is detected."""
    text = "bulk-grade-migration: approved by admin"
    assert _BULK_ANNOTATION_RE.search(text)


def test_bulk_annotation_not_matched_without_approved_by():
    """Annotation without 'approved by' is NOT matched."""
    text = "BULK-GRADE-MIGRATION: some other text"
    assert not _BULK_ANNOTATION_RE.search(text)


# ---------------------------------------------------------------------------
# Body-change detection (via regex — no git subprocess)
# ---------------------------------------------------------------------------


def test_grade_only_pattern_integration():
    """A diff with only grade lines is correctly classified as all-grade."""
    grade_lines = [
        "+graded_at: 2026-05-04",
        "-graded_at: 2026-04-30",
        "+grade: A",
        "-grade: B",
        "+graded_evaluators: full",
        "-graded_evaluators: audit",
    ]
    for line in grade_lines:
        assert _GRADE_FIELD_RE.match(line) or _GRADE_CONTINUATION_RE.match(line), (
            f"Expected line to be classified as grade-only: {line!r}"
        )


def test_non_grade_line_breaks_grade_only():
    """A diff with a non-grade line causes the file to NOT be grade-only."""
    non_grade_lines = [
        "+## New Section Added",
        "+This is new body prose.",
        "+title: Updated Title",
        "+  - ERC-cells-java-01298e56: new claim",
    ]
    for line in non_grade_lines:
        is_grade = _GRADE_FIELD_RE.match(line) or _GRADE_CONTINUATION_RE.match(line)
        assert not is_grade, (
            f"Expected line to NOT be grade-only but it was matched: {line!r}"
        )

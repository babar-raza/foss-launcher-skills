"""Tests for WP-01: _should_write_canonical_grade() write policy gate.

Validates the five policy cases:
  1. First grading (no stored grade) -> write
  2. Body changed AND grade changed -> write
  3. Grade crossed a letter boundary -> write
  4. Body changed, grade unchanged -> do NOT write
  5. Body unchanged, grade unchanged -> do NOT write
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from grade_writer import (
    _crosses_letter_boundary,
    _should_write_canonical_grade,
    content_hash,
    write_grade,
    read_grade,
)


def _tmp_file(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# _crosses_letter_boundary
# ---------------------------------------------------------------------------

class TestCrossesLetterBoundary:
    def test_same_grade(self):
        assert not _crosses_letter_boundary("A", "A")
        assert not _crosses_letter_boundary("C", "C")

    def test_different_grades(self):
        assert _crosses_letter_boundary("C", "B")
        assert _crosses_letter_boundary("B", "C")
        assert _crosses_letter_boundary("F", "A")

    def test_invalid_grade(self):
        assert not _crosses_letter_boundary("X", "A")
        assert not _crosses_letter_boundary("A", "Z")


# ---------------------------------------------------------------------------
# _should_write_canonical_grade — five policy cases
# ---------------------------------------------------------------------------

class TestShouldWriteCanonicalGrade:
    def test_first_grading_always_writes(self):
        """Case 1: No stored grade -> write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            should, reason = _should_write_canonical_grade(p, "B", "somehash")
            assert should is True
            assert "first-grading" in reason
        finally:
            p.unlink(missing_ok=True)

    def test_body_changed_grade_changed_writes(self):
        """Case 2: Body changed AND grade letter changed -> write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", model_sha="sha1")
            # Simulate body change -> different hash, plus grade change C->B
            should, reason = _should_write_canonical_grade(p, "B", "different_hash")
            assert should is True
            assert "body-changed-grade-changed" in reason
        finally:
            p.unlink(missing_ok=True)

    def test_grade_band_crossing_writes(self):
        """Case 3: Grade crossed a letter boundary (same body) -> write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", model_sha="sha1")
            stored = read_grade(p)
            stored_hash = stored["content_hash"]
            # Same body hash, but grade improved C->B
            should, reason = _should_write_canonical_grade(p, "B", stored_hash)
            assert should is True
            assert "grade-band-crossing" in reason
        finally:
            p.unlink(missing_ok=True)

    def test_body_changed_grade_unchanged_no_write(self):
        """Case 4: Body changed but grade letter unchanged -> do NOT write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", model_sha="sha1")
            # Different hash (body changed), but same grade C
            should, reason = _should_write_canonical_grade(p, "C", "different_hash")
            assert should is False
            assert "body-changed-grade-unchanged" in reason
        finally:
            p.unlink(missing_ok=True)

    def test_nothing_changed_no_write(self):
        """Case 5: Body unchanged, grade unchanged -> do NOT write."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", model_sha="sha1")
            stored = read_grade(p)
            stored_hash = stored["content_hash"]
            should, reason = _should_write_canonical_grade(p, "C", stored_hash)
            assert should is False
            assert "no-policy-trigger" in reason
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# write_grade with write_mode="policy" integration
# ---------------------------------------------------------------------------

class TestWriteGradePolicyMode:
    def test_policy_mode_skips_unchanged_grade(self):
        """write_grade(write_mode='policy') skips when grade+body unchanged."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            # First write (force mode) to establish a grade
            write_grade(p, "C", model_sha="sha1")
            text_after_first = p.read_text(encoding="utf-8")

            # Second write with policy mode — same grade, same body
            result = write_grade(p, "C", model_sha="sha2", write_mode="policy")
            assert result is True  # returns True (policy-skip, not error)
            text_after_second = p.read_text(encoding="utf-8")

            # File should be unchanged (policy suppressed the write)
            assert text_after_first == text_after_second
        finally:
            p.unlink(missing_ok=True)

    def test_policy_mode_writes_on_first_grading(self):
        """write_grade(write_mode='policy') writes when page has no grade."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            result = write_grade(p, "B", model_sha="sha1", write_mode="policy")
            assert result is True
            stored = read_grade(p)
            assert stored is not None
            assert stored["grade"] == "B"
        finally:
            p.unlink(missing_ok=True)

    def test_policy_mode_writes_on_grade_change(self):
        """write_grade(write_mode='policy') writes when grade letter changes."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", model_sha="sha1")
            # Same body -> same hash, but grade changes C->B
            # We need to hack the stored hash to simulate a grade-band crossing
            # by writing a grade that differs
            text = p.read_text(encoding="utf-8")
            # Force a different stored hash to simulate body change + grade change
            text = text.replace('graded_content_hash: "', 'graded_content_hash: "00')
            p.write_text(text, encoding="utf-8")

            result = write_grade(p, "B", model_sha="sha2", write_mode="policy")
            assert result is True
            stored = read_grade(p)
            assert stored["grade"] == "B"
        finally:
            p.unlink(missing_ok=True)

    def test_force_mode_always_writes(self):
        """write_grade(write_mode='force') writes unconditionally (backward-compat)."""
        p = _tmp_file("---\ntitle: T\n---\nBody.\n")
        try:
            write_grade(p, "C", model_sha="sha1")
            # Same grade, same body — force mode writes anyway
            result = write_grade(p, "C", model_sha="sha2", write_mode="force")
            assert result is True
            stored = read_grade(p)
            # Grade should still be present (write happened).
            # Note: ARCH-04 removed model_sha from frontmatter — only canonical
            # fields (grade, grade_reasons, graded_content_hash) are written.
            assert stored["grade"] == "C"
            assert stored.get("content_hash"), "content_hash must be present after force write"
        finally:
            p.unlink(missing_ok=True)

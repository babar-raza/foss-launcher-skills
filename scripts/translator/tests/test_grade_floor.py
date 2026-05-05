"""Tests for translator grade-floor guard (G-04 fix)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure scripts/ dirs are on path
_SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "pipeline"))


class TestReadPageGrade:
    """Test _read_page_grade helper."""

    def test_reads_grade_from_frontmatter(self, tmp_path):
        from translator.cli import _read_page_grade
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: B\n---\nBody.\n")
        assert _read_page_grade(p) == "B"

    def test_returns_empty_for_ungraded(self, tmp_path):
        from translator.cli import _read_page_grade
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\n---\nBody.\n")
        assert _read_page_grade(p) == ""

    def test_returns_empty_for_missing_file(self, tmp_path):
        from translator.cli import _read_page_grade
        p = tmp_path / "missing.md"
        assert _read_page_grade(p) == ""


class TestCheckGradeFloor:
    """Test _check_grade_floor guard."""

    def test_grade_a_passes(self, tmp_path):
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: A\n---\nBody.\n")
        assert _check_grade_floor(p) is True

    def test_grade_b_passes(self, tmp_path):
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: B\n---\nBody.\n")
        assert _check_grade_floor(p) is True

    def test_grade_c_blocked(self, tmp_path):
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: C\n---\nBody.\n")
        assert _check_grade_floor(p) is False

    def test_grade_d_blocked(self, tmp_path):
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: D\n---\nBody.\n")
        assert _check_grade_floor(p) is False

    def test_grade_f_blocked(self, tmp_path):
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: F\n---\nBody.\n")
        assert _check_grade_floor(p) is False

    def test_ungraded_allowed(self, tmp_path):
        """Ungraded pages should be allowed (grade not yet assigned)."""
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\n---\nBody.\n")
        assert _check_grade_floor(p) is True

    def test_skip_override_allows_low_grade(self, tmp_path):
        """--skip-grade-check override allows translation of low-grade pages."""
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: F\n---\nBody.\n")
        assert _check_grade_floor(p, skip=True) is True

    def test_skip_override_not_needed_for_good_grade(self, tmp_path):
        """skip=True with passing grade still works."""
        from translator.cli import _check_grade_floor
        p = tmp_path / "page.md"
        p.write_text("---\ntitle: T\ngrade: A\n---\nBody.\n")
        assert _check_grade_floor(p, skip=True) is True

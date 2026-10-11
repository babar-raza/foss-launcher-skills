"""Tests for heal-page Pass 2 preserve-first rule.

Sprint: heal-page-pass2-preserve-first
Covers: golden-diff fixtures A/B + anti-tests proving helper catches violations.
"""
from __future__ import annotations

import pathlib
import pytest

from scripts.pipeline.tests.helpers.preservation_assert import (
    assert_sections_preserved,
    assert_unit_preserved,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "heal_pass2_preserve"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# ─── Golden-diff tests ─────────────────────────────────────────────────────

class TestFixtureAGoldenDiff:
    """Fixture A: cross-section heal-page.
    API Usage section has a FAIL finding. See Also section has zero FAIL findings.
    See Also must survive unchanged.
    """

    def test_see_also_preserved(self):
        before = _read("fixture_a_before.md")
        after = _read("fixture_a_after.md")
        assert_sections_preserved(before, after, ["## See Also"])

    def test_see_also_link1_unit_preserved(self):
        before = _read("fixture_a_before.md")
        after = _read("fixture_a_after.md")
        assert_unit_preserved(before, after, "HEAL_FIXTURE_A_SEEALSO_LINK1")

    def test_see_also_link2_unit_preserved(self):
        before = _read("fixture_a_before.md")
        after = _read("fixture_a_after.md")
        assert_unit_preserved(before, after, "HEAL_FIXTURE_A_SEEALSO_LINK2")

    def test_para2_not_in_heal_target_preserved(self):
        """Para2 in API Usage has no FAIL finding and must survive."""
        before = _read("fixture_a_before.md")
        after = _read("fixture_a_after.md")
        assert_unit_preserved(before, after, "HEAL_FIXTURE_A_APIU_PARA2")


class TestFixtureBGoldenDiff:
    """Fixture B: same-section heal-page.
    Para1 in Overview has a FAIL finding; Para2 has none.
    Related Links has zero FAIL findings — must survive unchanged.
    """

    def test_related_links_preserved(self):
        before = _read("fixture_b_before.md")
        after = _read("fixture_b_after.md")
        assert_sections_preserved(before, after, ["## Related Links"])

    def test_para2_preserved_within_section(self):
        before = _read("fixture_b_before.md")
        after = _read("fixture_b_after.md")
        assert_unit_preserved(before, after, "HEAL_FIXTURE_B_OV_PARA2")

    def test_all_related_links_units_preserved(self):
        before = _read("fixture_b_before.md")
        after = _read("fixture_b_after.md")
        for marker in ["HEAL_FIXTURE_B_RL_LINK1", "HEAL_FIXTURE_B_RL_LINK2", "HEAL_FIXTURE_B_RL_LINK3"]:
            assert_unit_preserved(before, after, marker)


# ─── Anti-tests (proving helper catches violations) ────────────────────────

class TestAntiTests:
    """These tests prove the helper raises when violations occur."""

    def test_deletion_of_protected_section_detected(self):
        """Deleting See Also must raise AssertionError."""
        before = "## See Also\n[Link A](a.md)\n\n## Usage\ntext\n"
        after = "## Usage\ntext\n"
        with pytest.raises(AssertionError, match="deleted"):
            assert_sections_preserved(before, after, ["## See Also"])

    def test_body_change_in_protected_section_detected(self):
        """Changing link text in See Also must raise AssertionError."""
        before = "## See Also\n[Link A](a.md)\n"
        after = "## See Also\n[Link CHANGED](a.md)\n"
        with pytest.raises(AssertionError, match="body changed"):
            assert_sections_preserved(before, after, ["## See Also"])

    def test_reorder_of_protected_sections_detected(self):
        """Reordering See Also relative to another protected section must raise."""
        before = "## See Also\n[A](a.md)\n\n## Related Links\n[B](b.md)\n"
        after = "## Related Links\n[B](b.md)\n\n## See Also\n[A](a.md)\n"
        with pytest.raises(AssertionError):
            assert_sections_preserved(before, after, ["## See Also", "## Related Links"])

    def test_unit_moved_to_different_parent_detected(self):
        """Moving a unit to a different H2 parent must raise AssertionError."""
        before = "## API Usage\ntext\n\nHEAL_ANTI_MARKER detail\n\n## See Also\n[A](a.md)\n"
        after = "## See Also\n[A](a.md)\n\nHEAL_ANTI_MARKER detail\n\n## API Usage\ntext\n"
        with pytest.raises(AssertionError):
            assert_unit_preserved(before, after, "HEAL_ANTI_MARKER")

    def test_duplicate_protected_heading_raises_value_error(self):
        """Duplicate heading in fixture raises ValueError (not AssertionError)."""
        before = "## See Also\n[A](a.md)\n\n## See Also\n[B](b.md)\n"
        after = before
        with pytest.raises(ValueError):
            assert_sections_preserved(before, after, ["## See Also"])

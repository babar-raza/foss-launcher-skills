"""Tests for page-update preserve-first rule.

Sprint: heal-page-pass2-preserve-first
Covers: golden-diff fixtures C/D + anti-tests proving helper catches violations.
"""
from __future__ import annotations

import pathlib
import pytest

from scripts.pipeline.tests.helpers.preservation_assert import (
    assert_sections_preserved,
    assert_unit_preserved,
)

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "page_update_preserve"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# ─── Golden-diff tests ─────────────────────────────────────────────────────

class TestFixtureCGoldenDiff:
    """Fixture C: cross-section page-update.
    removed_apis targets Core API section. See Also has no delta target — must survive.
    """

    def test_see_also_preserved(self):
        before = _read("fixture_c_before.md")
        after = _read("fixture_c_after.md")
        assert_sections_preserved(before, after, ["## See Also"])

    def test_see_also_link1_preserved(self):
        before = _read("fixture_c_before.md")
        after = _read("fixture_c_after.md")
        assert_unit_preserved(before, after, "PU_FIXTURE_C_SEEALSO_LINK1")

    def test_see_also_link2_preserved(self):
        before = _read("fixture_c_before.md")
        after = _read("fixture_c_after.md")
        assert_unit_preserved(before, after, "PU_FIXTURE_C_SEEALSO_LINK2")

    def test_para2_no_delta_target_preserved(self):
        """Para2 in Core API has no delta target and must survive."""
        before = _read("fixture_c_before.md")
        after = _read("fixture_c_after.md")
        assert_unit_preserved(before, after, "PU_FIXTURE_C_CORE_PARA2")


class TestFixtureDGoldenDiff:
    """Fixture D: same-section page-update.
    Para1 in Installation is the delta target. Para2 and Related Links have none.
    """

    def test_related_links_preserved(self):
        before = _read("fixture_d_before.md")
        after = _read("fixture_d_after.md")
        assert_sections_preserved(before, after, ["## Related Links"])

    def test_para2_no_delta_target_preserved(self):
        before = _read("fixture_d_before.md")
        after = _read("fixture_d_after.md")
        assert_unit_preserved(before, after, "PU_FIXTURE_D_INST_PARA2")

    def test_all_related_link_units_preserved(self):
        before = _read("fixture_d_before.md")
        after = _read("fixture_d_after.md")
        for marker in ["PU_FIXTURE_D_RL_LINK1", "PU_FIXTURE_D_RL_LINK2"]:
            assert_unit_preserved(before, after, marker)


# ─── Anti-tests (proving helper catches violations) ────────────────────────

class TestAntiTests:
    """These tests prove the helper raises when violations occur."""

    def test_deletion_of_protected_section_detected(self):
        before = "## See Also\n[Link A](a.md)\n\n## Core API\ntext\n"
        after = "## Core API\ntext\n"
        with pytest.raises(AssertionError, match="deleted"):
            assert_sections_preserved(before, after, ["## See Also"])

    def test_body_change_in_protected_section_detected(self):
        before = "## Related Links\n[Link A](a.md)\n"
        after = "## Related Links\n[Link MUTATED](a.md)\n"
        with pytest.raises(AssertionError, match="body changed"):
            assert_sections_preserved(before, after, ["## Related Links"])

    def test_reorder_of_protected_sections_detected(self):
        before = "## See Also\n[A](a.md)\n\n## Related Links\n[B](b.md)\n"
        after = "## Related Links\n[B](b.md)\n\n## See Also\n[A](a.md)\n"
        with pytest.raises(AssertionError):
            assert_sections_preserved(before, after, ["## See Also", "## Related Links"])

    def test_unit_moved_to_different_parent_detected(self):
        before = "## Installation\ntext\n\nPU_ANTI_MARKER detail\n\n## See Also\n[A](a.md)\n"
        after = "## See Also\n[A](a.md)\n\nPU_ANTI_MARKER detail\n\n## Installation\ntext\n"
        with pytest.raises(AssertionError):
            assert_unit_preserved(before, after, "PU_ANTI_MARKER")

    def test_duplicate_protected_heading_raises_value_error(self):
        before = "## See Also\n[A](a.md)\n\n## See Also\n[B](b.md)\n"
        after = before
        with pytest.raises(ValueError):
            assert_sections_preserved(before, after, ["## See Also"])

"""Policy command invariant tests.

These tests verify that critical policy documents contain required sections
and phrases that enforce governance rules. If a policy doc is refactored and
a required phrase is removed, these tests will catch the regression.
"""

import pathlib

COMMANDS_DIR = pathlib.Path(__file__).resolve().parents[3] / ".claude" / "commands"


def _read_command(name: str) -> str:
    path = COMMANDS_DIR / name
    assert path.exists(), f"Command file not found: {path}"
    return path.read_text(encoding="utf-8")


class TestRefreshProductInvariants:
    """Verify refresh-product.md contains critical governance sections."""

    def test_refresh_product_has_step_11_6(self):
        text = _read_command("refresh-product.md")
        assert "11.6" in text, "Step 11.6 reference missing from refresh-product.md"
        assert "Body-update planner routing" in text, (
            "Body-update planner routing heading missing from refresh-product.md"
        )

    def test_generated_reference_pages_excluded(self):
        text = _read_command("refresh-product.md")
        assert "Generated reference pages are never counted" in text, (
            "Generated reference page exclusion rule missing from refresh-product.md"
        )

    def test_source_baseline_missing_fails_closed(self):
        text = _read_command("refresh-product.md")
        assert "SOURCE_EVIDENCE_UNAVAILABLE" in text, (
            "SOURCE_EVIDENCE_UNAVAILABLE status missing from refresh-product.md"
        )
        assert "fail-closed" in text, (
            "fail-closed policy missing from refresh-product.md"
        )


class TestPageUpdateInvariants:
    """Verify page-update.md contains PIA enforcement rule."""

    def test_page_update_has_pia_enforcement(self):
        text = _read_command("page-update.md")
        assert "PIA enforcement" in text, (
            "PIA enforcement section missing from page-update.md"
        )


class TestGradeRemediateInvariants:
    """Verify grade-remediate.md contains hash-only rejection rule."""

    def test_grade_remediate_rejects_hash_only(self):
        text = _read_command("grade-remediate.md")
        assert "mere body hash change" in text, (
            "Hash-only rejection rule missing from grade-remediate.md"
        )

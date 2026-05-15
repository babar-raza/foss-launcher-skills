"""Narrow regression guard: prevents reintroduction of broad rewrite/removal wording
in heal-page and page-update canonical skill files.

Sprint: heal-page-pass2-preserve-first v9
Authorized under: evidence/12-optional-hardening-decision.md
"""
from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HEAL_PAGE = REPO_ROOT / "skills" / "heal-page.md"
PAGE_UPDATE = REPO_ROOT / "skills" / "page-update.md"


class TestHealPagePreserveFirstGuard:
    """heal-page must have preserve-first rule and must NOT have broad rewrite wording."""

    def test_preserve_first_rule_present(self):
        text = HEAL_PAGE.read_text(encoding="utf-8")
        assert "Preserve-first rule" in text, (
            "skills/heal-page.md is missing 'Preserve-first rule'. "
            "Sprint heal-page-pass2-preserve-first added this — do not remove it."
        )

    def test_broad_rewrite_wording_absent(self):
        text = HEAL_PAGE.read_text(encoding="utf-8")
        assert "Rewrite entire failing sections from scratch" not in text, (
            "skills/heal-page.md contains forbidden broad rewrite wording: "
            "'Rewrite entire failing sections from scratch'. "
            "This was removed in sprint heal-page-pass2-preserve-first — do not reintroduce it."
        )

    def test_broad_removal_wording_absent(self):
        text = HEAL_PAGE.read_text(encoding="utf-8")
        assert "Remove sections that cannot be fixed" not in text, (
            "skills/heal-page.md contains forbidden broad removal wording: "
            "'Remove sections that cannot be fixed'. "
            "This was removed in sprint heal-page-pass2-preserve-first — do not reintroduce it."
        )

    def test_pass2_scope_present(self):
        text = HEAL_PAGE.read_text(encoding="utf-8")
        assert "Pass 2 scope" in text, (
            "skills/heal-page.md is missing 'Pass 2 scope'. "
            "This scoping block is required by the preserve-first enforcement."
        )

    def test_agent_owned_review_lane_present(self):
        text = HEAL_PAGE.read_text(encoding="utf-8")
        assert "agent-owned review lane" in text, (
            "skills/heal-page.md is missing 'agent-owned review lane' reference. "
            "Unmappable edits must route to S-73/S-90."
        )


class TestPageUpdatePreserveFirstGuard:
    """page-update must have preserve-first rule and add-only constraint."""

    def test_preserve_first_rule_present(self):
        text = PAGE_UPDATE.read_text(encoding="utf-8")
        assert "Preserve-first rule" in text, (
            "skills/page-update.md is missing 'Preserve-first rule'. "
            "Sprint heal-page-pass2-preserve-first added this — do not remove it."
        )

    def test_smallest_affected_unit_present(self):
        text = PAGE_UPDATE.read_text(encoding="utf-8")
        assert "smallest affected unit" in text, (
            "skills/page-update.md is missing 'smallest affected unit'. "
            "This constraint prevents whole-section rewrites from single delta targets."
        )

    def test_add_only_constraint_present(self):
        text = PAGE_UPDATE.read_text(encoding="utf-8")
        assert "add-only" in text, (
            "skills/page-update.md is missing 'add-only' constraint. "
            "new_claims/new_apis must not trigger rewrites."
        )

    def test_not_a_deletion_reason_present(self):
        text = PAGE_UPDATE.read_text(encoding="utf-8")
        assert "not a deletion reason" in text, (
            "skills/page-update.md is missing 'not a deletion reason' wording. "
            "Absence from claims.json/api_surface.json must not be treated as deletion reason."
        )

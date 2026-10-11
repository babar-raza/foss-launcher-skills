"""Tests for heal_policy.py — policy table mapping issue class → heal mode + skill."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure pipeline is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heal_policy import HealPolicy, lookup, is_heal_enabled, get_policy_table


def _make_triaged(fix_type: str, category: str = "AA", level: str = "FAIL") -> MagicMock:
    """Create a mock TriagedFinding for testing."""
    finding = MagicMock()
    finding.category = category
    finding.level = level
    triaged = MagicMock()
    triaged.fix_type = fix_type
    triaged.finding = finding
    return triaged


class TestLookup:
    """Test the lookup() function."""

    def test_auto_finding_returns_auto_policy(self):
        triaged = _make_triaged("auto", "RV")
        policy = lookup(triaged)
        assert policy.heal_mode == "auto"
        assert policy.effort == "low"
        assert policy.regen_after is False

    def test_llm_aa_returns_specific_policy(self):
        triaged = _make_triaged("llm", "AA")
        policy = lookup(triaged)
        assert policy.heal_mode == "llm"
        assert policy.skill == "S-21"
        assert "API accuracy" in policy.description

    def test_llm_pc_returns_platform_policy(self):
        triaged = _make_triaged("llm", "PC")
        policy = lookup(triaged)
        assert policy.heal_mode == "llm"
        assert "Platform contamination" in policy.description

    def test_llm_fc_returns_forbidden_policy(self):
        triaged = _make_triaged("llm", "FC")
        policy = lookup(triaged)
        assert policy.heal_mode == "llm"
        assert "Forbidden claim" in policy.description

    def test_llm_pt_returns_prose_truth_policy(self):
        triaged = _make_triaged("llm", "PT")
        policy = lookup(triaged)
        assert policy.heal_mode == "llm"
        assert "Prose truth" in policy.description

    def test_llm_cp_returns_code_plausibility_policy(self):
        triaged = _make_triaged("llm", "CP")
        policy = lookup(triaged)
        assert policy.heal_mode == "llm"

    def test_llm_unknown_category_falls_to_wildcard(self):
        triaged = _make_triaged("llm", "ZZ")
        policy = lookup(triaged)
        assert policy.heal_mode == "llm"
        assert policy.skill == "S-21"
        assert "default" in policy.description.lower()

    def test_upstream_returns_regen_policy(self):
        triaged = _make_triaged("upstream", "DL")
        policy = lookup(triaged)
        assert policy.heal_mode == "regen"
        assert policy.skill == "S-80"
        assert policy.regen_after is True
        assert policy.effort == "high"

    def test_human_returns_manual_policy(self):
        triaged = _make_triaged("human", "CG")
        policy = lookup(triaged)
        assert policy.heal_mode == "human"
        assert policy.skill == ""
        assert policy.effort == "high"

    def test_skip_returns_noop_policy(self):
        triaged = _make_triaged("skip", "ST")
        policy = lookup(triaged)
        assert policy.heal_mode == "skip"
        assert policy.effort == "low"

    def test_unknown_fix_type_falls_to_human(self):
        triaged = _make_triaged("unknown_type", "AA")
        policy = lookup(triaged)
        assert policy.heal_mode == "human"
        assert "escalating" in policy.description.lower()


class TestIsHealEnabled:
    """Test the is_heal_enabled() convenience function."""

    def test_auto_is_enabled(self):
        assert is_heal_enabled(_make_triaged("auto", "RV")) is True

    def test_llm_is_enabled(self):
        assert is_heal_enabled(_make_triaged("llm", "AA")) is True

    def test_upstream_is_enabled(self):
        assert is_heal_enabled(_make_triaged("upstream", "DL")) is True

    def test_human_is_not_enabled(self):
        assert is_heal_enabled(_make_triaged("human", "CG")) is False

    def test_skip_is_not_enabled(self):
        assert is_heal_enabled(_make_triaged("skip", "ST")) is False


class TestPolicyTable:
    """Test policy table completeness."""

    def test_all_fix_types_have_wildcard(self):
        """Every fix type from triage should have at least a wildcard entry."""
        table = get_policy_table()
        fix_types_with_wildcard = {k[0] for k in table if k[1] == "*"}
        for expected in ("auto", "llm", "human", "skip", "upstream"):
            assert expected in fix_types_with_wildcard, f"Missing wildcard for {expected}"

    def test_critical_categories_have_specific_policies(self):
        """Critical categories (FC, PC, TA) should have specific LLM policies."""
        table = get_policy_table()
        for cat in ("FC", "PC"):
            assert ("llm", cat) in table, f"Missing specific policy for llm/{cat}"

    def test_policy_is_frozen_dataclass(self):
        policy = HealPolicy(
            heal_mode="auto", skill="", description="test",
            regen_after=False, effort="low",
        )
        with pytest.raises(AttributeError):
            policy.heal_mode = "llm"  # type: ignore[misc]

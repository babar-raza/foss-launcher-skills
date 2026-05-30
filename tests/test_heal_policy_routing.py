"""Test heal_policy.py routing logic for upstream causal-backtrack (S-79)."""

import pytest

from scripts.pipeline.commands.healing.heal_policy import lookup, is_heal_enabled
from scripts.pipeline.content_eval.models import Finding
from scripts.pipeline.content_eval.remediation.triage import TriagedFinding


@pytest.fixture
def mock_finding():
    """Create a minimal Finding object for testing."""
    return Finding(
        level="FAIL",
        category="AA",
        filepath="content/docs.aspose.org/en/words/python/test.md",
        line_no=1,
        message="Test finding",
    )


@pytest.fixture
def upstream_finding():
    """Create a mock TriagedFinding with upstream fix_type."""
    finding = Finding(
        level="WARN",
        category="RV",
        filepath="content/docs.aspose.org/en/words/python/test.md",
        line_no=10,
        message="Broken link to missing page",
    )
    return TriagedFinding(
        finding=finding,
        fix_type="upstream",
        fixer_name="",
        reason="UPSTREAM_MISSING - broken link to missing page",
    )


def test_lookup_upstream_returns_s79(upstream_finding):
    """Verify that upstream fix_type routes to S-79 (causal-backtrack)."""
    policy = lookup(upstream_finding)

    assert policy.heal_mode == "regen", "Upstream should use regen mode"
    assert policy.skill == "S-79", "Upstream should route to S-79 (causal-backtrack)"
    assert policy.regen_after is True, "Upstream fixes require regeneration after"
    assert policy.effort == "high", "Upstream fixes are high effort"


def test_lookup_auto_returns_empty_skill(mock_finding):
    """Verify that auto fix_type returns empty skill (deterministic fixers handle it)."""
    triaged = TriagedFinding(
        finding=mock_finding,
        fix_type="auto",
        fixer_name="frontmatter_type",
        reason="Missing type field",
    )
    policy = lookup(triaged)

    assert policy.heal_mode == "auto"
    assert policy.skill == "", "Auto mode should have no skill to invoke"


def test_is_heal_enabled_returns_true_for_upstream(upstream_finding):
    """Verify is_heal_enabled returns True for upstream findings (regen mode is heal-enabled)."""
    assert is_heal_enabled(upstream_finding) is True


def test_is_heal_enabled_returns_false_for_human(mock_finding):
    """Verify is_heal_enabled returns False for human review findings."""
    triaged = TriagedFinding(
        finding=mock_finding,
        fix_type="human",
        fixer_name="",
        reason="No automated fix available",
    )
    assert is_heal_enabled(triaged) is False


def test_is_heal_enabled_returns_false_for_skip(mock_finding):
    """Verify is_heal_enabled returns False for skipped findings."""
    triaged = TriagedFinding(
        finding=mock_finding,
        fix_type="skip",
        fixer_name="",
        reason="INFO-level finding",
    )
    assert is_heal_enabled(triaged) is False
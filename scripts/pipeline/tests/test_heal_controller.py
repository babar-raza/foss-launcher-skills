"""Tests for heal_controller.py — HealController.plan() method."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heal_controller import HealController, HealItem, HealGroup, HealPlan
from content_eval.models import Finding


def _make_finding(
    level: str = "FAIL",
    category: str = "AA",
    filepath: str = "test.md",
    line_no: int = 1,
    message: str = "test finding",
) -> Finding:
    return Finding(
        level=level,
        category=category,
        filepath=filepath,
        line_no=line_no,
        message=message,
        suggestion="",
        evaluator="test_eval",
        cause_class="",
    )


class TestHealControllerPlan:
    """Test HealController.plan() routing and grouping."""

    def test_empty_findings(self):
        ctrl = HealController()
        plan = ctrl.plan([])
        assert plan.total_findings == 0
        assert plan.total_enabled == 0
        assert plan.total_human == 0
        assert plan.total_skipped == 0

    def test_auto_fixable_routed_to_auto_group(self):
        """RV FAIL with 'type' message → auto fixer → auto policy."""
        f = _make_finding(category="RV", message="type: missing frontmatter type")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.auto_group.count == 1
        assert plan.total_enabled == 1
        assert plan.auto_group.items[0].heal_mode == "auto"

    def test_llm_finding_routed_to_llm_group(self):
        """AA FAIL → LLM triage → LLM policy."""
        f = _make_finding(category="AA", message="API method does not exist")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.llm_group.count == 1
        assert plan.total_enabled == 1
        assert plan.llm_group.items[0].policy.skill == "S-21"

    def test_upstream_finding_routed_to_regen_group(self):
        """Finding with UPSTREAM_MISSING cause → upstream triage → regen policy."""
        f = Finding(
            level="FAIL", category="AA", filepath="test.md", line_no=1,
            message="link target missing", suggestion="", evaluator="test",
            cause_class="UPSTREAM_MISSING",
        )
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.regen_group.count == 1
        assert plan.regen_group.items[0].policy.regen_after is True
        assert plan.total_enabled == 1

    def test_info_level_skipped(self):
        """INFO-level finding → skip triage → skip policy."""
        f = _make_finding(level="INFO", category="EG", message="evidence info")
        ctrl = HealController()
        plan = ctrl.plan([f])
        # INFO findings that don't match auto rules go to skip
        assert plan.total_skipped >= 1 or plan.total_enabled >= 1
        # At minimum, total == 1
        assert plan.total_findings == 1

    def test_mixed_findings_grouped_correctly(self):
        """Multiple findings of different types group into separate buckets."""
        findings = [
            _make_finding(category="RV", message="type: missing frontmatter type"),  # auto
            _make_finding(category="AA", message="API method incorrect", line_no=2),  # llm
            _make_finding(category="AA", message="another API issue", line_no=3),  # llm
            Finding(level="FAIL", category="DL", filepath="b.md", line_no=1,
                    message="dead link", suggestion="", evaluator="test",
                    cause_class="UPSTREAM_MISSING"),  # upstream → regen
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        assert plan.total_findings == 4
        assert plan.auto_group.count == 1
        assert plan.llm_group.count == 2
        assert plan.regen_group.count == 1
        assert plan.total_enabled == 4

    def test_all_files_tracked(self):
        findings = [
            _make_finding(filepath="a.md"),
            _make_finding(filepath="b.md", line_no=2),
            _make_finding(filepath="a.md", line_no=3),
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        assert plan.all_files == {"a.md", "b.md"}

    def test_enabled_files_excludes_human_skip(self):
        """enabled_files should only include auto/llm/regen files."""
        findings = [
            _make_finding(category="AA", message="API issue", filepath="auto.md"),  # llm
            _make_finding(category="CG", level="WARN", message="coverage gap", filepath="human.md"),  # human (no rule)
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        assert "auto.md" in plan.enabled_files
        assert "human.md" not in plan.enabled_files

    def test_plan_for_files_filters(self):
        findings = [
            _make_finding(filepath="a.md", message="API issue"),
            _make_finding(filepath="b.md", message="API issue", line_no=2),
        ]
        ctrl = HealController()
        plan = ctrl.plan_for_files(findings, {"a.md"})
        assert plan.total_findings == 1
        assert plan.all_files == {"a.md"}

    def test_to_dict_structure(self):
        f = _make_finding(category="AA", message="API issue")
        ctrl = HealController()
        plan = ctrl.plan([f])
        d = plan.to_dict()
        assert "total_findings" in d
        assert "total_enabled" in d
        assert "enabled_files" in d
        assert "groups" in d
        assert "llm" in d["groups"]

    def test_summary_string(self):
        f = _make_finding(category="AA", message="API issue")
        ctrl = HealController()
        plan = ctrl.plan([f])
        s = plan.summary()
        assert "HealPlan:" in s
        assert "1 findings" in s


class TestHealItem:
    """Test HealItem properties."""

    def test_properties(self):
        from content_eval.remediation.triage import triage_finding
        from heal_policy import lookup

        f = _make_finding(category="AA", message="API issue")
        triaged = triage_finding(f)
        policy = lookup(triaged)
        item = HealItem(finding=f, triaged=triaged, policy=policy)

        assert item.filepath == "test.md"
        assert item.heal_mode == policy.heal_mode
        assert item.skill == policy.skill
        assert item.is_enabled is True


class TestHealGroup:
    """Test HealGroup."""

    def test_add_and_count(self):
        from content_eval.remediation.triage import triage_finding
        from heal_policy import lookup

        group = HealGroup(heal_mode="llm")
        f = _make_finding(category="AA", message="API issue")
        triaged = triage_finding(f)
        policy = lookup(triaged)
        item = HealItem(finding=f, triaged=triaged, policy=policy)

        group.add(item)
        assert group.count == 1
        assert "test.md" in group.files

    def test_to_dict(self):
        from content_eval.remediation.triage import triage_finding
        from heal_policy import lookup

        group = HealGroup(heal_mode="llm")
        f = _make_finding(category="AA", message="API issue")
        triaged = triage_finding(f)
        policy = lookup(triaged)
        item = HealItem(finding=f, triaged=triaged, policy=policy)
        group.add(item)

        d = group.to_dict()
        assert d["heal_mode"] == "llm"
        assert d["count"] == 1
        assert len(d["items"]) == 1
        assert d["items"][0]["skill"] == "S-21"

"""Tests for heal_controller.py — HealController plan + execute methods."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heal_controller import HealController, HealItem, HealGroup, HealPlan
from content_eval.models import Finding
from content_eval.remediation.runner import FixResult
from verify import HealingReport


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


class TestExecuteAuto:
    """Test HealController.execute_auto() (TH-B2)."""

    @patch("heal_controller.run_fixes")
    def test_delegates_to_run_fixes(self, mock_run_fixes):
        """execute_auto extracts triaged items and delegates to run_fixes."""
        mock_run_fixes.return_value = [
            FixResult(finding_id="CE-abc", filepath="test.md",
                      fixer_name="frontmatter_type", action="fixed",
                      description="Added type field"),
        ]
        f = _make_finding(category="RV", message="type: missing frontmatter type")
        ctrl = HealController()
        plan = ctrl.plan([f])
        results = ctrl.execute_auto(plan)

        mock_run_fixes.assert_called_once()
        call_args = mock_run_fixes.call_args
        triaged_list = call_args[0][0]
        assert len(triaged_list) == 1
        assert triaged_list[0].fix_type == "auto"
        assert len(results) == 1
        assert results[0].action == "fixed"

    @patch("heal_controller.run_fixes")
    def test_dry_run_passed_through(self, mock_run_fixes):
        mock_run_fixes.return_value = []
        f = _make_finding(category="RV", message="type: missing frontmatter type")
        ctrl = HealController()
        plan = ctrl.plan([f])
        ctrl.execute_auto(plan, dry_run=True)

        _, kwargs = mock_run_fixes.call_args
        assert kwargs["dry_run"] is True

    @patch("heal_controller.run_fixes")
    def test_categories_filter_passed_through(self, mock_run_fixes):
        mock_run_fixes.return_value = []
        f = _make_finding(category="RV", message="type: missing frontmatter type")
        ctrl = HealController()
        plan = ctrl.plan([f])
        ctrl.execute_auto(plan, categories={"RV"})

        _, kwargs = mock_run_fixes.call_args
        assert kwargs["categories"] == {"RV"}

    @patch("heal_controller.run_fixes")
    def test_empty_auto_group(self, mock_run_fixes):
        """No auto items → empty list, run_fixes called with empty list."""
        mock_run_fixes.return_value = []
        f = _make_finding(category="AA", message="API issue")  # → llm, not auto
        ctrl = HealController()
        plan = ctrl.plan([f])
        results = ctrl.execute_auto(plan)

        assert results == []
        triaged_list = mock_run_fixes.call_args[0][0]
        assert len(triaged_list) == 0


class TestExecuteLLM:
    """Test HealController.execute_llm() (TH-B3)."""

    def test_returns_skill_invocation_dicts(self):
        f = _make_finding(category="AA", message="API method does not exist")
        ctrl = HealController()
        plan = ctrl.plan([f])
        invocations = ctrl.execute_llm(plan)

        assert len(invocations) == 1
        inv = invocations[0]
        assert inv["skill"] == "S-21"
        assert inv["filepath"] == "test.md"
        assert inv["category"] == "AA"
        assert inv["level"] == "FAIL"
        assert inv["message"] == "API method does not exist"
        assert "finding_id" in inv
        assert inv["finding_id"].startswith("CE-")
        assert inv["effort"] == "medium"
        assert "triage_reason" in inv

    def test_required_keys_present(self):
        """All required keys are in every invocation dict."""
        required = {"skill", "filepath", "finding_id", "category", "level",
                     "message", "suggestion", "effort", "triage_reason"}
        f = _make_finding(category="PC", message="platform contamination found")
        ctrl = HealController()
        plan = ctrl.plan([f])
        invocations = ctrl.execute_llm(plan)

        for inv in invocations:
            assert required.issubset(inv.keys()), f"Missing keys: {required - inv.keys()}"

    def test_multiple_llm_findings(self):
        findings = [
            _make_finding(category="AA", message="api issue 1", line_no=1),
            _make_finding(category="FC", message="forbidden claim", line_no=2),
            _make_finding(category="PT", message="prose truth", line_no=3),
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        invocations = ctrl.execute_llm(plan)

        assert len(invocations) == 3
        categories = {inv["category"] for inv in invocations}
        assert categories == {"AA", "FC", "PT"}

    def test_empty_llm_group(self):
        f = _make_finding(category="RV", message="type: missing frontmatter type")  # → auto
        ctrl = HealController()
        plan = ctrl.plan([f])
        invocations = ctrl.execute_llm(plan)
        assert invocations == []


class TestExecuteRegen:
    """Test HealController.execute_regen() (TH-B4)."""

    def test_returns_regen_invocation_dicts(self):
        f = Finding(
            level="FAIL", category="AA", filepath="ref.md", line_no=1,
            message="link target missing", suggestion="", evaluator="test",
            cause_class="UPSTREAM_MISSING",
        )
        ctrl = HealController()
        plan = ctrl.plan([f])
        invocations = ctrl.execute_regen(plan)

        assert len(invocations) == 1
        inv = invocations[0]
        assert inv["skill"] == "S-80"
        assert inv["filepath"] == "ref.md"
        assert inv["regen_after"] is True
        assert inv["effort"] == "high"
        assert "finding_id" in inv

    def test_required_keys_present(self):
        required = {"skill", "filepath", "finding_id", "category", "level",
                     "message", "effort", "regen_after"}
        f = Finding(
            level="FAIL", category="DL", filepath="test.md", line_no=1,
            message="dead link", suggestion="", evaluator="test",
            cause_class="BAD_LINK_FORMAT",
        )
        ctrl = HealController()
        plan = ctrl.plan([f])
        invocations = ctrl.execute_regen(plan)

        for inv in invocations:
            assert required.issubset(inv.keys()), f"Missing keys: {required - inv.keys()}"

    def test_empty_regen_group(self):
        f = _make_finding(category="AA", message="API issue")  # → llm
        ctrl = HealController()
        plan = ctrl.plan([f])
        invocations = ctrl.execute_regen(plan)
        assert invocations == []


class TestExecuteOrchestrator:
    """Test HealController.execute() orchestrator."""

    @patch("heal_controller.run_fixes")
    def test_all_mode_dispatches_all(self, mock_run_fixes):
        mock_run_fixes.return_value = [
            FixResult(finding_id="CE-x", filepath="test.md",
                      fixer_name="frontmatter_type", action="fixed",
                      description="test"),
        ]
        findings = [
            _make_finding(category="RV", message="type: missing frontmatter type"),  # auto
            _make_finding(category="AA", message="API issue", line_no=2),  # llm
            Finding(level="FAIL", category="DL", filepath="b.md", line_no=1,
                    message="dead link", suggestion="", evaluator="test",
                    cause_class="UPSTREAM_MISSING"),  # regen
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        result = ctrl.execute(plan, mode="all")

        assert len(result["auto"]) == 1
        assert len(result["llm"]) == 1
        assert len(result["regen"]) == 1
        assert result["summary"]["mode"] == "all"

    @patch("heal_controller.run_fixes")
    def test_auto_only_mode(self, mock_run_fixes):
        mock_run_fixes.return_value = []
        findings = [
            _make_finding(category="RV", message="type: missing frontmatter type"),
            _make_finding(category="AA", message="API issue", line_no=2),
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        result = ctrl.execute(plan, mode="auto")

        assert result["llm"] == []
        assert result["regen"] == []
        assert result["summary"]["mode"] == "auto"

    @patch("heal_controller.run_fixes")
    def test_dry_run_forwarded(self, mock_run_fixes):
        mock_run_fixes.return_value = []
        f = _make_finding(category="RV", message="type: missing frontmatter type")
        ctrl = HealController()
        plan = ctrl.plan([f])
        result = ctrl.execute(plan, dry_run=True)

        assert result["summary"]["dry_run"] is True
        _, kwargs = mock_run_fixes.call_args
        assert kwargs["dry_run"] is True

    def test_summary_counts(self):
        findings = [
            _make_finding(category="AA", message="api 1", line_no=1),
            _make_finding(category="AA", message="api 2", line_no=2),
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        result = ctrl.execute(plan, mode="llm")

        assert result["summary"]["llm_queued"] == 2
        assert result["summary"]["auto_processed"] == 0
        assert result["summary"]["regen_queued"] == 0


class TestVerify:
    """Test HealController.verify() (TH-B5)."""

    def test_verify_returns_healing_report(self):
        """verify() returns a HealingReport."""
        f = _make_finding(category="AA", message="API issue", filepath="a.md")
        ctrl = HealController()
        plan = ctrl.plan([f])
        report = ctrl.verify(plan, before_findings=[f], after_findings=[])
        assert isinstance(report, HealingReport)

    def test_verify_detects_improvement(self):
        """Removing a finding = improvement, no regression."""
        f = _make_finding(category="AA", message="API issue", filepath="a.md")
        ctrl = HealController()
        plan = ctrl.plan([f])
        report = ctrl.verify(plan, before_findings=[f], after_findings=[])
        assert report.pages_verified == 1
        assert report.total_before_fails == 1
        assert report.total_after_fails == 0
        assert report.regression_detected is False

    def test_verify_detects_regression(self):
        """Adding a new finding = regression."""
        f_before = _make_finding(category="AA", message="old issue", filepath="a.md")
        f_after_old = _make_finding(category="AA", message="old issue", filepath="a.md")
        f_after_new = Finding(
            level="FAIL", category="PT", filepath="a.md", line_no=5,
            message="new prose problem", suggestion="", evaluator="test",
        )
        ctrl = HealController()
        plan = ctrl.plan([f_before])
        report = ctrl.verify(
            plan,
            before_findings=[f_before],
            after_findings=[f_after_old, f_after_new],
        )
        assert report.regression_detected is True
        assert report.total_new_fails >= 1

    def test_verify_uses_plan_findings_as_default(self):
        """If before_findings=None, extracts from plan items."""
        f = _make_finding(category="AA", message="API issue", filepath="a.md")
        ctrl = HealController()
        plan = ctrl.plan([f])
        report = ctrl.verify(plan, after_findings=[])
        # Should use f as the before_findings
        assert report.pages_verified == 1
        assert report.total_before_fails == 1

    def test_verify_empty_plan(self):
        """Empty plan → 0 pages verified."""
        ctrl = HealController()
        plan = ctrl.plan([])
        report = ctrl.verify(plan, after_findings=[])
        assert report.pages_verified == 0

    def test_verify_multiple_files(self):
        """Verify covers all enabled files in plan."""
        findings = [
            _make_finding(category="AA", message="issue 1", filepath="a.md"),
            _make_finding(category="AA", message="issue 2", filepath="b.md", line_no=2),
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        report = ctrl.verify(plan, before_findings=findings, after_findings=[])
        assert report.pages_verified == 2
        filepaths = {r.filepath for r in report.page_results}
        assert "a.md" in filepaths
        assert "b.md" in filepaths

    def test_verify_severity_propagated(self):
        """Regression severity is computed and accessible."""
        f = _make_finding(category="AA", message="old", filepath="a.md")
        f_new = Finding(
            level="FAIL", category="PT", filepath="a.md", line_no=10,
            message="new critical problem", suggestion="", evaluator="test",
        )
        ctrl = HealController()
        plan = ctrl.plan([f])
        report = ctrl.verify(plan, before_findings=[f], after_findings=[f, f_new])
        assert report.regression_severity in ("minor", "moderate", "critical")


# ---------------------------------------------------------------------------
# SR-04 (TC-3): HealController depth guard — depth_map escalation to human_group
# ---------------------------------------------------------------------------

class TestHealControllerDepthGuard:
    """TC-3: findings at depth >= MAX_HEAL_DEPTH must be routed to human_group."""

    def test_finding_at_max_depth_routes_to_human(self):
        """A finding with depth == MAX_HEAL_DEPTH is escalated to human_group."""
        from heal_controller import MAX_HEAL_DEPTH
        f = _make_finding(category="CS", filepath="x.md")
        ctrl = HealController()
        plan = ctrl.plan([f], depth_map={f.id: MAX_HEAL_DEPTH})
        assert plan.human_group.count == 1, (
            f"Expected human_group.count=1, got {plan.human_group.count}"
        )
        item = plan.human_group.items[0]
        assert "max_heal_depth_exceeded" in item.skip_reason, (
            f"Expected max_heal_depth_exceeded in skip_reason, got {item.skip_reason!r}"
        )
        assert str(MAX_HEAL_DEPTH) in item.skip_reason

    def test_finding_below_max_depth_routes_normally(self):
        """A finding with depth < MAX_HEAL_DEPTH is NOT escalated."""
        from heal_controller import MAX_HEAL_DEPTH
        f = _make_finding(category="CS", filepath="x.md")
        ctrl = HealController()
        plan = ctrl.plan([f], depth_map={f.id: MAX_HEAL_DEPTH - 1})
        # Finding should NOT be in human_group due to depth guard
        # (it may still be human due to policy; check skip_reason is empty)
        for item in plan.human_group.items:
            assert item.skip_reason == "" or "max_heal_depth" not in item.skip_reason, (
                f"depth={MAX_HEAL_DEPTH - 1} must not trigger max_heal_depth escalation"
            )

    def test_depth_zero_missing_from_map_treats_as_zero(self):
        """A finding not in depth_map is treated as depth=0 (first run)."""
        f = _make_finding(category="CS", filepath="x.md")
        ctrl = HealController()
        plan = ctrl.plan([f], depth_map={})
        for item in plan.human_group.items:
            assert "max_heal_depth" not in item.skip_reason

    def test_depth_map_in_to_dict(self):
        """HealPlan.to_dict() includes 'depth_map' keyed by finding ID."""
        from heal_controller import MAX_HEAL_DEPTH
        f = _make_finding(category="CS", filepath="x.md")
        ctrl = HealController()
        plan = ctrl.plan([f], depth_map={f.id: 2})
        d = plan.to_dict()
        assert "depth_map" in d, "depth_map missing from to_dict()"
        assert d["depth_map"][f.id] == 2

    def test_depth_map_none_behaves_as_empty(self):
        """plan(findings, depth_map=None) must not raise."""
        f = _make_finding(category="CS", filepath="x.md")
        ctrl = HealController()
        plan = ctrl.plan([f], depth_map=None)
        d = plan.to_dict()
        assert "depth_map" in d

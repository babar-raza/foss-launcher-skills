"""Integration tests for healing pipeline with real category routing (TH-H3).

These tests exercise the full plan() path through real triage_finding()
and policy lookup() — no mocking of the triage/policy layer. Only
run_fixes() is mocked at the file-write level to avoid filesystem side
effects.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heal_controller import HealController, HealPlan
from content_eval.models import Finding


def _f(
    category: str,
    message: str = "test",
    filepath: str = "page.md",
    level: str = "FAIL",
    cause_class: str = "",
    **kw,
) -> Finding:
    return Finding(
        level=level,
        category=category,
        filepath=filepath,
        line_no=1,
        message=message,
        suggestion="",
        evaluator="test",
        cause_class=cause_class,
        **kw,
    )


class TestAutoRouting:
    """Findings that should route to auto group via triage rules."""

    def test_rv_type_frontmatter_routes_to_auto(self):
        """RV FAIL with 'type:' message → auto (frontmatter_type fixer)."""
        f = _f("RV", "type: missing frontmatter type field")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.auto_group.count == 1
        assert plan.llm_group.count == 0

    def test_st_placeholder_routes_to_auto(self):
        """ST WARN with 'placeholder' → auto (placeholder_remove fixer)."""
        f = _f("ST", "placeholder text detected in section", level="WARN")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.auto_group.count == 1

    def test_eg_evidence_routes_to_auto(self):
        """EG INFO with 'evidence' → auto (evidence_attach fixer)."""
        f = _f("EG", "evidence block missing", level="INFO")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.auto_group.count == 1


class TestLLMRouting:
    """Findings that should route to LLM group."""

    def test_aa_api_accuracy_routes_to_llm(self):
        """AA FAIL → llm group, skill S-21."""
        f = _f("AA", "API method Workbook.save does not exist")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.llm_group.count == 1
        item = plan.llm_group.items[0]
        assert item.skill == "S-21"

    def test_pt_prose_truth_routes_to_llm(self):
        """PT FAIL → llm group."""
        f = _f("PT", "Unsupported claim about thread safety")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.llm_group.count == 1

    def test_fc_forbidden_claim_routes_to_llm(self):
        """FC FAIL → llm group."""
        f = _f("FC", "Claim violates known limitation")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.llm_group.count == 1

    def test_rl_risk_language_routes_to_llm(self):
        """RL WARN → llm group."""
        f = _f("RL", "Risk language detected", level="WARN")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.llm_group.count == 1

    def test_cp_code_plausibility_routes_to_llm(self):
        """CP FAIL → llm group."""
        f = _f("CP", "Code example calls non-existent method")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.llm_group.count == 1


class TestRegenRouting:
    """Findings with UPSTREAM_MISSING cause_class route to regen."""

    def test_upstream_missing_routes_to_regen(self):
        """Any category with UPSTREAM_MISSING → regen group."""
        f = _f("AA", "link target missing", cause_class="UPSTREAM_MISSING")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.regen_group.count == 1
        item = plan.regen_group.items[0]
        assert item.policy.regen_after is True


class TestSkipRouting:
    """INFO-level findings without triage rules → skip."""

    def test_info_level_unknown_category_skipped(self):
        """INFO-level finding with no rule → skip group."""
        f = _f("ZZ", "informational note", level="INFO")
        ctrl = HealController()
        plan = ctrl.plan([f])
        assert plan.skip_group.count == 1
        assert plan.total_enabled == 0


class TestMixedBatch:
    """Mixed batch routing — all modes in one plan."""

    @patch("heal_controller.run_fixes")
    def test_mixed_batch_routes_correctly(self, mock_run_fixes):
        """Multiple categories in one batch route to correct groups."""
        mock_run_fixes.return_value = []
        findings = [
            _f("RV", "type: missing field", filepath="a.md"),          # auto
            _f("AA", "API method missing", filepath="b.md"),            # llm
            _f("PT", "wrong claim", filepath="c.md"),                   # llm
            _f("AA", "broken ref", filepath="d.md",
               cause_class="UPSTREAM_MISSING"),                         # regen
            _f("ZZ", "note", filepath="e.md", level="INFO"),           # skip
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)

        assert plan.auto_group.count == 1
        assert plan.llm_group.count == 2
        assert plan.regen_group.count == 1
        assert plan.skip_group.count == 1
        assert plan.total_findings == 5
        assert plan.total_enabled == 4  # auto + llm + llm + regen

        # Execute and verify structure
        result = ctrl.execute(plan, dry_run=True)
        assert result["summary"]["mode"] == "all"
        assert isinstance(result["llm"], list)
        assert isinstance(result["regen"], list)

    @patch("heal_controller.run_fixes")
    def test_mixed_batch_llm_invocations_have_correct_keys(self, mock_run_fixes):
        """LLM queue items from mixed batch have all required keys."""
        mock_run_fixes.return_value = []
        findings = [
            _f("AA", "API issue", filepath="x.md"),
            _f("PT", "prose issue", filepath="y.md"),
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        result = ctrl.execute(plan)

        required_keys = {
            "skill", "filepath", "finding_id", "category",
            "level", "message", "suggestion", "effort", "triage_reason",
        }
        for inv in result["llm"]:
            assert required_keys.issubset(inv.keys()), (
                f"Missing keys: {required_keys - inv.keys()}"
            )

    @patch("heal_controller.run_fixes")
    def test_mixed_batch_regen_invocations_have_regen_after(self, mock_run_fixes):
        """Regen queue items have regen_after flag."""
        mock_run_fixes.return_value = []
        findings = [
            _f("DL", "broken link", cause_class="UPSTREAM_MISSING"),
        ]
        ctrl = HealController()
        plan = ctrl.plan(findings)
        result = ctrl.execute(plan)

        for inv in result["regen"]:
            assert "regen_after" in inv
            assert inv["regen_after"] is True


class TestVerifyIntegration:
    """Integration: plan → verify with real findings."""

    def test_verify_detects_resolved_findings(self):
        """Resolved findings detected in verification."""
        before = [_f("AA", "API issue", filepath="a.md")]
        after = []  # all resolved
        ctrl = HealController()
        plan = ctrl.plan(before)
        report = ctrl.verify(plan, before_findings=before, after_findings=after)
        assert report.regression_detected is False
        assert report.total_before_fails == 1
        assert report.total_after_fails == 0

    def test_verify_detects_new_regressions(self):
        """New findings in after-report flagged as regression."""
        before = [_f("AA", "API issue", filepath="a.md")]
        after = [
            _f("AA", "API issue", filepath="a.md"),
            _f("PT", "new prose issue", filepath="a.md"),
        ]
        ctrl = HealController()
        plan = ctrl.plan(before)
        report = ctrl.verify(plan, before_findings=before, after_findings=after)
        assert report.regression_detected is True
        assert report.total_new_fails >= 1

"""Tests for lib/workflow_cost_circuit_breaker.py (MT069 PHB-03)."""
from __future__ import annotations

from lib import workflow_cost_circuit_breaker as breaker
from lib.workflow_cost_circuit_breaker import (
    ProposedWorkflowUsageVolume,
    check_ci_health,
    check_anomaly,
    check_cost_budget,
    check_static_caps,
    load_history,
    record_period,
)

_BUDGETS = {
    "max_total_minutes_per_period": 1500,
    "max_minutes_per_workflow_per_period": 500,
    "warmup_periods": 3,
    "anomaly_multiplier": 2.0,
    "ci_health_min_runs": 5,
    "ci_health_failure_rate_threshold": 0.9,
}


# --- static caps ---

def test_static_caps_pass_under_budget():
    volume = ProposedWorkflowUsageVolume(total_minutes=100.0, minutes_by_workflow={"a.yml": 100.0})
    assert check_static_caps(volume, _BUDGETS) == []


def test_static_caps_total_exceeded():
    volume = ProposedWorkflowUsageVolume(total_minutes=2000.0, minutes_by_workflow={})
    violations = check_static_caps(volume, _BUDGETS)
    assert len(violations) == 1
    assert "max_total_minutes_per_period" in violations[0]


def test_static_caps_per_workflow_exceeded():
    volume = ProposedWorkflowUsageVolume(total_minutes=600.0, minutes_by_workflow={"a.yml": 600.0})
    violations = check_static_caps(volume, _BUDGETS)
    assert any("a.yml" in v for v in violations)


# --- anomaly (rolling baseline) ---

def test_anomaly_inactive_during_warmup():
    volume = ProposedWorkflowUsageVolume(total_minutes=99999.0, minutes_by_workflow={})
    status, tripped = check_anomaly(volume, _BUDGETS, history={"total_minutes": [500.0]})
    assert not tripped
    assert "INACTIVE" in status


def test_anomaly_passes_within_ceiling():
    volume = ProposedWorkflowUsageVolume(total_minutes=900.0, minutes_by_workflow={})
    status, tripped = check_anomaly(volume, _BUDGETS, history={"total_minutes": [500.0, 500.0, 500.0]})
    assert not tripped
    assert "PASS" in status


def test_anomaly_trips_over_ceiling():
    volume = ProposedWorkflowUsageVolume(total_minutes=1500.0, minutes_by_workflow={})
    status, tripped = check_anomaly(volume, _BUDGETS, history={"total_minutes": [500.0, 500.0, 500.0]})
    assert tripped
    assert "ALERT" in status


def test_anomaly_zero_baseline_any_usage_trips():
    volume = ProposedWorkflowUsageVolume(total_minutes=1.0, minutes_by_workflow={})
    status, tripped = check_anomaly(volume, _BUDGETS, history={"total_minutes": [0.0, 0.0, 0.0]})
    assert tripped


def test_anomaly_zero_baseline_zero_usage_passes():
    volume = ProposedWorkflowUsageVolume(total_minutes=0.0, minutes_by_workflow={})
    status, tripped = check_anomaly(volume, _BUDGETS, history={"total_minutes": [0.0, 0.0, 0.0]})
    assert not tripped


# --- check_cost_budget (combined) ---

def test_check_cost_budget_allowed_when_clean():
    volume = ProposedWorkflowUsageVolume(total_minutes=100.0, minutes_by_workflow={"a.yml": 100.0})
    verdict = check_cost_budget(volume, budgets=_BUDGETS, history={"total_minutes": [100.0, 100.0, 100.0]})
    assert verdict.allowed
    assert verdict.static_cap_violations == []


def test_check_cost_budget_static_cap_reported_even_if_anomaly_also_fires():
    volume = ProposedWorkflowUsageVolume(total_minutes=2000.0, minutes_by_workflow={})
    verdict = check_cost_budget(volume, budgets=_BUDGETS, history={"total_minutes": [10.0, 10.0, 10.0]})
    assert not verdict.allowed
    assert verdict.static_cap_violations  # reported regardless of anomaly also tripping
    assert "ALERT" in verdict.anomaly_status


def test_check_cost_budget_anomaly_only():
    volume = ProposedWorkflowUsageVolume(total_minutes=800.0, minutes_by_workflow={})
    verdict = check_cost_budget(volume, budgets=_BUDGETS, history={"total_minutes": [100.0, 100.0, 100.0]})
    assert not verdict.allowed
    assert verdict.static_cap_violations == []
    assert verdict.reason == "anomaly check tripped"


# --- CI health ---

def test_ci_health_inactive_below_min_runs():
    verdict = check_ci_health("w.yml", ["failure", "failure"], budgets=_BUDGETS)
    assert not verdict.tripped
    assert "INACTIVE" in verdict.reason


def test_ci_health_trips_on_sustained_failure():
    verdict = check_ci_health("skill-governance.yml", ["failure"] * 10, budgets=_BUDGETS)
    assert verdict.tripped
    assert verdict.failure_rate == 1.0


def test_ci_health_passes_on_mostly_success():
    verdict = check_ci_health("w.yml", ["success"] * 9 + ["failure"], budgets=_BUDGETS)
    assert not verdict.tripped


def test_ci_health_excludes_cancelled_and_skipped_from_rate():
    conclusions = ["failure"] * 5 + ["cancelled"] * 5 + ["skipped"] * 5
    verdict = check_ci_health("w.yml", conclusions, budgets=_BUDGETS)
    assert verdict.run_count == 5  # only the 5 "failure" entries are scored
    assert verdict.tripped  # 5/5 = 100% >= 90% threshold, and 5 >= min_runs


# --- history persistence (record_period / load_history / configure) ---

def test_configure_isolates_history_path(tmp_path):
    breaker.configure(repo_root=tmp_path)
    try:
        assert breaker.HISTORY_PATH == tmp_path / "reports" / "gha-cost-telemetry" / "cost_budget_history.json"
        assert load_history() == {}  # nothing written yet in this isolated root
    finally:
        breaker.configure(repo_root=None)


def test_record_period_appends_and_persists(tmp_path):
    breaker.configure(repo_root=tmp_path)
    try:
        record_period(500.0)
        record_period(520.0)
        history = load_history()
        assert history["total_minutes"] == [500.0, 520.0]
    finally:
        breaker.configure(repo_root=None)


def test_record_period_is_atomic_write_not_partial(tmp_path):
    breaker.configure(repo_root=tmp_path)
    try:
        record_period(100.0)
        assert breaker.HISTORY_PATH.exists()
        # No stray .tmp-* files left behind after a successful write.
        leftovers = list(breaker.HISTORY_PATH.parent.glob(".tmp-*"))
        assert leftovers == []
    finally:
        breaker.configure(repo_root=None)

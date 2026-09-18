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


# --- MT069 HC-05: period scaling, period-length guards, explicit history path ---

def test_caps_scale_to_the_collection_window_the_real_2950_minutes_over_30_days_case():
    # 2026-09-18: a 30-day collection (2,950 min total) was compared to WEEKLY caps
    # (1,500 total / 500 per workflow) and "tripped" -- unlike quantities. Scaled
    # x(30/7), the same numbers are unremarkable.
    vol = ProposedWorkflowUsageVolume(
        total_minutes=2950.0,
        minutes_by_workflow={"content-governance-checks.yml": 1035.0, "skill-governance.yml": 772.0},
    )
    assert check_static_caps(vol, _BUDGETS)  # unscaled: the artifact reproduces (3 violations)
    assert len(check_static_caps(vol, _BUDGETS)) == 3
    assert check_static_caps(vol, _BUDGETS, period_days=30) == []  # scaled: cap = 6428.6 / 2142.9


def test_scaled_violation_message_says_it_was_scaled():
    vol = ProposedWorkflowUsageVolume(total_minutes=9000.0)
    (msg,) = check_static_caps(vol, _BUDGETS, period_days=30)
    assert "scaled x4.28571 for a 30-day window" in msg and "6428.57" in msg


def test_a_seven_day_window_needs_no_scaling():
    vol = ProposedWorkflowUsageVolume(total_minutes=1600.0)
    assert check_static_caps(vol, _BUDGETS, period_days=7) == check_static_caps(vol, _BUDGETS)
    assert "scaled" not in check_static_caps(vol, _BUDGETS, period_days=7)[0]


def test_cap_period_days_is_configurable():
    b = dict(_BUDGETS, cap_period_days=14)
    assert breaker.period_scale(b, 14) == 1.0 and breaker.period_scale(b, 28) == 2.0
    assert breaker.period_scale(b, None) == 1.0


def test_anomaly_refuses_to_compare_periods_of_different_lengths():
    history = {"total_minutes": [500.0, 520.0, 510.0], "period_days": 7}
    vol = ProposedWorkflowUsageVolume(total_minutes=99999.0)
    status, tripped = check_anomaly(vol, _BUDGETS, history=history, period_days=30)
    assert not tripped and "history holds 7-day periods, this run is 30-day" in status
    # same length: the anomaly check is live and trips
    assert check_anomaly(vol, _BUDGETS, history=history, period_days=7)[1] is True


def test_record_period_stores_the_period_length_and_starts_over_if_it_changes(tmp_path):
    breaker.configure(repo_root=tmp_path)
    try:
        record_period(500.0, period_days=7)
        record_period(520.0, period_days=7)
        assert load_history() == {"total_minutes": [500.0, 520.0], "period_days": 7}
        record_period(2000.0, period_days=30)   # never mix lengths in one series
        h = load_history()
        assert h["total_minutes"] == [2000.0] and h["period_days"] == 30
        assert "7 -> 30" in h["reset_reason"]
    finally:
        breaker.configure(repo_root=None)


def test_configure_history_path_points_the_series_at_an_explicit_file(tmp_path):
    target = tmp_path / "restored" / "cost_budget_history.json"
    breaker.configure(repo_root=tmp_path, history_path=target)
    try:
        assert breaker.HISTORY_PATH == target
        record_period(100.0, period_days=7)
        assert target.exists() and load_history()["total_minutes"] == [100.0]
    finally:
        breaker.configure(repo_root=None)
    assert breaker.HISTORY_PATH != target   # reset restores the default


def test_the_real_config_declares_the_new_keys_and_marks_the_caps_provisional():
    real = breaker.load_budgets()
    assert real["cap_period_days"] == 7 and real["ci_health_window_days"] == 14
    assert "upstream-monitor.yml" in real["ci_health_by_design_failing_steps"]
    assert "PROVISIONAL" in open(breaker.CONFIG_PATH, encoding="utf-8").read()

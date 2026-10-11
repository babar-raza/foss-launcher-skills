"""Tests for commands/ops/workflow_usage_ledger.py (MT069 PHB-03)."""
from __future__ import annotations

import pytest

from commands.ops import workflow_usage_ledger as ledger
from lib.workflow_usage_schema import WorkflowUsageEvent, now_iso8601


def _event(workflow_name="w.yml", runner_os="linux", minutes=10.0, runs=1, **overrides) -> WorkflowUsageEvent:
    base = dict(
        event_id="11111111-1111-1111-1111-111111111111",
        repo="Aspose/aspose.org",
        workflow_name=workflow_name,
        runner_os=runner_os,
        period_start="2026-09-01",
        period_end="2026-09-08",
        total_minutes=minutes,
        run_count=runs,
        collected_at=now_iso8601(),
    )
    base.update(overrides)
    return WorkflowUsageEvent(**base)


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path):
    path = tmp_path / "usage_events.jsonl"
    yield path


def test_record_and_load_round_trip(_isolated_ledger):
    events = [_event("a.yml"), _event("b.yml", minutes=5.0)]
    written = ledger.record_events(events, path=_isolated_ledger)
    assert written == 2

    loaded = ledger.load_events(_isolated_ledger)
    assert len(loaded) == 2
    assert {e.workflow_name for e in loaded} == {"a.yml", "b.yml"}


def test_load_events_missing_file_returns_empty(tmp_path):
    assert ledger.load_events(tmp_path / "does-not-exist.jsonl") == []


def test_record_events_is_all_or_nothing_on_invalid_event(_isolated_ledger):
    bad = _event("bad.yml", minutes=-5.0)  # invalid: negative minutes
    good = _event("good.yml")
    with pytest.raises(ledger.WorkflowUsageLedgerError):
        ledger.record_events([good, bad], path=_isolated_ledger)
    # Nothing written -- not even the valid one.
    assert ledger.load_events(_isolated_ledger) == []


def test_record_events_appends_across_calls(_isolated_ledger):
    ledger.record_events([_event("a.yml")], path=_isolated_ledger)
    ledger.record_events([_event("b.yml")], path=_isolated_ledger)
    loaded = ledger.load_events(_isolated_ledger)
    assert len(loaded) == 2


def test_validate_ledger_file_clean(_isolated_ledger):
    ledger.record_events([_event("a.yml")], path=_isolated_ledger)
    result = ledger.validate_ledger_file(_isolated_ledger)
    assert result.valid, result.errors


def test_aggregate_by_workflow_sums_minutes_and_filters_by_period():
    events = [
        _event("a.yml", minutes=10.0, runs=2, period_start="2026-09-01", period_end="2026-09-08"),
        _event("a.yml", minutes=20.0, runs=3, period_start="2026-09-01", period_end="2026-09-08"),
        _event("a.yml", minutes=999.0, runs=99, period_start="2026-08-01", period_end="2026-08-08"),  # outside window
    ]
    agg = ledger.aggregate_by_workflow(events, period_start="2026-09-01", period_end="2026-09-08")
    key = "Aspose/aspose.org::a.yml::linux"
    assert key in agg
    assert agg[key]["total_minutes"] == 30.0
    assert agg[key]["run_count"] == 5


def test_configure_changes_default_ledger_path(tmp_path):
    ledger.configure(repo_root=tmp_path)
    try:
        assert ledger.LEDGER_PATH == tmp_path / "reports" / "gha-cost-telemetry" / "usage_events.jsonl"
    finally:
        ledger.configure(repo_root=None)

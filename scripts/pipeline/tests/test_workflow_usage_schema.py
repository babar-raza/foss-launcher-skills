"""Tests for lib/workflow_usage_schema.py (MT069 PHB-03)."""
from __future__ import annotations

from lib.workflow_usage_schema import (
    WorkflowUsageEvent,
    now_iso8601,
    validate_event,
)


def _valid_event(**overrides) -> WorkflowUsageEvent:
    base = dict(
        event_id="11111111-1111-1111-1111-111111111111",
        repo="Aspose/aspose.org",
        workflow_name="content-governance-checks.yml",
        runner_os="linux",
        period_start="2026-09-01",
        period_end="2026-09-18",
        total_minutes=546.0,
        run_count=200,
        collected_at=now_iso8601(),
        method="proxy_reconstruction_v1",
    )
    base.update(overrides)
    return WorkflowUsageEvent(**base)


def test_valid_event_passes():
    result = validate_event(_valid_event())
    assert result.valid, result.errors


def test_bad_repo_format_rejected():
    result = validate_event(_valid_event(repo="not-a-repo"))
    assert not result.valid
    assert any("repo" in e for e in result.errors)


def test_bad_runner_os_rejected():
    result = validate_event(_valid_event(runner_os="amiga"))
    assert not result.valid
    assert any("runner_os" in e for e in result.errors)


def test_bad_method_rejected():
    result = validate_event(_valid_event(method="guesswork"))
    assert not result.valid
    assert any("method" in e for e in result.errors)


def test_negative_minutes_rejected():
    result = validate_event(_valid_event(total_minutes=-1.0))
    assert not result.valid
    assert any("total_minutes" in e for e in result.errors)


def test_negative_run_count_rejected():
    result = validate_event(_valid_event(run_count=-1))
    assert not result.valid
    assert any("run_count" in e for e in result.errors)


def test_period_end_before_start_rejected():
    result = validate_event(_valid_event(period_start="2026-09-18", period_end="2026-09-01"))
    assert not result.valid
    assert any("period_end" in e for e in result.errors)


def test_malformed_date_rejected():
    result = validate_event(_valid_event(period_start="not-a-date"))
    assert not result.valid

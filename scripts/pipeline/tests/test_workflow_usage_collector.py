"""Tests for lib/workflow_usage_collector.py (MT069 PHB-03).

Pure logic only -- fixtures shaped like real `gh api .../actions/runs` and
`.../jobs` responses, no subprocess/network involved.
"""
from __future__ import annotations

from lib.workflow_usage_collector import (
    classify_runner_os,
    job_billable_minutes,
    reconstruct_usage_events,
)


def _job(started, completed, labels):
    return {"started_at": started, "completed_at": completed, "labels": labels}


# --- classify_runner_os ---

def test_classify_linux_default():
    assert classify_runner_os(["ubuntu-latest"]) == "linux"


def test_classify_windows():
    assert classify_runner_os(["windows-latest"]) == "windows"


def test_classify_macos():
    assert classify_runner_os(["macos-latest"]) == "macos"


def test_classify_self_hosted_wins_over_os_labels():
    assert classify_runner_os(["self-hosted", "wsl2-linux", "gha-selfhosted-test"]) == "self-hosted"


def test_classify_no_labels_defaults_linux():
    assert classify_runner_os([]) == "linux"


# --- job_billable_minutes ---

def test_billable_minutes_linux_ceils_and_1x():
    # 90 seconds -> ceil to 2 minutes, linux multiplier 1x
    job = _job("2026-09-01T00:00:00Z", "2026-09-01T00:01:30Z", ["ubuntu-latest"])
    assert job_billable_minutes(job) == 2.0


def test_billable_minutes_windows_2x():
    job = _job("2026-09-01T00:00:00Z", "2026-09-01T00:01:00Z", ["windows-latest"])
    assert job_billable_minutes(job) == 2.0  # 1 min wall-clock * 2x


def test_billable_minutes_macos_10x():
    job = _job("2026-09-01T00:00:00Z", "2026-09-01T00:01:00Z", ["macos-latest"])
    assert job_billable_minutes(job) == 10.0


def test_billable_minutes_self_hosted_always_zero():
    job = _job("2026-09-01T00:00:00Z", "2026-09-01T00:30:00Z", ["self-hosted", "wsl2-linux"])
    assert job_billable_minutes(job) == 0.0


def test_billable_minutes_still_running_job_is_zero():
    job = _job("2026-09-01T00:00:00Z", None, ["ubuntu-latest"])
    assert job_billable_minutes(job) == 0.0


def test_billable_minutes_malformed_timestamp_is_zero():
    job = {"started_at": "not-a-date", "completed_at": "also-not-a-date", "labels": ["ubuntu-latest"]}
    assert job_billable_minutes(job) == 0.0


# --- reconstruct_usage_events ---

def test_reconstruct_aggregates_per_workflow_and_os():
    runs = [
        {"id": 1, "path": ".github/workflows/content-governance-checks.yml"},
        {"id": 2, "path": ".github/workflows/content-governance-checks.yml"},
        {"id": 3, "path": ".github/workflows/skill-governance.yml"},
    ]
    jobs_by_run_id = {
        1: [_job("2026-09-01T00:00:00Z", "2026-09-01T00:05:00Z", ["ubuntu-latest"])],   # 5 min linux
        2: [_job("2026-09-02T00:00:00Z", "2026-09-02T00:03:00Z", ["ubuntu-latest"])],   # 3 min linux
        3: [
            _job("2026-09-03T00:00:00Z", "2026-09-03T00:02:00Z", ["ubuntu-latest"]),   # 2 min linux
            _job("2026-09-03T00:00:00Z", "2026-09-03T00:04:00Z", ["windows-latest"]),  # 4 min -> 8 windows
        ],
    }
    events = reconstruct_usage_events(
        runs, jobs_by_run_id, repo="Aspose/aspose.org", period_start="2026-09-01", period_end="2026-09-08",
    )
    by_key = {(e.workflow_name, e.runner_os): e for e in events}

    cgc_linux = by_key[("content-governance-checks.yml", "linux")]
    assert cgc_linux.total_minutes == 8.0  # 5 + 3
    assert cgc_linux.run_count == 2

    sg_linux = by_key[("skill-governance.yml", "linux")]
    assert sg_linux.total_minutes == 2.0
    assert sg_linux.run_count == 1

    sg_windows = by_key[("skill-governance.yml", "windows")]
    assert sg_windows.total_minutes == 8.0
    assert sg_windows.run_count == 1


def test_reconstruct_run_with_no_jobs_contributes_nothing():
    runs = [{"id": 1, "path": ".github/workflows/w.yml"}]
    events = reconstruct_usage_events(
        runs, {1: []}, repo="Aspose/aspose.org", period_start="2026-09-01", period_end="2026-09-08",
    )
    assert events == []


def test_reconstruct_events_are_valid_per_schema():
    from lib.workflow_usage_schema import validate_event
    runs = [{"id": 1, "path": ".github/workflows/w.yml"}]
    jobs_by_run_id = {1: [_job("2026-09-01T00:00:00Z", "2026-09-01T00:01:00Z", ["ubuntu-latest"])]}
    events = reconstruct_usage_events(
        runs, jobs_by_run_id, repo="Aspose/aspose.org", period_start="2026-09-01", period_end="2026-09-08",
    )
    assert len(events) == 1
    result = validate_event(events[0])
    assert result.valid, result.errors

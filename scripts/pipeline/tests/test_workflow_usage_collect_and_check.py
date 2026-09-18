"""Tests for commands/ops/workflow_usage_collect_and_check.py (MT069 PHB-03).

Tests the gh-api-calling functions via their own `runner=` parameter (a real
DI seam matching this repo's testing-seams convention: "prefer explicit
dependency injection seams over broad monkeypatching") -- a fake runner
matching subprocess.run's interface, never a real subprocess or network
call. main() itself is a thin CLI wrapper (per the same convention, "keep
CLI entry points thin") and is exercised via a live dry-run smoke test
instead of a unit test here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from commands.ops.workflow_usage_collect_and_check import (
    fetch_recent_conclusions,
    fetch_runs_and_jobs,
    open_alert_issue,
)


@dataclass
class _FakeCompletedProcess:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class _FakeRunner:
    """Records every call it receives and returns the next queued response."""

    def __init__(self, responses: "list[_FakeCompletedProcess]"):
        self._responses = list(responses)
        self.calls: "list[list[str]]" = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if not self._responses:
            raise AssertionError(f"_FakeRunner ran out of queued responses at call: {args}")
        return self._responses.pop(0)


def test_fetch_runs_and_jobs_happy_path():
    runs_jsonl = "\n".join([
        json.dumps({"id": 1, "path": ".github/workflows/w.yml"}),
        json.dumps({"id": 2, "path": ".github/workflows/w.yml"}),
    ])
    jobs_page_1 = json.dumps([{"id": 10, "started_at": "2026-09-01T00:00:00Z", "completed_at": "2026-09-01T00:01:00Z", "labels": ["ubuntu-latest"]}])
    jobs_page_2 = json.dumps([{"id": 11, "started_at": "2026-09-02T00:00:00Z", "completed_at": "2026-09-02T00:01:00Z", "labels": ["ubuntu-latest"]}])

    runner = _FakeRunner([
        _FakeCompletedProcess(0, stdout=runs_jsonl),
        _FakeCompletedProcess(0, stdout=jobs_page_1),
        _FakeCompletedProcess(0, stdout=jobs_page_2),
    ])

    runs, jobs_by_run_id = fetch_runs_and_jobs("Aspose/aspose.org", "2026-09-01T00:00:00", runner=runner)

    assert len(runs) == 2
    assert jobs_by_run_id[1][0]["id"] == 10
    assert jobs_by_run_id[2][0]["id"] == 11
    assert len(runner.calls) == 3


def test_fetch_runs_and_jobs_raises_on_runs_fetch_failure():
    runner = _FakeRunner([_FakeCompletedProcess(1, stderr="rate limited")])
    with pytest.raises(RuntimeError, match="rate limited"):
        fetch_runs_and_jobs("Aspose/aspose.org", "2026-09-01T00:00:00", runner=runner)


def test_fetch_runs_and_jobs_tolerates_one_run_jobs_failure(capsys):
    runs_jsonl = json.dumps({"id": 1, "path": ".github/workflows/w.yml"})
    runner = _FakeRunner([
        _FakeCompletedProcess(0, stdout=runs_jsonl),
        _FakeCompletedProcess(1, stderr="transient error"),  # jobs fetch for run 1 fails
    ])
    runs, jobs_by_run_id = fetch_runs_and_jobs("Aspose/aspose.org", "2026-09-01T00:00:00", runner=runner)
    assert jobs_by_run_id[1] == []  # degrades to empty, does not raise
    assert "WARNING" in capsys.readouterr().err


def test_fetch_recent_conclusions_parses_lines():
    runner = _FakeRunner([_FakeCompletedProcess(0, stdout="success\nfailure\nsuccess\n")])
    conclusions = fetch_recent_conclusions("Aspose/aspose.org", "w.yml", runner=runner)
    assert conclusions == ["success", "failure", "success"]


def test_fetch_recent_conclusions_returns_empty_on_failure():
    runner = _FakeRunner([_FakeCompletedProcess(1, stderr="not found")])
    assert fetch_recent_conclusions("Aspose/aspose.org", "w.yml", runner=runner) == []


def test_open_alert_issue_creates_when_none_open():
    runner = _FakeRunner([
        _FakeCompletedProcess(0),  # label create
        _FakeCompletedProcess(0, stdout=""),  # issue list -> no existing
        _FakeCompletedProcess(0),  # issue create
    ])
    open_alert_issue("Aspose/aspose.org-workflows", "title", "body", "gha-cost-alert", runner=runner)
    assert runner.calls[-1][:3] == ["gh", "issue", "create"]


def test_open_alert_issue_comments_when_one_already_open():
    runner = _FakeRunner([
        _FakeCompletedProcess(0),  # label create
        _FakeCompletedProcess(0, stdout="42"),  # issue list -> #42 already open
        _FakeCompletedProcess(0),  # issue comment
    ])
    open_alert_issue("Aspose/aspose.org-workflows", "title", "body", "gha-cost-alert", runner=runner)
    assert runner.calls[-1][:3] == ["gh", "issue", "comment"]
    assert "42" in runner.calls[-1]

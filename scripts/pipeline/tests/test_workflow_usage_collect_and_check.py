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

from datetime import datetime, timedelta, timezone

from commands.ops import workflow_usage_ledger as ledger
from commands.ops.workflow_usage_collect_and_check import (
    effective_conclusions,
    fetch_failed_step_names,
    fetch_recent_conclusions,
    fetch_recent_runs,
    fetch_workflow_state,
    fetch_runs_and_jobs,
    main,
    open_alert_issue,
    parse_ci_health_target,
    rate_limit_remaining,
)
from lib import workflow_cost_circuit_breaker as breaker


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


# ---------------------------------------------------------------------------
# MT069 HC-05 -- window, by-design failures, repo routing, redaction, history.
# main() is driven end to end through an injected fake `gh` (runner=) and clock
# (now_fn=): no network, no real reports/ writes, no monkeypatching.
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
_BY_DESIGN = "Fail the job if drift was found (surfaces in workflow status/notifications)"
_PRIVATE, _PUBLIC = "Aspose/aspose.org", "Aspose/aspose.org-workflows"


@pytest.fixture(autouse=True)
def _isolate_module_state(tmp_path):
    breaker.configure(repo_root=tmp_path)
    ledger.configure(repo_root=tmp_path)
    yield
    breaker.configure()
    ledger.configure()


class _Router:
    """A fake gh: the first route whose needle occurs in the joined command wins;
    anything unrouted succeeds with empty output (label create, issue calls...)."""

    def __init__(self, routes):
        self.routes, self.calls = list(routes), []

    def __call__(self, args, **kwargs):
        cmd = " ".join(args)
        self.calls.append(cmd)
        for needle, response in self.routes:
            if needle in cmd:
                return response() if callable(response) else response
        return _FakeCompletedProcess(0, "")

    def issue_calls(self):
        return [c for c in self.calls if c.startswith("gh issue create") or c.startswith("gh issue comment")]


def _job(minutes, labels=("ubuntu-latest",)):
    start = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return {"labels": list(labels), "started_at": start.strftime(fmt),
            "completed_at": (start + timedelta(minutes=minutes)).strftime(fmt)}


def _runs_jsonl(*ids_paths):
    return "\n".join(json.dumps({"id": i, "path": f".github/workflows/{p}"}) for i, p in ids_paths)


def _ci_runs(*specs):
    return "\n".join(json.dumps({"id": i, "conclusion": c, "created_at": t}) for i, c, t in specs)


def _base_routes(minutes=13):
    ratelimit = iter(("5000", "4990"))
    return [
        ("rate_limit", lambda: _FakeCompletedProcess(0, next(ratelimit, "4990") + "\n")),
        ("actions/runs?created", _FakeCompletedProcess(0, _runs_jsonl((1, "content-governance-checks.yml")))),
        ("actions/runs/1/jobs", _FakeCompletedProcess(0, json.dumps([_job(minutes)]))),
    ]


def _failing_history(first_id=100, n=6, day="2026-09-17"):
    return _ci_runs(*[(first_id + i, "failure", f"{day}T00:00:00Z") for i in range(n)])


# --- pure helpers ---

def test_parse_ci_health_target_defaults_to_the_main_repo_and_accepts_owner_repo_prefix():
    assert parse_ci_health_target("skill-governance.yml", _PRIVATE) == (_PRIVATE, "skill-governance.yml")
    assert parse_ci_health_target(f"{_PUBLIC}:upstream-monitor.yml", _PRIVATE) == (_PUBLIC, "upstream-monitor.yml")


def test_effective_conclusions_drops_runs_outside_the_window():
    runs = [{"id": 1, "conclusion": "failure", "created_at": "2026-09-17T00:00:00Z"},
            {"id": 2, "conclusion": "failure", "created_at": "2026-08-01T00:00:00Z"}]
    got, stats = effective_conclusions(runs, now=_NOW, window_days=14)
    assert got == ["failure"] and stats["outside_window"] == 1 and stats["in_window"] == 1


def test_effective_conclusions_scores_a_by_design_failure_as_success():
    runs = [{"id": 7, "conclusion": "failure", "created_at": "2026-09-17T00:00:00Z"}]
    got, stats = effective_conclusions(runs, now=_NOW, window_days=14, by_design_steps=[_BY_DESIGN],
                                       failed_steps_fn=lambda run_id: [_BY_DESIGN])
    assert got == ["success"] and stats["by_design"] == 1


def test_a_run_that_also_failed_a_different_step_stays_a_failure():
    runs = [{"id": 7, "conclusion": "failure", "created_at": "2026-09-17T00:00:00Z"}]
    got, _ = effective_conclusions(runs, now=_NOW, window_days=14, by_design_steps=[_BY_DESIGN],
                                   failed_steps_fn=lambda run_id: [_BY_DESIGN, "Sweep drifted products"])
    assert got == ["failure"]


def test_an_unverifiable_exemption_never_hides_a_failure():
    runs = [{"id": 7, "conclusion": "failure", "created_at": "2026-09-17T00:00:00Z"}]
    got, stats = effective_conclusions(runs, now=_NOW, window_days=14, by_design_steps=[_BY_DESIGN],
                                       failed_steps_fn=lambda run_id: None)
    assert got == ["failure"] and stats["unverifiable"] == 1


def test_fetch_failed_step_names_returns_none_when_the_lookup_fails_or_is_garbled():
    assert fetch_failed_step_names("o/r", 1, runner=_FakeRunner([_FakeCompletedProcess(1, "", "boom")])) is None
    assert fetch_failed_step_names("o/r", 1, runner=_FakeRunner([_FakeCompletedProcess(0, "not json")])) is None
    assert fetch_failed_step_names("o/r", 1, runner=_FakeRunner([_FakeCompletedProcess(0, '["a","b"]')])) == ["a", "b"]


def test_fetch_recent_runs_parses_jsonl_and_tolerates_failure():
    ok = _FakeRunner([_FakeCompletedProcess(0, _ci_runs((1, "success", "2026-09-17T00:00:00Z")))])
    assert fetch_recent_runs("o/r", "w.yml", runner=ok) == [{"id": 1, "conclusion": "success", "created_at": "2026-09-17T00:00:00Z"}]
    assert fetch_recent_runs("o/r", "w.yml", runner=_FakeRunner([_FakeCompletedProcess(1, "")])) == []


def test_rate_limit_remaining_parses_an_int_and_returns_none_otherwise():
    assert rate_limit_remaining(runner=_FakeRunner([_FakeCompletedProcess(0, "4321\n")])) == 4321
    assert rate_limit_remaining(runner=_FakeRunner([_FakeCompletedProcess(1, "")])) is None
    assert rate_limit_remaining(runner=_FakeRunner([_FakeCompletedProcess(0, "n/a")])) is None


# --- main(): dry run, live, routing, redaction, windows, history ---

def test_dry_run_never_records_history_and_opens_no_issue(capsys):
    router = _Router(_base_routes())
    assert main(["--repo", _PRIVATE], runner=router, now_fn=lambda: _NOW) == 0
    assert not breaker.HISTORY_PATH.exists()
    assert router.issue_calls() == []
    assert "dry-run" in capsys.readouterr().out
    assert any("rate_limit" in c for c in router.calls)


def test_a_30_day_window_is_not_compared_to_weekly_caps_but_a_7_day_one_is(capsys):
    # one workflow used 1,000 minutes: over the 500/week per-workflow cap, well under the scaled 30-day one
    weekly = _Router(_base_routes(minutes=1000))
    assert main(["--repo", _PRIVATE, "--period-days", "7"], runner=weekly, now_fn=lambda: _NOW) == 1
    monthly = _Router(_base_routes(minutes=1000))
    assert main(["--repo", _PRIVATE, "--period-days", "30"], runner=monthly, now_fn=lambda: _NOW) == 0
    assert "Cost check: OK" in capsys.readouterr().out


def test_alerts_default_to_the_private_repo_never_the_public_one():
    router = _Router(_base_routes() + [("workflows/skill-governance.yml/runs", _FakeCompletedProcess(0, _failing_history()))])
    rc = main(["--repo", _PRIVATE, "--live", "--ci-health-workflows", "skill-governance.yml"],
              runner=router, now_fn=lambda: _NOW)
    assert rc == 1
    issue_cmds = router.issue_calls()
    assert issue_cmds and all(f"--repo {_PRIVATE} " in c and _PUBLIC not in c for c in issue_cmds)


def test_an_explicit_alert_repo_is_honoured():
    router = _Router(_base_routes() + [("workflows/skill-governance.yml/runs", _FakeCompletedProcess(0, _failing_history()))])
    main(["--repo", _PRIVATE, "--live", "--alert-repo", "Some/other", "--ci-health-workflows", "skill-governance.yml"],
         runner=router, now_fn=lambda: _NOW)
    assert router.issue_calls() and all("--repo Some/other " in c for c in router.issue_calls())


def test_redact_keeps_names_and_minutes_off_stdout_but_in_the_details_file(tmp_path, capsys):
    router = _Router(_base_routes(minutes=1000) + [("workflows/skill-governance.yml/runs", _FakeCompletedProcess(0, _failing_history()))])
    details = tmp_path / "details.txt"
    rc = main(["--repo", _PRIVATE, "--redact", "--details-file", str(details),
               "--ci-health-workflows", "skill-governance.yml"], runner=router, now_fn=lambda: _NOW)
    out = capsys.readouterr().out
    assert rc == 1
    assert "skill-governance.yml" not in out and "content-governance-checks.yml" not in out and "1000" not in out
    assert "CI-health: 1 workflow(s) checked, 1 tripped" in out
    full = details.read_text(encoding="utf-8")
    assert "skill-governance.yml" in full and "content-governance-checks.yml" in full


def test_ci_health_ignores_a_workflow_whose_history_is_all_outside_the_window(capsys):
    # a disabled or migrated-away workflow: its last failures are 48 days old -> INACTIVE, not an alert
    router = _Router(_base_routes() + [("workflows/skill-governance.yml/runs",
                                        _FakeCompletedProcess(0, _failing_history(200, 8, "2026-08-01")))])
    rc = main(["--repo", _PRIVATE, "--ci-health-workflows", "skill-governance.yml"], runner=router, now_fn=lambda: _NOW)
    out = capsys.readouterr().out
    assert rc == 0 and "INACTIVE" in out and "8 older ignored" in out


def test_the_real_upstream_monitor_shape_is_healthy_when_it_fails_only_by_design(capsys):
    router = _Router(_base_routes() + [
        (f"{_PUBLIC}/actions/workflows/upstream-monitor.yml/runs", _FakeCompletedProcess(0, _failing_history(300))),
        ("actions/runs/30", _FakeCompletedProcess(0, json.dumps([_BY_DESIGN]))),
    ])
    rc = main(["--repo", _PRIVATE, "--ci-health-workflows", f"{_PUBLIC}:upstream-monitor.yml"],
              runner=router, now_fn=lambda: _NOW)
    out = capsys.readouterr().out
    assert rc == 0 and "6 failed only by design" in out and "PASS" in out


def test_the_same_workflow_with_a_genuine_extra_failure_still_alerts(capsys):
    router = _Router(_base_routes() + [
        (f"{_PUBLIC}/actions/workflows/upstream-monitor.yml/runs", _FakeCompletedProcess(0, _failing_history(300))),
        ("actions/runs/30", _FakeCompletedProcess(0, json.dumps([_BY_DESIGN, "Sweep drifted products"]))),
    ])
    rc = main(["--repo", _PRIVATE, "--ci-health-workflows", f"{_PUBLIC}:upstream-monitor.yml"],
              runner=router, now_fn=lambda: _NOW)
    assert rc == 1 and "ALERT" in capsys.readouterr().out


def test_live_records_the_period_at_the_given_history_file_with_its_length(tmp_path):
    hist = tmp_path / "restored" / "cost_budget_history.json"
    router = _Router(_base_routes(minutes=13))
    assert main(["--repo", _PRIVATE, "--live", "--history-file", str(hist)], runner=router, now_fn=lambda: _NOW) == 0
    assert json.loads(hist.read_text(encoding="utf-8")) == {"period_days": 7, "total_minutes": [13.0]}


def test_fetch_workflow_state_returns_a_state_word_and_never_a_404_body():
    ok = _FakeRunner([_FakeCompletedProcess(0, "disabled_manually\n")])
    assert fetch_workflow_state("o/r", "w.yml", runner=ok) == "disabled_manually"
    failed = _FakeRunner([_FakeCompletedProcess(1, '{"message":"Not Found","status":"404"}')])
    assert fetch_workflow_state("o/r", "w.yml", runner=failed) is None
    garbage = _FakeRunner([_FakeCompletedProcess(0, '{"message":"Not Found"}')])   # a 404 body on stdout, rc 0 via --jq
    assert fetch_workflow_state("o/r", "w.yml", runner=garbage) is None


def test_a_disabled_workflow_with_a_stale_failing_history_is_inactive_not_an_alert(capsys):
    # the real 2026-09-19 case: skill-governance.yml, 28 pre-fix failures, disabled -- nothing can ever clear that history
    router = _Router(_base_routes() + [
        ("workflows/skill-governance.yml --jq", _FakeCompletedProcess(0, "disabled_manually\n")),
        ("workflows/skill-governance.yml/runs", _FakeCompletedProcess(0, _failing_history())),
    ])
    rc = main(["--repo", _PRIVATE, "--live", "--ci-health-workflows", "skill-governance.yml"],
              runner=router, now_fn=lambda: _NOW)
    out = capsys.readouterr().out
    assert rc == 0 and "INACTIVE (workflow is disabled_manually" in out
    assert router.issue_calls() == []


def test_an_active_workflow_is_still_checked_and_can_alert():
    router = _Router(_base_routes() + [
        ("workflows/skill-governance.yml --jq", _FakeCompletedProcess(0, "active\n")),
        ("workflows/skill-governance.yml/runs", _FakeCompletedProcess(0, _failing_history())),
    ])
    assert main(["--repo", _PRIVATE, "--live", "--ci-health-workflows", "skill-governance.yml"],
                runner=router, now_fn=lambda: _NOW) == 1
    assert router.issue_calls()


def test_an_unverifiable_workflow_state_never_hides_a_real_failure():
    router = _Router(_base_routes() + [
        ("workflows/skill-governance.yml --jq", _FakeCompletedProcess(1, "", "HTTP 502")),
        ("workflows/skill-governance.yml/runs", _FakeCompletedProcess(0, _failing_history())),
    ])
    assert main(["--repo", _PRIVATE, "--ci-health-workflows", "skill-governance.yml"],
                runner=router, now_fn=lambda: _NOW) == 1


def test_live_run_with_zero_minutes_does_not_record_an_idle_period(tmp_path, capsys):
    # every private workflow is disabled: the period is genuinely 0 minutes and must not become the baseline
    hist = tmp_path / "restored" / "cost_budget_history.json"
    router = _Router([("rate_limit", _FakeCompletedProcess(0, "5000\n")),
                      ("actions/runs?created", _FakeCompletedProcess(0, ""))])
    assert main(["--repo", _PRIVATE, "--live", "--history-file", str(hist)], runner=router, now_fn=lambda: _NOW) == 0
    assert not hist.exists()
    assert "not recording it" in capsys.readouterr().out


def test_collection_failure_returns_2(capsys):
    router = _Router([("actions/runs?created", _FakeCompletedProcess(1, "", "HTTP 502"))])
    assert main(["--repo", _PRIVATE], runner=router, now_fn=lambda: _NOW) == 2
    assert "ERROR" in capsys.readouterr().err

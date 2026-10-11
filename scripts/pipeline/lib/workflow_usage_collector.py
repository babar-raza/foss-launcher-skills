"""Proxy-reconstruction of GitHub Actions billable minutes from raw run/job
data, for the recurring cost-telemetry collector (MT069-2026-09-16-GHA-
MINUTES-REARCHITECTURE, PHB-03). Same method TC-04 used ad hoc to build
usage_dataset.json, now a real, tested, reusable module instead of a one-off
manual reconstruction.

Pure logic only -- no gh api subprocess calls here (that lives in
workflow_usage_collect_and_check.py's thin fetch wrapper), so this is fully
testable against fixture JSON shaped like the real API responses.

GitHub's real billing model (per https://docs.github.com/actions, unchanged
since GHA's introduction): each job's wall-clock duration is rounded UP to
the next whole minute, then multiplied by a per-OS rate multiplier
(Linux=1x, Windows=2x, macOS=10x) to get billable minutes. Self-hosted
runners are NEVER billed against the included-minutes allowance regardless
of duration -- this module always reports 0 billable minutes for a
self-hosted job (their real cost is the runner's own operating cost, out of
scope for this collector), while still counting them in run_count so a
self-hosted-vs-hosted split stays observable.
"""
from __future__ import annotations

import math
from datetime import datetime

from lib.workflow_usage_schema import WorkflowUsageEvent, generate_event_id, now_iso8601

_OS_MULTIPLIERS = {"linux": 1, "windows": 2, "macos": 10, "self-hosted": 0}


def classify_runner_os(labels: "list[str]") -> str:
    """Classify a job's runner_os from its `labels` list (gh api's own field
    on a job object). "self-hosted" wins over any other label present
    alongside it (a self-hosted runner can carry OS-like labels too, e.g.
    "self-hosted, wsl2-linux") since that changes the billing outcome
    entirely, not just the display name."""
    lowered = [l.lower() for l in labels]
    if "self-hosted" in lowered:
        return "self-hosted"
    if any("windows" in l for l in lowered):
        return "windows"
    if any("macos" in l or "mac-os" in l for l in lowered):
        return "macos"
    return "linux"  # GitHub-hosted default when no more specific label matches


def _parse_gh_timestamp(value: "str | None") -> "datetime | None":
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def job_billable_minutes(job: dict) -> float:
    """One job's billable minutes: ceil(wall-clock minutes) * OS multiplier.
    Returns 0.0 for a job with no completed_at (still running) or malformed
    timestamps -- never guesses a partial duration."""
    started = _parse_gh_timestamp(job.get("started_at"))
    completed = _parse_gh_timestamp(job.get("completed_at"))
    if started is None or completed is None or completed < started:
        return 0.0
    wall_clock_minutes = math.ceil((completed - started).total_seconds() / 60.0)
    runner_os = classify_runner_os(job.get("labels") or [])
    return float(wall_clock_minutes * _OS_MULTIPLIERS.get(runner_os, 1))


def reconstruct_usage_events(
    runs: "list[dict]",
    jobs_by_run_id: "dict[int, list[dict]]",
    *,
    repo: str,
    period_start: str,
    period_end: str,
) -> "list[WorkflowUsageEvent]":
    """Aggregate raw `gh api .../actions/runs` + `.../jobs` data into one
    WorkflowUsageEvent per (workflow_name, runner_os) pair -- matching the
    real Actions usage export's own per-OS row shape (TC-04's
    usage_dataset.json). `runs` items must each have a `path` field
    (".github/workflows/{name}.yml", present on every real run object);
    `jobs_by_run_id` maps each run's `id` to its `gh api .../jobs` response
    list."""
    totals: "dict[tuple[str, str], dict]" = {}

    for run in runs:
        path = run.get("path") or ""
        workflow_name = path.rsplit("/", 1)[-1] if path else str(run.get("workflow_id", "unknown"))
        jobs = jobs_by_run_id.get(run.get("id"), [])
        # A run with zero jobs (e.g. still queued) contributes nothing yet --
        # it will be picked up in a later collection once jobs exist.
        seen_os_for_this_run: "set[str]" = set()
        for job in jobs:
            runner_os = classify_runner_os(job.get("labels") or [])
            minutes = job_billable_minutes(job)
            key = (workflow_name, runner_os)
            row = totals.setdefault(key, {"minutes": 0.0, "runs": 0})
            row["minutes"] += minutes
            seen_os_for_this_run.add(runner_os)
        # run_count is per (workflow, os): a run contributes 1 to run_count
        # for each distinct OS its jobs actually used (correct for the
        # common single-OS-per-run case; a genuinely mixed-OS run counts
        # once per OS it touched, matching how the real usage export
        # attributes runs to separate OS rows rather than double-counting
        # minutes).
        for runner_os in seen_os_for_this_run:
            totals[(workflow_name, runner_os)]["runs"] += 1

    collected_at = now_iso8601()
    events: "list[WorkflowUsageEvent]" = []
    for (workflow_name, runner_os), agg in sorted(totals.items()):
        events.append(WorkflowUsageEvent(
            event_id=generate_event_id(),
            repo=repo,
            workflow_name=workflow_name,
            runner_os=runner_os,
            period_start=period_start,
            period_end=period_end,
            total_minutes=round(agg["minutes"], 2),
            run_count=agg["runs"],
            collected_at=collected_at,
            method="proxy_reconstruction_v1",
        ))
    return events

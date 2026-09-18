"""workflow_usage_collect_and_check.py -- the recurring GHA cost/CI-health
telemetry collector's CLI entry point (MT069-2026-09-16-GHA-MINUTES-
REARCHITECTURE, PHB-03).

Ties together the pure logic modules (never touching gh api or the network
themselves, so they stay fully unit-testable):
  - lib/workflow_usage_collector.py    -- proxy-minute reconstruction
  - commands/ops/workflow_usage_ledger.py -- durable JSONL event ledger
  - lib/workflow_cost_circuit_breaker.py  -- magnitude-cap alerting

Usage:
    # Real collection against the private repo, dry-run (default -- prints,
    # writes the ledger + history, but never opens an issue):
    PYTHONPATH=scripts/pipeline .venv/Scripts/python \\
      scripts/pipeline/commands/ops/workflow_usage_collect_and_check.py \\
      --repo Aspose/aspose.org --period-days 7

    # Live: actually open/update the alert issue if a check trips.
    ... --live --alert-repo Aspose/aspose.org-workflows

Exit codes:
  0 -- collection succeeded, no alert tripped (or dry-run)
  1 -- collection succeeded, at least one alert tripped
  2 -- collection itself failed (gh api / config error)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from commands.ops import workflow_usage_ledger as ledger
from lib import workflow_cost_circuit_breaker as breaker
from lib.workflow_usage_collector import reconstruct_usage_events


def _run_gh(args: "list[str]", *, runner=subprocess.run) -> "subprocess.CompletedProcess":
    return runner(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)


def fetch_runs_and_jobs(
    repo: str, since_iso: str, *, runner=subprocess.run,
) -> "tuple[list[dict], dict[int, list[dict]]]":
    """Real gh api calls: every run created on/after `since_iso`, then each
    run's own jobs list. Skips (logs, does not crash) any single run whose
    jobs call fails -- a transient API error on one run must not lose the
    whole period's collection."""
    result = _run_gh(
        ["api", f"repos/{repo}/actions/runs?created=>={since_iso}&per_page=100", "--paginate",
         "--jq", ".workflow_runs[] | {id, path}"],
        runner=runner,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api runs fetch failed for {repo}: {result.stderr.strip()}")

    runs: "list[dict]" = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        runs.append(json.loads(line))

    jobs_by_run_id: "dict[int, list[dict]]" = {}
    for run in runs:
        run_id = run["id"]
        jobs_result = _run_gh(
            ["api", f"repos/{repo}/actions/runs/{run_id}/jobs", "--paginate", "--jq", ".jobs"],
            runner=runner,
        )
        if jobs_result.returncode != 0:
            print(f"WARNING: jobs fetch failed for run {run_id} ({repo}): {jobs_result.stderr.strip()}", file=sys.stderr)
            jobs_by_run_id[run_id] = []
            continue
        pages = [json.loads(chunk) for chunk in jobs_result.stdout.splitlines() if chunk.strip()]
        jobs_by_run_id[run_id] = [job for page in pages for job in page]

    return runs, jobs_by_run_id


def fetch_recent_conclusions(
    repo: str, workflow_filename: str, *, limit: int = 10, runner=subprocess.run,
) -> "list[str]":
    """The last `limit` run conclusions for one workflow, for the CI-health check."""
    result = _run_gh(
        ["api", f"repos/{repo}/actions/workflows/{workflow_filename}/runs?per_page={limit}",
         "--jq", ".workflow_runs[].conclusion"],
        runner=runner,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and line.strip() != "null"]


def open_alert_issue(alert_repo: str, title: str, body: str, label: str, *, runner=subprocess.run) -> None:
    """Reuses the aspose-com-targets-watch.yml issue-creation pattern:
    dedup by an open issue with the same label, comment instead of spamming
    a new one each period. This function ALERTS -- it never disables,
    dispatches, or otherwise mutates any workflow, matching this capability's
    one non-negotiable design rule."""
    runner(["gh", "label", "create", label, "--repo", alert_repo,
            "--color", "d73a4a", "--description", f"{label} alert"],
           capture_output=True, text=True, encoding="utf-8", errors="replace")
    existing = runner(
        ["gh", "issue", "list", "--repo", alert_repo, "--label", label, "--state", "open",
         "--json", "number", "--jq", ".[0].number // empty"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    existing_number = existing.stdout.strip()
    if existing_number:
        runner(["gh", "issue", "comment", existing_number, "--repo", alert_repo, "--body", body],
               capture_output=True, text=True, encoding="utf-8", errors="replace")
    else:
        runner(["gh", "issue", "create", "--repo", alert_repo, "--title", title,
                "--label", label, "--body", body],
               capture_output=True, text=True, encoding="utf-8", errors="replace")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Aspose/aspose.org", help="Repo to collect usage for")
    parser.add_argument("--period-days", type=int, default=7)
    parser.add_argument("--live", action="store_true",
                         help="Actually open/update the alert issue. Default is dry-run (print only).")
    parser.add_argument("--alert-repo", default="Aspose/aspose.org-workflows",
                         help="Repo to open the alert issue in (default: the public repo, so an alert is visible without needing the private repo's own Actions re-enabled)")
    parser.add_argument("--ci-health-workflows", nargs="*", default=[],
                         help="Workflow filenames to also run the CI-health check against (in --repo)")
    args = parser.parse_args(argv)

    period_end_dt = datetime.now(timezone.utc)
    period_start_dt = period_end_dt - timedelta(days=args.period_days)
    period_start = period_start_dt.strftime("%Y-%m-%d")
    period_end = period_end_dt.strftime("%Y-%m-%d")

    try:
        runs, jobs_by_run_id = fetch_runs_and_jobs(args.repo, period_start_dt.isoformat())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    events = reconstruct_usage_events(
        runs, jobs_by_run_id, repo=args.repo, period_start=period_start, period_end=period_end,
    )
    written = ledger.record_events(events)
    print(f"Collected {len(events)} usage row(s) ({written} written to ledger) for {args.repo}, "
          f"period {period_start}..{period_end}")

    volume = breaker.ProposedWorkflowUsageVolume(
        total_minutes=sum(e.total_minutes for e in events),
        minutes_by_workflow={},
    )
    for e in events:
        volume.minutes_by_workflow[e.workflow_name] = volume.minutes_by_workflow.get(e.workflow_name, 0.0) + e.total_minutes

    cost_verdict = breaker.check_cost_budget(volume)
    print(f"Cost check: {'ALERT' if not cost_verdict.allowed else 'OK'} -- {cost_verdict.reason} "
          f"(anomaly: {cost_verdict.anomaly_status})")
    if cost_verdict.static_cap_violations:
        for v in cost_verdict.static_cap_violations:
            print(f"  - {v}")

    tripped_ci_health: "list[breaker.CIHealthVerdict]" = []
    for wf in args.ci_health_workflows:
        conclusions = fetch_recent_conclusions(args.repo, wf)
        verdict = breaker.check_ci_health(wf, conclusions)
        print(f"CI-health check ({wf}): {verdict.reason}")
        if verdict.tripped:
            tripped_ci_health.append(verdict)

    any_tripped = (not cost_verdict.allowed) or bool(tripped_ci_health)

    if args.live:
        breaker.record_period(volume.total_minutes)
        if not cost_verdict.allowed:
            body = (
                f"## GHA Cost Alert — {period_start} to {period_end}\n\n"
                f"{cost_verdict.reason}\n\n"
                + "\n".join(f"- {v}" for v in cost_verdict.static_cap_violations)
                + f"\n\nAnomaly check: {cost_verdict.anomaly_status}\n\n"
                "This is an alert only -- nothing has been disabled or changed automatically. "
                "A human should review whether this is expected growth or a real regression."
            )
            open_alert_issue(args.alert_repo, f"GHA cost alert — {period_start}", body, "gha-cost-alert")
        for v in tripped_ci_health:
            body = f"## CI-Health Alert\n\n{v.reason}\n\nAlert only -- nothing has been disabled automatically."
            open_alert_issue(args.alert_repo, f"CI-health alert — {v.reason.split(':')[0]}", body, "gha-ci-health-alert")
    else:
        print("(dry-run: not recording period to circuit-breaker history, not opening any issue -- pass --live to do both)")

    return 1 if any_tripped else 0


if __name__ == "__main__":
    sys.exit(main())

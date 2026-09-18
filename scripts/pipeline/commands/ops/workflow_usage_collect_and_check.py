"""workflow_usage_collect_and_check.py -- the recurring GHA cost/CI-health
telemetry collector's CLI entry point (MT069-2026-09-16-GHA-MINUTES-
REARCHITECTURE, PHB-03; hardened by card HC-05, 2026-09-18).

Ties together the pure logic modules (never touching gh api or the network
themselves, so they stay fully unit-testable):
  - lib/workflow_usage_collector.py    -- proxy-minute reconstruction
  - commands/ops/workflow_usage_ledger.py -- durable JSONL event ledger
  - lib/workflow_cost_circuit_breaker.py  -- magnitude-cap alerting

Usage:
    # Real collection against the private repo, dry-run (default -- prints,
    # writes the ledger, never records history and never opens an issue):
    PYTHONPATH=scripts/pipeline .venv/Scripts/python \\
      scripts/pipeline/commands/ops/workflow_usage_collect_and_check.py \\
      --repo Aspose/aspose.org --period-days 7

    # Live: record the period to history and open/update the alert issue if a
    # check trips. Alerts go to --alert-repo, which DEFAULTS TO --repo (the
    # private repo): an alert lists per-workflow names and minutes, which must
    # not be published in a public repo's issues.
    ... --live --history-file <path>

    # Health of a workflow that lives in ANOTHER repo (e.g. a migrated bot):
    ... --ci-health-workflows skill-governance.yml Aspose/aspose.org-workflows:upstream-monitor.yml

    # In a PUBLIC repo's Actions log, keep names/minutes out of stdout:
    ... --redact --details-file <path>

What HC-05 changed, each from a defect found live on 2026-09-18:
  * caps are scaled to --period-days (a 30-day run "exceeded" WEEKLY caps);
  * CI health only counts runs inside a window, so a disabled or migrated-away
    workflow does not alert forever on its last historical failures;
  * a workflow designed to fail when it finds something (upstream-monitor.yml)
    is not scored as unhealthy for that one step;
  * --history-file, because the default history lives under gitignored reports/
    and a stateless CI runner loses it (the anomaly baseline could never warm up);
  * main() takes an injected `runner` and clock, so it is unit-tested instead of
    being covered by "a live dry-run smoke test" (which is not a test).

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
    """The last `limit` run conclusions for one workflow (no time window --
    kept for callers that want the raw list; the CLI uses fetch_recent_runs +
    effective_conclusions so the window and by-design rules apply)."""
    result = _run_gh(
        ["api", f"repos/{repo}/actions/workflows/{workflow_filename}/runs?per_page={limit}",
         "--jq", ".workflow_runs[].conclusion"],
        runner=runner,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and line.strip() != "null"]


def fetch_recent_runs(
    repo: str, workflow_filename: str, *, limit: int = 30, runner=subprocess.run,
) -> "list[dict]":
    """The last `limit` runs of one workflow as {id, conclusion, created_at}."""
    result = _run_gh(
        ["api", f"repos/{repo}/actions/workflows/{workflow_filename}/runs?per_page={limit}",
         "--jq", ".workflow_runs[] | {id, conclusion, created_at}"],
        runner=runner,
    )
    if result.returncode != 0:
        return []
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def fetch_failed_step_names(repo: str, run_id: int, *, runner=subprocess.run) -> "list[str] | None":
    """Names of the steps that concluded `failure` in one run, or None when the
    lookup itself failed (the caller must then keep the run scored as a failure:
    an unverifiable exemption must never hide a real failure)."""
    result = _run_gh(
        ["api", f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
         "--jq", '[.jobs[].steps[] | select(.conclusion == "failure") | .name]'],
        runner=runner,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None


def _parse_ts(value: "str | None") -> "datetime | None":
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def effective_conclusions(
    runs: "list[dict]", *, now: datetime, window_days: int,
    by_design_steps: "tuple[str, ...] | list[str]" = (), failed_steps_fn=None,
) -> "tuple[list[str], dict]":
    """Turn raw runs into the conclusions the CI-health check should score.

    * runs older than `window_days` are dropped (a quiet workflow is INACTIVE,
      not perpetually unhealthy);
    * a `failure` whose only failing steps are in `by_design_steps` is scored
      `success` (the workflow did what it is designed to do);
    * if the failing steps cannot be determined, the run stays a `failure`.
    Returns (conclusions, stats)."""
    cutoff = now - timedelta(days=window_days)
    conclusions: "list[str]" = []
    stats = {"in_window": 0, "outside_window": 0, "by_design": 0, "unverifiable": 0}
    for run in runs:
        created = _parse_ts(run.get("created_at"))
        if created is None or created < cutoff:
            stats["outside_window"] += 1
            continue
        stats["in_window"] += 1
        conclusion = run.get("conclusion") or ""
        if conclusion == "failure" and by_design_steps:
            failed = failed_steps_fn(run["id"]) if failed_steps_fn else None
            if failed is None:
                stats["unverifiable"] += 1
            elif failed and all(step in by_design_steps for step in failed):
                conclusion = "success"
                stats["by_design"] += 1
        conclusions.append(conclusion)
    return conclusions, stats


def parse_ci_health_target(item: str, default_repo: str) -> "tuple[str, str]":
    """`file.yml` -> (default_repo, file.yml); `owner/repo:file.yml` -> that repo."""
    if ":" in item:
        repo, _, filename = item.partition(":")
        return repo, filename
    return default_repo, item


def rate_limit_remaining(*, runner=subprocess.run) -> "int | None":
    result = _run_gh(["api", "rate_limit", "--jq", ".resources.core.remaining"], runner=runner)
    try:
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except ValueError:
        return None


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


def main(argv: "list[str] | None" = None, *, runner=subprocess.run, now_fn=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default="Aspose/aspose.org", help="Repo to collect usage for")
    parser.add_argument("--period-days", type=int, default=7)
    parser.add_argument("--live", action="store_true",
                         help="Record the period to history and open/update alert issues. Default is dry-run (print only).")
    parser.add_argument("--alert-repo", default=None,
                         help="Repo to open alert issues in. DEFAULT: --repo. Deliberately not the public repo: an alert "
                              "lists per-workflow names and minutes.")
    parser.add_argument("--history-file", default=None,
                         help="Rolling-baseline history file (default: reports/gha-cost-telemetry/cost_budget_history.json, "
                              "which a stateless CI runner loses between runs)")
    parser.add_argument("--redact", action="store_true",
                         help="Keep per-workflow names and minutes out of stdout (for a public repo's Actions log); "
                              "the full text still goes into alert issues and --details-file")
    parser.add_argument("--details-file", default=None, help="Write the full, unredacted report here")
    parser.add_argument("--ci-health-workflows", nargs="*", default=[],
                         help="Workflows to run the CI-health check against: `file.yml` (in --repo) or `owner/repo:file.yml`")
    args = parser.parse_args(argv)

    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    alert_repo = args.alert_repo or args.repo
    if args.history_file:
        breaker.configure(history_path=args.history_file)

    details: "list[str]" = []

    def say(message: str, *, detail: bool = False) -> None:
        """detail=True lines carry workflow names/minutes; --redact keeps them off stdout."""
        details.append(message)
        if not (detail and args.redact):
            print(message)

    period_end_dt = now
    period_start_dt = period_end_dt - timedelta(days=args.period_days)
    period_start = period_start_dt.strftime("%Y-%m-%d")
    period_end = period_end_dt.strftime("%Y-%m-%d")
    budgets = breaker.load_budgets()

    rate_before = rate_limit_remaining(runner=runner)
    try:
        runs, jobs_by_run_id = fetch_runs_and_jobs(args.repo, period_start_dt.isoformat(), runner=runner)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    events = reconstruct_usage_events(
        runs, jobs_by_run_id, repo=args.repo, period_start=period_start, period_end=period_end,
    )
    written = ledger.record_events(events)
    say(f"Collected {len(events)} usage row(s) ({written} written to ledger) for {args.repo}, "
        f"period {period_start}..{period_end} ({args.period_days} days, {len(runs)} run(s))")

    volume = breaker.ProposedWorkflowUsageVolume(
        total_minutes=sum(e.total_minutes for e in events),
        minutes_by_workflow={},
    )
    for e in events:
        volume.minutes_by_workflow[e.workflow_name] = volume.minutes_by_workflow.get(e.workflow_name, 0.0) + e.total_minutes

    cost_verdict = breaker.check_cost_budget(volume, budgets=budgets, period_days=args.period_days)
    say(f"Cost check: {'ALERT' if not cost_verdict.allowed else 'OK'} -- {cost_verdict.reason} "
        f"(anomaly: {cost_verdict.anomaly_status})")
    for v in cost_verdict.static_cap_violations:
        say(f"  - {v}", detail=True)

    window_days = budgets.get("ci_health_window_days", 14)
    by_design = budgets.get("ci_health_by_design_failing_steps", {}) or {}
    tripped_ci_health: "list[breaker.CIHealthVerdict]" = []
    for target in args.ci_health_workflows:
        repo, wf = parse_ci_health_target(target, args.repo)
        steps_for_wf = tuple(by_design.get(wf, ()))
        raw = fetch_recent_runs(repo, wf, runner=runner)
        conclusions, stats = effective_conclusions(
            raw, now=now, window_days=window_days, by_design_steps=steps_for_wf,
            failed_steps_fn=lambda run_id, _r=repo: fetch_failed_step_names(_r, run_id, runner=runner),
        )
        verdict = breaker.check_ci_health(f"{repo}:{wf}" if repo != args.repo else wf, conclusions, budgets=budgets)
        note = (f" [window {window_days}d: {stats['in_window']} run(s), {stats['outside_window']} older ignored"
                + (f", {stats['by_design']} failed only by design" if stats["by_design"] else "")
                + (f", {stats['unverifiable']} unverifiable kept as failure" if stats["unverifiable"] else "") + "]")
        say(f"CI-health check ({target}): {verdict.reason}{note}", detail=True)
        if verdict.tripped:
            tripped_ci_health.append(verdict)
    if args.redact and args.ci_health_workflows:
        print(f"CI-health: {len(args.ci_health_workflows)} workflow(s) checked, {len(tripped_ci_health)} tripped")

    any_tripped = (not cost_verdict.allowed) or bool(tripped_ci_health)

    rate_after = rate_limit_remaining(runner=runner)
    if rate_before is not None and rate_after is not None:
        say(f"gh core rate limit: {rate_before} -> {rate_after} remaining ({rate_before - rate_after} call(s) used by this run)")

    if args.live:
        breaker.record_period(volume.total_minutes, period_days=args.period_days)
        if not cost_verdict.allowed:
            body = (
                f"## GHA Cost Alert — {period_start} to {period_end}\n\n"
                f"{cost_verdict.reason}\n\n"
                + "\n".join(f"- {v}" for v in cost_verdict.static_cap_violations)
                + f"\n\nAnomaly check: {cost_verdict.anomaly_status}\n\n"
                "The static caps are PROVISIONAL (set against the pre-migration baseline; see "
                "scripts/pipeline/config/workflow_cost_budgets.yaml). "
                "This is an alert only -- nothing has been disabled or changed automatically. "
                "A human should review whether this is expected growth or a real regression."
            )
            open_alert_issue(alert_repo, f"GHA cost alert — {period_start}", body, "gha-cost-alert", runner=runner)
        for v in tripped_ci_health:
            body = f"## CI-Health Alert\n\n{v.reason}\n\nAlert only -- nothing has been disabled automatically."
            open_alert_issue(alert_repo, f"CI-health alert — {v.reason.split(':')[0]}", body, "gha-ci-health-alert", runner=runner)
    else:
        say("(dry-run: not recording period to circuit-breaker history, not opening any issue -- pass --live to do both)")

    if args.details_file:
        with open(args.details_file, "w", encoding="utf-8") as fh:
            fh.write("\n".join(details) + "\n")

    return 1 if any_tripped else 0


if __name__ == "__main__":
    sys.exit(main())

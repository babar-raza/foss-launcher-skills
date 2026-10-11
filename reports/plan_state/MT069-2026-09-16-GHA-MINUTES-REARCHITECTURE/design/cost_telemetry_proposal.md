# Recurring Cost Telemetry + Circuit Breaker Proposal

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Taskcard:** MT069-TC-13-RECURRING-COST-TELEMETRY-PROPOSAL
**Date:** 2026-09-17
**Status:** Design/proposal only — no telemetry code built or deployed by this taskcard.

## Why this is the actual root-cause fix, not a nice-to-have

Root causes #1 and #2 identified in the governing plan's "Root-cause analysis" section:
zero recurring cost observability exists anywhere in this repo, and no cost/blast-radius
circuit breaker was ever extended to CI (despite the identical *pattern* already working
for content operations). This capability closes both — and has value independent of how
many workflows this mission ultimately migrates or self-hosts.

**Extended scope (2026-09-17, post-`TC-05`)**: this capability should also watch CI-check
*health*, not just cost. `TC-05`'s failure investigation found `skill-governance.yml` had
been failing 100% of the time on a false positive for 12 days (40+ runs) before anyone
looked — the same "nobody's watching until a human happens to notice" pattern as the
cost problem itself. A required check failing continuously for N consecutive days/runs
is exactly the kind of anomaly the same alert infrastructure can detect without building
a second, separate system.

## Design

- **Telemetry skeleton**: reuse the generic event → validated ledger → aggregate →
  gated-submit mechanics already proven in
  `scripts/pipeline/commands/ops/metrics_event_ledger.py` / `run_metrics.py` /
  `metrics_submitter.py` (dry-run by default, secrets never logged, endpoint/token via
  env vars only). **Do not reuse `MetricsRow` itself** — it is LLM-call-specific (17
  fixed fields tied to the Aspose product/platform taxonomy). Define a new
  `WorkflowUsageEvent`/`WorkflowUsageRow` and taxonomy, mirroring the mechanics, not the
  schema.
- **Collector**: a small, read+report-only scheduled job (itself a clean public-migration
  candidate) that runs weekly, reconstructs proxy minutes via the same method `TC-04`
  used, and appends a durable local snapshot + trend. Baseline to reproduce:
  `usage/usage_dataset.json` (1,494 min, 561 job runs, 2026-09-01 through 2026-09-18).
- **Circuit breaker**: a magnitude-cap trigger, **not** a failure-count trigger — the
  repo's one prior circuit-breaker precedent
  (`scripts/translator/backends/circuit_state.py`) used failure-count and was deleted
  along with the whole in-house translator package; it is also the wrong trigger type
  for a cost problem. Model this instead on the *live* pattern in
  `scripts/pipeline/lib/install_change_budget.py` / `publish_watcher.py
  --max-auto-apply`: a static cap plus a rolling-baseline anomaly check.
- **CI-health extension**: a required check with a failure-rate above a threshold (e.g.
  >90%) sustained for more than N runs/days triggers the same alert path — this is what
  would have caught the platform-capabilities bug (`TC-14`) automatically after a day or
  two instead of 12.
- **Action when tripped: alert, never auto-disable.** Auto-disabling was the blunt
  instrument that caused this mission to exist. Reuse the existing
  `aspose-com-targets-watch.yml` issue-creation pattern.

## Optional, lower-priority: check-layer parity audit

Generalize `check_workflow_drift.py`'s existing 3-way-comparison pattern to a new
domain: for every blocking check invoked from a push-triggered (not PR-gated) workflow,
verify it also appears in `scripts/pre-commit-audit.sh` and/or
`scripts/ci/hooks/simulate_pr_checks.sh`; flag any that don't. This would have caught
`TC-15`'s evaluator-version-bump gap automatically. Flagged as genuinely additional
scope, not required to close this taskcard.

## Disposition — see the new gap-escalation report

This slice is re-filed as `recurring-candidate` (not `bounded-oneoff`) — see
`reports/skill-gaps/2026-09-17-gha-cost-and-ci-health-telemetry.md` and the updated
`reports/skill-gaps/index.yaml` entry.

## What this taskcard does NOT do

- No `WorkflowUsageEvent`/`WorkflowUsageRow` code is written.
- No collector job is scheduled or deployed.
- No circuit breaker is implemented.

This is `MT069-PHB-03`'s design input for eventual Phase B execution, once separately
authorized (or once a proposed skill is built, per the gap report's disposition).

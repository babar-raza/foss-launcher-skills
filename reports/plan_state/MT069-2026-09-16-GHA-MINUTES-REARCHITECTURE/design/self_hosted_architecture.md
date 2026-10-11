# Self-Hosted Runner Architecture Design

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Taskcard:** MT069-TC-08-SELF-HOSTED-ARCHITECTURE-DESIGN
**Date:** 2026-09-17
**Status:** Design only — no runner registered or brought online by this taskcard.

## Named targets

- `content-governance-checks.yml` (full workflow) — confirmed #1 real cost driver (546
  of 1,494 minutes, 36.5%, per the 2026-09-18 usage export).
- `skill-governance.yml`'s required `enforce-venv-python` job (Linux) — confirmed #3
  cost driver (326 min combined / 21.8%). The soft-launched `governance-tests-windows`
  job is a separate, deferred decision (see below).

## Why self-hosting is the only lever for these two, not one option among several

Both gate `push(main)` and need native integration with this exact private repo's
commits, which a workflow running in another repo cannot provide (confirmed: this
private repo cannot enable branch protection at its current plan tier, so neither
workflow is a GitHub-enforced "required check" in the strict sense — but they still
need to fire on THIS repo's own push events with immediate feedback, which only a
native or self-hosted execution context can do without introducing polling latency;
see the "open architectural question" note in `analysis/destination_decision_matrix.json`
for the not-fully-evaluated polling-based public alternative). Self-hosting is
therefore the only path to zero marginal Actions cost, short of retiring the checks
(not proposed — both are `P0_CRITICAL` per `analysis/importance_matrix.json`).

**Residual risk is lower than the general self-hosted case**: this repo's real
production flow is direct push, not PR-from-fork (confirmed in `TC-01`/`TC-03`), so the
usual "never run untrusted PR code on a persistent self-hosted runner" hazard does not
apply here. The residual risk is operational (a hung/runaway job competing with the
maintainer's interactive session), not code-injection.

**Confirmed viable by the user (2026-09-16)** on this same Windows 11 Pro dev machine.

## Architecture

WSL2-hosted runner, persistent listener with a fresh Docker container per job, on this
Windows 11 Pro dev machine, routed via a dedicated label (`runs-on: [self-hosted,
wsl2-linux, gha-private-native]`) so only these two workflows use it. Never the
schedule bots — this machine isn't reliably on at 09:00-11:00 UTC daily regardless of
the maintainer's presence, an independent, non-cost argument for keeping those on
GitHub-hosted or public execution.

**Open item, not yet confirmed (flagged by TC-11 independent review, 2026-09-17)**:
Docker Desktop's per-seat licensing terms may apply to this usage depending on the
organization's size and how the daemon is invoked from WSL2 — this was not checked
during this design pass. LOW confidence this is actually a blocker (a rootless/Docker
Engine-only WSL2 setup without Docker Desktop likely sidesteps it entirely), but it
should be confirmed — or the Docker Desktop dependency swapped for plain `dockerd`/
`containerd` in WSL2 — before `PHB-07` provisions the real runner, not assumed away.

**Precondition, not optional**: land the concurrency/cancel-in-progress guard on
`content-governance-checks.yml` before cutover, not after. **Correction (TC-11
independent review, 2026-09-17)**: this line previously said "done — `TC-14`/`TC-15`
work already added this," which was wrong on both counts — the guard was actually added
via `/workflow-harden` (S-115) under `TC-03` (`TC-14`/`TC-15` fixed unrelated CI-checker
defects), and `git status --porcelain` confirms it is still **uncommitted**, not "done."
This precondition is therefore still open, not satisfied — must be committed before
`PHB-07` cutover. A single self-hosted machine has no elastic parallelism the way
GitHub-hosted runners do — back-to-back pushes without a concurrency guard would stack
real builds on one physical machine.

## `skill-governance.yml`'s Windows job — still an open, deferred decision

Real usage data reversed an earlier assumption: the Windows job costs *more* (223 min)
than the required Linux job (103 min), not less. Two options, cheapest first:
1. **Try first, independent of self-hosting**: since this job is `continue-on-error:
   true` (non-blocking, soft-launched), evaluate via `/workflow-harden` whether it needs
   to run on every matching push at all, or whether demoting it to a daily
   schedule/`workflow_dispatch` captures most of its coverage value at a fraction of the
   cost. Not yet evaluated — a candidate for a future taskcard, not this one.
2. If it must stay push-triggered, self-host it too, inside its own isolated,
   hard-timeout container — mechanically simpler than the Linux case (host is already
   Windows) but gives up GitHub-hosted Windows runners' one real advantage (VM
   disposability) for this specific job.

## Runner lifecycle (closes the "narrative-only design" structural weakness)

```
PROVISIONED → REGISTERED → HEALTHY ⟷ DEGRADED → DECOMMISSIONED
```

- **Health check**: a heartbeat (rides the telemetry mechanism from `TC-13`) confirming
  the runner is alive and has processed a job within an expected window.
- **`DEGRADED`** (no heartbeat within N hours) triggers an alert, never a silent
  fallback — GitHub's own behavior when a self-hosted runner is offline is to queue the
  job indefinitely, which for a push-gated check looks like a hung commit status. This
  design must surface that quickly, not let a human discover it cold.
- **Decommission** is an explicit verb including workspace/secret cleanup, matching the
  "never stuck ACTIVE for any reason" philosophy this repo already uses for
  `refresh_run.py`'s own `abandon` verb (see the Phase B state-machine design for the
  precedent this borrows from).

## Safety notes carried from the concurrency-fix work

**Correction (TC-11 independent review, 2026-09-17)**: this section's title and body
previously said the concurrency guards were "already done"/"landed," attributed to
"`TC-14`/`TC-15` work." Both corrected: the guards on `content-governance-checks.yml` and
`skill-governance.yml` were added via `/workflow-harden` (S-115) under `TC-03` (`git
diff`-confirmed purely additive, 4 lines each, no gate weakened) — `TC-14`/`TC-15` fixed
two unrelated CI-checker defects (platform-capabilities comparison bug and the
evaluator-version-bump pre-commit gap), not this. And `git status --porcelain` confirms
these edits are still **uncommitted** working-tree changes, not landed. They remain a
direct precondition for this design, not a separate concern — without them, self-hosting
would compound the single-machine resource-contention risk this design already flags —
but that precondition is currently open, not satisfied, and must be committed before any
`PHB-07` cutover.

## What this taskcard does NOT do

- No runner is provisioned or registered.
- No workflow's `runs-on:` is changed.
- No workflow is re-enabled or dispatched (Hard Constraint, unchanged).

This is `MT069-PHB-07`'s design input for eventual Phase B execution, once separately
authorized per-workflow.

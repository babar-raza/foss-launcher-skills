# Mission Plan: GitHub Actions Audit, Re-Architecture, Migration & Stabilization — `aspose.org`

> Reorganized 2026-09-17 for coherence (content preserved, structure and dedup rewritten
> — see the note at the end of this header). Original scattered/duplicated version is in
> git-free local history only; this file is the single current source of truth.

## Status (as of 2026-09-18)

- **Master task-list authorization executed end-to-end (2026-09-18)**: the user gave
  a comprehensive, itemized go-ahead covering every remaining category of open work.
  Summary of outcomes (each item's own detailed entry is elsewhere in this log):
  1. All uncommitted work committed (12 commits this session: 3 PHB-05/PHB-06 doc
     corrections/fixes, PHB-03 telemetry, the llms-generation.yml scoped-regen fix,
     the repo_patrol.py auto-clone fix, AGENTS.md, seo-keyword-refresh.yml, the
     self-hosted-runner wiring).
  2. Time-dependent items (PHB-05 canary observation, PHB-08 final comparison)
     tracked in `backlog/REMINDERS.md` (R-07/R-08) and `backlog/inbox.md` (ST-200/201)
     — not re-litigated here, still genuinely time-gated.
  3. PHB-03 (cost/CI-health telemetry) executed fully: built, tested (54 tests),
     live dry-run smoke-tested against the real private repo, committed. It
     correctly surfaced both real defects below independently of how they were found.
  4. `launch-dashboard.yml` and `ci-eval-consistency.yml` deep-dive review: already
     complete as of the prior day's entries in this log (split migration + the
     two-pass launch-dashboard.yml correction) — no further engineering needed.
     `llms-generation.yml` got a second, deeper pass this session (see below) and its
     fix is now committed.
  5. `upstream-monitor.yml`'s "issue #94 PAT gap" corrected — see the entry directly
     below. This was the "needs a human token" item; the real answer is no token was
     ever needed, reported honestly rather than force-fitted to the user's premise.
     Issue #94 closed on GitHub with the corrected root cause. The genuinely-new fix
     (`repo_patrol.py`'s `cmd_sweep()` auto-clone self-heal) was proven live twice:
     once via a local empty-cache-dir + real network clone, and once via a real
     GitHub Actions dispatch of the public `upstream-monitor.yml`
     (run `35321867511`, `fetch_failures: 0` vs. `33/33` before the fix).
  6. `AGENTS.md` §9a's dead link fixed via `override_manager.py` (token
     `20260918-075342-AGENTS-md`, consumed against commit `b4e819fb9e`) — the two
     stale `docs/workflows/evaluator-changes.md` references now point at the real
     replacement, `docs/development/evaluator-changes.md`.
  7. PRs #99, #100, #103 independently reviewed as three separate cases and merged
     after verification: #99's PyPI version claim (`aspose-note` 26.3.2) confirmed
     live against the real PyPI API; #100 confirmed purely additive audit-report
     data; #103 initially contained a real destructive regression (would have
     replaced 250 lines of real per-product freshness data with `{}`, a direct
     symptom of the pre-fix `fetch_failures: 33/33` bug) — not merged as-is; instead,
     the underlying bug was fixed first, then the public workflow was re-dispatched
     live, which updated PR #103 in place with correct data before merging it.
  8. `seo-keyword-refresh.yml` investigated per explicit instruction not to ignore a
     pre-existing finding just because this mission didn't cause it — see its own
     entry below. Real finding: the drift ran backwards from the usual case (the
     deployed copy had an incident-tested credential fix never backported locally).
  9. Self-hosted runner wired to `content-governance-checks.yml` and
     `skill-governance.yml`'s required Linux job. Found and fixed a real,
     load-bearing gap while doing this: the runner already running on this dev
     machine was registered against the wrong repo (`Aspose/aspose.org-workflows`,
     public) and could never have served either job — see its own entry below.
     `skill-governance.yml`'s soft-launched Windows job is intentionally NOT
     self-hosted yet (a separate, not-yet-decided item per this plan's own design —
     try trigger-demotion first).
  - **What remains genuinely open, not executed today**: the new private-repo
    runner (`alienware-m18-wsl2-private`) is running via `nohup ./run.sh &`, not yet
    a systemd service — that step needs the same interactive `sudo ./svc.sh
    install/start` the user ran for the first runner (PHB-07, 2026-09-17). End-to-end
    proof that a real job executes on it is necessarily deferred to a future,
    explicit human-approved re-enable of one or both target workflows — the standing
    hard constraint prohibits dispatching them to test this now.
- **Self-hosted runner registration mismatch found and fixed (2026-09-18)**: the
  runner already registered on this dev machine (`alienware-m18-wsl2-test`,
  directory `~/actions-runner-aspose-org-workflows`) turned out to be registered
  against `Aspose/aspose.org-workflows` (the PUBLIC repo) via its own `.runner`
  config file's `gitHubUrl`, not `Aspose/aspose.org` (the private repo both
  `content-governance-checks.yml` and `skill-governance.yml` live in and require).
  This means the self-hosted design's actual goal — zero marginal cost for these two
  specific private-repo required checks — could never have been reached by wiring
  `runs-on:` alone, no matter how that field was set, since a runner registered to
  one repo cannot service another repo's queued jobs. **Why:** likely conflated
  during PHB-07's original setup with the earlier proven-out public-repo migration
  work happening in the same session. **Fix:** registered a second, correctly-scoped
  runner (`alienware-m18-wsl2-private`, label `gha-private-native`, reusing the
  cached runner tarball) directly against `Aspose/aspose.org`, confirmed
  `status: online` via the real Actions API. **Standing rule**: before trusting any
  self-hosted-runner design document's claim about which repo a runner serves,
  verify it directly against the runner's own `.runner` config file or the
  `GET /repos/{owner}/{repo}/actions/runners` API — a plausible directory name is not
  proof of correct registration.
- **CORRECTION (2026-09-18): `upstream-monitor.yml`'s "issue #94 PAT gap" was a
  months-old misdiagnosis, not a real credential problem.** Every prior record in
  this mission — this plan's own earlier entries below, both `upstream-monitor.yml`
  copies' header comments (private and the public `aspose.org-workflows` template),
  `dossiers/upstream-monitor.md`, `analysis/failure_signatures.json`,
  `analysis/destination_decision_matrix.json`, and
  `phase_b/migrations/pr-gated-watcher-bots.json` — asserted the "Sweep drifted
  products" step's 100% `fetch_failures` meant `secrets.GITHUB_TOKEN` 403s against
  the `aspose-*-foss` orgs, requiring a human-provisioned PAT (framed as genuinely
  outside agent authority). Investigating the user's "try `GH_PAT`/`GITHUB_TOKEN`/
  other GitHub system vars, one should work" instruction directly disproved this:
  an anonymous-request control test showed the orgs are fully public (any request,
  authenticated or not, returns 200 — the earlier "token works" signal was a false
  positive), which led to reading `repo_patrol.py`'s actual `cmd_sweep()` source
  instead of trusting the prior write-up. Found: `clone_exists()` is a pure
  filesystem check against `runs/.clone_cache/`, gitignored and therefore never
  present on any fresh checkout — every product failed with "no local clone
  exists" before any git/API call was ever attempted, regardless of any token.
  Confirmed via a live repro (empty cache dir → `clone_exists()` returns `False`
  unconditionally) and fixed by wiring the pre-existing `ensure_clone()` (a plain
  unauthenticated `git clone` of the public FOSS mirror) into `cmd_sweep()` as a
  self-heal, with 2 new DI-seam-based tests plus a live end-to-end network-clone
  proof (commit `72821fbb4a`, mission `MISSION_AUTHORITY` re-verified unaffected).
  **No PAT, secret, or token of any kind was needed** — the user's premise that
  "one of `GH_PAT`/`GITHUB_TOKEN`/etc. has proper access" does not apply here,
  since the real blocker was never a permissions problem. Issue #94 should be
  closed as a misdiagnosis. Both workflow files' header comments and this plan
  file are corrected; the gitignored `reports/plan_state/` analysis files
  (dossier, failure-signatures, destination-decision-matrix, PHB-06 migration
  record) are corrected in place as local-only documentation, not re-committed
  (they were never tracked in git to begin with).
- **`ci-eval-consistency.yml` split migration complete (2026-09-18)**: its
  `onboarding-integrity` job's schedule leg (the `consistency` job's own schedule leg
  was already dead weight, correctly no-op'd via its own `if:` guard) migrated to
  `Aspose/aspose.org-workflows` as `ci-onboarding-integrity-weekly.yml`, proven live
  (green run, checks AGENTS.md/CLAUDE.md/etc. — all git-tracked, no data-availability
  concerns). Offset to Monday 06:15 UTC to avoid the exact collision this plan had
  already flagged with `seo-analysis.yml`'s own Monday 06:00 UTC schedule. Private
  original's schedule trigger removed (push/PR legs unchanged).
- **`launch-dashboard.yml`: a real defect found, a wrong self-correction caught and
  fixed the same day (2026-09-18)** — worth recording both passes, not just the final
  answer. Yesterday's HP-11 "missing pip install" theory was disproved by reading the
  script's actual imports (none) and running it in a bare local venv (worked). That
  first correction concluded the workflow was healthy and reclassified it
  `SPLIT_BETWEEN_PRIVATE_AND_PUBLIC`. **That conclusion was itself wrong** — the local
  test used this session's own working directory, which has locally-accumulated report
  files a real CI checkout never has. Actually migrating the schedule leg and
  dispatching it for real on a fresh checkout produced `NO REPORT: 33/33, Gaps: 99`, not
  the 2-gap result the local test showed. Real root cause: `launch_dashboard.py`'s
  inputs (`reports/phase_state.json`, `reports/human-review/**`,
  `reports/**/readiness.md`) are gitignored, cumulative local state built up over time
  by `project_phase_store.py` — never available in any fresh checkout, public or
  private, self-hosted or GitHub-hosted. Not a hosting-location problem; no migration
  destination fixes it. Reverted the public schedule leg to `workflow_dispatch`-only
  the same day (commit `6e6085f`) rather than leave it running and misleading. 3 of the
  private original's own 5 push-trigger paths are also structurally dead for the same
  gitignore reason (a real, previously-uncaught, second defect). Reclassified back to
  `REQUIRES_REDESIGN`, this time for the correct, verified reason — the actual fix
  (rebuild from git-tracked data, or retire as a CI job) is not scoped here. Full
  two-pass history: `dossiers/launch-dashboard.md`.
- **Phase B execution, third pass (2026-09-17)**: `PHB-07` reached
  `IMPLEMENTED` for real — the user completed the `sudo ./svc.sh install/start`
  step interactively; the runner is now a genuine systemd service (survives
  reboot). One real conflict surfaced and was fixed: this session's earlier
  manual `nohup ./run.sh &` process was still holding the runner's listener
  session, blocking the new service from connecting cleanly — killed, service
  now holds the session alone, confirmed via `gh api .../actions/runners`
  (`online`) and `systemctl is-active` (`active`), neither needing sudo.
  **`PHB-06` reached `IMPLEMENTED`**: the 4 remaining auto-commit watcher bots
  (`upstream-monitor.yml`, `maven-publish-watcher.yml`,
  `install-literal-sweep.yml`, `package-publish-watch.yml`) were migrated and
  converted from direct-commit to PR-gated (`peter-evans/create-pull-request@v6`,
  per explicit user decision), all proven live: 3 real PRs opened on the
  private repo (#99, #100, #103) plus 2 deduped issues (#101, #102), none
  merged (human-authority boundary respected). `upstream-monitor.yml`'s
  separate defect (issue #94, believed at the time to be a PAT gap — **CORRECTED
  2026-09-18, see entry above: it was a missing-clone-cache bug, not a credential
  problem, now fixed**) was confirmed to reproduce identically after migration
  (`fetch_failures: 33/33`) — migration neither fixed nor worsened it, exactly as
  expected (both are true regardless of which root cause is correct). 2 partial-split candidates
  (`ci-eval-consistency.yml`, `launch-dashboard.yml`) were unmigrated as of
  this entry — **both now resolved 2026-09-18, one migrated successfully,
  one found to be un-migratable for a real structural reason — see the status
  entries above this one.** Full detail:
  `phase_b/migrations/pr-gated-watcher-bots.json`,
  `phase_b/PHB-07_self_hosted_runner_status.md`.
- **Phase B execution, second pass (2026-09-17)**: two more clean-tier workflows
  migrated live and proven end-to-end: `backlink-compliance-watch.yml` (commit
  `4e4d883`) and `seo-analysis.yml` → renamed `seo-weekly-analysis.yml` on the public
  side (commit `9142da5`, collision-avoiding rename). The latter's real dispatch hit
  the analysis script's own findings-gate (26 new duplicate-title groups — a real,
  pre-existing content backlog, not a migration defect) and correctly routed the
  resulting issue to the private `Aspose/aspose.org` repo (issue #98), proving the
  failure-routing path works, not just the clean-pass path. **Self-hosted runner
  (PHB-07) machinery proven live**: fixed a real Docker-Desktop/WSL2 integration gap
  on the dev machine (permanently resolves the previously-flagged Docker Desktop
  licensing question — the runner uses the same Docker Desktop instance already in
  normal use here, not a new install), registered a runner against the public
  `aspose.org-workflows` repo (per the explicit instruction never against the
  private repo), and proved a real per-job Docker container executing a dispatched
  job end-to-end. **Genuinely incomplete, not just deferred**: the runner is running
  via a manual foreground process, not a systemd service — completing that needs one
  `sudo` command only the user can run interactively (exact commands in
  `phase_b/PHB-07_self_hosted_runner_status.md`). The 4 auto-commit watcher bots
  (`upstream-monitor.yml`, `maven-publish-watcher.yml`, `install-literal-sweep.yml`,
  `package-publish-watch.yml`) still need PR-gated conversion before migrating — user
  decided (2026-09-17) to convert them to PR-gated rather than keep auto-commit or
  skip; not yet executed. `PHB-06`/`PHB-07` both `IN_PROGRESS`, honestly not
  `IMPLEMENTED` — real work remains in both.
- **Phase B execution started (2026-09-17)**: user explicitly authorized real execution
  ("execute phase B... everything else can be enabled including the workflows on
  aspose.org-workflows and self hosted runners for testing"), with the hard constraint
  (never enable/dispatch any of the 20 private workflows) re-confirmed and unchanged.
  `PHB-01`/`PHB-02` delivered as a **lightweight** per-migration JSON state/reconciliation
  record instead of the full 9-state CLI the Phase A design sketched (the plan itself
  flagged this exact tradeoff as a scale-appropriate default for 11 one-time migrations —
  see `phase_b/PHB-01-02_lightweight_decision.md`). `PHB-04` (machinery proof) and the
  first real slice of `PHB-05` (canary migration) are complete:
  `aspose-com-targets-watch.yml` is now live on `Aspose/aspose.org-workflows`
  (commit `a00a2265`), proven end-to-end via a real dispatched run (checked out the
  private `Aspose/aspose.org` repo, ran its real checks against live data, completed
  green), and the private original's trigger was flipped to `workflow_dispatch`-only
  (not deleted — pure rollback-preserving edit, no enable/disable API called). `PHB-05`
  stays `IN_PROGRESS`, not `IMPLEMENTED` — its own spec requires observing 5-7 real daily
  cycles before `STABILIZED`, which needs the passage of time, not more work today. Full
  detail: `reports/plan_state/.../phase_b/migrations/aspose-com-targets-watch.json`.
  A real, unrelated pre-existing drift finding (`seo-keyword-refresh.yml`, local template
  stale vs. deployed) was surfaced by extending `check_workflow_drift.py` and is flagged,
  not fixed, in that same record. Per the standing per-taskcard stop-gate, execution
  paused here — `PHB-06` (remaining migrations) and `PHB-07` (self-hosted runner) await
  the user's next explicit go-ahead.
- **Mission**: `MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE` — registered, `OPEN`, Phase A
  in progress. Root `MISSION_AUTHORITY.yaml` is bound to it (override token
  `20260916-162212-MISSION_AUTHORITY-yaml`, still **pending** — consumed at the TC-12
  commit, not before). Narrative file: `plans/missions/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE.md`.
  Indexed in `plans/master-plan.md`.
- **Taskcards**: 15 Phase A + 8 Phase B (`PHB-01..08`, authorized 2026-09-18, see below)
  in `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/taskcards.jsonl`.
  `TC-01` through `TC-11`, `TC-13` through `TC-15` = `IMPLEMENTED` (all 20 per-workflow
  dossiers complete; independent review complete with corrections applied — see below).
  Only `TC-12` (closeout) remains in Phase A.
  `PHB-01` is now unblocked (dependency `TC-10` closed); the rest of Phase B still waits
  on the user's per-taskcard go-ahead, per the standing stop-gate protocol.
- **`TC-11` independent review complete (2026-09-17)**: a fresh, context-free Agent
  adversarially re-verified `TC-01`-`TC-10`'s deliverables against live ground truth
  (`git`/`gh api`, direct file reads) rather than trusting their self-description. It
  found 6 real issues; the primary session independently re-verified each before
  correcting anything, found 1 more (invalid JSON in `destination_decision_matrix.json`)
  along the way, and fixed all 7 — including a genuine fail-open code defect in `TC-15`'s
  new pre-commit gate (now fixed, tested, and validated against the full suite). Full
  detail, every correction, and what was checked and found solid:
  `reports/plan_state/.../review/independent_review.md`. **Two corrections materially
  change prior conclusions, not just wording**: the concurrency-guard fixes for the top-3
  workflows are real but were wrongly described as "landed" — they remain uncommitted,
  a real open precondition for `PHB-07`; and `llms-generation.yml`'s destination changed
  from `INSUFFICIENT_EVIDENCE` to `REQUIRES_REDESIGN` now that the duplication question
  is resolved (partially duplicated, not fully — its fail-fast gate value is real and
  not replicated by the public deploy repo).
- **A second gap-escalation report filed (2026-09-17)**: `TC-13` concluded recurring
  cost/CI-health telemetry is genuinely needed (not just bounded-oneoff) —
  `reports/skill-gaps/2026-09-17-gha-cost-and-ci-health-telemetry.md`, disposition
  `recurring-candidate`. Design-only; no skill built, no code deployed.
- **CI defect remediation closed (2026-09-17)**: both real defects found by `TC-05`
  are fixed and verified — the platform-capabilities checker bug (`TC-14`, 12/12
  targeted tests) and the evaluator-version-bump shift-left (`TC-15`, 8/8 tests
  including 2 added same-day for a fail-open gap the `TC-11` independent review found
  and this session fixed — see below). Full `scripts/ci/tests/` suite: 1,113 passed, 1
  skipped, 1,114 collected (corrected from an earlier, wrong "1594"/"1102" figure — see
  `TC-11`'s review for the correction). One item remains a human action, not
  agent-executable: `AGENTS.md` §9a's dead link (that file is human-maintainer-authored
  only). Full detail: "CI defect remediation" section below and
  `reports/plan_state/.../ci_defect_remediation/`.
- **Major finding from Section A3 (2026-09-17)**: real run-history data (172 days
  retained, not a limited window) revealed the top-3 cost drivers also have serious,
  previously-unknown failure rates — `skill-governance.yml` failed 100% of its September
  runs, `content-governance-checks.yml` 49%. Both root-caused to real, specific issues
  (a content-pipeline registry gap; a recurring evaluator-version-bump discipline gap) —
  neither is a CI/workflow defect, and self-hosting does not fix or worsen either.
  `upstream-monitor.yml` is confirmed 93% broken from a cause `TC-03` already found
  (HP-05, believed at the time to be a PAT gap — **CORRECTED 2026-09-18, see Status
  entry above: a missing-clone-cache bug, now fixed, needed no credential at all**)
  — reclassified `REQUIRES_REDESIGN` rather than assigned a
  migration destination at the time, since relocating a broken workflow doesn't fix it
  (though it was migrated anyway in `PHB-06`, with the defect confirmed unchanged, once
  the "auto-commit to PR-gated" redesign gave it a real reason to move regardless).
  **`launch-dashboard.yml`'s matching HP-11 diagnosis was corrected 2026-09-18**: the
  "missing pip install" theory was never actually verified against the script's real
  imports (this plan's own `TC-05`/HP-11 write-up said so at the time). Verified live:
  zero third-party dependencies, runs successfully in a genuinely bare venv — the 100%
  exit-1 rate is the script correctly reporting 2 real, still-open coverage gaps, not a
  crash. Reclassified `SPLIT_BETWEEN_PRIVATE_AND_PUBLIC` (its originally-intended
  category, unblocked). Also discovered: this repo's private-repo branch
  protection is unavailable at its current plan tier, meaning no workflow here is a
  GitHub-enforced "required check" — softening (not eliminating) the self-hosting
  rationale for `content-governance-checks.yml`/`skill-governance.yml`/`llms-generation.yml`;
  a polling-based public alternative is now a recorded, not-yet-evaluated option. Full
  detail: `reports/plan_state/.../analysis/failure_signatures.json`,
  `destination_decision_matrix.json`, `threat_assessment.md`.
- **Execution model (2026-09-18)**: section-by-section approval — the user approves a
  named section, the agent executes and verifies it, and work does not advance until the
  user confirms satisfaction. Applies to all remaining Phase A and Phase B taskcards.
- **Gap escalation**: filed 2026-09-16, `bounded-oneoff`
  (`reports/skill-gaps/2026-09-16-github-actions-minutes-rearchitecture-scope-gaps.md`),
  unblocking `TC-04`/`TC-07`/`TC-08`/`TC-09`. `TC-13` will file a **second**, separate
  gap report reclassifying the cost-telemetry slice as `recurring-candidate` — see
  "Design: recurring cost telemetry."
- **Scope of this document**: Phase A (investigation → execution-ready plan) in full,
  plus a Phase B production-execution *design* (final section) that is itself one of
  Phase A's deliverables — not an authorization to execute Phase B. Phase B start is a
  separate, explicit human decision (see "Human decisions").
- **Human decisions already resolved** (2026-09-16): the workflow mass-disable was
  intentional; the user will supply Billing UI figures directly rather than granting
  broader token scope; the self-hosted candidate machine is this same dev machine; the
  user chose to register the mission and start Phase A immediately. Full detail under
  "Human decisions" below — not repeated elsewhere in this document.
- **Real usage data received (2026-09-18)**: the user pulled the org's Actions usage
  metrics export, satisfying `TC-04` Phase 4b. Headline: top 3 workflows
  (`content-governance-checks.yml`, `llms-generation.yml`, `skill-governance.yml`) =
  75.7% of all Actions minutes; `llms-generation.yml` is a newly-surfaced major cost
  driver not previously flagged; `skill-governance.yml`'s Windows job costs more than its
  Linux job, reversing an earlier assumption. Full table and analysis under "Technical
  findings" below.
- **Phase B authorized (2026-09-18)**: the user explicitly authorized seeding Phase B's
  taskcards (`PHB-01` through `PHB-08`, see the end of this document) ahead of Phase A's
  own completion. **User-supervised execution**: a stop gate applies after every Phase B
  taskcard reaches a terminal/implemented state — the next one does not start without the
  user's explicit go-ahead. This does not change Phase A's own scope or gates.

## Context & mission framing

The user asked for a full audit of every GitHub Actions workflow in the private
`Aspose/aspose.org` repo, real usage/billing measurement, an individual evidence-backed
destination decision per workflow (stay private, self-host, move to the public
`Aspose/aspose.org-workflows` repo, consolidate, or retire), execution-ready taskcards,
and — in a later, separately-gated phase — controlled migration with proof the result is
cheaper, safer, and functionally equivalent.

This repo already has a governed skill (S-115 `workflow-harden`) for workflow hygiene and
an existing mission/taskcard system (`MISSION_AUTHORITY.yaml` + taskcard schema 5f) that
all multi-step plans must bind to rather than inventing new tracking (AGENTS.md §17).
Investigation this session (repo inventory, live GitHub API/CLI recon, governance-
convention mapping, two design passes, and a targeted precedent search) surfaced findings
that changed the mission's shape from what the original brief assumed — most importantly,
that all 20 workflows were already disabled before this mission started, and that the
public `aspose.org-workflows` repo already proves part of the intended solution in
production.

**Registration already happened this session**: `mission_authority.py allocate --track
main --slug GHA-MINUTES-REARCHITECTURE` → `MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE` →
`activate` (succeeded without `--force`; the prior root incumbent, `MT068`, was
`mission_locked: false`) → root `MISSION_AUTHORITY.yaml` hand-edited under the override
token above → `open` archived the snapshot to
`reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/mission_authority.yaml` →
narrative and index files created. The full `in_scope_outcomes` / `out_of_scope_items` /
`mandatory_acceptance_criteria` / `human_authority_boundaries` contract lives in
`MISSION_AUTHORITY.yaml` itself — that is its authoritative location; it is not repeated
here.

## Critical findings

**All 20 workflows are currently `disabled_manually`, and this was intentional.** The
GitHub API (`gh workflow list --repo Aspose/aspose.org --all`) reports every file-defined
workflow disabled, despite several having successful runs as recent as 2026-09-14 (the
only `active` entry is GitHub's own synthetic Dependabot workflow). **The user confirmed
directly (2026-09-16) that they disabled all 20 themselves as an emergency cost
stopgap** — this is documented as the authoritative explanation at
`reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/inventory/disabled_vs_running_anomaly.md`
(TC-02, `IMPLEMENTED`), not treated as a live anomaly to forensically investigate. Two
consequences follow and apply throughout this plan:
- Every push(main) gate — `content-governance-checks.yml`, `skill-governance.yml`, etc.
  — is currently not enforcing anything. Restoring correct gating *without* restoring the
  cost is a co-equal deliverable of this mission.
- Live usage currently reads as ~zero for everything. Any cost baseline must come from
  historical (pre-2026-09-14) run data, not current state — this depends on this repo's
  Actions run-history retention window, checked as part of TC-04.

**MT066 is a real, ongoing overlap risk, not a blocker.**
`MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION` is open with taskcard
`PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX` at status `READY`, targeting a PR against
`Aspose/aspose.org-workflows`'s deploy-trigger logic — a different subsystem of the same
repo this mission also targets (the SEO templates, and eventually migrated workflows).
Two prior missions (MT062, MT066) already independently declared "any
`aspose.org-workflows` PR merge is a human-authority boundary" — this mission inherits
that norm. **Formal gate**: before any dossier (TC-10) finalizes a destination touching
`aspose.org-workflows`, re-run `mission_authority.py list` and check
`PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX`'s current status; record the check as one of
TC-09's `evidence_refs`. If genuinely unresolved, surface it — do not guess.

## Hard constraint: no workflow re-enablement or dispatch, ever

**No taskcard in this mission may call `gh workflow enable`, any `.../enable` API, or
`gh workflow run` (dispatch) against any of the 20 `Aspose/aspose.org` workflows, for any
reason, including verification or testing.** This is the single most important invariant
in this document and applies to everything below without exception.

This directly constrains `TC-03`'s delegation to `/workflow-harden`: S-115's own standard
verification protocol (`.agents/skills/workflow-harden/SKILL.md`, "POST-EXECUTION:
Evidence Bundle") includes a **Remote** step — `gh workflow run` + `gh run watch` for
`workflow_dispatch`-enabled workflows, or monitoring "the next natural run" for
push-triggered ones. Since every workflow is disabled, that step as written would either
fail outright or invite re-enabling one to make it work. **When `TC-03` invokes
`/workflow-harden`, it must scope that invocation to local-only verification (YAML parse
+ `actionlint`) and record real-run verification as `DEFERRED`** — the same legitimate
deferral pattern S-115 already uses in its own Phase 3 for things that are correctly not
a code change right now. Real-run verification of any fix (including the
`content-governance-checks.yml` concurrency guard, see below) happens only when a
workflow is deliberately, individually re-enabled as part of a human-approved Phase B
cutover.

Editing a workflow's trigger configuration is **not** the same as enabling it — flipping
a migrated workflow's trigger to `workflow_dispatch`-only (part of the public-migration
mechanism below) is a pure YAML edit and does not change GitHub's independent
enabled/disabled state. This mission never calls the enable/disable API in either
direction, in Phase A or in Phase B's canary step.

## Existing capabilities reused (do not reinvent)

- **S-115 `workflow-harden`** already owns static correctness/security/hygiene review of
  `.github/workflows/**` + `scripts/ci/**`, including a "CI weight" probe. It explicitly
  does **not** cover cost/billing measurement, self-hosted migration, or public-repo
  migration — one of its own Stop Conditions is to halt if a self-hosted runner is ever
  discovered. Ordinary workflow-file edits (timeouts, caching, the concurrency fix below)
  go through `/workflow-harden`, never ad hoc edits from this mission.
- **`Aspose/aspose.org-workflows` is already a working "Option B" precedent in
  production** — it is the actual Hugo build+deploy engine for every subdomain, and
  already hosts 5 SEO-pipeline workflow templates that check out `Aspose/aspose.org` via
  a scoped token, do work, and push results back via PR (never auto-commit). A drift
  checker (`scripts/ci/checks/check_workflow_drift.py`) keeps local templates
  (`scripts/seo/workflows/*.yml`) and deployed copies in sync. The public-migration
  design below reuses this exact pattern.
- **Mission/taskcard system**: `MISSION_AUTHORITY.yaml` (root, single mutable pointer,
  not a lock) → `mission_authority.py` → `plans/missions/<id>.md` +
  `reports/plan_state/<id>/{mission_authority.yaml,taskcards.jsonl}` +
  `plans/master-plan.md`. Taskcards created via `taskcard_cli.py --mission <id> seed
  --from-json <batch.json>`.

## Root-cause analysis

Treating the cost problem as a production incident rather than a one-off: the visible
**symptom** is that private-repo Actions minutes became a substantial share of the org's
allowance, and the only available response was disabling all 20 workflows. That symptom
has four distinct **root causes**, confirmed against the actual repo rather than assumed:

1. **Zero recurring cost observability exists anywhere in this repo.** A targeted search
   of `.github/workflows/`, `scripts/`, `docs/`, and `reports/` found no partial
   implementation, past attempt, or design doc for GH Actions usage/cost tracking. Nobody
   could see the trend forming — the crisis was invisible until the bill made it visible.
2. **No cost/blast-radius circuit breaker was ever extended to CI**, despite this exact
   *pattern* — a magnitude-cap guard, not a failure-count trigger — already existing and
   working in this repo for content operations (`scripts/pipeline/lib/install_change_budget.py`,
   `publish_watcher.py --max-auto-apply`: static caps + rolling-baseline anomaly check,
   excess recorded and reported, never silently dropped). Nothing analogous watches
   Actions minutes.
3. **No cost-impact gate exists at workflow-authoring time.** `/workflow-harden` reviews
   *existing* workflows for hygiene; nothing gates a *new* workflow, or a new job added to
   an existing one (like `skill-governance.yml`'s Windows job), for cost impact before it
   merges.
4. **The "disable everything" stopgap is itself a symptom, not a fix** — it was the only
   lever available because no graduated, automatic, intermediate control (per-workflow
   budget, concurrency enforcement, anomaly-triggered alert) existed between "normal
   operation" and "shut off all 20 at once."

Separately, the *original Phase A/B design* (before this reorganization) had three
**structural weaknesses** of its own — these would have caused real problems if executed
as first drafted, independent of the cost problem itself:

1. **No run-bound, resumable state machine for migration mechanics.** Copy-template /
   deploy / flip-trigger / watch-5-cycles has no defined behavior under interruption,
   retry, or a second session resuming weeks later — exactly the gap that caused real,
   named incidents elsewhere in this repo (see "Design: the migration-run state machine").
2. **"We pushed the template" was treated as sufficient evidence of success**, with no
   dedicated mechanism to verify the external outcome actually landed and stayed landed.
3. **No self-hosted runner lifecycle beyond a narrative recommendation** — no defined way
   to know the runner is healthy, detect it going offline, or safely decommission it.

These three are addressed by design, not patched with more prose — see the three design
sections below and the full Phase B section at the end of this document.

## Technical findings (evidence base)

**Workflow inventory**: 20 files in `.github/workflows/*.yml`, all GitHub-hosted, zero
matrix strategies, zero composite actions, zero `workflow_call` reusable workflows.
Full structured dataset: `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/inventory/workflows_inventory.json`
(TC-01, `IMPLEMENTED`). Two suspected largest cost drivers, both addressed in "Design:
the self-hosted runner track" below:
- `content-governance-checks.yml` — full Hugo build (~30 steps), **no
  concurrency/cancel-in-progress block**, against ~266 `content/` commits in the first 16
  days of September alone. The cheapest, highest-leverage fix available today,
  independent of any migration decision, is adding a concurrency guard via
  `/workflow-harden`.
- `skill-governance.yml` — its soft-launched `windows-latest` job runs the *same*
  ~50-entry broad path filter as the required Linux job, compounding the duplicate-OS
  cost.

Also of note: `content-audit.yml`'s PR trigger structurally never fires (dead weight,
T-00 undeletable, leave alone — not a cost lever); `example-verification-tests.yml` runs
its suite on both `ubuntu-latest` and `windows-latest` on every matching push (narrow
filter, likely small — check in TC-05 whether the Windows leg tests anything genuinely
OS-sensitive); the 4 auto-commit watcher bots (`upstream-monitor`,
`maven-publish-watcher`, `install-literal-sweep`, `package-publish-watch`) share a
near-identical checkout→venv→script→issue/commit shape and are a legitimate,
migration-independent consolidation candidate regardless of their eventual destination.

**Static review (S-115 `/workflow-harden`, executed 2026-09-17)**: full 8-dimension probe
of all 20 workflows, per `TC-03`. Evidence bundle:
`reports/sprint/workflow-harden-2026-09-17/` (verdict: `PARTIAL_EXECUTION` — remote
verification explicitly `DEFERRED` per the Hard Constraint above, since all 20 workflows
are deliberately disabled; local YAML-parse validation is clean). 14 findings total:

- **Fixed this sprint, but not yet committed**: concurrency/cancel-in-progress guards
  added to the 3 confirmed top cost drivers — `content-governance-checks.yml`,
  `llms-generation.yml`, `skill-governance.yml` (75.7% of total real usage combined).
  Each change is purely additive (4 lines, 0 deletions, confirmed via diff) — no gate
  weakened. This is the concurrency fix referenced throughout this plan. **Correction
  (TC-11 independent review, 2026-09-17)**: this line previously said the fix was "now
  landed, not just proposed" — that overstated it. `git status --porcelain` confirms all
  three files are still `M` (uncommitted working-tree edits) as of the review. The edits
  are real and correct, but not durable — they would be lost to a `git checkout --` or an
  unrelated session's conflicting edit until committed, and this is a real, open
  precondition for `PHB-07`'s self-hosted cutover, not a satisfied one.
- **New correctness finding, unrelated to cost**: `upstream-monitor.yml` has a step
  ("Sweep drifted products") with no `continue-on-error`, despite its own code comment
  (at the time) documenting it as *currently always failing* — believed then to be a
  PAT gap tracked as issue #94, **CORRECTED 2026-09-18: a missing-clone-cache bug,
  now fixed, see Status entry above**. If true, every downstream step in that job
  (snapshot persistence, bounded regeneration, commit, fail-the-job) never runs. This
  was deferred pending a human decision at the time —
  the correct fix depends on intent (mask the gap with `continue-on-error` vs. fix the
  underlying PAT, which is a secret-owner action this skill cannot take) and cannot be
  verified live since the workflow is disabled. Flagged for your attention separately
  from the cost-reduction thread.
- **Other deferred findings** (10 total, MEDIUM/LOW): zero SHA-pinned actions repo-wide
  (policy decision); 5 workflows with likely-dead PR triggers (need per-file confirmation
  before removing); an undocumented exact schedule collision (`seo-analysis.yml` /
  `launch-dashboard.yml`, both Monday 09:00 UTC); two more audit-step/regression-step
  unguarded-consumption patterns (`backlink-compliance-watch.yml`, and `content-audit.yml`
  — the latter moot since its trigger never fires); `launch-dashboard.yml` runs with no
  `pip install` step (works today, fragile assumption); minor caching/consistency gaps.
  Full detail: `reports/sprint/workflow-harden-2026-09-17/preflight/hidden_problems.json`.

**Usage/billing measurement**: the legacy `orgs/Aspose/settings/billing/actions` REST
endpoint is deprecated (HTTP 410); the org-level Actions-policy endpoint 403s (token
lacks `read:org`/`admin:org`). Three-tier plan:
1. Human pulls the org Billing UI export — fastest, needs no new token scope. **The user
   has chosen this option** (2026-09-16) rather than granting broader scope.
2. GitHub's newer Enhanced Billing Platform usage API
   (`GET /organizations/{org}/settings/billing/usage`) — plan-eligibility and required
   auth level are unverified, not assumed working.
3. Proxy reconstruction from `gh api .../actions/runs` + `.../jobs` durations — works
   today with the current token, ceiling each job to the next billing minute, applying
   the OS multiplier.

`TC-04` is explicitly **two-phase** so a missing human input never blocks downstream
work: Phase 4a (agent-doable now — check the retention window, build the tier-3 proxy
dataset from historical, pre-mass-disable data) is sufficient for `TC-05`/`TC-06`/`TC-07`'s
*relative* prioritization. Phase 4b (reconcile against the user's Billing UI figures) is
genuinely human-gated — the agent has no browser/credential access to view GitHub's
Billing settings as this specific user.

**Phase 4b received (2026-09-18)** — the user pulled the org's real "Actions usage
metrics" export (Insights → Actions usage metrics, period 2026-09-01 through 2026-09-18,
current month to date):

| Workflow | Minutes | Runs | Runner/OS | Share of total |
|---|---:|---:|---|---:|
| `content-governance-checks.yml` | 546 | 200 | linux | 36.5% |
| `llms-generation.yml` | 259 | 89 | linux | 17.3% |
| `skill-governance.yml` | 223 | 40 | **windows** | 14.9% |
| `skill-governance.yml` | 103 | 40 | linux | 6.9% |
| `seo-tests.yml` | 83 | 41 | linux | 5.6% |
| `example-verification-tests.yml` | 61 | 22 | windows | 4.1% |
| `aspose-com-targets-watch.yml` | 40 | 13 | linux | 2.7% |
| `example-verification-tests.yml` | 30 | 22 | linux | 2.0% |
| `ci-eval-consistency.yml` | 26 | 11 | linux | 1.7% |
| `package-publish-watch.yml` | 26 | 13 | linux | 1.7% |
| `backlink-compliance-watch.yml` | 24 | 13 | linux | 1.6% |
| `act-pipeline.yml` | 19 | 6 | linux | 1.3% |
| `launch-dashboard.yml` | 17 | 14 | linux | 1.1% |
| `maven-publish-watcher.yml` | 16 | 13 | linux | 1.1% |
| `extraction-pipeline.yml` | 8 | 5 | linux | 0.5% |
| `reference-index-structure.yml` | 8 | 6 | linux | 0.5% |
| `seo-analysis.yml` | 3 | 1 | linux | 0.2% |
| `upstream-monitor.yml` | 2 | 1 | linux | 0.1% |
| **Total** | **1,494** | **561 jobs** | | **100%** |

Not present in the export (zero minutes this period): `content-audit.yml` (expected —
its trigger structurally never fires, confirms it's genuinely dead, not undercounted),
`cross-repo-index-sync.yml` (consistent with its single-file path filter being rarely
hit), `metrics-governance.yml` (consistent with its narrow path filter), and
`install-literal-sweep.yml` — **RESOLVED (TC-11 independent review, 2026-09-17;
re-verified independently a second time via `git log --follow --diff-filter=A`)**: this
line originally claimed it "should have fired at least twice in this 18-day window,"
implying a possible defect. That's wrong — the file was added 2026-09-10 (commit
`f9cbe210fb`), so its weekly Monday-11:00-UTC schedule had at most **one** possible
firing (2026-09-14, the same date other workflows' last successful runs land before the
mass-disable) inside the window, not two. Zero recorded minutes is fully explained by the
file's young age plus the mass-disable's timing — not a real defect.

**This changes three things, not just confirms the existing hypothesis:**
1. **Top 3 workflows account for 75.7% of all usage** (`content-governance-checks.yml` +
   `llms-generation.yml` + `skill-governance.yml` combined = 1,131 of 1,494 minutes). The
   public-repo migrations (everything else in the table) total ~12.6% combined —
   worth doing for the reasons already stated (free public minutes, good practice,
   proving the mechanism safely), but they are **not where the cost reduction actually
   comes from**. Prioritize accordingly: the self-hosted track and the `llms-generation.yml`
   investigation below are the high-impact work; the public migrations are the low-risk,
   lower-impact work, and the two should proceed as parallel tracks with that
   expectation set correctly, not as if migrating the small bots first will materially
   move the total.
2. **`llms-generation.yml` (259 min, 17.3%) was not previously identified as a top
   driver** — it never appeared in the earlier proxy-based "suspected top 2" analysis.
   Given it's push(main)-path-filtered only, doesn't deploy anything itself (its own
   header comment says deployment happens again in `aspose.org-workflows`'s per-site
   workflows, which re-run the generator at deploy time), this needed a genuine
   investigation, not an assumed disposition. **RESOLVED (TC-11 independent review,
   2026-09-17)**: the answer is "both, for different parts of the same job" — the
   deploy repo's `docs.aspose.org.yml` does re-run the generator (confirmed live), but
   only on manual `workflow_dispatch` and without this workflow's `detect_stale_llms.py
   --check-only` gate, so the fail-fast correctness value is real and not duplicated,
   even though the raw regeneration computation is. The right fix is `REQUIRES_REDESIGN`
   (keep a lightweight verification step, shed the full duplicate regeneration), not
   outright elimination — see `dossiers/llms-generation.md` §12-13 for the full evidence
   and reasoning.
3. **`skill-governance.yml`'s Windows job costs *more* than its Linux job (223 vs 103
   minutes), reversing the earlier assumption that it was "narrow and probably small."**
   See the updated self-hosted design below — this is no longer a deferred, low-priority
   sub-decision.

**Destination triage** (first pass; confirmed by real usage data in `TC-04`-`TC-07`
before any dossier finalizes):

| Bucket | Workflows | Lever |
|---|---|---|
| Self-host primary | `content-governance-checks.yml`, `skill-governance.yml` (both jobs — see updated design below) | Only lever to zero cost — public migration structurally unavailable (push-gated, needs native required-check integration). Confirmed by real usage data as 58.3% of total cost combined. |
| **Redesign, not pure elimination** | `llms-generation.yml` | 259 min / 17.3% of total, newly surfaced by real usage data. **RESOLVED (TC-11 independent review, 2026-09-17)**: duplication question answered by live-checking both repos' real workflow files directly — the deploy repo's `docs.aspose.org.yml` does re-run the generator, but only on manual `workflow_dispatch` and without this workflow's `detect_stale_llms.py --check-only` gate, so the fail-fast correctness value is real and NOT duplicated, even though the regeneration computation is. Correct disposition is `REQUIRES_REDESIGN` (keep a lightweight verification step, shed the full duplicate regeneration), not "eliminate outright" — see `dossiers/llms-generation.md` §12 for the full evidence. |
| Move to public, clean | `aspose-com-targets-watch.yml`, `backlink-compliance-watch.yml`, `seo-analysis.yml` (rename first) | Reuse the proven SEO-template pattern as-is. Combined real cost: ~2.9% of total — safe first mechanism proof, low cost impact. |
| Move to public, needs decision | `upstream-monitor.yml`, `maven-publish-watcher.yml`, `install-literal-sweep.yml`, `package-publish-watch.yml` | Requires converting auto-commit → PR-gated merge first (user product decision). Combined real cost: ~3.2% of total (`install-literal-sweep.yml` shows zero minutes this period — resolved as expected for a file this young, see correction above, not a functionality concern). |
| Partial split | `ci-eval-consistency.yml`, `launch-dashboard.yml` | Push/PR leg stays private; schedule leg can move — needs a file split, not a pure copy. Combined real cost: ~2.8% of total. |
| Stay private, optimize only | `extraction-pipeline.yml`, `metrics-governance.yml`, `reference-index-structure.yml`, `seo-tests.yml`, `act-pipeline.yml`, `cross-repo-index-sync.yml` | In-place optimization (concurrency, caching) only. `seo-tests.yml` (83 min/5.6%) is the only one of these worth prioritizing — the rest are ≤1.3% each. |
| Dead, leave alone | `content-audit.yml` | Confirmed zero minutes in the real usage export — not a cost lever. |
| Consolidation-independent | `example-verification-tests.yml` (both jobs, 91 min/6.1% combined — Windows leg costs more than Linux here too), the 4 watcher bots (matrix consolidation) | Worth doing regardless of destination |

## Design: the self-hosted runner track

**Why self-hosting is the only lever for these two, not just an option**: both
`content-governance-checks.yml` and `skill-governance.yml` gate `push(main)` and need
native required-check integration with this exact private repo's commits, which a
workflow running in another repo cannot provide. Self-hosting is therefore the only path
to zero marginal Actions cost short of retiring the checks (not proposed). The residual
risk here is lower than the general self-hosted case: this repo's real flow is direct
push, not PR-from-fork, so the usual "never run untrusted PR code on a persistent
self-hosted runner" hazard doesn't apply — the residual risk is operational (a
hung/runaway job competing with the maintainer's interactive session), not
code-injection. Confirmed viable by the user (2026-09-16) on this same dev machine.

**Architecture**: WSL2-hosted runner, persistent listener with a fresh Docker container
per job, on this Windows 11 Pro dev machine, routed via a dedicated label (e.g.
`runs-on: [self-hosted, wsl2-linux, gha-private-native]`) so only these two workflows use
it — never the schedule bots (this machine isn't reliably on at 09:00-11:00 UTC daily
regardless of the maintainer's presence, an independent, non-cost argument for keeping
those on GitHub-hosted or public execution).

- **`content-governance-checks.yml`** (Linux-only) is a clean fit. **Land the
  concurrency/cancel-in-progress fix via `/workflow-harden` before cutover, not after** —
  a single self-hosted machine has no elastic parallelism the way GitHub-hosted runners
  do, so back-to-back pushes without a concurrency guard would stack real builds on one
  physical machine.
- **`skill-governance.yml`'s required Linux job** gets the same treatment. Its
  soft-launched Windows job is **no longer a deferred, low-priority sub-decision** — real
  usage data (2026-09-18) shows it costs *more* than the required Linux job (223 vs 103
  minutes), not less. Two options, cheapest first:
  1. **Cheapest, try this first, independent of self-hosting**: since this job is
     `continue-on-error: true` (non-blocking, soft-launched), check via `/workflow-harden`
     whether it needs to run on *every* matching push at all, or whether demoting it to a
     daily schedule / `workflow_dispatch` — a one-line trigger change — captures most of
     its coverage value at a fraction of the cost. This is cheaper and lower-risk than
     self-hosting and should be evaluated before defaulting to self-hosting it too.
  2. If it must stay push-triggered, self-host it inside its own isolated,
     hard-timeout container — mechanically simpler than the Linux case since the host is
     already Windows, at the cost of giving up GitHub-hosted Windows runners' one real
     advantage (VM disposability).
- **Canary-first, and unusually cheap to prove right now**: because all 20 workflows are
  currently disabled, there is no live required check at risk while the runner setup is
  validated end-to-end.

**Lifecycle** (closes the "narrative-only design" structural weakness):
```
PROVISIONED → REGISTERED → HEALTHY ⟷ DEGRADED → DECOMMISSIONED
```
Health check is a heartbeat (rides the telemetry mechanism below) confirming the runner
is alive and has processed a job within an expected window. `DEGRADED` (no heartbeat
within N hours) triggers an alert, never a silent fallback — GitHub's own behavior when a
self-hosted runner is offline is to queue the job indefinitely, which for a push-gated
required check looks like a hung commit status, a regression this design must surface
quickly. Decommission is an explicit verb including workspace/secret cleanup.

This is `TC-08`'s deliverable (`design/self_hosted_architecture.md`).

## Design: the public-repo migration track

**Mechanism** (reuses the proven SEO-template pattern — nothing new to invent):
1. Copy the workflow into a new local template directory, `scripts/ci/deployed-workflows/`
   (parallel to `scripts/seo/workflows/`), pointing `actions/checkout@v4` at
   `repository: Aspose/aspose.org` with the token already present in
   `Aspose/aspose.org-workflows` (`REPO_TOKEN`/`GH_TOKEN`) — no new secret needed.
2. Hand-copy-deploy into `Aspose/aspose.org-workflows/.github/workflows/`, matching
   today's SEO-template convention (no automated sync exists; that's the norm here).
3. Extend `check_workflow_drift.py`'s coverage to the new template directory.
4. Flip the private original's trigger to `workflow_dispatch`-only (currently a no-op
   since all 20 are disabled) rather than deleting it — preserves rollback. This is a
   pure YAML edit; see "Hard constraint" above — it does not enable anything.
5. Clean-tier workflows keep read+report behavior unchanged; needs-decision-tier
   workflows switch from auto-commit to opening a branch + PR, mirroring the SEO
   workflows exactly.
6. Prove attribution before trusting it — see "Canary" below.

**Roster and order**: see the destination-triage table above for the full tier
breakdown. Migration order: `aspose-com-targets-watch.yml` first (fastest signal, safest
permissions — this mission's designated canary) → `backlink-compliance-watch.yml` →
`seo-analysis.yml` (after rename — it collides with the already-deployed public template
of the same name) → the 4 watcher bots, pending the auto-commit→PR-gated decision → the 2
partial-split workflows last, since splitting a file is more involved than copying one.
Each migration is proven individually before the next starts.

**Canary**: `aspose-com-targets-watch.yml` — daily cadence (fast signal), read+report-only
permissions (`contents: read`, `issues: write` — structurally incapable of corrupting the
repo), single job/5 steps, no cross-repo secrets beyond the checkout token already
proven. Deploy a template copy, extend the drift checker, let it run 5-7 daily cycles,
prove attribution three ways: runs land publicly, stop appearing privately, and a real
billing-cycle number trends flat/down for that slot. **The actual execution of this
migration, including how attribution is proven durably rather than as a one-time manual
check, is governed by a dedicated state machine — see the Phase B section at the end of
this document.**

This is `TC-09`'s deliverable (`design/public_execution_boundary.md`).

## Design: recurring cost telemetry & circuit breaker

This is the actual fix for root causes #1 and #2 above, and the one piece of this
mission's design that has value independent of how many workflows end up migrating.

- **Telemetry skeleton**: reuse the generic event → validated ledger → aggregate →
  gated-submit mechanics already proven in `scripts/pipeline/commands/ops/metrics_event_ledger.py`
  / `run_metrics.py` / `metrics_submitter.py` (dry-run by default, secrets never logged,
  endpoint/token via env vars only). **Do not reuse `MetricsRow` itself** — it is
  LLM-call-specific. Define a new `WorkflowUsageEvent`/`WorkflowUsageRow` and taxonomy,
  mirroring the mechanics, not the schema.
- **Collector**: a small, read+report-only scheduled job (itself a clean public-migration
  candidate) that runs weekly, reconstructs proxy minutes via `TC-04`'s own method, and
  appends a durable local snapshot + trend.
- **Circuit breaker**: a magnitude-cap trigger, **not** a failure-count trigger — the
  repo's one prior circuit-breaker precedent (`scripts/translator/backends/circuit_state.py`)
  used failure-count and was deleted along with the whole in-house translator package; it
  is also the wrong trigger type for a cost problem. Model this instead on the *live*
  pattern in `install_change_budget.py` / `publish_watcher.py --max-auto-apply`: a static
  cap plus a rolling-baseline anomaly check.
- **Action when tripped: alert, never auto-disable.** Auto-disabling was the blunt
  instrument that caused this mission to exist. The fix for a silent-until-crisis
  observability gap is a fast, specific, human-actionable signal (reusing the existing
  `aspose-com-targets-watch.yml` issue-creation pattern), not a second automated version
  of the same all-or-nothing stopgap.
- **Disposition**: this slice should be re-filed as `recurring-candidate` — Phase A's
  existing gap report explicitly deferred this exact question, and this analysis
  concludes it is needed.

This is `TC-13`'s deliverable (`design/cost_telemetry_proposal.md` + a second,
`recurring-candidate` gap-escalation report).

## CI defect remediation (TC-05 follow-up, deep pass 2026-09-17)

`TC-05`'s failure-signature analysis surfaced two real defects behind the two highest-cost
workflows' bad failure rates. Investigated properly (not guessed) before designing a fix —
see below. **Both defects are the actual, verified root causes, confirmed by reading the
checker code, the test history, and the git history directly** — not inferred from the
failure symptom alone.

### Symptoms vs. root causes vs. structural weaknesses

**Symptoms**: `skill-governance.yml` fails 100% of the time (Sept 2026); `content-governance-checks.yml`
fails 49% of the time. Both looked, on the surface, like the same class of problem
("governance checks are broken/noisy"). They are not — treating them as one problem would
have produced the wrong fix for both.

**Root cause 1 — `skill-governance.yml`: a latent bug in the checker, not real drift.**
`platform_capabilities.yaml` and `registry.PLATFORM_CONTRACT`
(`scripts/pipeline/lib/example_verification/registry.py`) are fully in sync for all 7
platforms — verified by direct comparison. The failure comes from
`check_platform_capabilities.py::check_example_verification()`
(`scripts/ci/checks/check_platform_capabilities.py`, lines ~383-439), added 2026-09-06
(commit `acd165e07e`), whose reverse-completeness loop compares the full, real
`registry.PLATFORM_CONTRACT` (never fixture-mocked) against a *narrowed* `checkable_platforms`
parameter rather than everything the tested YAML actually declares. A pre-existing
negative-control test, `test_same_fixture_passes_once_the_value_is_corrected`
(`scripts/ci/tests/test_check_platform_capabilities.py`, dated 2026-08-29 — 8 days
*before* the buggy function existed), uses a single-platform (`typescript`-only) synthetic
fixture that the new function trips over every time, producing 6 spurious findings.
**This workflow has been failing on a false positive, continuously, since 2026-09-06 (12
days, 40+ runs as of this writing) with nobody reconciling the test to the new check.**

**Root cause 2 — `content-governance-checks.yml`: an incomplete shift-left rollout, not a
bypass.** The original hypothesis (that `git_plumb_commit.py`'s well-known hook-skipping
behavior explains this) is **refuted** — `git_plumb_commit.py` genuinely skips all git
hooks, but `check_evaluator_version_bump.py` was never *in* a hook to skip. It exists
solely inside the push-triggered CI workflow, absent from `scripts/pre-commit-audit.sh`
(the real pre-commit hook, confirmed by grep), absent from `git_plumb_commit.py`'s manual
pre-flight re-checks (which *does* re-implement one hook-only check,
`stale_file_regression`, for exactly this reason — evaluator-version-bump was simply never
added to that list), and absent from the local CI-simulation mirror script (which *does*
include the sibling `check_evaluator_freeze.py`). Compounding this: `AGENTS.md` §9a links
to `docs/workflows/evaluator-changes.md`, deleted 2026-05-30; its replacement,
`docs/development/evaluator-changes.md`, dropped the version-bump guidance entirely — the
one place meant to teach this rule to a human or agent editing evaluators no longer does.

**Structural weakness underneath both** (the deeper pattern, not just two isolated bugs):
this repo has extensive content/quality checks, but no reliable mechanism ensuring the
checks THEMSELVES stay correct, current, and consistently wired across every layer they
need to run in. It has checks on content, but no checks on the checks. Two more data
points reinforce this: (a) `check_workflow_drift.py` already proves this repo knows how to
build a multi-source drift classifier — for a *different* pair of things (SEO templates
vs. deployed copies) — the same pattern is directly reusable here, not novel; (b)
`check_governance_link_paths.py` (referenced in prior mission memory) already has its own
known false-positive bug, meaning the tool meant to catch exactly the AGENTS.md-dead-link
class of problem is itself unreliable — a second instance of "the watcher is broken." This
structural weakness is the same shape as the GH-Actions-cost root cause already identified
above (root cause #1, "zero recurring cost observability") — this repo systematically
lacks observability into its own governance-system health, not just its Actions spend.

### What this preserves vs. redesigns

**Preserved**: the intent of both checks (real evaluator-version-bump enforcement, real
registry/YAML drift detection) — neither should be weakened or removed.
`git_plumb_commit.py`'s hook-skipping design is preserved unchanged — it was never the
actual cause and remains legitimate, necessary infrastructure for this repo's concurrent-
session safety.

**Redesigned**: where and when both checks run (shift genuinely left, not just documented
as should-be-left); the actual buggy comparison logic in `check_example_verification()`;
the stale test fixture; the broken documentation link; and, as a new capability, a
lightweight mechanism that would have caught both of these classes of gap automatically
instead of waiting for a cost-motivated failure investigation to stumble onto them.

### Concrete implementation directions

1. **Fix the platform-capabilities bug** (surgical, well-localized):
   `check_example_verification()`'s tail loop should iterate over the tested YAML's own
   declared platform set (`caps["platforms"].keys()`), not the narrower
   `checkable_platforms` parameter passed in from `check_all()`. This is the fix the
   investigating agent itself judged most correct, matching the check's actual intent ("a
   platform PLATFORM_CONTRACT declares but the YAML never mirrors" — a YAML-declaration
   question, not an active-platform question).
2. **Fix the stale test**: update `test_same_fixture_passes_once_the_value_is_corrected`
   (and audit sibling tests in the same file for the same narrow-fixture blind spot) to
   remain valid under the corrected logic — either give it a fixture covering all 7 real
   platforms, or scope its assertion the way `test_typescript_class_kinds_disagreeing_with_real_code_fails`
   already correctly does (filter findings to the platform under test, not a blanket
   `findings == []`).
3. **Give `check_evaluator_version_bump.py` real pre-commit enforcement, in all three
   places this repo already uses for exactly this purpose**: add it as a new step in
   `scripts/pre-commit-audit.sh` (adapted to diff staged/working changes against `HEAD`,
   not `origin/main` — a real semantic difference from the CI invocation that needs
   deliberate handling, not a blind copy-paste); add it to `git_plumb_commit.py`'s manual
   pre-flight re-check list, mirroring its existing `stale_file_regression` re-
   implementation exactly; add it to the local CI-simulation mirror script alongside its
   sibling `check_evaluator_freeze.py` (confirm that script's exact path before
   implementing — the investigating agent confirmed it exists and includes the sibling
   check, but its exact filename wasn't fully pinned down in this pass).
4. **Fix the documentation gap**: `AGENTS.md` §9a's link should point at
   `docs/development/evaluator-changes.md`, and that doc should have the version-bump rule
   restored. **`AGENTS.md` is human-maintainer-authored only per its own header — this is
   a human action item, not something for an agent taskcard to edit directly.** The
   `docs/development/evaluator-changes.md` content fix may be agent-executable; the
   `AGENTS.md` link fix is not.
5. **New capability, tied into the already-designed telemetry work (`TC-13`)**: extend
   that capability's scope to also watch CI-check *health*, not just cost — a required
   check failing continuously for N consecutive days/runs is exactly the kind of anomaly
   the same magnitude-cap/alert infrastructure (already designed for cost) can detect
   without building a second, separate system. This is what would have caught the
   platform-capabilities bug automatically after a day or two, instead of 12.
6. **Optional, lower-priority: a check-layer parity audit.** Generalize
   `check_workflow_drift.py`'s existing 3-way-comparison pattern to a new domain: for every
   blocking (non-`continue-on-error`) check invoked from a push-triggered (not PR-gated)
   workflow, verify it also appears in `scripts/pre-commit-audit.sh` and/or the local CI-
   mirror script; flag any that don't. This would have caught the evaluator-version-bump
   gap automatically and would catch the same incomplete-rollout pattern for any future
   check. Flagged as genuinely additional scope, not required to close out the two
   immediate defects — see tradeoffs below.

### Validation

- Run `pytest scripts/ci/tests/test_check_platform_capabilities.py -v` locally after the
  fix (safe, local-only, not a workflow dispatch) — confirm the corrected test passes and
  the full 1594-test governance suite shows no new regressions.
- Stage a synthetic evaluator-file edit without a version bump and attempt a commit
  through both `/commit` (S-76) and `git_plumb_commit.py` — confirm both now correctly
  block it; then bump the version and confirm both allow it.
- After the `docs/development/evaluator-changes.md` content fix, re-run
  `check_governance_link_paths.py` (acknowledging its own known false-positive bug — pair
  with a manual visual check, don't trust that tool alone here).

### Regression controls

- Add a test pinning `check_example_verification()`'s corrected behavior against a
  *partial* fixture (more than one, fewer than all real platforms) — the exact shape of
  fixture that silently broke this time — not just the single-platform case that already
  existed.
- Add pre-commit-hook test coverage for the new evaluator-version-bump enforcement,
  mirroring the pattern `test_check_stale_file_regression.py` already uses for its sibling
  check.
- Once built, the CI-check-health extension to `TC-13`'s telemetry (direction 5 above) is
  itself the durable regression control for *both* defect classes recurring silently again
  in the future — this is the piece that actually closes the "consistency across reruns"
  gap, not the two point-fixes alone.

### Tradeoffs, risks, and honest limits

- Pre-commit diff semantics (staged/working vs. `HEAD`) differ from CI's push-vs-parent
  diff — a naive copy-paste of the CI check's diff logic into the pre-commit hook risks
  subtle behavioral divergence (e.g., a multi-commit push where the local hook only ever
  sees one commit at a time). Needs deliberate design, not assumed equivalent.
- The check-layer parity audit (direction 6) is genuinely additional engineering, not a
  quick add-on — consistent with this mission's own earlier caution about scope relative
  to size, it's presented as valuable but optional, not bundled into the mandatory fix set.
- **This pass found two real defects because they happened to surface during `TC-05`'s
  cost-motivated failure investigation — it does not claim to have found every instance of
  "the checker itself is broken" across this repo's ~40+ CI check scripts.** A full audit
  of that kind is a materially larger undertaking, out of scope here, and should not be
  assumed complete.
- `AGENTS.md`'s edit is a human action item — flagged, not planned as agent-executable.
- The local CI-simulation mirror script's exact path needs confirmation before
  implementation — not fully pinned down in this investigation pass.

## Phase A taskcards & execution

### Taskcard breakdown

15 taskcards, listed in dependency/execution order (not creation order — `TC-13` was
allocated after `TC-10`-`TC-12` already existed in the ledger, and `TC-14`/`TC-15` were
allocated after `TC-13`, so none of their numbers match their execution position; `TC-13`
runs parallel to `TC-08`/`TC-09` immediately after `TC-07`, and `TC-14`/`TC-15` run
parallel to each other immediately after `TC-05` since both are follow-ups to its
findings, independent of the `TC-06`/`TC-07`/`TC-08`/`TC-09`/`TC-13` chain):

| Taskcard | Purpose | Depends on |
|---|---|---|
| TC-01 | Baseline/org-state reconciliation: full inventory, `aspose.org-workflows` side, known access gaps | — |
| TC-02 | Disabled-vs-running anomaly write-up (user-confirmed intentional, not investigated further) | TC-01 |
| TC-03 | Structured inventory dataset; delegates static-review/CI-weight to `/workflow-harden` (local-only verification per Hard Constraint) | TC-01 |
| TC-04 | Usage/billing collection — two-phase (agent-doable proxy now, human Billing-UI reconciliation deferred to TC-12) | TC-02 |
| TC-05 | Failure-signature analysis from historical run data | TC-03 |
| TC-06 | Importance matrix (criticality × frequency × consumer-impact) | TC-03, TC-05 |
| TC-07 | Destination-decision matrix (13-value enum) + threat assessment | TC-04, TC-06 |
| TC-08 | Self-hosted runner track design (see above) | TC-07 |
| TC-09 | Public-repo migration track design (see above) | TC-07 |
| TC-13 | Recurring cost-telemetry proposal (see above) | TC-07 |
| TC-10 | ~20 per-workflow dossiers, each with a cited destination decision | TC-07, TC-08, TC-09, TC-13 |
| TC-11 | Independent review of dossiers, decisions, and threat assessment | TC-10 |
| TC-12 | Master report, evidence bundle, completeness check, governance-artifact commit | TC-11 |
| TC-14 | Fix `check_example_verification()`'s comparison bug + stale test fixture (see CI defect remediation) — via `/workflow-harden` (S-115), whose scope already covers `scripts/ci/**` | TC-05 |
| TC-15 | Evaluator-version-bump 3-way pre-commit wiring (hook, `git_plumb_commit.py` pre-flight, local CI-mirror) + `docs/development/evaluator-changes.md` content fix (the `AGENTS.md` link itself is a human action item, not agent-executable) | TC-05 |

Per-workflow *execution* taskcards (mission brief's Stage 12) are a later, separate batch
created only after Phase A's destination decisions are locked in.

### Execution order

1. Baseline/org-state reconciliation. (TC-01)
2. Disabled-vs-running anomaly write-up. (TC-02)
3. Structured inventory dataset. (TC-03)
4. Usage/billing collection, two-phase. (TC-04)
5. Failure-signature analysis. (TC-05)
6. Fix the platform-capabilities checker bug + stale test (CI defect remediation). (TC-14)
7. Evaluator-version-bump shift-left + docs fix. (TC-15)
8. Importance matrix. (TC-06)
9. Destination-decision matrix + threat assessment. (TC-07)
10. Self-hosted runner track design. (TC-08)
11. Public-repo migration track design. (TC-09)
12. Recurring cost-telemetry proposal. (TC-13)
13. Per-workflow dossiers. (TC-10)
14. Independent review. (TC-11)
15. Master report, evidence bundle, commit. (TC-12)

### Lane ownership & parallelization (swarm-ready)

No repo-wide "swarm coordinator" convention exists beyond the taskcard system's own
row-level CAS (`TaskcardStore.update_taskcard_status`, contention raises
`TaskcardCASError`) and session-ledger/skill-context attribution — lane safety here is
built from those primitives. Every taskcard writes to a distinct file set, so no two
lanes fight over the same write:

| Taskcard | Writes | Parallel with |
|---|---|---|
| TC-01 | `inventory/workflows_inventory.json` | — (first) |
| TC-02 | `inventory/disabled_vs_running_anomaly.md` | — |
| TC-03 | extends TC-01's inventory file | **TC-04** |
| TC-04 | `usage/usage_dataset.json`, `usage/billing_reconciliation.md` | **TC-03** |
| TC-05 | `analysis/failure_signatures.json` | — |
| TC-14 | `scripts/ci/checks/check_platform_capabilities.py`, `scripts/ci/tests/test_check_platform_capabilities.py` | **TC-15** |
| TC-15 | `scripts/pre-commit-audit.sh`, `git_plumb_commit.py` pre-flight list, local CI-mirror script, `docs/development/evaluator-changes.md` | **TC-14** |
| TC-06 | `analysis/importance_matrix.json` | — |
| TC-07 | `analysis/destination_decision_matrix.json`, `analysis/threat_assessment.md` | — |
| TC-08 | `design/self_hosted_architecture.md` | **TC-09**, **TC-13** |
| TC-09 | `design/public_execution_boundary.md` | **TC-08**, **TC-13** |
| TC-13 | `design/cost_telemetry_proposal.md`, new gap report | **TC-08**, **TC-09** |
| TC-10 | `dossiers/{workflow-name}.md` (~20 files) | — |
| TC-11 | `review/independent_review.md` | — |
| TC-12 | `final_report.md`, `EVIDENCE_BUNDLE.md`, governance commit | — (last) |

Critical path: `TC-01 → TC-02 → {TC-03 ‖ TC-04} → TC-05 → TC-06 → TC-07 → {TC-08 ‖ TC-09
‖ TC-13} → TC-10 → TC-11 → TC-12`, with `{TC-14 ‖ TC-15}` branching off `TC-05` as an
independent side-thread (CI defect remediation) that does not gate `TC-06` onward — it can
finish anytime before `TC-12`'s closeout without blocking the mission's core destination-
decision path. These three fan-out points are the only genuine parallelism opportunities
at this scale — do not decompose `TC-10`'s 20 dossiers into 20 separate taskcards purely
to manufacture more parallelism.

### Durable artifact locations

```
reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/
  mission_authority.yaml
  taskcards.jsonl
  inventory/workflows_inventory.json
  inventory/disabled_vs_running_anomaly.md
  usage/usage_dataset.json
  usage/billing_reconciliation.md
  analysis/failure_signatures.json
  analysis/importance_matrix.json
  analysis/destination_decision_matrix.json
  analysis/threat_assessment.md
  design/self_hosted_architecture.md
  design/public_execution_boundary.md
  design/cost_telemetry_proposal.md
  dossiers/{workflow-name}.md          (~20 files)
  review/independent_review.md
  EVIDENCE_BUNDLE.md
  final_report.md
```
`reports/` is gitignored by design — none of this is committed to git; it persists only
as local files under `D:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE\`.
That absolute path (specifically `EVIDENCE_BUNDLE.md`'s) is the one fact that must appear
in any closing report on this mission.

### Human decisions

**Resolved (2026-09-16)**:
1. Disabled-workflow mass-disable — confirmed intentional user action.
2. Org-level billing access — user will pull the Billing UI export directly. **Done**
   2026-09-18 — see "Real usage data received" in Status and "Technical findings" above.
3. Self-hosted machine identity — this same Windows 11 Pro dev machine.
4. Proceed now — user chose to register the mission and start Phase A immediately.
5. **Phase B start — RESOLVED 2026-09-18.** User explicitly authorized seeding Phase B's
   taskcards ahead of Phase A's own completion, on condition of personal supervision: a
   stop gate applies after every Phase B taskcard reaches a terminal/implemented state —
   execution does not auto-advance to the next taskcard without the user's explicit
   go-ahead.

**Still open** (execution-time checks, not upfront blockers):
- **MT066 coordination** — formal gate on `TC-09`, see "Critical findings" above.
- **Auto-commit watcher bots** — whether converting the 4 bots to PR-gated merge is
  acceptable is an open question for `TC-07`'s destination decisions on those four
  specifically; their dossiers stay `INSUFFICIENT_EVIDENCE` until answered.
- **Root-slot takeover go/no-go** — if the root `MISSION_AUTHORITY.yaml` incumbent
  becomes locked+open by a different mission before this one's next session, stop and ask
  rather than force-taking-over.

### Failure handling & rollback

Phase A's only production-facing changes are the `content-governance-checks.yml`
concurrency fix (via `/workflow-harden`, its own governed rollback applies) and
mission/gap-escalation paperwork. Failure modes and responses:

- **Taskcard CAS contention**: re-read via `taskcard_cli.py latest --task <id>` and retry
  with the current `--expected` status — never force past a CAS error.
- **`gh api` rate-limit or transient failure mid-TC-04**: back off and resume from the
  last successfully fetched page; record the actual covered range rather than
  extrapolating silently.
- **`/workflow-harden` returns a verdict conflicting with this mission's own read**: do
  not override S-115's verdict from outside its own skill context — record the conflict
  and route through S-115's own remediation path.
- **Override token `20260916-162212-MISSION_AUTHORITY-yaml` expires (7-day TTL) before
  the TC-12 commit**: recreate it via `override_manager.py create` before committing.
- **Root `MISSION_AUTHORITY.yaml` slot taken over mid-run**: this mission's own archived
  snapshot is durable regardless of root-pointer changes — taskcard work continues
  uninterrupted; re-binding the root pointer is a separate human call.
- **Concurrent-session dirty working tree** (this repo routinely has 80+ unrelated dirty
  files from other sessions): never stage or commit anything outside this mission's
  explicit file list. The TC-12 commit uses `git_plumb_commit.py --files <exact list>`,
  never `git add -A`/`git add .` — both because of the concurrent-session hazard and
  because `/plans` and `/backlog` are gitignored at the repo root with no negation
  carve-out (`.gitignore:94-95`), so a bare `git add` would silently skip this mission's
  own new `plans/` files; `git_plumb_commit.py`'s scoped `git add -f <exact paths>`
  handles this correctly by construction.
- **A dossier can't reach a confident destination decision**: mark it
  `INSUFFICIENT_EVIDENCE` with a stated reason — a valid, expected outcome, not a mission
  failure.

### Single-go execution gate sequence

An execution agent picking this plan up runs this sequence top to bottom in one
continuous session, stopping only at a genuine stop condition.

**Pre-flight**:
1. `mission_authority.py status --json` and `list` — confirm the mission is still known
   and `open`. If the root pointer now references a different, locked+open mission, do
   not force-reclaim it; this mission's taskcard work is unaffected regardless — flag the
   root-pointer question for a human rather than forcing.
2. Confirm the gap-escalation report exists and is registered (it does, filed 2026-09-16).
3. `taskcard_cli.py latest` — resume from the first non-terminal card in dependency
   order.
4. Check the override token hasn't expired; recreate it if needed before TC-12.

**Stop conditions** (pause and report, never work around):
- A dossier can't reach a confident decision → `INSUFFICIENT_EVIDENCE`, continue with the
  rest.
- TC-04's Billing UI reconciliation is still missing at TC-12 → expected, not an error;
  report it and return `PLAN_READY_EXCEPT_DOCUMENTED_EXTERNAL_AUTHORITY`.
- MT066's status check shows a real, unresolved overlap → stop and ask.
- A taskcard CAS error repeats after one fresh-read retry → stop and report.
- `/workflow-harden` returns `SECURITY_RISK` → do not resolve it from inside this
  mission; record and route to S-115.
- **Any point where the next action would be `gh workflow enable`, an `.../enable` API
  call, or `gh workflow run` against one of the 20 workflows — hard stop, no
  exceptions**, including if `/workflow-harden`'s own default remote-verification logic
  doesn't honor the local-only scoping from the Hard Constraint above.

**Closeout (TC-12)**:
5. Run `check_plan_taskcard_completeness.py --plan-file plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md --taskcards reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/taskcards.jsonl` —
   expect `OK` (13 execution-order steps ≤ 13 distinct taskcards; re-verified live
   2026-09-17 against this reorganized file).
6. Assemble `EVIDENCE_BUNDLE.md` — a single index of every artifact this mission
   produced, with absolute paths — and `final_report.md`. Every acceptance item from
   "Verification" below must be checked off here, not left implicit.
7. Commit governance artifacts via `git_plumb_commit.py --files MISSION_AUTHORITY.yaml
   plans/missions/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE.md
   plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md plans/master-plan.md ...`,
   then `override_manager.py consume --token-id 20260916-162212-MISSION_AUTHORITY-yaml
   --commit-sha <sha>`.
8. State the final planning verdict (`PLAN_READY_FOR_AUTONOMOUS_EXECUTION` /
   `PLAN_READY_EXCEPT_DOCUMENTED_EXTERNAL_AUTHORITY` / `PLAN_REQUIRES_FURTHER_INVESTIGATION`
   / `INSUFFICIENT_EVIDENCE`) and `EVIDENCE_BUNDLE.md`'s absolute path in the final
   response.

**Verification checklist** (the specific acceptance items step 6 above must satisfy):
- Every workflow (20 current + any found deleted/renamed in git history) has a dossier
  with a cited destination decision — none left at `INSUFFICIENT_EVIDENCE` without a
  stated reason.
- Any destination recommending public or self-hosted execution cites a completed threat
  assessment naming every secret/credential/data class exposed.
- Independent review completed with no open `CONFIRMED` findings.
- `TC-03` cites an existing or freshly-run `reports/sprint/workflow-harden-{date}/`
  bundle rather than re-deriving S-115's own probe results.
- MT066's status was re-checked immediately before `TC-09` finalized, not just at
  mission-open — evidenced in `TC-09`'s `evidence_refs`.

---

## Phase B: production execution design (authorized 2026-09-18, user-supervised)

This section's design was produced as Phase A output. **The user explicitly authorized
Phase B taskcard seeding on 2026-09-18**, ahead of Phase A's own completion, on one
condition: **personal supervision with a stop gate after every taskcard.**

**Supervision & stop-gate protocol (binding on every `PHB-*` taskcard)**:
- After a `PHB-*` taskcard reaches `IMPLEMENTED` (or any terminal state), stop. Do not
  begin the next taskcard — even one with satisfied dependencies — without the user's
  explicit go-ahead in that session.
- Report what was done, what the taskcard produced (with file paths), and what the next
  queued taskcard would be, then wait.
- This does not relax any other gate in this document — the Hard Constraint (no
  enable/dispatch), the MT066 coordination check, and Phase A's own taskcards' rules all
  still apply in full to Phase B work.
- This protocol is recorded in `MISSION_AUTHORITY.yaml`'s `human_authority_boundaries`
  and in each seeded `PHB-*` taskcard's own description — it is not just prose here.

### What this design preserves vs. redesigns

Preserved unchanged: the mission/taskcard system as the *investigation/coordination*
layer (correct for cross-session signaling, insufficient on its own as the safety
mechanism for an irreversible external side effect — see below); the SEO-template deploy
mechanism as the underlying action; `/workflow-harden` delegation; the no-enable/
no-dispatch hard constraint (made a structural invariant of the state machine below, not
just a prose rule); the self-hosted candidate decision.

Redesigned, because the original sketch had the three structural weaknesses named in
"Root-cause analysis" above: migration mechanics get a proper resumable state machine
(below), "push succeeded" is no longer treated as proof of a durable outcome (a dedicated
reconciler is added), and the self-hosted runner gets the lifecycle already specified
above instead of staying narrative-only.

### The migration-run state machine

Modeled directly on `scripts/pipeline/commands/ops/refresh_run.py` — this repo's most
battle-tested precedent for exactly this problem class (resumable, hash-verified,
externally-visible production changes) — adapted for
`scripts/pipeline/commands/foss/readme_refresh_run.py` and
`scripts/pipeline/lib/publication_reconciler.py`'s lessons about *external* side effects,
since Phase B's mutating effect is a push to a sibling repo, not a local commit.

```
CREATED → BASELINE_PINNED → TEMPLATE_BUILT → CANARY_DEPLOYED → CANARY_OBSERVING →
CANARY_CONFIRMED → CUTOVER_STAGED → CUTOVER_LIVE → STABILIZED
BLOCKED re-enterable from: BASELINE_PINNED, TEMPLATE_BUILT, CANARY_DEPLOYED,
  CANARY_OBSERVING, CUTOVER_STAGED
Terminals: STABILIZED, ABANDONED, ROLLED_BACK
```

Each design point answers a specific, real failure mode found by reading the precedents,
not a hypothetical one:

- **`BASELINE_PINNED`** hash-pins the private workflow file plus its Phase-A usage
  baseline before any change — `refresh_run.py`'s `scope.json`/`initial_hashes` pattern,
  a hash-verifiable "nothing else touched this file" guard rather than a trusted status
  field.
- **`CANARY_OBSERVING` is a distinct state with a minimum dwell time**, gated on a new
  **reconciler component** modeled on `publication_reconciler.py`'s "ask GitHub what
  actually happened" principle — it polls `gh api` against both repos (real runs landing
  publicly, zero new runs firing privately, billing trend once available) before
  advancing. This exists because `readme_refresh_run.py`'s own production history
  includes two real PRs that merged externally but stayed invisible to local state, and
  one that was silently wiped after landing on a mirror repo instead of the canonical
  target — both caught only because this exact kind of reconciler was built.
- **Every `BLOCKED` resume target is a state other than the one that failed** —
  `readme_refresh_run.py` has a real, found-live `PUSHING → PUSHING` bug that made its
  own documented retry path unable to complete until fixed; this rule exists specifically
  to prevent repeating it.
- **`ROLLED_BACK`** is a first-class terminal: for the private side, hash-verified
  restore of the trigger-config edit from the pinned baseline; for the public side, since
  history rewrite on a repo with external visibility is unacceptable, rollback means a
  new commit that reverts or disables the deployed template — restoring by addition,
  never by rewriting history.
- **Locking** reuses `scripts/pipeline/lib/advisory_lock.py`'s `FileLock` (atomic,
  PID-liveness-aware, session-identity-double-checked), with an orphaned-lock escape
  hatch built in from day one — `readme_refresh_run.py` had a real incident where five
  products stayed locked by dead sessions for 12 days before one was retrofitted.
- **Any local commit this run makes** goes through `git_plumb_commit.py` and a
  `bind_commit()`-style forensic check (right trailers, right base, exact expected file
  set, hash-matched bytes) before the state advances.

### Validation, regression controls, and implementation directions

- **Dry-run rehearsal before any real cutover**, mirroring `readme_refresh_run.py`'s
  `PUSHING → APPROVED` pattern. Not theoretical: `readme_refresh_run.py` hit a real
  `[WinError 5] Access is denied` cleaning up a disposable clone's read-only git objects
  on this same Windows platform, which blocked its own dry-run-then-live sequence until
  patched — test this specific failure mode on this machine before relying on any
  clone/push mechanics for the real migration.
- **Machinery canary before content canary**: exercise the new state machine end-to-end
  on a synthetic/throwaway workflow first, separate from `aspose-com-targets-watch.yml`'s
  already-planned canary of the migration itself.
- **Regression control**: a workflow that quietly regresses (fires privately again after
  being marked migrated, or a self-hosted job silently falls back to GitHub-hosted) must
  be caught automatically by the recurring reconciler, not by a human noticing next
  month's bill.

### Tradeoffs, risks, and honest limits

- **This is real engineering effort, not a quick script.** `readme_refresh_run.py` is
  ~6,300 lines and self-describes as *less* hardened than `refresh_run.py` (~3,600 lines,
  hardened over months against real incidents). A new migration-run machine, even reusing
  patterns, is a multi-week investment.
- **Possibly more machinery than this mission's scale justifies on its own.** Phase A's
  gap escalation classified this whole effort `bounded-oneoff` — roughly 11 one-time
  migration candidates, not a recurring deliverable. **Real, stated tradeoff, not a
  default**: build the full state machine primarily because the cost-telemetry
  component's value is ongoing and independent of this migration; for the migration
  mechanics specifically, consider the lighter-weight alternative of reusing `FileLock` +
  session-identity + `git_plumb_commit`/`bind_commit`-style verification as direct
  library calls inside the existing taskcard system, without a dedicated 9-state CLI, if
  11 one-time migrations don't justify the heavier build. This is a decision for the
  user, not settled here.
- **`readme_refresh_run.py` is the closer analogue but is itself self-graded as less
  proven** — "only exercised against local scratch git repos" at time of writing, not a
  real external org. Treat it as a template with real, named limits.
- **GitHub's Enhanced Billing Platform API eligibility for this org remains unverified.**
- **The Windows `WinError 5` risk is proven, not speculative** — a real, previously
  shipped defect in an analogous clone/push flow on this exact OS.

### Phase B taskcard skeleton — authorized and seeded 2026-09-18

Real task IDs (mirroring Phase A's `MT069-TC-*` naming):

| Taskcard | Purpose | Depends on |
|---|---|---|
| `MT069-PHB-01-MIGRATION-RUN-STATE-MACHINE` | Build the migration-run state machine (or the lighter-weight library-call version) | Phase A `TC-10` (dossiers) |
| `MT069-PHB-02-RECONCILER-COMPONENT` | Build the reconciler component | `PHB-01` |
| `MT069-PHB-03-COST-TELEMETRY-CIRCUIT-BREAKER` | Build the cost-telemetry collector + circuit breaker | `TC-13`'s `recurring-candidate` gap report |
| `MT069-PHB-04-MACHINERY-CANARY` | Machinery canary on a synthetic workflow, including the Windows clone-cleanup dry run | `PHB-01`, `PHB-02` |
| `MT069-PHB-05-CONTENT-CANARY-ASPOSE-COM-TARGETS-WATCH` | Content canary: migrate `aspose-com-targets-watch.yml` for real | `PHB-04` |
| `MT069-PHB-06-MIGRATE-REMAINING-CANDIDATES` | Migrate remaining candidates, one at a time, each individually proven | `PHB-05`, user's auto-commit→PR-gated decision |
| `MT069-PHB-07-SELF-HOSTED-RUNNER-PROVISIONING` | Self-hosted runner provisioning + lifecycle | `PHB-04`, user machine-readiness confirmation |
| `MT069-PHB-08-POST-MIGRATION-STABILIZATION` | Post-migration stabilization + final cost/reliability comparison | `PHB-06`, `PHB-07` |

**Every one of these depends on real Phase A prerequisites that are not yet done**
(`TC-10`'s dossiers, `TC-13`'s gap report) — seeding them now records the authorized
intent and dependency graph; it does not make them ready to start. `PHB-01` in
particular cannot actually begin until `TC-10` closes. The stop-gate protocol above
applies regardless of when each one becomes ready.

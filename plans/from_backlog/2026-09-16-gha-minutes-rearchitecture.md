# Mission Plan: GitHub Actions Audit, Re-Architecture, Migration & Stabilization — `aspose.org`

> Reorganized 2026-09-17 for coherence (content preserved, structure and dedup rewritten
> — see the note at the end of this header). Original scattered/duplicated version is in
> git-free local history only; this file is the single current source of truth.

## Status (as of 2026-09-18)

> **READ THIS FIRST (added by Plan File Hardening, 2026-09-18).** The bullets below are a
> chronological, append-only journal: later entries supersede earlier ones, and several
> earlier lines are now factually stale (each such line carries an inline
> `[SUPERSEDED …]` annotation). **The authoritative current state of every task, gate,
> blocker and verification is the "Plan File Hardening" section at the end of this file**
> (Unresolved Work Register, Taskcard Register, Gate Contract, Remaining True Blockers).
> When the journal and that section disagree, that section wins.

- **Deep-dive, production-incident treatment (2026-09-18): `skill-governance.yml`'s
  Windows-job "not yet decided" cost question is a cross-mission entanglement, not an
  independent decision — MT069's own recommendation for it is withdrawn.** The user
  pushed for a second, deeper pass on "why has this not been decided" rather than
  accepting the earlier dossier's framing ("try trigger-demotion before self-hosting").
  Investigation (reading the 2026-08-30 stale-guard-redesign plan file directly, real
  `gh run list` history, and `git_plumb_commit.py`'s live `--wide-findings` default)
  found the real answer, with hard evidence at every step:
  - **Symptom**: `governance-tests-windows` has been `continue-on-error: true` for 19
    days, 5 days past its own planned 2026-09-13 flip date (`R-04`/`TC-SG-07`/`ST-127`).
    MT069 independently flagged its cost (223 min, 14.9% of total, more than the
    required Linux job) as an open question needing a fresh decision.
  - **Real root cause chain, not a single bug**: (1) `TC-SG-20` correctly certified both
    governance workflows "green" on 2026-08-31 — true at the time. (2) A wholly
    unrelated commit (`acd165e07e`, 2026-09-06) introduced the `check_platform_
    capabilities.py` comparison bug this mission's own `TC-14` later fixed — silently
    re-breaking `skill-governance.yml`'s required Linux job and dragging the
    *workflow-level* conclusion back to `failure` for every run through the last one on
    2026-09-11 (verified directly: 15/15 recent runs `conclusion: failure` via
    `gh run list`). Nothing re-validated `TC-SG-20`'s "completed_verified" status
    against this later regression. (3) `R-04`, the reminder meant to gate the flip
    decision, was written referencing the (by-then 6-day-stale) "precondition met"
    claim and was never revisited before its 2026-09-13 due date passed — it is a
    "manual" reminder with no forcing function beyond a session choosing to reopen it.
    (4) ~2026-09-14, an unrelated cost-emergency stopgap disabled all 20 workflows,
    freezing the only mechanism (live runs) that could ever produce the soak evidence
    `TC-SG-07` needs — before the `TC-14` fix even existed. (5) `TC-14` landed today
    (commit `d795f669e6`) as a side effect of *this* mission's cost investigation, not
    anyone working the stale-guard graduation checklist directly — and the workflow has
    never run since, so **zero live evidence exists that a post-fix run is actually
    green at the workflow level**. The flip is not neglected; it is currently
    undecidable with real evidence.
  - **Structural weakness (third instance of the same shape this mission has now
    found)**: nothing in this repo re-validates a `completed_verified` taskcard's
    continued truth when something later touches the same surface — the same "no
    checks on the checks" gap already named for `check_platform_capabilities.py` and
    `check_evaluator_version_bump.py` earlier in this plan's CI-defect-remediation
    section. A second, independent structural gap: no mechanism surfaces "is this exact
    config attribute already the subject of another active initiative's pending
    decision" before a new mission forms its own recommendation about it — the
    MT066/`aspose.org-workflows` PR-merge-conflict check this mission correctly
    performed is the right pattern, but it was applied narrowly to one cross-repo case,
    not generalized to every shared file a mission touches.
  - **Corrected**: `dossiers/skill-governance.md` §§11-13/15-20 and
    `analysis/destination_decision_matrix.json`'s row for this file (both
    `reports/plan_state/`, local-only) — recommendation changed from
    `SPLIT_BETWEEN_HOSTED_AND_SELF_HOSTED` (MEDIUM) to
    `SELF_HOSTED_FOR_REQUIRED_JOB_NO_ACTION_ON_WINDOWS_JOB` (HIGH for the Linux job,
    N/A for the Windows job — explicitly out of MT069's scope). `backlog/REMINDERS.md`'s
    `R-04` corrected to state its own premise is stale and its due date reset from a
    fixed calendar date to "after the next real re-enable of `skill-governance.yml`."
  - **Trigger-demotion, MT069's own earlier cheapest-fix suggestion, is explicitly
    withdrawn**, not just deprioritized: demoting this job's trigger would destroy the
    soak-observation signal `TC-SG-07` needs to graduate it safely — a strictly worse
    outcome than doing nothing, and exactly the "a soft launch that never flips"
    failure mode that plan's own authors named as the thing they were designing against.
  - **What this does NOT do**: re-enable the workflow to manufacture the missing
    evidence (would violate the standing hard constraint for a soft, non-urgent
    verification); independently re-verify the Step 34/plumb-WARN lookback-false-
    positive precondition (no dated log was found this pass — flagged as an honest
    evidence gap, not assumed clean); or build the two generalizable fixes this finding
    points toward (a "held by another initiative" cross-reference checker for shared CI
    files; extending the PHB-03 telemetry to watch soft-launched jobs past their own
    stated soak-end date) — both are real, scoped follow-up engineering, proposed but
    not built, and belong to a decision the user makes, not something to build ad hoc
    while investigating one instance of the problem.
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
     try trigger-demotion first). **[SUPERSEDED 2026-09-18: the "try trigger-demotion
     first" recommendation was WITHDRAWN later the same day — it would destroy the
     soak evidence TC-SG-07 needs; see the "Deep-dive" entry above and HC-10.]**
  - **What remains genuinely open, not executed today**: the new private-repo
    runner (`alienware-m18-wsl2-private`) is running via `nohup ./run.sh &`, not yet
    a systemd service — that step needs the same interactive `sudo ./svc.sh
    install/start` the user ran for the first runner (PHB-07, 2026-09-17). End-to-end
    proof that a real job executes on it is necessarily deferred to a future,
    explicit human-approved re-enable of one or both target workflows — the standing
    hard constraint prohibits dispatching them to test this now.
    **[SUPERSEDED 2026-09-18, first half only: the user ran `sudo ./svc.sh install` /
    `start` (systemd unit `actions.runner.Aspose-aspose.org.alienware-m18-wsl2-private`,
    `enabled`, symlink present under `multi-user.target.wants`); a stale duplicate
    `nohup` listener was found and killed; verified single `Runner.Listener` under
    `runsvc.sh` and API `status: online`. The SECOND half — no real job has ever run on
    this runner — is STILL TRUE and is card HC-02 (blocked on a human re-enable).]**
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
  merged (human-authority boundary respected) **[SUPERSEDED 2026-09-18: all three were
  independently reviewed and merged on 2026-09-18 under the user's explicit
  authorization; #103 only after a destructive regression in it was caught and the
  underlying bug fixed — see item 7 of the master-authorization entry]**. `upstream-monitor.yml`'s
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
  **[SUPERSEDED 2026-09-18, verified against live state: the override token is CONSUMED
  (`reports/overrides/archived/…`, `consumed_by_commit` `68f45c4186`, 2026-09-17); the
  ledger shows `TC-12` `IMPLEMENTED` (2026-09-18T07:05Z), so Phase A is complete; the
  root `MISSION_AUTHORITY.yaml` slot has since been re-bound by other missions (MT068,
  MT071 — see `git log -- MISSION_AUTHORITY.yaml`) while MT069 remains `open` in
  `mission_authority.py list`; the narrative file's own line-4 status ("TC-12 closeout in
  progress") is stale — card HC-01.]**
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
  **[PARTIALLY SUPERSEDED 2026-09-18: the user later issued a comprehensive, itemized
  go-ahead covering the enumerated categories of remaining work; those items were
  executed without per-section stops. That authorization does NOT extend to new work:
  the HC-* cards below are governed by the Gate Contract (GATE-HUMAN) — agent-executable
  where marked, human-gated where they touch production state (enabling a private
  workflow, credentials, runner registration/removal).]**
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
  **[SUPERSEDED: RESOLVED 2026-09-17 — the user decided to convert them to PR-gated; all 4
  were migrated (`PHB-06`).]**
- **Root-slot takeover go/no-go** — if the root `MISSION_AUTHORITY.yaml` incumbent
  becomes locked+open by a different mission before this one's next session, stop and ask
  rather than force-taking-over.
  **[UPDATE 2026-09-18: the root slot HAS since been re-bound by other missions (MT068,
  MT071). MT069 was not force-reclaimed; its archived snapshot under
  `reports/plan_state/MT069-…/mission_authority.yaml` is the durable record and taskcard
  work is unaffected, exactly as this section anticipated. Re-binding remains a human call
  and is not a blocker for any HC-* card.]**

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
   --commit-sha <sha>`. **[DONE: consumed against `68f45c4186`, 2026-09-17 — verified in
   `reports/overrides/archived/`.]**
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

**[SUPERSEDED 2026-09-18 — the paragraph above describes the state at seeding time.
Actual ledger state (`taskcard_cli.py latest`, read live during hardening):
`PHB-01`, `PHB-02`, `PHB-04`, `PHB-06`, `PHB-07` = `IMPLEMENTED`; `PHB-05` = `IN_PROGRESS`;
`PHB-03`, `PHB-08` = `TODO`. Ledger status is NOT the same as verified status — see the
graded re-assessment in the Taskcard Register (e.g. `PHB-03` is `TODO` in the ledger but
its code is committed and tested; `PHB-07` is `IMPLEMENTED` but no real private-repo job
has ever run on the runner it provisioned).]**

---

## Plan File Hardening (2026-09-18) — authoritative current state

Everything above this line is preserved as written (with inline `[SUPERSEDED …]`
annotations where a line had become factually wrong). Everything below is the
hardening layer: it converts the audit findings of the 2026-09-18 execution session and
its follow-up reviews into taskcards, gates, evidence rules and closeout criteria.

**Method (so a cold reader can judge how far to trust this section).** Every "current
state" claim below was re-observed live during hardening, not copied from an earlier
write-up: the taskcard ledger (`taskcard_cli.py latest`), the drift checker
(`check_workflow_drift.py`), the Actions API for both repos (runs, runners, workflow
state), `mission_authority.py list`, the override-token archive, `git log` for
`MISSION_AUTHORITY.yaml`, the failing SEO liveness run's log, and the WSL2 host's
installed tools. Where a fact could not be established this run, it is written as
"not established" — never inferred.

**Scope and limits.** This run edited this plan file only. No source code, workflow,
secret, runner, ledger row or remote was changed, and nothing was committed, pushed or
deployed (the plan file is now a tracked-but-uncommitted modification). New card IDs
(`MT069-HC-nn`, "hardening card") are **plan-registered but not yet seeded into
`taskcards.jsonl`** — seeding them is itself card HC-01. Existing IDs (`TC-*`, `PHB-*`)
are kept unchanged.

### H1. Plan File Hardening Change Log

| # | Where | Change | Why |
|---|---|---|---|
| 1 | Status, first lines | Added a "READ THIS FIRST" pointer making this section authoritative over the journal | The journal contains superseded claims; a cold reader would otherwise act on them |
| 2 | Status, item 9 of master-authorization entry | Annotated "try trigger-demotion first" as WITHDRAWN | Contradicts the later Deep-dive entry (would destroy TC-SG-07 soak evidence) |
| 3 | Status, "What remains genuinely open" | Annotated: systemd install is DONE; "no real job has run" is STILL TRUE | The `nohup` claim was stale; the unproven-job claim was not |
| 4 | Status, PHB-06 entry | Annotated "none merged" as superseded (#99/#100/#103 merged 2026-09-18) | Historical line read as current |
| 5 | Status, "Mission" bullet | Annotated override token CONSUMED (`68f45c4186`), TC-12 `IMPLEMENTED`, root slot re-bound by other missions, narrative status line stale | Four independent stale facts in one bullet |
| 6 | Status, "Execution model" | Annotated: master authorization covered only enumerated items; new HC cards fall under GATE-HUMAN | Prevents treating a past blanket go-ahead as covering new production actions |
| 7 | Human decisions → "Still open" | Marked auto-commit-bot decision RESOLVED; recorded the root-slot re-binding | Listed as open after being resolved / after the anticipated event occurred |
| 8 | Single-go closeout step 7 | Marked override-token consumption DONE with evidence | Instruction re-read as an outstanding step |
| 9 | Phase B skeleton footer | Replaced the seeding-time dependency claim with the live ledger state and pointed to graded re-assessment | It claimed Phase A prerequisites "not yet done" |
| 10 | End of file (this section) | Added H1–H13: change log, audit findings, preserved work, unresolved register, taskcard register (23 existing re-graded + 19 new), lanes, gate contract, evidence contract, verification matrix, repair loop, anti-overclaim rules, closeout criteria, true blockers | Required hardening content; the plan previously had no register of unresolved work, no graded statuses, and no gate that distinguishes "implemented" from "proven" |
| 11 | H2 (AF-24…AF-30), H4, H5.3 (status lines of HC-02/03/04/05/06/07/09/11/16/17), H14 pointer + resume prompt, new §H15 | 2026-09-19 checkpoint requested by the user before a machine restart: true graded statuses, seven new findings, a **correction of my own "2,950 > 1,500" overclaim** (AF-27), and a resume guide | The register still described HC-04…HC-17 as not started while ten of them had commits or live runs; a cold reader would have redone or distrusted finished work |
| 12 | H2 (AF-31…AF-34), H4 (HC-05, HC-06, new HC-20), H5.3 (HC-02/04/05/06 status lines, new card HC-20), H15 pointer, new §H16 | Progress after the user said "resume" (2026-09-19): HC-06 finished, HC-05 nearly finished, and the real runs produced four new findings, one of them a gate defect that would have turned HC-02's first live run red for a reason that has nothing to do with the runner | Records must move with the work; the HC-20 finding in particular changes how HC-02's result must be classified |
| 13 | H2 (AF-35, AF-36), H4 + H5.3 (HC-02 now partially_done), H16 pointer, new §H17 | HC-02 stage 1 executed under the user's recorded go-ahead: one green run on the self-hosted runner, workflow re-disabled | The single most important open claim ("a private job runs on the self-hosted runner") became evidence; its limits are recorded next to it |
| 14 | H2 (AF-37, AF-38), H4 + H5.3 (new cards HC-21, HC-22, HC-23; HC-02 row revised), new §H18 | The maintainer's decisions on the two remaining billed workflows: the Windows leg and `llms-generation.yml` both leave the private repo | The private repo's four largest minute consumers now all have a zero-private-minute destination (design; proof status in §H18), and a real hook defect that the standing red had hidden was found by the move |
| 15 | H2 (AF-39, AF-40, AF-41), H4 + H5.3 (HC-23 done, HC-02 stage 2), new §H19 | The maintainer's "YES" (fix HC-23 first) and "OK" (stage 2): the hook was repaired, the public Windows leg went green, and `skill-governance.yml` ran once on the self-hosted runner and was re-disabled | Two of the three things stage 2 found were invisible on hosted runners: a wrong global git identity on the host, and a test that passed only because another workflow had left full history behind |
| 16 | H2 (AF-41 closes AF-35's inference), H4 + H5.3 (HC-02 → weakly verified; new card HC-24), new §H20 | The confirming stage-2b run was green after the fix, so HC-02's acceptance is met for both private targets | HC-02 can be closed honestly only as *weakly* verified: three claims were never exercised live, so they got their own card instead of being implied |

**Deliberately not changed:** the Phase A design sections, the destination triage, the
usage tables, the state-machine design and all historical journal entries other than the
9 annotated lines (rewriting history would destroy the record of what was believed and
why — the correction trail is itself evidence, per this repo's living-spec convention).
The mission narrative (`plans/missions/MT069-…md`) and the `plans/master-plan.md` row are
separate files and were not edited; their staleness is card HC-01.

### H2. Audit Findings Incorporated

Sources: (a) the 2026-09-18 execution session's findings and reviews as recorded in this
plan's Status journal; (b) live re-observation during this hardening run (commands named
per row); (c) the two prior independent reviews already in the record (`TC-11`,
`review/independent_review.md`; the 2026-09-18 skill-governance deep-dive). "Disposition"
names the card that owns the unresolved part.

| ID | Finding | How established (this run unless noted) | Disposition |
|---|---|---|---|
| AF-01 | The only self-hosted runner was registered against the PUBLIC repo and could never serve the private required checks | Runner `.runner` `gitHubUrl`; commits `c5a78f499f`/`e4ef71f833`; API lists `alienware-m18-wsl2-private` `online` on `Aspose/aspose.org` | **Resolved** (second runner); residual → HC-02, HC-03, HC-04 |
| AF-02 | `upstream-monitor.yml` "PAT gap / issue #94" was a misdiagnosis; real cause = missing gitignored clone cache | Anonymous control test; live repro; commit `72821fbb4a`; public run `35321867511` `fetch_failures: 0` (was 33/33); issue #94 closed | **Resolved**; lesson → AO-2, AO-9 |
| AF-03 | `skill-governance.yml`'s Windows job is the deliberate soft launch of TC-SG-07/R-04; its flip is undecidable without a post-fix live run | `gh run list`: 15/15 recent runs `failure`, last 2026-09-11; fix `d795f669e6` pushed 2026-09-18 12:05 +05:00; workflow `disabled_manually` | **Open** → HC-10 |
| AF-04 | PR #103 would have replaced 250 lines of freshness data with `{}` | PR diff read before merge; re-dispatch produced correct data; merged as `ddb0b0e1a8` | **Resolved**; lesson → AO-12 |
| AF-05 | `llms-generation.yml`'s "Stale check gate" is structurally vacuous (manifest rebuilt immediately before it is checked); scoped-regeneration cost fix is implemented but never run live | Source read of `detect_stale_llms.py`; 3 scratch-repo scenarios; commit `b6327ae052`; workflow disabled | **Open** → HC-12 |
| AF-06 | `launch-dashboard.yml` reads gitignored, cumulative local state — unfixable by relocating; 3 of 5 private push paths structurally dead | Public dispatch produced `NO REPORT: 33/33` (workflow `Launch Dashboard (weekly)` last run `failure`) | **Open** → HC-13 |
| AF-07 | Deployed `seo-keyword-refresh.yml` carried an incident-tested credential fix the local template lacked | Drift diff; commit `4d66250340`; checker `IN_SYNC` twice; once returned `deployed=unresolved` (transient lookup failure reported as `DIVERGED`) | **Resolved**; false-alarm mode → HC-09 |
| AF-08 | The drift checker is advisory-only (no caller in any workflow, hook or gate); `upstream-monitor.yml` is `DEPLOYED_UNAPPROVED` after my documentation-only redeploy; the checker has no approve verb; its tests live in two directories | Checker run (exit 1, "2 of 15 not in sync"); `grep` for callers finds only its own tests; baseline `approved_baseline_sha256` `87fd14f9…` (seeded 2026-09-17T18:30Z) ≠ deployed `ca31bef32dd8…`; `git log` shows the 276-line suite (`scripts/ci/checks/tests/`) predates my 104-line suite (`scripts/ci/tests/`) | **Open** → HC-08, HC-09 |
| AF-09 | The public repo's `GH_TOKEN` secret is dead (401 Bad credentials); the daily liveness probe has been failing since 2026-09-06 (issue #43, 13 comments) | Run `35334880814` log: probe checks `REPO_TOKEN` (passes), `GH_TOKEN` (401), `GOOGLE_API_KEY`; all 8 migrated templates and the SEO templates are REPO_TOKEN-primary (the one `GH_TOKEN \|\|` grep hit is a comment) | **Open** → HC-07 (blast radius is a lost fallback + alert fatigue, NOT current breakage) |
| AF-10 | The design specified a fresh container per job; the two private jobs have no `container:` key and run directly on the WSL2 host, which mounts the Windows filesystem | `grep container:` on both workflows: none; `command -v npm` → `/mnt/c/Program Files/nodejs/npm`; design in `design/self_hosted_architecture.md` | **Open** → HC-03 |
| AF-11 | The runner lifecycle's `DEGRADED` alerting is unbuilt; a push-gated check queues forever if the machine is off; decommissioning is manual | Design doc; no heartbeat code or workflow exists; guide states decommission "not yet automated" | **Open** → HC-04, HC-18 |
| AF-12 | Toolchain compatibility of the two jobs on the runner host is only statically checked | Host lacks `go`, `jq`, `unzip`, `make`, `shellcheck`, `hugo` (Hugo is installed at runtime by `peaceiris/actions-hugo`); `npm` resolves to the Windows binary via interop; only 2 check scripts shell out to `go`/`hugo` and neither is called by the target workflows | **Open** → HC-06 |
| AF-13 | No live evidence exists for any fix or cutover made since the workflows were disabled (TC-14, TC-15, concurrency guards, self-hosting, scoped llms regen) | `gh workflow list --all`: all 20 private workflows `disabled_manually` (only the synthetic Dependency Graph is `active`); `skill-governance.yml` last ran 2026-09-11 | **Open** → HC-02 |
| AF-14 | `PHB-03` is only partially delivered: ledger says `TODO`; code committed; `--live` never run; not wired into any workflow; breaker in warm-up (`N=0/3`); caps unvalidated; CI-health check would permanently flag `upstream-monitor.yml`, whose job is *designed* to fail when drift exists | Ledger; commit `8aa41839da`; dry-run output; `grep` shows no workflow invokes the CLI | **Open** → HC-05 |
| AF-15 | Plan, ledger and narrative disagree (PHB-03 `TODO`; PHB-07 `IMPLEMENTED` but unproven on its real target; narrative line 4 says TC-12 in progress; journal stale) | `taskcard_cli.py latest`; narrative `head`; this file | **Open** → HC-01 |
| AF-16 | The independent review (TC-11) re-verified the *record*, so it missed three diagnoses that later proved wrong (`upstream-monitor`, `launch-dashboard`, the skill-governance Windows-job framing) | Compare `review/independent_review.md` with the three later corrections | **Structural** → AO-2, AO-5; TC-10/TC-11 re-graded; the 16 uncorrected dossiers are still record-consistent only → HC-19 |
| AF-17 | Canary/observation evidence is far short of its own bar: `PHB-05` has 1 scheduled + 1 dispatch run (needs ≥5 scheduled cycles); four migrated workflows have never fired on schedule; the private `install-literal-sweep.yml` has **no runs ever** | `gh run list` per workflow; cron table (first Monday fires: 2026-09-21) | **Open** → PHB-05, HC-14 |
| AF-18 | Structural gaps: nothing re-validates a `completed_verified` card when its surface later changes; nothing detects that another initiative already owns a decision on the same file; manual reminders have no forcing function | Skill-governance deep-dive (R-04 stale for 12 days, undetected) | **Open, needs go/no-go** → HC-15 |
| AF-19 | Merged PR #103 dropped `checked_mode` and `freshness_guard_state` from `data/fleet_freshness_snapshot.json`; readers of those fields are not established | `grep` finds no reader in `scripts/`, `docs/`; writer's origin not established (history search not completed) | **Open, low** → HC-16 |
| AF-20 | The first working sweep found 21 of 33 launched products changed upstream (0 HIGH, 9 MEDIUM, 12 LOW); nothing acts on it (regeneration selection is observability-only) | Run `35321867511`: `{'changed': 21, 'unchanged': 12, 'fetch_failures': 0, 'high_impact': 0, 'medium_impact': 9, 'low_impact': 12}` | **Out of MT069 scope** → HC-17 (route, don't absorb) |
| AF-21 | The runner setup script/guide are only partly tested: parsing, guards and the pipeline up to an invalid token were exercised; a full registration + service install on a fresh machine was not | Test transcript of this session; guide states decommission is manual | **Open** → HC-18 |
| AF-22 | R-04's first flip precondition (no unresolved lookback-class false positive since 2026-08-30) has no dated log to check; R-04 itself points to a plan file outside the repo (`C:\Users\prora\.claude\plans\…`) | Searched; none found; path is outside the repo tree | **Open** → HC-10 |
| AF-23 | GitHub scheduled runs are delayed: the 10:30 UTC cron of `aspose-com-targets-watch.yml` ran at 14:33 UTC | Run list timestamps | **Note** → PHB-05 counting rule (count events by date, never by cron time) |
| AF-24 | **Found during the execution loop (2026-09-18/19).** The PHB-07 "container per job works" proof does not hold for the service-managed runner: under systemd the service `PATH` comes from `<runner>/.path`, which has no Docker, so a `container:` job fails with `docker: command not found`. The earlier proof came from an interactive session | Container smoke test run `35381073902` failed; host probe runs `35380303439`, `35381064675` show `in_container=no`, uid 1000 | **Resolved as a fact** (troubleshooting added to the runner guide; HC-03 target (b) needs no containers); PHB-07 stays `completed_but_weakly_verified` |
| AF-25 | `skill-governance.yml` had **no `workflow_dispatch` trigger**, so HC-11/HC-02's dispatch-one-run procedure could not have been applied to it | Read of the workflow; loop log 2026-09-18T18:42Z | **Resolved** (`workflow_dispatch: {}` added; workflow still `disabled_manually`); live effect → HC-02 |
| AF-26 | `scripts/ci/checks/tests/` (113 tests, including the drift checker's 39) was collected by **no** CI job — an orphan test directory | Commit `c069713946`; `skill-governance.yml` now has a separate step and trigger paths for it; 113 pass locally | **Resolved locally, unproven in CI** (host workflow disabled) → HC-02 |
| AF-27 | **PHB-03 defects found on its first collector run, and a CORRECTION to my own earlier claim.** (a) The CI-health check read "the last N runs" with no time window, so disabled or migrated workflows alerted forever (`skill-governance.yml` 100%, `upstream-monitor.yml` 90%, both from runs made before their fixes). (b) A 30-day collection was compared against WEEKLY caps. **CORRECTION:** the PHB-03 commit message (`8aa41839da`) presented "2,950 > 1,500 cap" as a real finding; it was this unit mismatch (30 days vs a 7-day cap), **not** a cost overrun. (c) Alerts defaulted to the checkout repo, which is the PUBLIC one — private workflow names and minutes would have leaked into a public issue. (d) The collector could read only `--repo`, but `upstream-monitor.yml` lives in the public repo. (e) The rolling history was never persisted between runs. (f) `upstream-monitor.yml` is *designed* to fail when it finds drift | Dry-run output; `workflow_cost_budgets.yaml` comments; 51 tests | **Code fixed** in `94e3a2dfe3`; **not yet deployed or run live** → HC-05 |
| AF-28 | **Operating hazards learned the hard way (not product defects; carried as rules in §H15).** Python text-mode writes produce CRLF and broke a WSL bash script (its log went to `mt069-sim.log\r`); a background WSL process dies with its session; `actions/setup-python`'s tool-cache Python needs `LD_LIBRARY_PATH`; the Bash-tool venv hook false-positives on strings like `python -` or `pip ` inside command text; a heredoc with unbalanced quotes fails to parse and writes nothing; piping a helper through `tail` hid its `COMMIT_OK` | Transcript of the failures | **Recorded** → §H15 operating rules |
| AF-29 | **Ledger-integrity incident (corrected).** HC-01's first commit failed silently (a concurrent-session ref race) and I advanced the ledger citing another session's SHA `257281755a` | Real commit `9ac1744b05` verified on `origin/main`; a correction record was appended to the ledger | **Resolved**; rule: advance the ledger only after `loop_commit.sh` prints `COMMIT_OK` |
| AF-30 | The public `selfhosted-runner-smoke-test.yml` (container job) now fails by construction under the service-managed runner. It is kept as a documented negative control, not deleted | Workflows-repo commit `a549958d` (comment-only STATUS NOTE); drift baseline approved | **Noted** — do not read its red as a runner fault |
| AF-31 | **A real gate defect surfaced by the HC-06 CI-mirror simulation.** `check_grade_presence.py` decides "English content, not a translation" by filename suffix only (`LOCALE_RE`, `.hi.md`), so translations that live in a locale *directory* (`content/docs.aspose.org/fa/…`, `provenance.translation_origin: translator-sync`, no grade by design) are demanded to carry a grade. The mirror failed exactly this one blocking step on 141 files. The real workflow runs the same script on `git diff --name-only $DIFF_BASE...HEAD`, so any push touching such files fails real CI — probably a large part of `content-governance-checks.yml`'s recent 80% failure rate (inferred, not measured per push) | Simulation log + `commands.log`; controls run locally: locale-directory file **fails**, graded English page **passes**, suffix-locale file exempt; source `check_grade_presence.py:23-25` | **Resolved** by card **HC-20** (`8c01cd7b98`, same day): it was first left open because exempting files from a blocking gate needs its own negative controls and a scope this mission had not opened; both were then added (141 → 0 on the exact window, English gate unchanged) |
| AF-32 | **The runners stay online only while a `wsl` session is open.** After the 2026-09-19 restart both services came up, then ~25 minutes later with no terminal open the distro was `Stopped` and both runners `offline`; the availability watch reported it correctly. A systemd service does not keep a WSL instance alive. The pre-restart hours of uptime were most likely propped by two long-running background `wsl` sessions (inference) | `wsl -l -v` = Stopped; runners API `offline`; run `35432016864` ("matching_runners=1 online=0"); a hidden `wsl.exe … sleep infinity` restored both (`online` at ~08:29Z) | **Mitigated for this session only**; permanent fix is a machine-owner decision (Scheduled Task at logon) → guide "Troubleshooting", H15/H16 |
| AF-33 | **Four more telemetry defects found by running it for real (public runs `35430975411` … `35432258368`), all fixed and mutation-checked.** (a) A disabled workflow's stale failure history alerted forever: `skill-governance.yml` read 100% over 28 runs, all from before its fix, and no new run can ever clear that. (b) A zero-minute period was recorded as baseline, so with every private workflow disabled the chain would have recorded only zeros and the first real week after a re-enable would have alerted. (c) The CLI imported `re` nowhere (caught by the tests before it reached a run). (d) `gh api rate_limit` lags — a run that made 407 calls read `5000 → 5000` — so it is not an API-cost measure; the CLI now counts its own `gh` calls (7-day window: 24 calls; 14-day window: 407). Also observed, **not changed**: `content-governance-checks.yml` reads **PASS at an 80% failure rate** because the trip threshold is 90% | Runs above; commits `d93185120f`, `b564f11225`; 59 tests | **Fixed** (a)-(d); the threshold question → HC-15 |
| AF-34 | **`runner-availability-watch.yml`'s "hourly" schedule does not fire hourly.** Scheduled runs were observed at 21:40Z, 00:20Z and 05:52Z (gaps of 2.7 h, 3.7 h, 5.5 h): GitHub delays or drops scheduled runs. HC-04's "alert within 2× the check interval" was therefore proven for the *logic* (dispatch runs) but not for the *cadence* | `gh run list --workflow runner-availability-watch.yml` timestamps | **Caveat recorded on HC-04**; expect hours, not minutes, of detection latency |
| AF-35 | **The first run on the self-hosted runner is dominated by a cold full-history clone.** `actions/checkout` with `fetch-depth: 0` fetched all 25 branches of a ~941 MB repository at ~1.6 MB/s on this machine's network: 848 s of a 1,029 s run. `_work` persists, so later runs should fetch only new objects (**inferred; not yet measured**). While it runs it holds the runner's single slot | Run `35433173048` step timings; `.git` growth sampled on the host (581 → 648 MB in 40 s) | **Noted**; a second run would measure the warm cost (optional stage 1b in §H17) |
| AF-36 | **What "host-direct" actually touched, measured for the first time.** The job (repo code) wrote only under `_work`; the setup actions used two standing caches outside it (`~/.cache/pip`, `~/actions_hugo`); `actions/checkout` *copies* the user's `~/.gitconfig` to a temp dir (a read — the real file's mtime is unchanged since 2026-08-29); zero references to `/mnt/` (the Windows side); zero secrets used, three masked values (the checkout token) | Log scan of run `35433173048` (`evidence/hc02/08_log_scan.txt`, local) | **Noted** — input to the HC-03 isolation decision: exposure was real but small for *this* workflow; it says nothing about other workflows |
| AF-37 | **The pre-commit hook's step numbering has drifted, and the standing red masked it.** `test_precommit_audit_step_numbering.py` fails 3 of its 8 tests **identically on Windows, on Linux and on the dev machine**: block 44 holds two unconditional top-level `_pc_step_end` calls (the "orphaned-block bug class": a check closing out another step's slot), and inline `[Step N]` labels and header comments are off by one from their real summary-table block. The script is LF with `eol=lf` pinned, so it is not a line-ending problem. The hook gained steps on 2026-09-11 and 2026-09-17; the test file was last touched 2026-08-31; `skill-governance.yml` was red for a different reason (TC-14) from 2026-09-06, so nothing noticed | Public run `35441199525` (3 failed / 369 passed); the same 3 on the runner host at `origin/main` `1a941fdcc` and locally; `git log` of the hook and the test | **Open** → new card **HC-23** (a live hook every session commits through: high blast radius). It also means `skill-governance.yml`'s **Linux** job would be red for this reason too — so HC-02 stage 2 should follow HC-23 |
| AF-38 | **The Windows leg, run for real, reproduces the production Windows conditions and passes almost everything.** On `windows-latest`: `core.autocrlf=true`, `preferred cp1252 utf8_mode 0`, Cygwin bash 5.3.15 — exactly the conditions the leg exists to test — with **369 passed and 3 failed** (AF-37) in 226 s. Its own claim "green since 2026-08-30" (in `_git_bash_guard.py`) is therefore stale, not false: the hook changed after that | Run `35441199525`, `evidence` in the log | **Recorded**; the leg is doing its job |
| AF-39 | **A host-direct runner leaks the maintainer's global git config into every job — and it is a wrong identity.** The WSL user's global git identity is `Test <test@example.com>` (unchanged since 2026-08-29). The commit-guard hook requires `Babar Raza <babar.raza@aspose.com>` and blocks a `git commit` from any other identity; on a GitHub-hosted runner there is no global identity, git errors, and the hook fails open. So `test_check_commit_bash_hook.py`'s 11 `git commit` cases failed on the runner and had passed on hosted ones | Live run `35443264874` (11 failed / 1,689 passed); **reproduced on the host with a control**: 11 failed as-is, 50 passed with `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1` | **Fixed in the workflow** (`6b1bbbda2c`), scoped to the two test steps. **A job-level setting would have broken `actions/checkout`** — measured: `git config --global` under `GIT_CONFIG_GLOBAL=/dev/null` fails with "could not lock config file /dev/null". The maintainer's `~/.gitconfig` was not touched. Input to HC-03: this is exactly the class of exposure host-direct isolation leaves open |
| AF-40 | **`test_verify_deploy_trigger.py` needs full git history; the workflow checked out depth 1, and it passed only by accident.** The tests assert on real historical commits (their docstring: the SHAs and every `content_sha` cited must exist locally). With depth 1, 12 of them fail ("`cd86f7ad67…` does not exist in the local repo"). The live run passed them because the self-hosted workspace still held full history from stage 1's `fetch-depth: 0` clone of a *different* workflow. A fresh or cleaned workspace, or a hosted fallback, would have failed | My replay in a shallow scratch clone: +12 failures; the same after `--unshallow`: 1,700 passed | **Fixed** (`6b1bbbda2c`: `fetch-depth: 0`). General rule: on a persistent runner, a green run can depend on state another workflow left behind |
| AF-41 | **The cold-clone cost is confirmed one-time.** Stage 1's `actions/checkout` took 848 s (a cold full-history clone, AF-35); stage 2's, on the same persistent workspace, took **7 s**. The "warm runs fetch incrementally" claim was an inference and is now measured | Step timings of runs `35433173048` and `35443264874` | **Closes** the open question in AF-35 |

### H3. Resolved / Preserved Work

"Preserved" means: do not redo, weaken or silently revert. Each row names the evidence
that would let a reviewer re-verify it. Grade is per H4-Taskcard-Register conventions.

| Item | Evidence | Grade | Preserve note |
|---|---|---|---|
| Phase A investigation and per-workflow dossiers (20) | `reports/plan_state/MT069-…/{inventory,analysis,dossiers,design,review}/`; `TC-11` independent review | `completed_verified` for structure; 4 dossier conclusions later corrected (see TC-10/TC-11 grading) | Keep the correction trail in place; never overwrite a dossier without a dated `CORRECTION` block |
| Real usage baseline (1,494 min, 561 jobs; top-3 = 75.7%) | User's Actions-usage export, 2026-09-18; `usage/usage_dataset.json` | `completed_verified` | This is the only baseline `PHB-08` may compare against |
| Concurrency guards on the top-3 cost drivers | Committed in `d795f669e6`; purely additive 4-line diffs | `completed_but_weakly_verified` (never exercised live) | Keep; precondition for any self-hosted cutover |
| `check_platform_capabilities.py` fix (`TC-14`) and evaluator-version-bump shift-left (`TC-15`) incl. the fail-open repair from `TC-11` | `d795f669e6`; 12/12 and 8/8 targeted tests; full `scripts/ci/tests/` suite recorded in the plan | `completed_but_weakly_verified` | Do not weaken either gate; live proof → HC-02 |
| Public migrations, 9 templates deployed; canary and PR-gated conversions | Commits on `Aspose/aspose.org-workflows` (`a00a2265`, `4e4d883`, `9142da5`, `4ab9d5c3`, …); run IDs in `phase_b/migrations/*.json` | `completed_but_weakly_verified` (see PHB-05/06) | Private originals kept as `workflow_dispatch`-only for rollback; do not delete them |
| `repo_patrol.py` auto-clone fix + DI seams | `72821fbb4a`; 78/78 tests; monkeypatch lint below baseline (39→37); public run `35321867511` | `completed_verified` (unit + live) | Do not re-introduce a PAT/secret for this step |
| Misdiagnosis corrections (docs, both `upstream-monitor.yml` copies, issue #94) | `22214a0b03`; workflows-repo commit `4ab9d5c3`; issue #94 closed | `completed_verified` | Keep the annotated history; the deployed copy still needs its baseline approved → HC-08 |
| `AGENTS.md` §9a dead link | `b4e819fb9e`; override `20260918-075342-AGENTS-md` consumed | `completed_verified` | — |
| `seo-keyword-refresh.yml` backport | `4d66250340`; checker `IN_SYNC` (twice) | `completed_verified` | The deployed copy is the source of truth for this file |
| PRs #99, #100, #103 | Merged as `60a049dd96`, `d31eef31c1`, `ddb0b0e1a8`; #99 claim checked live against PyPI; #103 regression caught | `completed_verified` | Only claim (a) of #99 was externally verified; its debounce counters were not |
| Runner setup script + operator guide | `2928e45b50`; tests listed in AF-21 | `completed_but_weakly_verified` | Keep `--repo`/`--labels` required, never defaulted |
| Private runner registered, systemd-managed, online | Runner API; service symlink; single listener | `completed_verified` for "registered+online"; **not** for "serves jobs" | Never run `run.sh` beside the service (real double-listener incident) |
| Design rules carried forward | This plan, Phase B section | preserved | Soft launch → flip (never a soft launch that never flips); alert, never auto-disable; PR-gated bots never self-merge; REPO_TOKEN-primary; scoped commits through `git_plumb_commit.py`; the hard constraint below |

**Standing invariant, preserved verbatim in force:** no workflow among the 20 in
`Aspose/aspose.org` may be enabled or dispatched — by enable API, `gh workflow enable`,
`gh workflow run`, or any equivalent — without an explicit human go-ahead. The only
sanctioned lifting procedure is card HC-02.

### H4. Unresolved Work Register

One row per open item. "Blocks" says what is prevented until it closes. Type: **A** =
agent-executable now; **H** = needs a human decision/action; **T** = needs time to pass.

| Card | Open item | Type | Priority | Blocks |
|---|---|---|---|---|
| HC-01 | ~~Ledger / plan / narrative reconciliation and seeding of HC cards~~ **DONE 2026-09-18** | A | P1 | — |
| HC-02 | ~~First controlled re-enable~~ **DONE 2026-09-19, weakly verified (§H20; follow-up HC-24):** both private targets ran green on the self-hosted runner, one run each, re-disabled (`35433173048`, `35444938440`); the earlier text below is the stage-1 state, kept as history. **Stage 1 of 3 was:** (§H17): `content-governance-checks.yml` ran green on the self-hosted runner (run `35433173048`, 0 billable minutes) and was re-disabled. **Open (revised 2026-09-19, §H19):** stage 2 `skill-governance.yml` **RAN** (single self-hosted Linux job, 98 s, bills nothing; HC-23 was fixed first): 11 host-state failures found, reproduced with a control and fixed in the workflow, **awaiting one confirming run (stage 2b, needs a go-ahead)**; ~~stage 3 `llms-generation.yml`~~ — **gone**: it is public now, so no private enable is needed; and the live exercise of the HC-20 fix, evaluator-version-bump and the concurrency guard (optional stage 1b) | H | P0 | live proof of TC-14, TC-15, guards; HC-10; PHB-08 |
| HC-03 | **PARTIAL 2026-09-19.** Agent part DONE (threat model, measured host facts, options, decision (b) recorded, time-boxed interim exception for the single HC-02 proof run). **Open:** the target-state distro setup, which needs a human with `sudo` (B-2) | H (sudo) | P0 | nothing for the single proof run; leaving any workflow enabled |
| HC-04 | ~~Runner-availability alerting~~ **DONE 2026-09-18** (`ebef471a01`; pass/alert/dedup/recover/debounce all proven live) | A | P0 | — |
| HC-05 | **NEARLY DONE 2026-09-19 (see §H16).** Collector hardened (`94e3a2dfe3`, `d93185120f`, `b564f11225`, `71da449f54`); weekly public workflow deployed (workflows-repo `cfa6e404`, `3de0897f`); dry-run, live, history-restore and alert-issue paths proven on real runs. **Open:** the first *scheduled* fire (Mon 2026-09-21 04:41 UTC) — `PHB-03` stays `IN_PROGRESS` until it is green; cap re-derivation and 3-period warm-up are time-gated | T | P1 | PHB-08's evidence |
| HC-06 | ~~Toolchain/compat verification~~ **DONE 2026-09-19** (ledger `IMPLEMENTED`, graded `completed_but_weakly_verified`): static enumeration + host probe + CI-mirror simulation on the runner host (PASS 16 / FAIL 1 / WARN 6; 0 tool-missing signatures). The one FAIL is a real gate defect, not a host fault → **HC-20** | A | P1 | — |
| HC-20 | ~~`check_grade_presence.py` flags locale-directory translations (AF-31)~~ **DONE 2026-09-19** (`8c01cd7b98`; 141 → 0 on the simulation's exact diff window, English gate unchanged) | A | P1 | — |
| HC-21 | ~~Move the billed Windows governance leg out of the private `skill-governance.yml`~~ **DONE 2026-09-19** (`c38cd936a4`; public workflow `governance-tests-windows.yml`, run `35441199525`: 369 passed / 3 failed, the 3 = HC-23) | A | P1 | — |
| HC-22 | ~~Move `llms-generation.yml` to the public repo~~ **DONE 2026-09-19** (`c38cd936a4`; public `llms-generation.yml`, run `35441201382` green; private original narrowed to dispatch-only) | A | P1 | — |
| HC-23 | ~~Repair `pre-commit-audit.sh` step numbering drift (AF-37)~~ **DONE 2026-09-19** (`6b6b1d13d9`, maintainer-approved override token; Windows leg 369+3 failed → **372 passed**, alert #50 closed by the workflow itself) | A | P1 | — |
| HC-24 | Stage 1b: exercise the HC-20 fix, evaluator-version-bump and the concurrency guard live on `content-governance-checks.yml` (one enable-window, needs a go-ahead) | H | P2 | upgrading HC-02 from weakly verified |
| HC-07 | ~~Dead `GH_TOKEN` secret~~ **DONE 2026-09-18** (`dc36f0e4fa`; credential-free option: the dead fallback is now an advisory warning; issue #43 closed). A green *scheduled* liveness fire is not yet observed | A | P1 | — |
| HC-08 | ~~Approve the `upstream-monitor.yml` deployed baseline~~ **DONE 2026-09-18** (`c71d3db64b`) | A | P1 | — |
| HC-09 | ~~Make the drift checker a real gate~~ **DONE 2026-09-18** (`c069713946`, baseline `40aa0358b3`; live pass / forced-red→#47 / recovery). Its CI wiring of the orphan tests is proven only when HC-02 runs `skill-governance.yml`; a real scheduled fire is not yet observed | A | P2 | — |
| HC-10 | Stale-guard graduation (TC-SG-07/R-04): re-premise, durable criteria, post-fix live evidence | H + T | P1 | flipping the Windows leg / `--wide-findings` |
| HC-11 | ~~First-live-run evidence-capture and rollback protocol~~ **DONE 2026-09-18** (`ebef471a01`; every observation command verified on public runs; private enable/disable steps marked unexercised) | A | P0 | — |
| HC-12 | `llms-generation.yml`: make the stale-check gate non-vacuous | A | P2 | genuine drift detection |
| HC-13 | `launch-dashboard.yml`: redesign vs retire | H (product) | P3 | — |
| HC-14 | Observe first scheduled runs of the migrated workflows not yet seen on schedule | T | P2 | PHB-05/06 grade upgrades |
| HC-15 | Generalised fixes: cross-initiative conflict check; soft-launch deadline watch; re-validation of `completed_verified` | H (go/no-go) | P2 | recurrence prevention |
| HC-16 | ~~Fleet-snapshot dropped fields~~ **DONE 2026-09-18** (no reader found; nothing to restore) | A | P3 | — |
| HC-17 | ~~Route the 21 upstream-drifted products~~ **DONE 2026-09-18** (local backlog item ST-202; nothing regenerated) | A (route only) | P3 | — |
| HC-18 | Guide/script: fresh-machine end-to-end test; decommission tooling | A (+H for `sudo`) | P3 | — |
| HC-19 | Reproduction-based re-review of the dossiers' root-cause claims (16 of 20 never reproduced) | A | P2 | trust in TC-10/TC-11 and in every destination that rests on an un-reproduced diagnosis |
| PHB-05 | Canary observation: ≥5 scheduled cycles (1 seen) | T | P2 | `IMPLEMENTED` for PHB-05 |
| PHB-08 | Final cost/reliability comparison (due 2026-10-08) | T | P2 | mission closeout |

### H5. Taskcard Register

**Status vocabulary (the only valid values):** `completed_verified` (proven by evidence
that meets §H8 and is still current), `completed_but_weakly_verified` (done, but the proof
is local/synthetic/record-based or predates a later change), `partially_done`,
`not_attempted`, `claimed_unproven` (asserted done, no evidence found), `blocker`
(cannot proceed without a named human action), `follow_up` (valid, deliberately deferred,
needs a go/no-go). The ledger's own `IMPLEMENTED` is **not** a status in this vocabulary —
it records that a session finished work, not that the work is proven (§H11, AO-4).

Global rules referenced by every card: **GA-1** (allowed), **GF-1…GF-7** (forbidden),
**GS-1…GS-4** (stop) — defined once in §H7. A card's own Allowed/Forbidden/Stop lines are
*in addition to* those.

#### H5.1 Existing cards — graded re-assessment (23)

| Card | Ledger | Graded status | Basis (what was and was not established) | Follow-up |
|---|---|---|---|---|
| TC-01 | IMPLEMENTED | completed_verified | Inventory reviewed by TC-11 against live `gh api` | — |
| TC-02 | IMPLEMENTED | completed_verified | Disablement confirmed by the user | — |
| TC-03 | IMPLEMENTED | completed_but_weakly_verified | Local-only validation by design; two of its suspected diagnoses (HP-05 PAT gap, HP-11 missing pip) later proved wrong | AO-2 |
| TC-04 | IMPLEMENTED | completed_verified | Reconciled against the user's real Actions export (1,494 min) | — |
| TC-05 | IMPLEMENTED | completed_but_weakly_verified | Failure counts are real; the `upstream-monitor` and `launch-dashboard` root-cause classifications were wrong | AO-2 |
| TC-06 | IMPLEMENTED | completed_verified | No contradicting evidence found; not re-audited in this run | — |
| TC-07 | IMPLEMENTED | completed_but_weakly_verified | Destination matrix corrected three times after the fact (skill-governance, upstream-monitor, launch-dashboard) | AO-2, AO-5 |
| TC-08 | IMPLEMENTED | completed_but_weakly_verified | Design ≠ implementation: no per-job container, label set differs, `DEGRADED` lifecycle unbuilt | HC-03, HC-04 |
| TC-09 | IMPLEMENTED | completed_verified | Executed and proven live by PHB-04/05/06 | — |
| TC-10 | IMPLEMENTED | completed_but_weakly_verified | 4 of 20 dossiers later needed material correction | AO-5 |
| TC-11 | IMPLEMENTED | completed_but_weakly_verified | Found and fixed 7 real issues, but re-verified the record rather than reproducing behaviour (AF-16) | AO-2, AO-5 |
| TC-12 | IMPLEMENTED | completed_but_weakly_verified | Verdict is a 2026-09-17 Phase A snapshot; `final_report.md` covers Phase A only; narrative status stale | HC-01, Closeout |
| TC-13 | IMPLEMENTED | completed_verified | Proposal + `recurring-candidate` gap report filed | HC-05 (implementation) |
| TC-14 | IMPLEMENTED | completed_but_weakly_verified | Unit-tested; never run in CI since the fix (workflow disabled) | HC-02 |
| TC-15 | IMPLEMENTED | completed_but_weakly_verified | Same as TC-14 | HC-02 |
| PHB-01 | IMPLEMENTED | completed_but_weakly_verified | Lightweight per-migration JSON record used across the migrations; behaviour under interruption/resume not evidenced | HC-01 |
| PHB-02 | IMPLEMENTED | completed_but_weakly_verified | Reconciliation is per-migration and manual; the design's *recurring* regression control does not exist | HC-05 |
| PHB-03 | **TODO** | partially_done | Code + 54 tests committed (`8aa41839da`), dry-run smoke run; not wired, never `--live`, breaker cold, false-alarm design | HC-05, HC-01 |
| PHB-04 | IMPLEMENTED | completed_verified | Machinery canary executed live (run records under `phase_b/`) | — |
| PHB-05 | IN_PROGRESS | partially_done | 1 of ≥5 scheduled cycles observed | PHB-05 card below |
| PHB-06 | IMPLEMENTED | completed_but_weakly_verified | 4 bots + PRs proven live; the recorded `upstream-monitor` proof carried the wrong root cause; 3 of 4 have exactly 1 scheduled success; `install-literal-sweep` 0 | HC-14 |
| PHB-07 | IMPLEMENTED | completed_but_weakly_verified | Public-repo runner proven with a real container job; private runner registered + systemd + online, **no job ever executed on it** | HC-02, HC-03, HC-04 |
| PHB-08 | TODO | not_attempted | Time-gated; comparison is only valid under conditions in its card | PHB-08 card below |

#### H5.2 Updated existing cards (full contract)

##### MT069-PHB-05-CONTENT-CANARY-ASPOSE-COM-TARGETS-WATCH — canary observation
- **Source audit finding:** AF-17, AF-23. **Why it matters:** the canary is the only proof that the public-migration mechanism keeps working unattended; one run is an anecdote.
- **Current status:** partially_done (ledger `IN_PROGRESS`). **Priority:** P2. **Lane owner:** L-CI (observer: primary agent session). **Type:** T.
- **Required work:** observe ≥5 scheduled cycles on 5 distinct UTC dates; confirm the private original stays silent; confirm attribution three ways (public runs land, private silent, billing trend once measurable). **Counting rule:** only `event == schedule` runs count, one per UTC calendar date of `createdAt`; a delayed run counts on its actual date (observed: the 10:30 UTC cron ran 14:33 UTC); `workflow_dispatch` runs never count; a failed scheduled run is observed but blocks closeout until classified.
- **Required verification:** `gh run list --repo Aspose/aspose.org-workflows --workflow aspose-com-targets-watch.yml --event schedule`; `gh run list --repo Aspose/aspose.org --workflow aspose-com-targets-watch.yml --limit 1` (must show `createdAt` ≤ 2026-09-13T14:35:39Z, the last pre-disable private run).
- **Required evidence:** ≥5 run IDs with UTC dates + conclusions (E-API); the private-silence query output; recorded in `phase_b/migrations/aspose-com-targets-watch.json` and reminder R-07 (due 2026-09-24).
- **Acceptance criteria:** ≥5 scheduled successes on 5 distinct UTC dates, zero private runs after 2026-09-13, no unclassified failure. Earliest possible: 2026-09-22 UTC, after that day's scheduled run lands (cycles on 09-18…09-22; GitHub may delay a run by hours).
- **Stop conditions:** the private original fires again (something re-enabled it) → stop and tell the human; two consecutive public failures → Repair Loop (§H10).
- **Allowed actions:** GA-1 read-only observation; ledger advance on success. **Forbidden actions:** dispatching to "speed up" the count; GF-1.
- **Dependencies:** time only. **Closeout rules:** advance ledger to `IMPLEMENTED` only after the acceptance criteria are met and evidence is recorded; then mark R-07 closed.

##### MT069-PHB-08-POST-MIGRATION-STABILIZATION — final cost/reliability comparison
- **Source audit finding:** AF-13, AF-14; usage baseline (H3). **Why it matters:** this is the mission's actual success metric — and the easiest one to fake by accident: all 20 private workflows are disabled, so *any* post-migration usage read today is ≈0 and would look like a 100% saving.
- **Current status:** not_attempted (ledger `TODO`). **Priority:** P2. **Lane owner:** L-TEL. **Type:** T (due 2026-10-08, reminder R-08).
- **Required work:** compare a fresh usage export against the 1,494-min baseline **only over a period in which every workflow in scope was enabled** (i.e. after HC-02, and after any workflow the human chose to keep disabled is excluded by name); report per-workflow minutes, expected zero-billed self-hosted jobs, the `llms-generation.yml` scoped-regeneration effect, the untouched Windows job, and before/after failure rates for the same workflows. If the window includes disabled workflows, the only valid output is `NOT_MEASURABLE` plus what is needed to measure.
- **Required verification:** export and API cross-check (`workflow_usage_collector` proxy vs the export; self-hosted jobs must show zero billable time — e.g. run `timing.billable` empty); explicit measurement-validity statement listing which workflows were enabled for how many days.
- **Required evidence:** export file path + hash, collector output, the validity statement, written into `final_report.md` (Phase B section).
- **Acceptance criteria:** comparison published with its validity statement, or `NOT_MEASURABLE` recorded with reasons; no savings figure appears anywhere without it.
- **Stop conditions:** window contains disabled workflows → do not publish a saving; baseline export not comparable (different scope/period definition) → stop and state the mismatch.
- **Allowed actions:** GA-1; edit `final_report.md`. **Forbidden actions:** projecting savings from design intent; comparing against a partial month without saying so; GF-6.
- **Dependencies:** HC-02, PHB-05, HC-05. **Closeout rules:** ledger `IMPLEMENTED` only with the validity statement present; close R-08.

#### H5.3 New hardening cards (19)

Ledger `task_id`s are `MT069-HC-nn-<SLUG>` (seeded 2026-09-18 by HC-01): 01 `LEDGER-PLAN-NARRATIVE-RECONCILIATION`, 02 `FIRST-CONTROLLED-REENABLE-LIVE-PROOF`, 03 `RUNNER-ISOLATION-MODEL`, 04 `RUNNER-AVAILABILITY-ALERTING`, 05 `FINISH-PHB03-TELEMETRY`, 06 `SELFHOSTED-TOOLCHAIN-COMPAT-VERIFICATION`, 07 `DEAD-GH-TOKEN-SECRET`, 08 `UPSTREAM-MONITOR-BASELINE-APPROVAL`, 09 `DRIFT-CHECKER-REAL-GATE`, 10 `STALE-GUARD-GRADUATION-TC-SG-07`, 11 `FIRST-LIVE-RUN-EVIDENCE-PROTOCOL`, 12 `LLMS-STALE-CHECK-NON-VACUOUS`, 13 `LAUNCH-DASHBOARD-REDESIGN-OR-RETIRE`, 14 `FIRST-SCHEDULED-RUN-OBSERVATION`, 15 `STRUCTURAL-FIXES-GO-NO-GO`, 16 `FLEET-SNAPSHOT-DROPPED-FIELDS`, 17 `ROUTE-UPSTREAM-DRIFTED-PRODUCTS`, 18 `RUNNER-GUIDE-FRESH-MACHINE-DECOMMISSION`, 19 `DOSSIER-ROOT-CAUSE-REPRODUCTION-REVIEW`. The plan's short `HC-nn` names are used everywhere else.

##### MT069-HC-01 — Reconcile ledger, plan and mission narrative; seed the HC cards
- **Source audit finding:** AF-15. **Why it matters:** status is only useful if the three records agree; today `PHB-03` reads `TODO` while its code is committed, and the mission narrative still says Phase A closeout is "in progress".
- **Current status:** completed_verified — **DONE 2026-09-18 (loop iteration 2).** Evidence: 19 cards seeded (`taskcard_cli.py seed`, all `seeded`, none skipped); `PHB-03` advanced `TODO → IN_PROGRESS` citing `8aa41839da` (deliberately not `IMPLEMENTED`); mission narrative status block rewritten with the superseded text quoted, its two stale bullets annotated; `plans/master-plan.md` row ("IN PROGRESS") checked and correct; `check_plan_taskcard_completeness.py` exit 0. **Priority:** P1. **Lane owner:** L-GOV.
- **Required work:** (1) seed HC-01…HC-19 into `taskcards.jsonl` via `taskcard_cli.py seed --from-json` with a batch file shaped like the existing `_taskcard_seed_batch*.json`; (2) advance `PHB-03` `TODO → IN_PROGRESS` citing `8aa41839da` (not `IMPLEMENTED` until HC-05 closes); (3) fix `plans/missions/MT069-…md` line 4 status and add a pointer to §H; (4) leave the `plans/master-plan.md` row unless its wording is wrong (it reads "IN PROGRESS", which is correct); (5) run `check_plan_taskcard_completeness.py`.
- **Required verification:** `taskcard_cli.py latest` lists the 19 new IDs and `PHB-03 IN_PROGRESS`; completeness checker exit 0, or the exact reason documented; narrative diff limited to status/pointer lines.
- **Required evidence:** CLI output (E-LOCAL), commit SHA(s) of the narrative change (E-COMMIT), updated `EVIDENCE_BUNDLE.md` index.
- **Acceptance criteria:** ledger ID-set equals the register's; no card is `IMPLEMENTED` unless its H5.1 grade is `completed_verified`, or `completed_but_weakly_verified` with a linked follow-up card.
- **Stop conditions:** CAS error repeats after one fresh-read retry (GS-2); the CLI rejects a field — report, never hand-edit the JSONL.
- **Allowed actions:** `taskcard_cli.py seed/advance/claim`; edit the narrative's status lines; `session_ledger.py adopt`; commits via GATE-COMMIT. **Forbidden actions:** hand-editing `taskcards.jsonl`; marking `PHB-03` `IMPLEMENTED`; editing `MISSION_AUTHORITY.yaml`; GF-*.
- **Dependencies:** none. **Closeout rules:** ledger snapshot saved to the evidence bundle; register/ledger diff is empty.

##### MT069-HC-02 — First controlled re-enable and live proof of the cutover
- **Source audit finding:** AF-13, AF-01. **Why it matters:** since 2026-09-11 nothing has executed live — not the TC-14/TC-15 fixes, the concurrency guards, the scoped `llms` regeneration, nor the self-hosted runner (AO-1, AO-3). Every "fixed" in this mission is currently unproven at the level that matters.
- **Current status:** completed_but_weakly_verified — **DONE 2026-09-19 (ledger `IMPLEMENTED`; follow-up card HC-24; full record §H17, §H19, §H20).** Both private targets have now run on the self-hosted runner, each under its own recorded go-ahead, one run each, re-disabled afterwards: `content-governance-checks.yml` (run `35433173048`, green, 36/36 steps) and `skill-governance.yml` (run `35443264874` found two real problems; after the fix, **confirming run `35444938440` is green: 17/17 steps, 1,700 passed / 45 skipped / 0 failed plus 113 passed, `billable = {}`**). `llms-generation.yml` and the Windows leg are public and proven there. **Weakly verified because** the HC-20 fix, TC-15's evaluator-version-bump behaviour and the concurrency guard were never exercised live (a dispatch diffs only `HEAD~1`) → HC-24. *Earlier status text, kept:* partially_done — **stage 2 RAN 2026-09-19 (§H19): `skill-governance.yml` on the self-hosted runner — 98 s, `billable = {}`, every setup/check step green, 1,689 tests passed and 11 failed; the failures were host state, reproduced with a control and fixed (`6b1bbbda2c`) but NOT yet re-proven in CI — that needs a second run (stage 2b) and the maintainer's go-ahead.** Stage 3 no longer exists (`llms-generation.yml` is public). *Earlier status text, kept:* **stage 1 of 3 DONE 2026-09-19 (ledger `IN_PROGRESS`; full record in §H17).** Under the user's recorded go-ahead (`content-governance-checks.yml` only, one run, then re-disable) run `35433173048` — a `workflow_dispatch` on proof branch `mt069-live-proof-20260919` at `08b6d8e8f9` — **succeeded, all 36 steps green, on `alienware-m18-wsl2-private` (runner 21), 3 s queue latency, `timing.billable = {}` (0 Actions minutes)**, 1,029 s of which 848 s was a one-time cold clone (AF-35). Enabled 08:52:20Z, disabled 09:09:51Z (17.5-minute window); the private repo is back to 20 × `disabled_manually`, nothing queued, proof branch deleted. **Not proven by this run:** the HC-20 fix and the evaluator-version-bump behaviour (a dispatch diffs only `HEAD~1`, so the steps saw "No content files changed" / "none changed"), the concurrency guard cancelling, TC-14 (`skill-governance.yml` not run), scoped `llms` regeneration (not run). Stages 2 and 3 need their own go-aheads. *Earlier status text, kept:* blocker (the standing hard constraint requires an explicit human go-ahead) — **as of the 2026-09-19 checkpoint: NOT STARTED; nothing has been enabled or dispatched.** The user's go-ahead for *this card only* is recorded verbatim in §H14 (E-HUMAN). Prerequisites: HC-03 decision ✓ recorded (target (b), with a time-boxed interim exception for the single proof run), HC-04 ✓, HC-11 ✓, **HC-06 ✓ done 2026-09-19** — so every prerequisite the plan set is met and the only remaining gate is the user's explicit yes/no naming `content-governance-checks.yml` (§H15.5 step 4; §H16). **Read HC-20 first:** the simulation showed the workflow's `check_grade_presence` step fails on any diff that contains locale-directory translations, so a proof run's red may be that known defect and not the runner (classify it (a), not (b)/(c)). The runners must also be online, which needs a live `wsl` session (AF-32). **Priority:** P0. **Lane owner:** L-RUN (human performs the enable/disable; agent observes and records).
- **Required work:** after HC-03, HC-04, HC-06, HC-11 are done and the human states the go-ahead **naming the workflow**: enable exactly one workflow first — `content-governance-checks.yml` (largest cost driver, 36.5%, no soft-launched sibling; supports `workflow_dispatch`) — and trigger exactly one run as HC-11's protocol prescribes; observe, classify every failure as (a) genuine finding, (b) runner/toolchain defect, (c) workflow bug; decide with the human whether to keep it enabled. Repeat for `skill-governance.yml` (the Windows job stays GitHub-hosted). Later stage: `llms-generation.yml` (GitHub-hosted) to prove scoped regeneration.
- **Required verification:** job metadata `runner_name == alienware-m18-wsl2-private` (a silent fallback to a GitHub-hosted runner must be impossible to miss); head SHA equals the intended commit; per-step conclusions; `timing.billable` empty for the self-hosted job; for `skill-governance.yml` the `check_platform_capabilities` step green (TC-14) and evaluator-version-bump behaving as designed (TC-15).
- **Required evidence:** E-LIVE bundle per §H8 for each run; the human's go-ahead text pasted verbatim into the bundle.
- **Acceptance criteria:** ≥1 complete run of each target workflow on the private runner with a recorded conclusion and every failing step root-caused under GATE-ROOTCAUSE; queue latency measured; the state the human chose afterwards recorded; TC-14/TC-15/PHB-07 grades upgraded *only* to what the evidence supports.
- **Stop conditions:** runner offline or job queued past HC-11's threshold; any step touching paths outside the workspace (see HC-03); a secret visible in a log; failures exceed HC-11's abort count → human disables, agent reports.
- **Allowed actions (agent):** read-only `gh run view/list`, `gh api …/timing`; evidence capture. **Forbidden actions:** the agent enabling or dispatching (GF-1); enabling more than one workflow at a time; leaving a workflow enabled while HC-04 alerting is inactive.
- **Dependencies:** HC-03, HC-04, HC-06, HC-11 + human go-ahead. **Closeout rules:** evidence bundle entry per run; grades updated in H5.1 with run IDs; if the human re-disables, record why.

##### MT069-HC-03 — Runner isolation model
- **Source audit finding:** AF-10. **Why it matters:** the design promised a fresh container per job; the private jobs run repo code directly on the maintainer's daily-driver host, as their user, with the Windows drive reachable (`npm` already resolves to `/mnt/c/…`) and a persistent `_work` directory. Direct-push (no fork PRs) removes the classic untrusted-PR vector but not a compromised dependency or a bad commit.
- **Current status:** partially_done (ledger `IN_PROGRESS`, 2026-09-19). **Done (agent part):** threat-model delta with *measured* host facts (host-direct, uid 1000, `/mnt/c` readable, WSL interop enabled, state persists across jobs — public runs `35380303439`, `35381064675`); options (a)/(b)/(c) with costs; decision recorded in `docs/operations/self-hosted-runner-setup.md` "Isolation model": target **(b)** dedicated WSL distro with automount and interop off, with a **time-boxed interim exception** letting only the single observed HC-02 proof run use (c); the container option was disproved for the service-managed runner (AF-24). **Not done:** the human `sudo` steps of (b) — marked *untested as written* in the guide — and the negative control for the chosen model (reading a `/mnt/c` canary must fail), which can only be run after (b) exists (B-2). **Priority:** P0. **Lane owner:** L-RUN. **Type:** H (decision) + A (implementation).
- **Required work:** write the threat-model delta (design vs reality); evaluate at least: (a) `container:` per job (fresh filesystem, no host mounts; costs: image choice, JS-action node requirement, Docker Desktop dependency), (b) a dedicated WSL distro/user for the runner with `[interop] enabled=false` and `[automount] enabled=false` in `/etc/wsl.conf` (needs root and a distro restart — human), (c) host-direct with mitigations (low-privilege user, clean workspace per run, `--ephemeral`). Record a recommendation labelled as a leaning, not a finding; the human decides.
- **Required verification:** negative control for the chosen model — as the runner's user, reading a canary path under `/mnt/c` must fail; and two consecutive runs on the **public test runner** (authorised) must show a marker file written in run 1 absent in run 2.
- **Required evidence:** config diff, negative-control transcript, two run IDs (E-LOCAL, E-LIVE).
- **Acceptance criteria:** decision recorded here and in `docs/operations/self-hosted-runner-setup.md`; both controls pass; `TC-08`/`PHB-07` re-graded.
- **Stop conditions:** any option needs `sudo` → hand the exact commands to the human (GS-1); an option would disturb the pre-existing `gitlab-runner` / seo-intelligence containers on the same Docker Desktop → stop.
- **Allowed actions:** read-only inspection, doc edits, public smoke-test template changes, drafting `wsl.conf` diffs. **Forbidden actions:** editing `/etc/wsl.conf` or Docker Desktop settings without the human; touching the existing containers; GF-*.
- **Dependencies:** none (feeds HC-02). **Closeout rules:** design doc reconciled with reality.

##### MT069-HC-04 — Runner-availability alerting
- **Source audit finding:** AF-11. **Why it matters:** an offline self-hosted runner leaves push-triggered checks queued indefinitely — a hung commit status with no signal — and this runner lives on a machine that is not always on.
- **Current status:** completed_verified — **DONE 2026-09-18, commit `ebef471a01`** (ledger `IMPLEMENTED`). Template `scripts/ci/deployed-workflows/runner-availability-watch.yml` (hourly `17 * * * *`; alert issue label `runner-offline` in the public repo) deployed to `Aspose/aspose.org-workflows`; drift baseline seeded. All five paths proven live: online/no-alert `35382618609` (proves `REPO_TOKEN` can read the private repo's runners: matching=1 online=1); alert `35382743233` → issue #46; dedup `35382828640` (comment, no second issue); recovery `35382884301` (#46 closed 18:54:34Z); debounce `35382970613` (first observation warns, opens nothing). Two defects were caught and fixed before deploy (shell injection through a dispatch input; missing `actions:read`). **Caveat kept honest:** the *queued-run age* check (`max_queue_minutes`) is unexercised — it needs a private workflow to be enabled (HC-02); the thresholds are proposals. **Expect after a restart:** if the machine stays off for more than about two hourly checks, this workflow will open a `runner-offline` issue — that is the alerting working, not a fault. **Proven on the real event (2026-09-19):** it opened #48 at 21:40Z on 2026-09-18 when the machine restarted, reported `matching_runners=1 online=0` again at 08:26Z when WSL had stopped (AF-32), and its recovery path closed #48 at 08:29:44Z (run `35432110873`) once the runner was back. **Caveat (AF-34):** GitHub delays or drops scheduled runs — observed gaps of 2.7 h, 3.7 h and 5.5 h — so real detection latency is hours, not "2× the interval". **Priority:** P0. **Lane owner:** L-TEL.
- **Required work:** a scheduled, read-only public-repo workflow (GitHub-hosted, free minutes) calling `GET /repos/Aspose/aspose.org/actions/runners`, opening/updating **one deduped issue** when the `gha-private-native` runner is not `online` for N consecutive checks, and (once workflows are enabled) flagging queued runs older than a threshold. Thresholds are proposals to be recorded as such. Reuse the dedup pattern of `aspose-com-targets-watch.yml`. First establish whether `REPO_TOKEN` may read that endpoint (not established: it needs repo-admin scope).
- **Required verification:** (1) endpoint reachable with `REPO_TOKEN` in a dispatched run; (2) control: point the check at a non-existent runner label → alert opens; (3) recovery path → issue closed or commented; (4) no alert while online.
- **Required evidence:** run IDs for the pass / alert / recover paths; issue numbers.
- **Acceptance criteria:** alert within 2× the check interval for an absent runner; single issue on repeats; documented in the guide.
- **Stop conditions:** `REPO_TOKEN` lacks the scope → stop and report (credential decision → HC-07, GS-1); never escalate token scope.
- **Allowed actions:** new template under `scripts/ci/deployed-workflows/`, public-repo deploy (pre-authorised for this mission), drift-checker registration, tests. **Forbidden actions:** enabling private workflows; storing runner tokens; auto-disabling anything on alert (alert-only invariant); GF-*.
- **Dependencies:** none hard (HC-08 keeps the drift baseline honest). **Closeout rules:** template and deployed copy in sync (checker green).

##### MT069-HC-05 — Finish PHB-03 (telemetry + circuit breaker)
- **Source audit finding:** AF-14. **Why it matters:** the telemetry runs only when someone remembers to run it; its breaker has no history; and as built its CI-health check would alert forever on `upstream-monitor.yml`, whose job is *designed* to fail when drift exists.
- **Current status:** partially_done (ledger `IN_PROGRESS`; `PHB-03` also stays `IN_PROGRESS`) — **UPDATED after the resume, 2026-09-19 (details in §H16): one acceptance criterion is left, and it can only be met by the calendar.** Now also done and proven on real public runs: (1) the weekly workflow `workflow-cost-telemetry.yml` (template `scripts/ci/deployed-workflows/`, deployed as workflows-repo `cfa6e404` then `3de0897f`, drift baseline approved); (2) `--live` (run `35431326742`: history artifact uploaded, 0 checks tripped, no issue opened); the history chain (run `35431835805` restored it from the artifact, anomaly `N=1/3`); alert issues to a real API (`open_alert_issue` created #49, the second call commented instead of duplicating, then closed); `upstream-monitor` correctly scored "failed only by design" (2 runs) with no false alert; a real API-call counter (7-day window: 24 calls, 14-day: 407) replaces the lagging `rate_limit` reading. Two defects were found and fixed by actually running it (AF-33). **Still open:** the first *scheduled* fire, Mon 2026-09-21 04:41 UTC — it must also confirm the `github.event_name == 'schedule'` expression that makes scheduled runs live (a dispatch cannot prove it); then `PHB-03 → IMPLEMENTED`. The test artifacts were deleted so the chain starts empty; note that the first recorded weekly period may be a partial pre-disable week — discard the artifact if it skews the baseline. *Earlier status text, kept:* partially_done, 2026-09-19. **Done and on `origin/main` (commit `94e3a2dfe3`):** items (4), (5), (6)-partial of the required work — static caps marked PROVISIONAL and given a `cap_period_days` so a 30-day collection is scaled instead of compared with weekly caps (AF-27b); a 14-day CI-health window (a workflow with fewer than 5 runs in the window is `INACTIVE`, not an alert); `ci_health_by_design_failing_steps` so `upstream-monitor.yml` counts as healthy when its **only** failing step is the by-design "Fail the job if drift was found" step (any other failing step, or an unverifiable lookup, still counts as a failure); `owner/repo:file.yml` CI-health targets; alerts default to the **private** repo, `--redact` + `--details-file` keep names and minutes out of public logs; `--history-file` lets a workflow restore/save the rolling history; `gh api rate_limit` measured before/after. Verified by 51 unit tests (25 CLI incl. end-to-end `main()` runs with an injected fake `gh`, 26 breaker) and **three source mutations that each fail a test** (public alert default, redact off, period scaling off); monkeypatch ratchet exit 0; subprocess-encoding parity clean. **NOT done:** (1) the scheduled public workflow; the artifact-chain that persists history between runs (`gh run download` → run → `upload-artifact`, sparse checkout of `scripts/pipeline/__init__.py`, `lib/__init__.py`, `lib/workflow_*.py`, `commands/ops/workflow_usage_*.py`, `config/workflow_cost_budgets.yaml` — verified to run `--help` from that minimal set); a live dry-run; (2) `--live`; (3) warm-up needs ≥3 recorded periods (time-gated). **Do not** advance `PHB-03` to `IMPLEMENTED` until (1) and (2) are proven live. **Priority:** P1. **Lane owner:** L-TEL.
- **Required work:** (1) a scheduled public workflow that runs `workflow_usage_collect_and_check.py` weekly (dry-run first); (2) then `--live` with the alert issue on the private repo; (3) breaker warm-up needs ≥3 recorded periods (`N=0/3` today) — time-gated, record the limitation; (4) mark the static caps `provisional` (1,500 total / 500 per workflow were set against the pre-migration baseline) and re-derive after PHB-08; (5) suppress the by-design failure: per-workflow `expected_failure_semantics` or step-level outcome, tested against the real `upstream-monitor` run outcomes; (6) measure API cost (`gh api rate_limit` before/after) and add a `since` window so weekly runs do not re-fetch history (the first dry run made ~300 per-run job calls); (7) advance the ledger only per the acceptance criteria.
- **Required verification:** unit tests for (5); live dry-run run ID; live `--live` run ID + created/deduped issue number; rate-limit delta.
- **Required evidence:** run IDs, issue number, test output, rate-limit numbers (E-LIVE, E-API, E-LOCAL).
- **Acceptance criteria:** ≥1 scheduled fire green; no false alert for `upstream-monitor.yml` in a run where drift exists but the workflow behaved by design; caps recorded provisional; ledger `PHB-03 → IMPLEMENTED` only after (1), (2), (5) are proven live, with (3)/(4) tracked as time-gated follow-ups.
- **Stop conditions:** `--live` would open an issue on the wrong repo or duplicate; rate-limit exhaustion.
- **Allowed actions:** edit the telemetry modules within their S-115 scoped globs plus `registry.yaml`; public template deploy; commits via GATE-COMMIT (three gates bit during PHB-03's own commit: monkeypatch baseline, subprocess-encoding parity, `registry.yaml` registration). **Forbidden actions:** any auto-disable/dispatch from the breaker; lowering caps to silence an alert; GF-*.
- **Dependencies:** none hard; PHB-08 for cap re-derivation. **Closeout rules:** ledger honest; remaining time-gated pieces have a reminder.

##### MT069-HC-06 — Toolchain/compatibility verification without dispatching
- **Source audit finding:** AF-12. **Why it matters:** the host lacks `go`, `jq`, `unzip`, `make`, `shellcheck`, `hugo`; `npm`/`docker` are Windows binaries via interop. The first live run should not be where that is discovered.
- **Current status:** completed_but_weakly_verified — **DONE 2026-09-19 after the resume** (ledger `IMPLEMENTED`). The dynamic CI-mirror simulation ran to completion on the runner host: `simulate_pr_checks.sh` in a scratch clone as the runner user, with the tool-cache Python 3.13.15 (`requirements-ci.txt` install exit 0) and Hugo `0.154.5` extended (the Hugo build step PASSED). **Result PASS 16 / FAIL 1 / WARN 6; zero tool-missing signatures (`command not found`, `FileNotFoundError`, `ModuleNotFoundError`), zero skips.** Classification (§H10): the one blocking FAIL — `check_grade_presence` on 141 locale-directory translation files — is **(a) a genuine gate defect, reproduced with controls** (AF-31, card HC-20), not a host or workflow fault; the 6 advisory WARNs are what real CI reports too (landing-state notices; `reports/audit/baseline-fail-counts.json` is gitignored so a fresh checkout never has it). **Weak part:** the mirror script is not the workflow YAML and did not run under the runner *service's* environment (I exported `LD_LIBRARY_PATH` by hand), so only HC-02 can prove the real thing. *Earlier status text, kept:* partially_done (ledger `IN_PROGRESS`, 2026-09-19). **Done:** (1) transitive enumeration — the two target jobs' scripts need only git, bash, grep, coreutils, python (via `actions/setup-python`) and hugo (via `peaceiris/actions-hugo`); the host lacks go/jq/unzip/make/shellcheck, none needed by these jobs; (3) host probe `selfhosted-host-probe.yml` on the public test runner proves `actions/checkout`, `actions/setup-python` and `peaceiris/actions-hugo` work host-direct (runs `35380303439`, `35381064675`). **NOT done:** (2) the dynamic CI-mirror simulation of `content-governance-checks.yml` in a scratch clone — three attempts failed for *environment* reasons, not findings: the process died with its session (fix: `setsid nohup … & disown`), setup-python's Python needs `LD_LIBRARY_PATH=~/actions-runner-aspose-org-workflows/_work/_tool/Python/3.13.15/x64/lib`, and a CRLF-corrupted `sim.sh`. No valid simulation result exists yet, so "no unexplained tool-missing failure" is **unproven**. (4) is therefore also open. **Priority:** P1. **Lane owner:** L-RUN.
- **Required work:** (1) enumerate every external binary reachable from both workflows' steps **and** every `scripts/ci/checks/*.py` they call, transitively (the hardening run did only a two-tool grep: `check_go_code_blocks.py` needs `go`, `repo_doctor.py` needs `go`/`hugo`, neither called by the target workflows); (2) reproduce the job step sequence in a **scratch clone** inside the runner's WSL distro as the runner user (using `scripts/ci/hooks/simulate_pr_checks.sh` or a step script) with a fresh `.venv` from `requirements-ci.txt`; (3) prove `actions/setup-python@v5` and `peaceiris/actions-hugo@v3` work on this host by dispatching a small workflow on the **public** test runner (authorised); (4) for each genuinely missing tool: prove irrelevant, or list the install step for a human.
- **Required verification:** simulation transcript with exit codes; public-runner run ID; final tools-needed-vs-present table.
- **Required evidence:** E-LOCAL transcript, E-LIVE run ID.
- **Acceptance criteria:** no unexplained tool-missing failure in the simulation; every host gap proven irrelevant or owned by a human.
- **Stop conditions:** the simulation would write to the real repo or use secrets; it needs `sudo`.
- **Allowed actions:** scratch clone in a temp dir; read-only otherwise; a public test-workflow deploy. **Forbidden actions:** touching the real repo's `.venv`/`reports/`; `sudo`; GF-*.
- **Dependencies:** none. **Closeout rules:** findings appended to the guide's Troubleshooting.

##### MT069-HC-07 — Dead `GH_TOKEN` secret on the public repo
- **Source audit finding:** AF-09. **Why it matters:** the fallback credential is dead and the daily probe has failed since 2026-09-06 (issue #43, 13 comments). Blast radius today is small — every template is REPO_TOKEN-primary — but a permanently-red alert hides the next real failure of the same probe (`REPO_TOKEN`, `GOOGLE_API_KEY`), and if `REPO_TOKEN` ever dies there is no working fallback.
- **Current status:** completed_but_weakly_verified — **DONE 2026-09-18, commit `dc36f0e4fa`** (ledger `IMPLEMENTED`), via the credential-free option, so no secret was created, rotated, printed or deleted (GF-2 intact). Survey: `secrets.GH_TOKEN` appears in 14 of 30 public workflows, 13 only as the inert fallback half of `REPO_TOKEN || GH_TOKEN`; no deploy workflow uses it. The deployed `seo-token-liveness.yml` (workflows-repo `9a760a28`) now treats a dead fallback-only `GH_TOKEN` as a `::warning::` plus step summary and exits 0; the drift baseline was approved after checking the prior baseline equalled the deployed file's parent blob. Live proof: liveness run `35380342397` success (REPO_TOKEN OK, GOOGLE_API_KEY OK, GH_TOKEN advisory); issue #43 closed 2026-09-18T18:28:12Z. Sibling fix: `ARBITER.md` example now REPO_TOKEN-first (workflows-repo `ae9faa50`). **Weak part:** acceptance asked for a green *scheduled* fire — not yet observed (proof was a dispatch). **Still optional and human-only:** deleting the orphaned dead secret. **Priority:** P1. **Lane owner:** L-CRED.
- **Required work:** the human chooses: (a) rotate `GH_TOKEN` on `Aspose/aspose.org-workflows` with a fresh least-privilege token, or (b) drop the fallback — REPO_TOKEN-only in all templates and remove `GH_TOKEN` from the probe (agent-executable diff), which first needs a survey proving no other consumer of `GH_TOKEN` exists in that repo (not established). Placing a credential in a **public** repo's secrets is a security decision (write-access collaborators can exfiltrate secrets via a workflow edit). Not acceptable: silencing the probe.
- **Required verification:** after the action, dispatch `seo-token-liveness.yml` (public, authorised) → green; confirm issue #43 closes (verify that the workflow's success path does this).
- **Required evidence:** run ID, issue state, consumer-survey output.
- **Acceptance criteria:** the liveness workflow green on a scheduled fire; issue #43 closed; the `GH_TOKEN` consumer list recorded.
- **Stop conditions:** any consumer of `GH_TOKEN` beyond these templates is found → stop for the human.
- **Allowed actions (agent):** read-only survey of the workflows repo via `gh api …/contents`; prepare option (b)'s diff; dispatch the liveness workflow after the human acts. **Forbidden actions:** creating, rotating or printing secrets and `gh secret set` (GF-2); reusing the local environment's token as a repo secret without fresh explicit approval — the earlier instruction to record a working token as a secret arose in the #94 context, which was a misdiagnosis and is now moot.
- **Dependencies:** none. **Closeout rules:** issue closed; survey recorded.

##### MT069-HC-08 — Approve the `upstream-monitor.yml` deployed baseline
- **Source audit finding:** AF-08. **Why it matters:** the drift checker reports `DEPLOYED_UNAPPROVED` because the deployed copy no longer matches the baseline seeded 2026-09-17T18:30Z (`87fd14f9…`) — the consequence of my documentation-only redeploy (`4ab9d5c3`). The checker cannot go green until someone approves the new hash, and it has no approve verb.
- **Current status:** completed_verified — **DONE 2026-09-18 (loop iteration 1), commit `c71d3db64b`.** Evidence: the prior baseline `87fd14f9…` equals the sha256 of the deployed file's parent blob (workflows-repo `6e6085f`), so the only delta is `4ab9d5c3` (`#` comments, a PR-body message string, one heredoc message line — no logic); baseline set to the checker's own full hash `ca31bef32dd8209e…`; `check_workflow_drift.py --no-seed` → "All 15 workflow(s) in sync". Ledger `IMPLEMENTED`. **Priority:** P1. **Lane owner:** L-CI.
- **Required work:** confirm local == deployed (`ca31bef32dd8` both), and that the change since the baseline is exactly `4ab9d5c3` — comments plus two human-readable message strings (a PR-body note and an issue-body line), no logic; then set `approved_baseline_sha256` for `upstream-monitor.yml` in `data/workflow_deploy_baselines.json` to the deployed hash (full 64-hex from `check_workflow_drift()`; never the short form) via `git_plumb_commit.py`.
- **Required verification:** diff review of `4ab9d5c3`; checker output shows `upstream-monitor.yml` `IN_SYNC`.
- **Required evidence:** the diff, checker output, commit SHA.
- **Acceptance criteria:** the checker reports every workflow `IN_SYNC` and exits 0 (allowing for the transient-lookup issue, HC-09).
- **Stop conditions:** deployed ≠ local (a new unapproved live change) → stop, diff, report — that is precisely what the baseline exists to catch; the diff contains anything but comments/message strings → do not approve.
- **Allowed actions:** GA-1; one tracked-data edit. **Forbidden actions:** approving an unreviewed hash; editing other baselines; GF-*.
- **Dependencies:** none. **Closeout rules:** commit SHA recorded.

##### MT069-HC-09 — Make the drift checker a real gate
- **Source audit finding:** AF-08, AF-07. **Why it matters:** `check_workflow_drift.py` is advisory-only — its only callers are its own tests — yet this plan and the migration records rely on it to keep 15 templates honest (AO-6). It also once reported a transient lookup failure as `DIVERGED`, and its tests live in two directories (276-line `scripts/ci/checks/tests/…` from `096db3c03c`; 104-line `scripts/ci/tests/…` from `d795f669e6`).
- **Current status:** completed_but_weakly_verified — **DONE 2026-09-18, commits `c069713946` (checker) and `40aa0358b3` (baseline seed)** (ledger `IMPLEMENTED`). Delivered: `UNRESOLVED` status with bounded retries (a transient lookup failure is no longer `DIVERGED`; exit 3 for unresolved-only); `--approve NAME --reason` (refuses unless deployed == local, exit 4); `--baselines PATH` for scratch controls; DI seams; 20 new tests (39 + 5 pass); the daily `workflow-drift-watch.yml` deployed publicly (`23 5 * * *`, issue label `workflow-drift`). Live: clean pass `35385437951` (all 18 in sync); forced-red control `35385535807` → `DEPLOYED_UNAPPROVED` on exactly the corrupted scratch entry + issue #47, real baseline byte-identical on `origin/main`; recovery `35385671831` → #47 closed 19:23:53Z. **Weak parts:** (i) no *scheduled* fire observed yet (first: 05:23 UTC); (ii) the orphan `scripts/ci/checks/tests/` (113 tests) is wired into `skill-governance.yml` with its own step and trigger paths, but that workflow is disabled, so the CI wiring is proven only by 113 local passes until HC-02 runs it; (iii) the test directories were wired, not merged. **Priority:** P2. **Lane owner:** L-CI.
- **Required work:** (1) choose where it runs — weekly scheduled public workflow that opens a deduped issue on non-zero exit (recommended: it needs network lookups, which suits a scheduled job better than a pre-commit step) plus a manual on-touch run when templates change; record the tradeoff; (2) an explicit `--approve <workflow>` verb that refuses unless deployed == local and prints the change from the prior baseline; (3) distinguish a failed lookup from divergence (bounded retries, then `UNRESOLVED` with a distinct exit code); (4) decide the canonical test location, establish whether `scripts/ci/checks/tests/` is collected by any CI/pytest configuration (not established), and merge or wire accordingly.
- **Required verification:** unit tests including a negative control built from the real `DEPLOYED_UNAPPROVED` state seen 2026-09-18; approve refuses on mismatch; `UNRESOLVED` path; a live scheduled run ID; a forced-red control against a scratch baseline path (via `configure()`, never the real baseline).
- **Required evidence:** test output, run ID, issue number from the forced-red control.
- **Acceptance criteria:** nothing that changes a template or its deployed copy can go unreported for longer than the schedule interval; approve is a verb, not a hand-edit; test locations unified.
- **Stop conditions:** GATE-COMMIT failures twice (GS-3).
- **Allowed actions:** edit the checker and tests within S-115 scope; add a template; deploy to the public repo. **Forbidden actions:** weakening classification (`DEPLOYED_UNAPPROVED` must stay a failure); GF-*.
- **Dependencies:** HC-08. **Closeout rules:** checker registered in `registry.yaml` if new modules are added.

##### MT069-HC-10 — Stale-guard graduation (TC-SG-07 / R-04)
- **Source audit finding:** AF-03, AF-22. **Why it matters:** the Windows leg is the soft launch of a separate campaign; "a soft launch that never flips" is that campaign's own named failure mode, and it is 5 days past its date. R-04's premise ("precondition met 2026-08-31") went stale on 2026-09-06 and nothing re-checked it. The flip is currently **undecidable**, not neglected.
- **Current status:** blocker (needs a live post-fix run = HC-02, then a soak). **Priority:** P1. **Lane owner:** L-GOV. **Type:** H + T.
- **Required work:** (1) copy the graduation criteria into a tracked location — today they live in a file **outside the repo** (`C:\Users\prora\.claude\plans\plan-based-on-above-foamy-hartmanis.md`) and in gitignored `backlog/REMINDERS.md`: flip surfaces are (a) `--wide-findings` default `warn`→`block` in `check_stale_file_regression.py` and `git_plumb_commit.py` (still `warn`, `git_plumb_commit.py:1960`), (b) `continue-on-error: false` on `governance-tests-windows`, (c) drop the `content/` D-A(ii) suppression (TC-SG-08 decision), (d) `PYTHONUTF8=1` in `pre-commit-audit.sh` and `find_python.sh`, (e) T10 docs, then the TC-SG-21 closeout exercise; stop rule: ≥1 unresolved false positive → do not flip; (2) decide and build a durable record of lookback-class findings (none exists — precondition (1) cannot currently be checked); (3) after HC-02's first live `skill-governance.yml` run, judge workflow-level green, then run the soak the workflow's own comment requires (two weeks of triaged runs); (4) only then flip everything in **one** commit.
- **Required verification:** a workflow-level green run dated after `d795f669e6`; the Windows job green across the soak; no unresolved false positive; TC-SG-21 transcript.
- **Required evidence:** run IDs, soak notes, flip commit SHA (E-LIVE, E-COMMIT).
- **Acceptance criteria:** criteria durable in-repo; either flipped with evidence or explicitly re-dated with the reason and a reminder that names the blocking condition (not a bare date).
- **Stop conditions:** any unresolved false positive; workflow-level red for a reason unrelated to the Windows leg (fix first — the standing-red masking problem TC-SG-20 identified).
- **Allowed actions:** GA-1; documentation; the flips **only** once acceptance evidence exists. **Forbidden actions:** demoting the Windows job's trigger for cost (withdrawn — it destroys the soak evidence); flipping any surface early; GF-*.
- **Dependencies:** HC-02, time. **Closeout rules:** R-04 closed or re-dated with its blocking condition named.

##### MT069-HC-11 — First-live-run evidence-capture and rollback protocol
- **Source audit finding:** AF-13. **Why it matters:** a re-enable that is performed but not observed produces no evidence, and the hard constraint's only exit needs a procedure that makes the exit safe and reversible.
- **Current status:** completed_verified — **DONE 2026-09-18, commit `ebef471a01`** (ledger `IMPLEMENTED`): `docs/operations/first-live-run-protocol.md`. Every observation command was verified on real public runs: branch-ref dispatch `35381607387` + `gh run cancel`; the REST jobs API populates `runner_name`/`runner_id`/`labels`/`started_at` once a job starts (runs `35382133262`, `35380303439`; `gh run view --json jobs` does **not** carry them); `timing.billable` is `{}` for a self-hosted job and populated for a hosted one; queue latency 3 s. Private-repo enable/disable steps are **explicitly marked unexercised**. It also found that `skill-governance.yml` had no `workflow_dispatch` (AF-25, since added). Not independently executed by someone other than its author. **Priority:** P0. **Lane owner:** L-GOV. **Type:** A.
- **Required work:** a protocol document (in `docs/operations/`) with: pre-state snapshot (workflow enabled/disabled states, runner status, latest run IDs, `origin/main` SHA, usage snapshot); step order (enable ONE workflow → trigger → observe); an observation checklist (which runner took the job, queue time, `timing.billable`, per-step conclusions, log scan for out-of-workspace paths and unmasked secrets); failure classification (a/b/c as in HC-02); rollback (human disables; `gh run cancel` for queued/hung runs); abort thresholds proposed for the human to confirm (e.g. queued > 15 min with the runner online; any job on a non-`gha-private-native` runner); post-state snapshot; the E-LIVE bundle layout; a mandatory slot for the human's verbatim go-ahead.
- **Required verification:** dry-run every observation command against a dispatched **public** workflow on the public test runner (authorised) to prove each yields the field it claims.
- **Required evidence:** the document; dry-run run ID and captured outputs.
- **Acceptance criteria:** someone who did not write it can execute it; the dry-run shows every command works; it states plainly that only a human may lift GF-1.
- **Stop conditions:** a command needs a private-workflow enable to test → do not test it, mark it untested.
- **Allowed actions:** doc + optional read-only snapshot script (new code follows GATE-COMMIT). **Forbidden actions:** GF-1 during the dry run; GF-*.
- **Dependencies:** none. **Closeout rules:** referenced from HC-02.

##### MT069-HC-12 — `llms-generation.yml`: make the stale-check gate non-vacuous
- **Source audit finding:** AF-05. **Why it matters:** the "Stale check gate" compares a manifest to the state it was rebuilt from seconds earlier, so it cannot detect drift; the workflow's real remaining value is only "the generator did not crash". The scoped-regeneration cost fix is committed (`b6327ae052`) but has never run live.
- **Current status:** not_attempted (gate); the scoped-regeneration fix is `completed_but_weakly_verified`. **Priority:** P2. **Lane owner:** L-CI.
- **Required work:** persist the manifest across runs (evaluate `actions/cache` restored *before* regeneration, versus a tracked manifest, versus computing staleness from tracked inputs); this is `scripts/generator/**` engineering, outside the S-115 scope this mission used — open the correct skill/scope first; keep the scoped-regeneration logic.
- **Required verification:** in a scratch repo, mutate content without regenerating → the gate **must fail** (impossible today — this is the acceptance test); regenerate → passes; scoped-regeneration scenarios re-run; live run after HC-02's later stage.
- **Required evidence:** scratch-repo transcripts, later live run ID.
- **Acceptance criteria:** the negative control fails as required; no false failure on an unchanged tree; documented.
- **Stop conditions:** the redesign would increase minutes materially without a matching detection gain → stop and re-plan.
- **Allowed actions:** scratch-repo experiments; scoped edits under the right skill context. **Forbidden actions:** removing the gate; GF-*.
- **Dependencies:** none for design; a human enable for the live proof. **Closeout rules:** dossier `llms-generation.md` gets a dated correction block.

##### MT069-HC-13 — `launch-dashboard.yml`: redesign or retire
- **Source audit finding:** AF-06. **Why it matters:** its inputs are gitignored cumulative local state, so it is wrong in every fresh checkout; 3 of the private original's 5 push paths are structurally dead; the public schedule leg was reverted to dispatch-only.
- **Current status:** follow_up. **Priority:** P3. **Lane owner:** L-CI. **Type:** H (product decision).
- **Required work:** the human decides: (a) rebuild from git-tracked inputs, (b) retire it as a CI job and run on demand locally, (c) leave dispatch-only. Deleting a workflow file is a tracked action needing a deletion-governance record (`docs/DELETION_GOVERNANCE.md`).
- **Required verification:** for (a), a fresh-checkout run must equal the local result within a stated tolerance — the exact check that exposed the earlier wrong conclusion; for (b), the deletion record.
- **Required evidence:** decision text, run IDs or the deletion record.
- **Acceptance criteria:** decision recorded; whichever option is chosen is verified on a fresh checkout, not on the maintainer's working directory (AO-8).
- **Stop conditions:** none beyond GS-*. **Allowed actions:** analysis, prototype in a scratch clone. **Forbidden actions:** deleting the workflow without a deletion record; GF-*.
- **Dependencies:** none. **Closeout rules:** dossier `launch-dashboard.md` updated.

##### MT069-HC-14 — Observe first scheduled runs of the migrated workflows
- **Source audit finding:** AF-17. **Why it matters:** four migrated workflows have never fired on schedule, and the private `install-literal-sweep.yml` has no runs ever — so its logic has no scheduled-run history anywhere.
- **Current status:** not_attempted. **Priority:** P2. **Lane owner:** L-CI. **Type:** T.
- **Required work:** after the Monday 2026-09-21 fires (UTC: `ci-onboarding-integrity-weekly` 06:15, `upstream-monitor` 08:00, `seo-weekly-analysis` 09:00, `install-literal-sweep` 11:00 — GitHub may delay), record each run's conclusion and classify it as success / failure-by-design (`upstream-monitor` when drift exists) / defect; each defect becomes a new card.
- **Required verification:** `gh run list --repo Aspose/aspose.org-workflows --workflow <name> --event schedule`.
- **Required evidence:** run IDs + classification.
- **Acceptance criteria:** each of the four has ≥1 scheduled run with a classified conclusion.
- **Stop conditions:** a scheduled run fails for a reason not seen before → Repair Loop.
- **Allowed actions:** GA-1. **Forbidden actions:** dispatching to substitute for a scheduled run; GF-1.
- **Dependencies:** time. **Closeout rules:** PHB-06's grade may move to `completed_verified` only when all four are classified.

##### MT069-HC-15 — Generalised structural fixes (go/no-go)
- **Source audit finding:** AF-18. **Why it matters:** the same shape has now recurred three times — a certified-green card silently stale, a decision owned by another initiative unseen, a manual reminder with no forcing function. Point fixes do not stop the fourth.
- **Current status:** follow_up. **Priority:** P2. **Lane owner:** L-GOV. **Type:** H.
- **Required work:** obtain a go/no-go per proposal, recording tradeoffs: (1) cross-initiative conflict check — a structured `subject-files:` tag on reminders/taskcards plus a WARN when a change touches a subject file with an open decision owned elsewhere (limit: cannot parse existing free-text reminders; prevents future collisions only); (2) soft-launch deadline watch — a sidecar mapping `continue-on-error` jobs to a soak-end date and owning card, watched by the HC-05 telemetry (limit: needs the sidecar kept current); (3) re-validation of `completed_verified` — cards may declare a read-only `revalidate:` check that telemetry re-runs (limit: only as good as the declared check). Nothing is built without the go.
- **Required verification (when built):** each must fail-then-pass against its real incident: the deadline watch would have alerted by 2026-09-13; the conflict check would have flagged MT069's Windows-job recommendation against R-04; the re-validation would have caught TC-SG-20's certification going stale on 2026-09-06.
- **Required evidence:** the decision record; later, negative-control transcripts.
- **Acceptance criteria:** a recorded go or no-go for each, with reasons.
- **Stop conditions:** building without a go. **Allowed actions:** write the decision record. **Forbidden actions:** building new governance tooling unasked; GF-*.
- **Dependencies:** HC-05 (for 2 and 3). **Closeout rules:** each proposal `completed_verified` (built and proven) or closed `follow_up` with the no-go reason.

##### MT069-HC-16 — Fleet-snapshot dropped fields
- **Source audit finding:** AF-19. **Why it matters:** merged PR #103 removed `checked_mode` and `freshness_guard_state` from `data/fleet_freshness_snapshot.json`; I judged them unread and did not prove it.
- **Current status:** completed_verified — **DONE 2026-09-18** (ledger `IMPLEMENTED`; a read-only investigation, no commit). Result: nothing in `scripts/`, `docs/`, `.github/` or `data/` references `freshness_guard_state` or `checked_mode`; the documented schema is the compact per-product SHA table, which matches the new shape; the snapshot is written only by `upstream-monitor` and referenced by one comment in `git_plumb_commit.py`; `bounded_auto_regen.py` reads `sweep_report.json` and `upstream_drift_state.json`, not the snapshot; the dropped fields came from the one-off FRESH-001 data commit `baf1353f0e` (no committed writer found by pickaxe). No reader, so nothing to restore. Limit: this proves absence in this repository only. **Priority:** P3. **Lane owner:** L-CI.
- **Required work:** search all readers by key name and by file (`bounded_auto_regen.py`, `check_upstream_drift.py`, tests, the documented schema in `docs/workflows/freshness-and-bounded-regen.md`); bound the history search for who wrote those fields; confirm `bounded_auto_regen.py select --json` still works on the current snapshot.
- **Required verification:** grep transcript; `select --json` run.
- **Required evidence:** transcripts (E-LOCAL).
- **Acceptance criteria:** "no reader" proven, or the fields restored with a test.
- **Stop conditions:** a reader is found that breaks → fix under the Repair Loop. **Allowed actions:** read-only + a tests-only change. **Forbidden actions:** GF-*.
- **Dependencies:** none. **Closeout rules:** dated note on the PHB-06 record.

##### MT069-HC-17 — Route the 21 upstream-drifted products
- **Source audit finding:** AF-20. **Why it matters:** the first *working* sweep found 21 of 33 products changed upstream (0 HIGH, 9 MEDIUM, 12 LOW). Regeneration selection is observability-only, so nobody acts on it. This is real content-freshness debt — but **not MT069's to absorb**.
- **Current status:** completed_verified — **DONE 2026-09-18** (ledger `IMPLEMENTED`; route-only, nothing regenerated). Recorded as local, gitignored backlog item `ST-202`: 21 drifted products (9 MEDIUM, 12 LOW, 0 HIGH) derived from the committed `data/fleet_freshness_snapshot.json` (`ddb0b0e1a8`); the list reproduces the sweep exactly. **Priority:** P3. **Lane owner:** L-GOV.
- **Required work:** record the list (derivable from the committed `data/fleet_freshness_snapshot.json`, merged as `ddb0b0e1a8`) as a tracking item for the knowledge-pipeline owner (backlog inbox entry or an issue); regenerate nothing.
- **Required verification:** the record exists and matches the snapshot.
- **Required evidence:** the record's location. **Acceptance criteria:** owner has the list. **Stop conditions:** none.
- **Allowed actions:** create the tracking record. **Forbidden actions:** regenerating or editing content; GF-*.
- **Dependencies:** none. **Closeout rules:** closed once handed off.

##### MT069-HC-18 — Runner guide/script: fresh-machine test and decommission tooling
- **Source audit finding:** AF-21. **Why it matters:** the script's parsing, guards and pipeline (up to an invalid token) were tested; a real registration + service install on a clean machine was not, and decommissioning is a manual, undocumented-by-test procedure.
- **Current status:** follow_up. **Priority:** P3. **Lane owner:** L-RUN (+H for `sudo`).
- **Required work:** register a temporary third runner against the **public** repo (authorised for testing) by following the guide literally; install its service (human, `sudo`); then decommission it using the manual steps; fix every guide gap found; add `scripts/ci/decommission-self-hosted-runner.sh`.
- **Required verification:** the temporary runner appears `online`, then is absent from the API and the host after decommission.
- **Required evidence:** API outputs before/after; the guide diff.
- **Acceptance criteria:** the guide is accurate as written; the decommission script removes service, registration and directory.
- **Stop conditions:** the test would touch either real runner. **Allowed actions:** a uniquely-named temporary runner. **Forbidden actions:** removing `alienware-m18-wsl2-private` or `-test`; GF-*.
- **Dependencies:** none. **Closeout rules:** `docs/operations/self-hosted-runner-setup.md` "Decommissioning" section replaced by the tested procedure.

##### MT069-HC-19 — Reproduction-based re-review of the dossiers' root-cause claims
- **Source audit finding:** AF-16. **Why it matters:** TC-11 re-verified the *record*; four of the 20 dossiers (`upstream-monitor`, `launch-dashboard`, the `skill-governance` Windows-job framing, `llms-generation`) later proved materially wrong on root cause or scope. The other 16 dossiers and `analysis/failure_signatures.json` are record-consistent but were never reproduced, and several drive real decisions (destinations, what to self-host, what to fix, what to leave alone).
- **Current status:** not_attempted. **Priority:** P2. **Lane owner:** L-GOV. **Type:** A.
- **Required work:** (1) extract every root-cause / failure-mechanism claim from the 20 dossiers and `failure_signatures.json` into a table — claim, the decision it supports, and how it was established (`reproduced` / `code-read` / `recorded` / `inferred`); (2) for every claim that is not `reproduced` and that supports a destination, a `REQUIRES_REDESIGN`/`INSUFFICIENT_EVIDENCE` outcome, or a fix, attempt reproduction *with a control* (§H10 step 4) in a scratch clone or through read-only API — the four already-corrected dossiers are excluded; (3) record a verdict per claim; where one is contradicted, open a Repair Loop with a dated `CORRECTION` block and, if a destination changes, a new card; (4) revise the TC-10/TC-11 grades only from this card's evidence.
- **Required verification:** reproduction transcripts with controls; the claims table complete, including the "how established" column.
- **Required evidence:** E-LOCAL / E-API / E-NEG entries; the table saved under `reports/plan_state/MT069-…/review/` (local) with each verdict's key IDs copied into this plan (EV-6).
- **Acceptance criteria:** every decision-driving root-cause claim is either `reproduced` or explicitly listed as hypothesis-only, and no destination rests on a hypothesis-only claim without its dossier saying so.
- **Stop conditions:** reproducing a claim would require enabling or dispatching a private workflow → mark it "unreproducible without B-1" and stop (do not test it); evidence contradicts the card's premise (GS-4).
- **Allowed actions:** read-only inspection, scratch clones, public-repo observation. **Forbidden actions:** GF-1; rewriting a dossier without a `CORRECTION` block (GF-7).
- **Dependencies:** none (some claims may only become reproducible after HC-02). **Closeout rules:** TC-10/TC-11 re-graded with the evidence; unreproducible claims carried into the closeout exception list (C-14).

##### MT069-HC-20 — `check_grade_presence.py` flags locale-directory translations (gate defect)
- **Source audit finding:** AF-31 (found by the HC-06 simulation, 2026-09-19). **Why it matters:** the check's own docstring says it applies to "English content (not a translation)", but it decides that from the *filename suffix* only (`LOCALE_RE = \.(?:codes)\.md$`). Docs/KB/reference translations live in locale *directories* (`content/docs.aspose.org/fa/3d/python/_index.md`, `provenance.translation_origin: translator-sync`, no grade by design), so every one is reported as "missing a grade". The real workflow runs the identical script on `git diff --name-only $DIFF_BASE...HEAD -- 'content/**/*.md'`, so any push containing such files goes red — plausibly a large share of `content-governance-checks.yml`'s recent 80% failure rate (inferred; not measured per push), and a trap for HC-02's first live run.
- **Current status:** completed_verified — **DONE 2026-09-19, commit `8c01cd7b98`** (ledger `IMPLEMENTED`). Intent confirmed from the shared constant's own comment ("Locale codes used by folder-based sites **and** translation filename suffixes") and the check's docstring; the check now also recognises `content/<site>.aspose.org/<code>/…` (blog excluded — it uses suffixes only; `en` is not a locale; only the segment directly under the site counts). Tests written first: the 5 defect-describing tests failed and the 4 "gate stays strict" controls passed; 23 pass after. Mutation checks: exempt-everything fails 4 tests, removing the blog carve-out fails 1; a third guard (`len(parts) > i + 3`) survived its mutation because it was **dead code** — reduced to the bounds check indexing needs. **Faithful before/after on the exact 654-file diff window the HC-06 simulation used: the old check reports 141 files missing grades (matching the simulation exactly), the fixed check reports 0**; a synthetic ungraded English page still fails. The neighbouring workflow test, the encoding ratchet (no increase) and the monkeypatch ratchet pass. **Limit:** this removes a known false-positive class; it does not show that `content-governance-checks.yml` now passes end to end (HC-02 is the proof). *Earlier status text, kept:* not_attempted (ledger `TODO`, seeded 2026-09-19). **Priority:** P1. **Lane owner:** L-GOV. **Type:** A (with a policy sanity check).
- **Required work:** (1) confirm the intent — that translations are not graded — from the check's docstring, the grading policy docs and the fact that suffix-locale files are already exempt; (2) make the translation test recognise a locale *directory* the way `content_discovery` already knows the locale codes, without touching how English files are judged; (3) add tests **before** the fix: locale-directory translation without a grade → passes; English page **without** a grade → still FAILS (the gate must stay live); suffix-locale → still exempt; an English page whose path merely contains a locale code as a non-locale segment → still checked; (4) open the correct skill/scope for `scripts/pipeline/commands/governance/**` (outside the S-115 scope this mission used).
- **Required verification:** the tests above, each mutation-checked (remove the new exemption → the new test fails; widen it to all files → the English-without-grade test fails); then re-run the HC-06 simulation's exact step over the same 141 files → 0 reported, and over a synthetic English file without a grade → 1 reported.
- **Required evidence:** test output + mutation transcript (E-LOCAL, E-NEG); before/after counts on the 141 files; the commit SHA.
- **Acceptance criteria:** the 141 translations pass; every English page without a grade still fails; no other gate changed; the decision is recorded here with its reasoning.
- **Stop conditions:** the fix would exempt any English file, or the policy docs say translations *should* be graded (then the defect is the missing grades, not the check — stop and report, GS-4); a second unrelated failure appears in the same step.
- **Allowed actions:** scoped edits to the check and its tests under the right skill context; read-only content inspection. **Forbidden actions:** editing content; weakening the gate beyond translations; flipping any other check; GF-*.
- **Dependencies:** none. **Closeout rules:** AF-31 closed with the counts; if HC-02 has already run, its classification of the red step is corrected to this card.

##### MT069-HC-21 — Move the billed Windows governance leg out of the private `skill-governance.yml`
- **Source audit finding:** AF-38 (and the cost table: 223 of 1,494 minutes, 14.9%). **Why it matters:** the soft-launched `governance-tests-windows` job cost *more* than the required Linux job beside it. The maintainer asked whether it could be Linux and, failing that, required it to move to a self-hosted runner or the public repo.
- **Current status:** completed_verified for the move — **DONE 2026-09-19, commit `c38cd936a4`** (ledger `IMPLEMENTED`). **Can it be Linux? No, measured from the file's own text and the test lists:** the job's stated purpose is defect classes that are "Windows-only in their silent forms" (cp1252 reader-thread swallow, the ~32 KB argv ceiling, a WSL bash stub defeating `GIT_INDEX_FILE`, `\r` in bash reads of `python.exe` stdout, `core.autocrlf=true` worktrees), and **all 15** of its test files already run on Linux in the sibling job (13 named explicitly, the 2 `scripts/ci/tests/` ones through that directory, checked against the pre-change file at `1a941fdcce`) — what it adds is the OS. **Decision (the agent's, recorded and reversible): the public repo, not a self-hosted Windows runner.** Free real Windows runners; no job code running under the maintainer's own Windows account; no dependence on the machine being on. **Built:** `scripts/ci/deployed-workflows/governance-tests-windows.yml`, deployed to `Aspose/aspose.org-workflows` as `53bd46ca` — daily 03:37 UTC plus dispatch (input `ref`, validated), private repo checked out with `REPO_TOKEN` and `persist-credentials: false`, the identical 15-file pytest list, an alert issue that opens and dedups on red and closes on green; drift baseline seeded. **Removed** from the private `skill-governance.yml` (not merely disabled), so re-enabling it cannot bill Windows minutes; rollback = `git show 1a941fdcce:.github/workflows/skill-governance.yml`. **Proven live:** run `35441199525` on `windows-latest` with `core.autocrlf=true`, `cp1252`, Cygwin bash — 369 passed / 3 failed in 226 s; the red path opened issue #50 (mechanism proven); the 3 failures are **not** Windows-specific (AF-37, HC-23). **Tradeoffs the maintainer accepted by choosing to move it, stated so they can be reversed:** daily/dispatch, not per-push; it cannot block a push (the TC-SG-07 "flip to `continue-on-error: false`" surface no longer exists — graduation now means "the public run is green across the soak and its alert issue stays closed", see HC-10); the run log is public. **Priority:** P1. **Lane owner:** L-CI.
- **Required work / verification / evidence / acceptance:** all met as above — run `35441199525`, issue #50, `c38cd936a4`, workflows-repo `53bd46ca`, drift 21/21 in sync.
- **Stop conditions / forbidden actions:** no private workflow enabled or dispatched; no secret created. **Dependencies:** none. **Closeout rules:** the soak that used to be "two weeks of triaged runs" restarts from a green run — it cannot start until HC-23 is fixed.

##### MT069-HC-22 — Move `llms-generation.yml` to the public repo
- **Source audit finding:** AF-05 (vacuous gate), the dossier's "partially duplicated with the deploy repo", and the maintainer's instruction that it "has to go to the public repo". **Why it matters:** 259 of 1,494 minutes (17.3%) for the signal "the generator did not crash".
- **Current status:** completed_verified for the move — **DONE 2026-09-19, commit `c38cd936a4`** (ledger `IMPLEMENTED`). The private original is read-only in effect — it regenerates `llms-output/` and discards it (no commit, no deploy, no artifact, no secret) — so it moves cleanly. **Built:** `scripts/ci/deployed-workflows/llms-generation.yml`, deployed as workflows-repo `ef724a9b` — daily 04:11 UTC plus dispatch (input `ref`, validated), **full** regeneration (minutes are free, so the scoping logic is dropped), same generator commands, alert issue on red (label `llms-generation-red`) that closes on green; drift baseline seeded. **Private original** kept with its body and its trigger narrowed to `workflow_dispatch` (the precedent of the earlier migrations), with a rollback note. **Proven live:** run `35441201382` green. **Not proven:** the alert-on-red path (it needs a failing generator; the same pattern was proven on the Windows workflow); and the carried-over "Stale check gate" is **still structurally vacuous** (HC-12) — a green run means "the generator completed", not "no drift", and the step name now says so. **Effect on HC-12:** its live proof no longer needs a private enable (B-1) — a public dispatch is enough. **Priority:** P1. **Lane owner:** L-CI.
- **Required work / verification / evidence / acceptance:** all met as above — run `35441201382`, `c38cd936a4`, workflows-repo `ef724a9b`, drift 21/21 in sync.
- **Stop conditions / forbidden actions:** no private workflow enabled or dispatched. **Dependencies:** none. **Closeout rules:** dossier `llms-generation.md` gets a dated correction block (destination is now public, not self-hosted).

##### MT069-HC-23 — Repair the pre-commit hook's step numbering drift
- **Source audit finding:** AF-37. **Why it matters:** the hook's own regression tests fail 3 of 8 on every OS: a `_pc_step_end` in block 44 closes out a slot that a different check owns (a check's result can be attributed to another step), and the inline `[Step N]` labels and header comments no longer match the summary table. It also keeps both `skill-governance.yml` jobs red. The failure was invisible because that workflow was already red for another reason.
- **Current status:** completed_verified — **DONE 2026-09-19, commit `6b6b1d13d9`** (ledger `IMPLEMENTED`; governed by override token `20260919-122456-scripts-pre-commit-audit-sh`, created on the maintainer's explicit "YES" and consumed by the commit). Two defects, one of them **mine**: (1) TC-15's evaluator-version-bump gate (2026-09-17) was added with no `_pc_step_start`, so it closed "pipeline registry completeness" a second time — every full run printed the "INTERNAL ERROR … desynchronized" banner (45 names, 46 results) and a FAIL in that gate would have been reported under the wrong step; it now has its own slot (Step 45). (2) The 2026-09-17 "Step 5b" insertion left every later `[Step N]` label and `# Step N:` header one behind its real block index; 106 inline labels and 26 headers were rewritten. **Proof that only numbering changed:** with step numbers normalised the before/after diff is `+6 -0` (the new `_pc_step_start` and its five comment lines). **Real end-to-end run** of the full hook in the harness's sparse worktree with each version overlaid: OLD exit 0 / 45 rows / banner; FIXED exit 0 / 46 rows / no banner / 43 pass, 3 skip, 0 fail. Tests: numbering 8/8, 26 neighbouring hook tests, full-run 6/6 at the new `HEAD` — and `test_precommit_full_run.py` now **asserts the banner is absent**, which it did not before (it passed throughout the two days the banner printed). **Live:** the public Windows leg at the fix commit, run `35442951064`: 372 passed, and its own green path closed issue #50. **A trap found on the way:** the full-run harness builds its worktree from the committed `HEAD`, so an uncommitted hook edit is invisible to it — validate a pending edit by overlaying it into the harness's fixture. Prose comments citing old step numbers were left as historical. *Earlier status text, kept:* not_attempted (ledger `TODO`, seeded 2026-09-19). **Priority:** P1. **Lane owner:** L-GOV. **Type:** A (careful).
- **Required work:** (1) reproduce with the test's own diagnostics on the current tree (block 44 lines ~1971/2019; labels 6→7 … 21→22 and header comments); (2) find the commit that inserted the block that shifted the numbering (`git log -S` on the hook: candidates `1957516439` 09-11, `43b1e614f4` / `1effb57e65` 09-17); (3) decide per finding whether the *script* or the *test's expectation* is wrong — an orphaned second `_pc_step_end` is a real defect, off-by-one labels are cosmetic but the test forbids them; (4) fix with the smallest change that keeps every check's behaviour; (5) check that no other session has the hook open before editing (this repo has concurrent sessions), and commit it alone.
- **Required verification:** the 8 tests pass; `test_precommit_full_run.py` (the full unmodified hook against a sparse worktree) still passes; run the hook's summary table once and compare the step list before/after (same steps, same order, same pass/fail); the three tests re-run on Windows (dispatch the public leg with `ref` = the fix commit).
- **Required evidence:** before/after test output, the step-table comparison, the Windows run ID (E-LOCAL, E-LIVE). **Acceptance criteria:** 3 → 0 failures on Windows, Linux and the dev machine; issue #50 closes by itself on the next green run.
- **Stop conditions:** the fix changes which checks run or their exit behaviour; another session is editing the hook; a step's body has to change beyond its numbering. **Allowed actions:** edits to `scripts/pre-commit-audit.sh` (and only if the test's expectation proves wrong, its test) under the right skill scope. **Forbidden actions:** weakening or skipping a hook step; deleting the failing tests; `--no-verify`; GF-*.
- **Dependencies:** none. **Closeout rules:** AF-37 closed; the public leg's alert issue closed by a green run, not by hand.

##### MT069-HC-24 — Stage 1b: exercise the diff-dependent steps and the concurrency guard live
- **Source audit finding:** the "Not proven" rows of §H17 and §H20. **Why it matters:** HC-02 was closed as *weakly* verified. A `workflow_dispatch` run diffs only `HEAD~1`, so in stage 1 the grade-presence step printed "No content files changed" and the version-bump step "none changed": the HC-20 fix and TC-15's behaviour have only local proof, and the concurrency guard (`cancel-in-progress`) has never fired.
- **Current status:** not_attempted (ledger `TODO`, seeded 2026-09-19). **Priority:** P2. **Lane owner:** L-RUN. **Type:** H (needs a go-ahead naming `content-governance-checks.yml`).
- **Required work:** one enable-window per `first-live-run-protocol.md`: (a) a proof ref whose last commit touches locale-directory translations (for example `e63c268614`), so `check_grade_presence` runs on real changed files; (b) optionally a proof ref whose last commit changes an evaluator file — once without a version bump (the gate must fail) and once with one (it must pass); (c) two dispatches on the same ref in quick succession, to see the older run cancelled; then re-disable and delete the proof refs.
- **Required verification:** (a) the step lists the locale files and ends "All N file(s) have grades" / exit 0; (b) fail-then-pass; (c) the first run `cancelled`, the second completes. Warm checkout time recorded again.
- **Required evidence:** run IDs and step outputs (E-LIVE), the go-ahead verbatim, pre/post snapshots.
- **Acceptance criteria:** each claim above observed live, or explicitly recorded as not achievable; HC-02 re-graded from that evidence.
- **Stop conditions:** any red step not explained by the proof ref's own content; a second workflow would need enabling. **Allowed actions:** the protocol's steps for that one workflow; proof refs only. **Forbidden actions:** editing content or evaluators on `main`; leaving anything enabled; any other workflow; GF-*.
- **Dependencies:** the maintainer's go-ahead. **Closeout rules:** proof refs deleted; HC-02's grade updated from the result.

### H6. Lane Ownership

Lanes exist so two workers never write the same file. The repo is routinely worked by many
concurrent sessions, so lane discipline is enforced by the write-sets below plus
`git_plumb_commit.py --files <exact list>` (never `git add -A`).

| Lane | Owner | Cards | Write-set (exhaustive for agent work) | Skill context to open first |
|---|---|---|---|---|
| **L-RUN** runner & host | Agent for docs/scripts; **human for host config, `sudo`, service units, enable/disable** | HC-02, HC-03, HC-06, HC-18 | `docs/operations/self-hosted-runner-setup.md`, `scripts/ci/setup-self-hosted-runner.sh`, `scripts/ci/decommission-self-hosted-runner.sh`, public smoke-test template | S-115, scope `scripts/ci/**,docs/operations/**` |
| **L-CI** workflows & drift | Agent | HC-08, HC-09, HC-12, HC-13, HC-14, HC-16, PHB-05 | `scripts/ci/deployed-workflows/**`, `scripts/ci/checks/check_workflow_drift.py` + its tests, `data/workflow_deploy_baselines.json`, `.github/workflows/**`; `scripts/generator/**` only for HC-12 under its own skill/scope | S-115 (HC-12: the skill that governs `scripts/generator/`) |
| **L-TEL** telemetry & alerting | Agent | HC-04, HC-05, PHB-08 | `scripts/pipeline/lib/workflow_*`, `scripts/pipeline/commands/ops/workflow_*`, `scripts/pipeline/config/workflow_*`, `scripts/pipeline/tests/test_workflow_*`, `scripts/pipeline/config/registry.yaml`, telemetry/alert public templates | S-115 with the globs above **plus** `registry.yaml` (omitting it blocked PHB-03's own commit) |
| **L-GOV** plan, ledger, protocols | Agent | HC-01, HC-10, HC-11, HC-15, HC-17, HC-19 | this plan file, `plans/missions/MT069-…md`, `taskcards.jsonl` (**via `taskcard_cli.py` only**), `backlog/REMINDERS.md`, protocol docs under `docs/operations/` | none for `plans/`; S-115 for `docs/operations/**` |
| **L-CRED** credentials | **Human only** | HC-07 | repo secrets (never touched by the agent) | — |

**Serialisation rules (a violation is a stop, GS-2):**
1. `data/workflow_deploy_baselines.json` is single-writer — the checker also *seeds* baselines for new templates, so HC-04, HC-05, HC-08, HC-09 must not touch it concurrently.
2. `taskcards.jsonl` is single-writer through the CLI's CAS; HC-01 owns seeding.
3. `docs/operations/self-hosted-runner-setup.md` receives edits from HC-03, HC-06, HC-18 — serialise, each in its own section.
4. HC-08 → HC-09 (same checker/baseline surface).
5. HC-02 cannot start until HC-03, HC-04, HC-06, HC-11 are `completed_verified` **and** the human has spoken.

**Parallel-safe:** HC-03 ‖ HC-04 ‖ HC-06 ‖ HC-11 ‖ HC-05 (steps 1, 2, 5, 6) ‖ HC-16 ‖ HC-17. **Time-gated (no lane work):** PHB-05, HC-14, PHB-08, the soak inside HC-10.

**Critical path:** `{HC-03, HC-04, HC-06, HC-11} → human go-ahead → HC-02 → {HC-10 soak, PHB-08 window} → closeout`. HC-07, HC-13 and HC-15 are human decisions off the critical path (HC-07 gates only the noise, not the cutover).

**After every commit by any lane:** `checkout_sync.py report` (a plumbing commit left real-index residue that would have silently reverted `AGENTS.md` on the next porcelain commit) and `git diff --stat <sha>^ <sha>` to confirm the commit is non-empty.

### H7. Gate Contract

**Enforcement honesty first** — a gate that exists only as prose is recorded as such, so it is not mistaken for protection:

| Gate | Enforced by today | Status | Hardening card |
|---|---|---|---|
| GATE-HARD (no private-workflow enable/dispatch) | **Instruction only** — no hook, permission or token restriction prevents it | prose | HC-11 (procedure for the only legitimate exit) |
| GATE-HUMAN | Instruction only | prose | — |
| GATE-COMMIT | Technical — `git_plumb_commit.py` runs the Tier-1 steps against an isolated index | **real** | — |
| GATE-LEDGER | `check_plan_taskcard_completeness.py` exists but is run only at closeout | partial | HC-01 |
| GATE-DRIFT | `check_workflow_drift.py` has **no caller** — advisory | advisory | HC-08, HC-09 |
| GATE-LIVE | Instruction only | prose | HC-11 |
| GATE-ROOTCAUSE | Instruction only | prose | — |
| GATE-ISOLATION | Nothing | absent | HC-03 |
| GATE-ALERTING | Nothing | absent | HC-04 |

**GATE-HARD — the standing invariant.** No workflow among the 20 in `Aspose/aspose.org`
is enabled or dispatched by any means without an explicit human go-ahead that is pasted
verbatim into the evidence bundle. The only legitimate lifting procedure is HC-02 using
HC-11's protocol. Public-repo workflows (`Aspose/aspose.org-workflows`) and self-hosted
runners for *testing* remain authorised, as the user stated on 2026-09-17.

**GATE-HUMAN — actions that always need the human, even inside an authorised card:**
enabling/disabling/dispatching a private workflow; creating, rotating, deleting or printing
any secret; registering, removing or reconfiguring a runner or its host (`sudo`,
`/etc/wsl.conf`, Docker Desktop settings); deleting a workflow file; merging an automated
PR whose diff was not read; re-binding `MISSION_AUTHORITY.yaml`. A past blanket go-ahead
never covers a new instance of these (AO-15).

**GATE-COMMIT — the sanctioned path and its known traps.** `git_plumb_commit.py --files
<exact list> --skills S-xx --plan "…" --co-author "…"`, after `session_ledger.py adopt` for
files it does not yet own, inside a `skill_context.py begin … end` that **covers every file
in the commit**. Real failures this mission hit, each now a checklist item:
(1) `not_in_ledger` refusal → verify the diff is yours, then `adopt`;
(2) monkeypatch ratchet (`check_monkeypatch_lint.py --strict --tier 1,2 --compare-baseline
scripts/ci/monkeypatch_baseline.json`) compares **raw per-file counts** — every new
`patch(...)` call site counts even against an already-baselined target → use DI seams;
(3) subprocess text-mode calls without `encoding=` fail the parity ratchet;
(4) every new file under `scripts/pipeline/{lib,commands}/` needs a `registry.yaml` entry;
(5) `--ack-gitignored` takes explicit paths, not a bare flag;
(6) plumbing commits can leave real-index residue → `checkout_sync.py report`.
Never `--skip-tier1-checks`, `--skip-ledger-check`, `--skip-stale-check` or
`SKIP_SKILL_CONTEXT_CHECK`.

**GATE-LEDGER.** A card's ledger status is advanced in the session that lands its
evidence, and never to `IMPLEMENTED` unless its §H5 grade is `completed_verified` or
`completed_but_weakly_verified` with a linked follow-up. Register and ledger must agree at
closeout (`check_plan_taskcard_completeness.py` exit 0).

**GATE-DRIFT.** Any card that changes a template or its deployed copy re-runs
`check_workflow_drift.py` and records the result; until HC-09 lands this is a manual step
that must not be skipped precisely because nothing else enforces it. A transient
`deployed=unresolved` is retried, not accepted as `DIVERGED`, and not ignored.

**GATE-LIVE.** A claim about CI behaviour is verified only by a live run that (a) post-dates
the change, (b) ran the intended commit, (c) is cited by run ID. Local, synthetic, dry-run
and record-based evidence can support `completed_but_weakly_verified` at most.

**GATE-ROOTCAUSE.** A root-cause statement in a dossier, taskcard or issue must cite a saved
reproduction plus a control that would answer differently if the claim were false. Absent
that it is written as a hypothesis and cannot justify closing an issue or withholding a fix.

**GATE-ISOLATION / GATE-ALERTING (preconditions for HC-02).** Isolation: the HC-03 decision
recorded and its negative control passed. Alerting: HC-04's alert workflow demonstrated
firing and recovering. HC-02 may not start without both.

**Global rule sets referenced by every card**

- **GA-1 (allowed):** read-only `gh api`/`gh run view|list`/`git`/`taskcard_cli.py latest`; local test runs; edits inside the card's lane write-set; commits through GATE-COMMIT; public-repo template deploys (authorised for this mission) using the safe cross-repo pattern — `git fetch` first, build the commit on the *fetched* tip, push the SHA, never rewrite local refs; observation of public-repo runs.
- **GF-1:** enabling, dispatching, or otherwise activating any private-repo workflow (except the human performing HC-02). **GF-2:** creating, rotating, reading-out, logging or committing secrets or tokens. **GF-3:** `git commit` porcelain; any `--skip-*`/bypass flag; editing hooks to pass. **GF-4:** force-push, history rewrite, deleting workflow files, branches or runners. **GF-5:** writing outside the card's write-set. **GF-6:** advancing a status without evidence meeting §H8. **GF-7:** overwriting a dossier or journal entry instead of adding a dated `CORRECTION` block.
- **GS-1:** stop when the next command would violate a GF or needs `sudo`/human authority — hand over the exact command. **GS-2:** stop on an unexpected concurrent change to a file in the write-set, or a repeated CAS error after one fresh-read retry. **GS-3:** stop after two failed repair iterations on one card in one session (§H10). **GS-4:** stop when evidence contradicts the card's premise — re-plan, do not force-fit.

### H8. Evidence Contract

Every "verified" claim must cite evidence a third party can **re-observe** — a run ID, a
commit SHA, an issue/PR number, a command whose output can be regenerated. A path under
gitignored storage is a convenience copy, not the evidence.

| Type | Proves | Required fields |
|---|---|---|
| **E-LIVE** | a CI run behaved a certain way | run URL/ID; workflow file + head SHA it executed; event; conclusion; per-step conclusions for any step the claim rests on; `runner_name` for self-hosted claims; created/completed timestamps; for cost claims the `timing.billable` value |
| **E-API** | current external state (runners, workflow state, issues, secrets *names*) | exact `gh api` call; jq filter; UTC timestamp; raw output excerpt |
| **E-LOCAL** | behaviour of code on a machine | command; exit code; output excerpt; commit SHA of the tree tested; whether the tree was a scratch clone or a working tree |
| **E-COMMIT** | a change landed | SHA; `git show --stat` proving it is non-empty; gate summary from `git_plumb_commit.py` |
| **E-NEG** | a check can actually fail | the mutation applied; the observed failure; the restoration; run in a scratch location |
| **E-HUMAN** | a human decision or go-ahead | the person's words verbatim, with date and the scope they covered |

**Rules.**
- **EV-1 (no proof by absence):** a missing command, a skipped check, an empty grep, or `shutil.which(...)` returning `None` is not a pass; record it as *not exercised*.
- **EV-2 (freshness):** evidence is void once the evidenced file/config changes (compare hashes/SHAs), or, for live claims, when it pre-dates the fix it is cited for. Re-collect; do not carry forward.
- **EV-3 (synthetic ceiling):** E-LOCAL, dry-run and fixture evidence can never upgrade a CI-behaviour claim past `completed_but_weakly_verified`.
- **EV-4 (control):** an authentication, permission or availability claim needs an E-NEG-style control that would give the *same* answer if the claim were false.
- **EV-5 (regenerated/deployed artifacts):** a change to a generator, template or deployed copy is *applied* only when the regenerated/deployed artifact is refreshed **and** GATE-DRIFT is green; the source change alone is not the change.
- **EV-6 (durability):** run IDs, SHAs and issue numbers are copied into this tracked plan; `EVIDENCE_BUNDLE.md` and `phase_b/*` (gitignored, single-machine) index them but are not the sole copy.
- **EV-7 (redaction):** evidence never contains token values; log excerpts are checked for unmasked secrets before being recorded.

### H9. Verification Matrix

"Does not count" is as important as "counts": it names the shortcut that would otherwise
be mistaken for proof.

| Claim | Real proof | Does **not** count | State today |
|---|---|---|---|
| Private jobs run on the self-hosted runner | E-LIVE with `runner_name == alienware-m18-wsl2-private` | Runner `online`; `runs-on:` edited; systemd `active` | **Unproven** (HC-02) |
| TC-14 removed the false failures | E-LIVE workflow-level green of `skill-governance.yml` after `d795f669e6` | 12/12 unit tests; local run | **Unproven** (HC-02) |
| TC-15 gate works in CI | E-LIVE run on an evaluator-touching push + the existing local E-NEG | Local pre-commit tests alone | Local only |
| Concurrency guards cancel superseded runs | Two pushes in quick succession, the first run `cancelled` | The `concurrency:` block existing | **Unproven** |
| `upstream-monitor` sweep fix | E-LIVE run `35321867511` (`fetch_failures: 0`) + tests + local repro | — | **Verified** |
| Public migrations stable | ≥5 scheduled cycles on distinct UTC dates; private original silent | Dispatch runs; the first green run | 1 of 5 (PHB-05); 4 workflows unseen on schedule (HC-14) |
| Telemetry alerts correctly | E-LIVE dry-run + `--live` runs, false-alarm suppression tested on real outcomes | The 54 unit tests; the dry-run smoke | Partial (HC-05) |
| Runner-offline alert works | E-LIVE pass/alert/recover runs (control label for the alert path) | The workflow existing | **Unbuilt** (HC-04) |
| Drift checker is a gate | A scheduled run + a forced-red control against a scratch baseline | The script passing when run by hand | Advisory (HC-09) |
| Isolation model holds | E-NEG: `/mnt/c` unreadable to the runner user; marker file absent in run 2 (public test runner) | A design document | **Unproven** (HC-03) |
| Toolchain suffices | Scratch-clone simulation + public-runner run of `setup-python`/`actions-hugo` | Static grep of tool names | Static only (HC-06) |
| Stale-check gate can fail | E-NEG in a scratch repo: content changed, not regenerated → gate fails | The step going green | **Cannot fail today** (HC-12) |
| `GH_TOKEN` problem resolved | Liveness workflow green on a scheduled fire; issue #43 closed | Silencing or deleting the probe | Failing (HC-07) |
| Cost reduced | PHB-08 comparison with an enabled-window validity statement | Zero usage while workflows are disabled; projections | **Not measurable now** |
| Ledger consistent with plan | `taskcard_cli.py latest` + completeness checker exit 0 | This document's own table | Inconsistent (HC-01) |
| An automated PR is safe to merge | The diff read for destructive deltas + one externally checked fact | A green check; a plausible title | Practised on #99/#100/#103 |

### H10. Repair Loop

Applies to any failed gate, red run, contradicted premise or defect found while executing
a card. Two attempts per card per session (GS-3).

1. **Detect and record** the failing observation verbatim (command + output or run ID).
2. **Classify in three layers** — *symptom* (what is visibly wrong), *root cause* (the mechanism, with its evidence), *structural weakness* (why nothing caught it earlier). A fix that addresses only the symptom is a workaround and is labelled as one.
3. **Reproduce** with a saved command (GATE-ROOTCAUSE). If it cannot be reproduced, the diagnosis is a labelled hypothesis; act on it only if the action is reversible and independently justified.
4. **Run a control** for any permission/credential/availability claim (anonymous request, fresh checkout, non-existent label). The 2026-09-18 "PAT gap" survived several reviews because none did this; the control took one request.
5. **Fix at the source, smallest change.** Never weaken a gate to get green: no new `continue-on-error`, no baseline edited to match a regression, no `--skip-*`.
6. **Verify at the level the claim was made** — a CI claim needs a CI run (GATE-LIVE). Local success on the maintainer's working tree proves nothing about a fresh checkout (`launch-dashboard.yml` was declared healthy on exactly that basis, then failed 33/33 on a fresh checkout).
7. **Sweep siblings:** search for the same class elsewhere — every document repeating a corrected diagnosis, every runner's registration, every consumer of a bad credential, every template sharing the defective pattern.
8. **Record** with a dated `CORRECTION` block (GF-7) and update the register and, via the CLI, the ledger. Annotate, never erase: the trail of what was believed is evidence.
9. **Post-commit hygiene:** `checkout_sync.py report`; `git diff --stat <sha>^ <sha>`; for anything deployed, GATE-DRIFT.
10. **Escalate at the limit:** after two failed iterations, stop and hand the human what was tried, what was observed and the exact next command (GS-3). Do not try a third variation.

### H11. Anti-Overclaim Rules

Each rule is written from a real slip or near-slip in this mission's record.

- **AO-1** A disabled workflow produces no evidence. No CI-behaviour claim is "verified" without a live run dated after the change. *(TC-14/15, guards, self-hosting: all unproven since 2026-09-11.)*
- **AO-2** A root-cause claim needs a saved reproduction. A code comment, docstring, issue body or earlier report is a hypothesis. *(The "PAT gap" was repeated by a comment, a docstring, an issue, two dossiers and an independent review.)*
- **AO-3** "Runner online" ≠ "runner serves that repo" ≠ "jobs execute there". Verify the binding (`.runner`/API) **and** a real job's `runner_name`. *(Wrong-repo registration.)*
- **AO-4** Ledger `IMPLEMENTED` is not "verified". Use the §H5 vocabulary. *(PHB-03 `TODO` with committed code; PHB-07 `IMPLEMENTED` with no job ever run.)*
- **AO-5** Review of records is not review of behaviour. An independent review that endorses a root cause must have reproduced it; otherwise its grade is "record-consistent only". *(TC-11.)*
- **AO-6** An advisory script is not a gate; a check with no caller enforces nothing. *(`check_workflow_drift.py`.)*
- **AO-7** A dry run or smoke test is not production proof. *(PHB-03's live dry-run against the real repo.)*
- **AO-8** Local success proves nothing about a fresh checkout. *(`launch-dashboard.yml`.)*
- **AO-9** Authentication/permission claims need a control that would answer the same if the claim were false. *(Anonymous request to a public org.)*
- **AO-10** A manual reminder's premise is re-verified when acted on and when it falls due; a due date without a named blocking condition is not a plan. *(R-04.)*
- **AO-11** Time-gated evidence counts only after the time has passed — scheduled events only, distinct UTC dates, never dispatches or projections. *(PHB-05; the 10:30 cron that ran at 14:33.)*
- **AO-12** An automated PR is merged only after its diff is read for destructive deltas. *(#103 would have replaced 250 lines with `{}`.)*
- **AO-13** Zero usage while workflows are disabled is not a saving. *(PHB-08's trap.)*
- **AO-14** A fix is not done until every place that repeated the wrong belief is corrected. *(Nine artifacts repeated the PAT narrative.)*
- **AO-15** A past blanket authorisation never covers a new production action; re-confirm scope. *(HC-07's secret; HC-02.)*
- **AO-16** A source change is not applied until its generated/deployed artifact is refreshed and drift is green; an artifact merely existing is not correctness. *(EV-5.)*
- **AO-17** A skipped check, a missing tool or a command that ran nothing is "not exercised", never "passed". *(EV-1; `shutil.which("go")` → `None`.)*

### H12. Closeout Criteria

The mission may be reported complete only when **all** of the following hold, each backed
by evidence meeting §H8:

- **C-1** Ledger and register agree (HC-01 acceptance); every card is terminal, or is `follow_up`/`blocker` with the named human action recorded.
- **C-2** The P0 cards HC-02, HC-03, HC-04, HC-11 are `completed_verified`.
- **C-3** Live proof (E-LIVE) exists for: both target workflows on the private runner; TC-14's workflow-level green; TC-15's behaviour; guard cancellation — **or** the human has recorded (E-HUMAN) that a named item is accepted as unproven.
- **C-4** PHB-05's acceptance is met and HC-14 is classified.
- **C-5** HC-05's acceptance is met (telemetry live; the alert-only invariant intact) with its time-gated remainder ticketed.
- **C-6** The drift checker is green and wired (HC-08, HC-09), or the human recorded a decision to leave it advisory.
- **C-7** HC-07 resolved (issue #43 closed) or the human recorded that the failing probe is accepted.
- **C-8** PHB-08 done with a valid measurement statement, or `NOT_MEASURABLE` recorded with reasons. No saving figure appears anywhere without one.
- **C-9** HC-10 resolved: flipped with evidence, or re-dated with the *blocking condition named*.
- **C-10** `final_report.md` has a Phase B section; the mission narrative and `plans/master-plan.md` row are current; `EVIDENCE_BUNDLE.md` indexes every E-* item with re-observable IDs.
- **C-11** This plan file is committed through GATE-COMMIT and `check_plan_taskcard_completeness.py` exits 0.
- **C-12** The status of GATE-HARD is stated explicitly: still in force, or lifted per HC-02 with the human's words.
- **C-13** A final sweep finds no journal line that contradicts current state without a `[SUPERSEDED]` annotation.
- **C-14** HC-19 is done, or every root-cause claim it could not reproduce is listed **by name** among the closeout exceptions.

**Allowed final verdicts (one only):** `MISSION_COMPLETE_VERIFIED` (all C-* met);
`MISSION_COMPLETE_WITH_DOCUMENTED_EXCEPTIONS` (each un-proven claim listed by name);
`MISSION_BLOCKED_ON_HUMAN` (each blocker in §H13 listed). Any verdict claiming a cost saving
must quote C-8's validity statement.

**What may honestly be claimed today (2026-09-18):** Phase A is complete; Phase B is
partially executed (9 templates deployed; canary in observation; runner registered); the
`upstream-monitor` sweep defect is fixed and live-proven; **no cost saving has been
measured or proven, and no self-hosted job has ever run.**

### H13. Remaining True Blockers

A blocker is something the agent cannot resolve by working harder. Everything else in the
register is executable.

| # | Blocker | Blocks | Who / what unblocks it |
|---|---|---|---|
| **B-1** | The standing hard constraint: no private workflow may be enabled or dispatched without an explicit human go-ahead | HC-02 → live proof of TC-14, TC-15, guards, self-hosting; HC-10; PHB-08 | The human names the workflow and gives the go-ahead once HC-03, HC-04, HC-06, HC-11 are done |
| **B-2** | Isolation-model decision, and any `sudo`/`/etc/wsl.conf`/Docker Desktop change it needs | HC-02 | The human picks (a)/(b)/(c) from HC-03 and runs the privileged commands the agent hands over |
| **B-3** | Which credential resolves the dead public-repo `GH_TOKEN` — or the decision to drop the fallback | HC-07 (noise, lost fallback); not the cutover | The human, per HC-07 |
| **B-4** | Calendar time: 2026-09-21 first Monday scheduled fires (HC-14); ≥5 scheduled canary cycles, earliest evening 2026-09-22 (PHB-05); R-07 due 2026-09-24; R-08/PHB-08 due 2026-10-08; three recorded periods for the breaker's baseline (HC-05); the stale-guard soak (HC-10) | PHB-05, HC-14, PHB-08, parts of HC-05/HC-10 | Nothing but time — do not dispatch to compensate |
| **B-5** | Product decision on `launch-dashboard.yml` | HC-13 only | The human |
| **B-6** | Go/no-go on new governance tooling | HC-15 only | The human |
| **B-7** | An interactive `sudo` for any service install/removal in HC-18 | HC-18's live test | The human at a real terminal |

**Not blockers — executable today:** HC-01, HC-08, HC-09, HC-11, HC-06, HC-03's analysis and
public-runner controls, HC-04 (stop only if `REPO_TOKEN` lacks the runner-read scope), HC-05
steps 1, 2, 5, 6, HC-12's design and scratch-repo work, HC-16, HC-17.

**Recommended order:** (1) HC-08 (tiny; makes drift green) and HC-01; (2) in parallel HC-03
analysis, HC-04, HC-06, HC-11; (3) the human decisions B-2, B-3, B-5, B-6; (4) HC-02, one
workflow at a time; (5) time: 2026-09-21 → HC-14, 2026-09-22 → PHB-05, 2026-09-24 → R-07,
2026-10-08 → R-08/PHB-08.

**Hardening verdict for this file (2026-09-18):** the plan now carries a graded status for
all 23 existing cards, full-contract cards for every unresolved audit finding, gates that
say honestly whether they are enforced, an evidence contract with a synthetic-evidence
ceiling, and closeout criteria that refuse to call the mission complete on ledger status
alone. It is **ready for execution of the agent-executable cards**; the mission as a whole
is **not** closeable until B-1 is resolved by a human.

### H14. Execution Loop

Added on the user's instruction (2026-09-18) to "create a loop to complete all remaining
work". The loop is how §H4's agent-executable cards get executed, one at a time, each
through the Repair Loop (§H10) and each closed only on §H8 evidence.

**Authority (E-HUMAN, verbatim).** 2026-09-18, first: *"create a loop to complete all
remaining work"*; then, mid-run: *"do everything from HC-01 to HC-19"*. The second message
names the whole card set, including the cards §H4 marks as needing a human (HC-02, HC-03's
decision, HC-07, HC-13, HC-15). **Interpretation, recorded so it can be reversed:**
- It is the go-ahead GATE-HARD requires for **HC-02 as that card is written** — one workflow at a time, `content-governance-checks.yml` first, exactly the protocol of HC-11 — and for nothing broader. HC-02 still may not start until HC-03's decision is recorded, HC-04 has demonstrated alerting and HC-06/HC-11 are done (GATE-ISOLATION/GATE-ALERTING); a workflow that has been proven is **re-disabled** afterwards and left disabled until the user says otherwise, because "leave it enabled" is a production choice the message does not make.
- The "human decisions" in HC-03, HC-07, HC-13, HC-15 are delegated to the agent, so each is decided, written down with its reasoning, and made **reversible**. Where an option needs a credential or `sudo`, the credential-free/no-`sudo` option is taken.
- It does **not** cover, and the loop will not perform: creating, rotating, reading out or deleting any secret (GF-2); anything needing `sudo`; deleting a runner, workflow file or branch that pre-existed this loop; re-binding `MISSION_AUTHORITY.yaml`; or any claim that a time-gated item (HC-14, PHB-05, PHB-08, the HC-10 soak) is done before its date. Those are parked with a re-entry date.

**Iteration protocol (every pass, in order):**
- **L-0 Pre-flight:** `taskcard_cli.py latest`; `checkout_sync.py report`; `git status --porcelain` on the card's write-set (GS-2 if another session touched it); both runners `online`; re-read this section's queue.
- **L-1 Pick** the first card in the queue that is unblocked and not parked.
- **L-2 Open** the skill context for the card's lane (§H6) — scope must cover every file to be committed.
- **L-3 Execute** within GA-1 and the card's Allowed/Forbidden lines; new code goes through GATE-COMMIT's known traps.
- **L-4 Verify** at the level the claim is made (GATE-LIVE for CI claims; a control for any permission/availability claim — §H10 step 4).
- **L-5 Record:** evidence IDs into this plan's card (status per §H5 vocabulary), the ledger through `taskcard_cli.py` only, and an entry in the local loop log (`reports/plan_state/MT069-…/loop_log.md`).
- **L-6 Commit** through `git_plumb_commit.py` (never porcelain), then `checkout_sync.py report` and a non-empty check.
- **L-7 Sibling sweep** (§H10 step 7) for anything the card corrected.
- **L-8 Park or continue:** if the card needs a human or time, write the parking-lot entry and move on; two failed repair iterations = park (GS-3).
- **L-9 Exit test:** if no unparked, unblocked card remains → stop the loop and report; otherwise return to L-0.

**Queue (execution order; deps and lane serialisation from §H6).** *Live status of every queue row at the 2026-09-19 checkpoint: see §H15.1 — the "Loop-done means" column below is the original target, not the current state.*

| Order | Card | Loop-done means | If it cannot finish |
|---|---|---|---|
| 1 | HC-08 | upstream-monitor baseline approved, checker `IN_SYNC` for it | park if deployed ≠ local (unapproved live change) |
| 2 | HC-01 | 19 cards seeded in ledger, `PHB-03 IN_PROGRESS`, narrative fixed, completeness checker exit 0 | park on repeated CAS error |
| 3 | HC-16, HC-17 | readers of dropped fields established; drift list handed off | — |
| 4 | HC-07 (agent part) | `GH_TOKEN` consumer survey recorded | the credential decision stays parked (B-3) |
| 5 | HC-11 | protocol written and every command dry-run against a public workflow | — |
| 6 | HC-06 | transitive tool list + scratch-clone simulation + public-runner run | any needed `sudo` install → parked for the human |
| 7 | HC-04 | alert workflow deployed and its pass/alert/recover paths demonstrated | park if `REPO_TOKEN` lacks runner-read scope (B-3-adjacent) |
| 8 | HC-03 (agent part) | threat-model delta, options, recommendation, baseline probe on the public test runner | the isolation decision stays parked (B-2) |
| 9 | HC-09 | approve verb, `UNRESOLVED` status, scheduled gate, unified tests | — |
| 10 | HC-05 | scheduled telemetry workflow, false-alarm suppression, persistence problem resolved, rate-limit measured | `--live`/warm-up/cap re-derivation that need time → parked with a date |
| 11 | HC-10 (agent part) | graduation criteria copied into a tracked location | flips and soak stay parked (B-1, time) |
| 12 | HC-12 | manifest persistence with the negative control passing in a scratch repo | live proof stays parked (B-1) |
| 13 | HC-19 | claims table complete, decision-driving claims reproduced or labelled | claims needing a private run → "unreproducible without B-1" |
| 14 | HC-18 (agent part) | temporary public runner registered, removed, guide corrected, decommission script | service install/removal → parked (B-7) |

**Parking lot (the loop never executes these; it only keeps them current):** HC-02 (B-1),
HC-07's decision (B-3), HC-13 (B-5), HC-15 (B-6), HC-03's decision (B-2), the privileged
part of HC-18 (B-7), and the time-gated PHB-05 (2026-09-22), HC-14 (2026-09-21), R-07
(2026-09-24), PHB-08/R-08 (2026-10-08). Re-entry for the time-gated items is by scheduled
wake-up, never by dispatching to hurry the calendar (AO-11).

**Termination:** the loop ends when L-9 finds only parked items. Its final report must list,
per parked item, the human action or date it is waiting on. It may not report the mission
complete (§H12).

**Resume prompt (verbatim, for a new session or a scheduled wake-up):**
> Resume the MT069 execution loop. **Start with §H15 (Checkpoint & Resume Guide, 2026-09-19) — it supersedes this paragraph where they differ.** Read `plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md` §H4, §H7, §H14, §H15 and `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/loop_log.md`. Run the iteration protocol L-0…L-9 on the first unparked card. Never enable or dispatch any private `Aspose/aspose.org` workflow, never touch secrets, never run `sudo`. Park anything needing a human. Stop when only parked items remain and report what each is waiting on.

### H15. Checkpoint & Resume Guide (2026-09-19)

Written on the user's instructions *"stop at a clean checkpoint. I need to restart the machine. you can resume when I say so"* and *"update the plan file with true statuses and updates to make resume easy"*. **The execution loop is PAUSED, not finished.** Do not start any card until the user says to resume. Nothing was enabled, dispatched, rotated or deleted at the checkpoint, and the standing hard constraint (no private `Aspose/aspose.org` workflow enabled or dispatched without a human go-ahead — §H14 E-HUMAN records the only one given, for HC-02 as written) is unchanged.

*Progress after this checkpoint (the user's "resume", 2026-09-19) is in §H16, which supersedes the H15.1 rows for HC-02, HC-05 and HC-06 and adds HC-20.*

**How far to trust this section.** Ledger statuses were read with `taskcard_cli.py latest` at the checkpoint (HC-05 and HC-06 were advanced `TODO → IN_PROGRESS` in this pass, each citing evidence that exists on `origin/main`). Every commit SHA named here was verified as an ancestor of `origin/main`. **External state (runners online, workflows disabled) was last observed on 2026-09-18/19 and was NOT re-checked after the restart request** — re-observe it in the first pre-flight, do not copy it forward.

#### H15.1 Live status of every hardening card (checkpoint)

| Card | Ledger | Plan grade (§H5 vocabulary) | Proof (all on `origin/main` / public runs) | What is left | Waiting on |
|---|---|---|---|---|---|
| HC-01 | IMPLEMENTED | completed_verified | `9ac1744b05` | — | — |
| HC-02 | TODO | blocker (not started) | — | First controlled re-enable, one workflow, per `docs/operations/first-live-run-protocol.md` | HC-06 dynamic simulation; a fresh pre-flight; see H15.5 step 4 |
| HC-03 | IN_PROGRESS | partially_done | Isolation-model section + measured host facts; runs `35380303439`, `35381064675`; decision (b) recorded | Human `sudo` steps to build the dedicated distro; negative control after it exists | **B-2** (human) |
| HC-04 | IMPLEMENTED | completed_verified | `ebef471a01`; runs `35382618609`, `35382743233`→#46, `35382828640`, `35382884301`, `35382970613` | Queued-run-age path unexercised (needs HC-02) | — |
| HC-05 | IN_PROGRESS | partially_done | `94e3a2dfe3`; 51 tests; 3 mutations caught | Scheduled workflow, artifact-chain history, dry-run, `--live`; warm-up ≥3 periods | agent (next); time |
| HC-06 | IN_PROGRESS | partially_done | Static enumeration; probe runs above | Dynamic CI-mirror simulation (`sim.sh`), never completed | agent (next) |
| HC-07 | IMPLEMENTED | completed_but_weakly_verified | `dc36f0e4fa`; run `35380342397`; #43 closed | A green *scheduled* liveness fire; optional human deletion of the dead secret | time / human (optional) |
| HC-08 | IMPLEMENTED | completed_verified | `c71d3db64b` | — | — |
| HC-09 | IMPLEMENTED | completed_but_weakly_verified | `c069713946`, `40aa0358b3`; runs `35385437951`, `35385535807`→#47, `35385671831` | First scheduled fire (05:23 UTC); CI wiring of the orphan tests proven only by HC-02 | time; HC-02 |
| HC-10 | TODO | blocker | — | Copy TC-SG-07 criteria into a tracked file (agent part); flips + soak | **B-1**, time |
| HC-11 | IMPLEMENTED | completed_verified | `ebef471a01`; runs `35381607387`, `35382133262` | Private enable/disable steps unexercised (by design) | — |
| HC-12 | TODO | not_attempted | — | Manifest persistence + negative control in a scratch repo; needs the right skill/scope for `scripts/generator/**` | agent |
| HC-13 | TODO | follow_up | — | Decision: default is keep `launch-dashboard` dispatch-only unless the user says otherwise | user (product) |
| HC-14 | TODO | not_attempted (time-gated) | — | Observe the first scheduled runs on Mon 2026-09-21 (UTC: ci-onboarding-integrity-weekly 06:15, upstream-monitor 08:00, seo-weekly-analysis 09:00, install-literal-sweep 11:00) | time (**B-4**) |
| HC-15 | TODO | follow_up | — | Go/no-go per proposal; likely "build the soft-launch deadline watch" | user (**B-6**) |
| HC-16 | IMPLEMENTED | completed_verified | read-only investigation | — | — |
| HC-17 | IMPLEMENTED | completed_verified | local backlog `ST-202` | — | — |
| HC-18 | TODO | follow_up | — | Fresh-machine test with a temporary public runner + decommission script; the service install needs a human `sudo` | **B-7** (human) |
| HC-19 | TODO | not_attempted | — | Reproduction-based re-review of the 16 un-reproduced dossier claims | agent |
| PHB-03 | IN_PROGRESS | partially_done | as HC-05 | as HC-05; **do not mark `IMPLEMENTED` before it is proven live** | HC-05 |
| PHB-05 | IN_PROGRESS | partially_done | 1 scheduled run seen | ≥5 scheduled cycles on distinct UTC dates; earliest 2026-09-22 | time (**B-4**) |
| PHB-08 | TODO | not_attempted | — | Final comparison, due 2026-10-08; valid only if the workflows were enabled during the window | time; HC-02 |

Existing cards TC-01…TC-13 and PHB-01/02/04/06/07 are ledger `IMPLEMENTED` with the grades already in §H5.1; the checkpoint changed none of them.

#### H15.2 Repository and working-tree state

- All mission code and documents are committed to `origin/main`; the last code commit is `94e3a2dfe3` (HC-05). This plan file is committed as the checkpoint commit (`git log -1 -- plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md`). Nothing from this mission was left uncommitted.
- Other sessions keep committing to `main` and leave `content/**`, `.claude/settings.json`, `.gitignore`, `backlog/inbox.md` and the untracked `docs/discourse/` dirty. **Those are not ours — never stage them.** Commit only through `git_plumb_commit.py` with exact `--files`.
- Local, gitignored helpers in `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/` survive the restart (the repo lives under OneDrive) but are not in git: `loop_commit.sh` (`[ACK="paths"] bash loop_commit.sh "<message>" "<plan>" <files…>` — prints `COMMIT_OK <sha>` only when the commit is pushed **and** an ancestor of `origin/main`, and retries the concurrent-ref race), `deploy_public.sh` (deploys a template to the workflows repo), `sim.sh` (the WSL CI-mirror simulation — must stay LF), `loop_log.md`, `_taskcard_seed_batch_hc.json`, `_wfrepo/` (a shallow clone of the workflows repo — `git pull` before use), `apply_hc09_*.py`, `last_commit.log`.

#### H15.3 External state at last observation (re-verify first)

- All 20 private workflows `disabled_manually`. Two self-hosted runners, both systemd services inside WSL2: `alienware-m18-wsl2-private` (`Aspose/aspose.org`, label `gha-private-native`) and `alienware-m18-wsl2-test` (`Aspose/aspose.org-workflows`). Never run `run.sh` beside a service (a real double-listener incident).
- Public repo additions by this mission: `selfhosted-host-probe.yml`, `runner-availability-watch.yml` (hourly `17 * * * *`), `workflow-drift-watch.yml` (daily `23 5 * * *`), the `seo-token-liveness.yml` fix (`9a760a28`), the smoke-test STATUS NOTE (`a549958d`), `ARBITER.md` (`ae9faa50`), `upstream-monitor.yml` (`4ab9d5c3`). The drift baselines are in `data/workflow_deploy_baselines.json`, 18 entries.
- Public-repo issues #43, #46 and #47 are closed (#46 and #47 were control tests); issue #94 was closed earlier (AF-02). None opened by this mission is open.

#### H15.4 What the restart will do (expected, not faults)

1. WSL2 stops, so both runner services stop and both runners go **offline** until WSL starts. `svc.sh install` enables the unit, so they should return with the distro — verify with `systemctl is-enabled`, do not assume.
2. `runner-availability-watch.yml` checks hourly at :17 with a 2-check debounce. If the machine stays off for more than roughly two checks it will open a `runner-offline` issue on the public repo. That is the alerting working. Its recovery path closes the issue itself (proven with #46); if a stale issue remains after recovery, close it by hand.
3. The new session has a new session id: files it edits need `session_ledger.py adopt --files …` after checking the diff, and the skill context must be reopened: `skill_context.py begin --skill S-115 --scope "scripts/pipeline/lib/workflow_*,scripts/pipeline/commands/ops/workflow_*,scripts/pipeline/config/workflow_*,scripts/pipeline/tests/test_workflow_*,scripts/pipeline/config/registry.yaml,scripts/ci/**,.github/workflows/**,docs/operations/**"`. Commit this plan with `ACK=plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md` (it is gitignored) through `loop_commit.sh`.
4. `bvbmrctd8` / `bqz9c4ol6`-style background shells from the old session are gone; start nothing that depends on them.

#### H15.5 Exact next steps after the user says "resume" (in order)

1. **Pre-flight (L-0).** `taskcard_cli.py --mission MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE latest`; `git fetch` and `git log -1 origin/main`; `checkout_sync.py report`; both runners' API status and `busy`; `gh workflow list --repo Aspose/aspose.org --all` (all 20 must still be disabled); open issues labelled `runner-offline` / `workflow-drift` on the public repo; `check_workflow_drift.py --no-seed` (expect all in sync). Record the result in `loop_log.md`.
2. **HC-05 remainder.** Add a scheduled public template (new file under `scripts/ci/deployed-workflows/`, deploy with `deploy_public.sh`, seed its drift baseline, commit) that: restores `cost_budget_history.json` from the previous successful run's artifact (`gh run download`), runs `workflow_usage_collect_and_check.py --repo Aspose/aspose.org --history-file … --redact --details-file …` with `--ci-health-workflows Aspose/aspose.org-workflows:upstream-monitor.yml` and `skill-governance.yml`, uploads the new history as an artifact, and uses a sparse checkout limited to the files listed in the HC-05 card. Dry-run dispatch first, read the log, then `--live`; alerts must land on the **private** repo. Only after both are proven live, advance `PHB-03` to `IMPLEMENTED`.
3. **HC-06 dynamic simulation.** Re-run `sim.sh` **detached** (`setsid nohup … & disown`), as the runner user, with `LD_LIBRARY_PATH` set and LF endings; classify every failure as (a) genuine finding, (b) host/toolchain defect, (c) workflow bug (§H10). Hugo is `0.154.5` extended; the tool-cache Python is `~/actions-runner-aspose-org-workflows/_work/_tool/Python/3.13.15/x64/bin`.
4. **HC-02 (only after 1–3).** The §H14 authority is an *interpretation* of a broad message. Before the enable step, ask the user one yes/no question naming `content-governance-checks.yml`, then follow `first-live-run-protocol.md` exactly: one workflow, a proof-branch dispatch, observe, classify, **re-disable**, and ask whether to leave it enabled. Never enable a second workflow in the same pass.
5. **Agent-executable, no gate:** HC-10 agent part (copy the graduation criteria into a tracked file), HC-12, HC-19, HC-18 agent part. **Decisions to record:** HC-13 (default: keep dispatch-only), HC-15 (go/no-go per proposal).
6. **Time-gated, wake up by schedule, never by dispatching:** HC-14 on Mon 2026-09-21; PHB-05 from 2026-09-22; R-07 on 2026-09-24; PHB-08 / R-08 on 2026-10-08.

#### H15.6 Operating rules learned the hard way (from AF-28, AF-29)

- Advance the ledger **only** after `loop_commit.sh` prints `COMMIT_OK`; never pipe that helper through `tail` or `grep`, which hides the line.
- Never write scripts with a Windows-side text-mode Python write (CRLF) if WSL will run them; write with the Write tool and check `file`/`cat -A`.
- Put long commands and heredocs in files: the Bash-tool hook false-positives on `python -`, `pip ` and `python3` inside command text, and a heredoc with unbalanced quotes writes nothing.
- A background WSL process dies with its session; detach it. `actions/setup-python`'s Python needs `LD_LIBRARY_PATH`.
- A one-off "Permission denied" writing a source file was seen once under OneDrive; retry, and re-verify with `cmp` that a restore really happened before trusting a mutation test.
- Test the tests: before believing a suite written in one pass, mutate the source in the places the tests claim to protect and confirm each mutation fails a test (done for HC-05; the three mutations are in H5.3).

#### H15.7 Do not claim (yet)

`PHB-03` implemented; HC-02 done or any private workflow "working" after the cutover; container isolation; that a cap was "exceeded" (the 2,950 figure was a unit mismatch — AF-27); that `skill-governance.yml` runs the orphan test directory in CI; that any migrated workflow has fired on schedule (only the 2026-09-21 fires can show that); that the runner isolation target (b) exists.

### H16. Resume Log and Current State (2026-09-19, after "resume")

The user said "resume". The loop ran the §H15.5 pre-flight and then the agent-executable cards. Everything below was observed in this pass; nothing was enabled or dispatched in the private repo (the only dispatches were of *public* workflows).

**Pre-flight observed:** `origin/main` = `c2fee380d6` and both checkpoint commits are ancestors; the drift checker reported 18/18 in sync; all 20 private workflows still `disabled_manually` (only GitHub's own Dependency Graph is `active`); both runners `offline` (expected after the restart, the services having auto-started with the distro); public issue #48 (`runner-offline`) had been opened at 2026-09-18T21:40:59Z by the availability watch.

| # | What was done | Result | Evidence |
|---|---|---|---|
| 1 | HC-06 dynamic simulation (detached in WSL, scratch clone, runner user) | PASS 16 / FAIL 1 / WARN 6; 0 tool-missing signatures; Python 3.13.15 + Hugo 0.154.5 work host-direct; the 1 FAIL is a real gate defect → **HC-20** | §H5.3 HC-06, AF-31 |
| 2 | HC-05: scheduled telemetry workflow written, deployed, run | 5 public runs; live path, history chain, real alert-issue mechanics and by-design suppression all proven; 4 defects found and fixed (AF-33) | runs `35430975411`, `35431261729`, `35431326742`, `35431835805`, `35432258368`; commits `d93185120f`, `b564f11225`, `71da449f54`; workflows-repo `cfa6e404`, `3de0897f`; issue #49 (control, closed) |
| 3 | Runner availability re-proven on a *real* outage | Watch reported `online=0` when WSL stopped (AF-32); after a keepalive restored the runners, its recovery path closed #48 at 08:29:44Z | runs `35432016864` (correct failure), `35432110873` (recovery) |
| 4 | Guide updated | New troubleshooting entry: WSL stops when no session is open | `docs/operations/self-hosted-runner-setup.md` |
| 5 | Ledger | HC-05 `IN_PROGRESS`; HC-06 `IMPLEMENTED`; HC-20 seeded `TODO`; `PHB-03` `IN_PROGRESS` | `taskcard_cli.py latest` |

**Status delta (supersedes §H15.1 for these rows):**

| Card | Ledger | Plan grade | What is left | Waiting on |
|---|---|---|---|---|
| HC-02 | TODO | blocker (not started) — **all plan prerequisites now met** | The user's yes/no naming `content-governance-checks.yml`; then the protocol in `first-live-run-protocol.md` | **the user** (B-1); read HC-20 first |
| HC-05 | IN_PROGRESS | partially_done (one time-gated criterion) | First scheduled fire, Mon 2026-09-21 04:41 UTC, then `PHB-03 → IMPLEMENTED` | time (B-4) |
| HC-06 | IMPLEMENTED | completed_but_weakly_verified | Only HC-02 can prove the real service environment | HC-02 |
| HC-20 | IMPLEMENTED | completed_verified | **Done in this same pass** (`8c01cd7b98`): 141 → 0 on the simulation's exact 654-file window; English gate unchanged | — |
| PHB-03 | IN_PROGRESS | partially_done | as HC-05 | HC-05 |

**Current external state (as of ~08:35 UTC 2026-09-19; re-verify in the next pre-flight):** both runners `online`, but **only because this session started a hidden keepalive** (`wsl.exe -d Ubuntu-22.04 --exec sleep infinity`, pid 50952) — it ends at logoff or reboot, after which the runners go offline again and the watch will alert (AF-32); public issues #48 and #49 closed, none of ours open; no telemetry artifacts exist (test ones deleted so the chain starts empty); the drift checker is 19/19 in sync; all 20 private workflows unchanged.

**Repository:** commits since the checkpoint are `d93185120f`, `b564f11225`, `71da449f54`, `f3f7dc1af7` (this section and the guide entry) and `8c01cd7b98` (HC-20). HC-20's ledger row lives only in the gitignored `taskcards.jsonl` (the ledger is local by design).

**Operating rules added:** in the Bash tool `grep -c $'\r'` returns the line count (the quoting collapses) — count carriage returns with `tr -cd '\r' < file | wc -c`; the Write tool wrote LF here, but check before deploying anything a shell will run; `gh run list --workflow X` first looks the workflow up and can fail on a transient network error even when the dispatch before it succeeded — guard poll loops against an empty run id and re-list before re-dispatching; `pgrep -f` inside `wsl -e bash -c '…'` matches its own command line.

**Update, same pass:** HC-20 was then fixed under an `S-99` skill context scoped to the check and its test (commit `8c01cd7b98`); AF-31 is closed. HC-02's proof run should therefore no longer go red on that step — but it still may on others, so classify every red step from evidence.

**Next, in order:** (1) ask the user the HC-02 yes/no; (2) ~~HC-20~~ done; (3) HC-10 agent part, HC-12, HC-19, HC-18 agent part; decisions HC-13 (default: dispatch-only) and HC-15 (including whether a required check may read PASS at an 80% failure rate — AF-33); (4) time: Mon 2026-09-21 04:41 UTC telemetry first fire, then the four HC-14 fires; 2026-09-22 PHB-05; 2026-09-24 R-07; 2026-10-08 PHB-08. **Do not claim:** that the telemetry has run on schedule; that a live *private-repo* alert issue has been created (the mechanics were proven against the public repo, the default routing to the private repo only in unit tests); that `skill-governance.yml` is healthy (its CI-health reads INACTIVE only because it is disabled).

### H17. HC-02 Stage 1 — Record of the First Controlled Re-enable (2026-09-19)

*Supersedes the HC-02 row of §H16 ("all plan prerequisites met, awaiting the user").*

**Authority (E-HUMAN, verbatim, recorded per `first-live-run-protocol.md`).** The agent asked, naming the workflow: *"HC-02: may I enable ONE private workflow, content-governance-checks.yml, and dispatch ONE observed run on a proof branch, to prove the self-hosted cutover for real? … I would re-disable it right afterwards."* The user answered: *"Yes: one run, then re-disable (Recommended)"* (2026-09-19, ~08:50 UTC). **Scope:** that one workflow, one run, then re-disable. It does not cover a second run, `skill-governance.yml`, `llms-generation.yml`, or leaving anything enabled.

**What happened (all times UTC, 2026-09-19).**

| Time | Step | Evidence |
|---|---|---|
| 08:51:47 | Step 0 pre-state: 20 × `disabled_manually` (+ Dependency Graph `active`); runner online, idle; `origin/main` = `08b6d8e8f9`; 0 queued; WSL running | `evidence/hc02/01_pre_state.txt` |
| ~08:52 | Step 1 proof ref `mt069-live-proof-20260919` created at that SHA; it started no runs (`total_count` 0) | `02_proof_ref.txt` |
| 08:52:20 / :24 | Steps 2–3: `gh workflow enable`, then `gh workflow run … --ref <proof branch>` | `03_enable_dispatch.txt` |
| 08:52:27 | Run `35433173048` started; job `governance-checks` created 08:52:29, **started 08:52:32 on `alienware-m18-wsl2-private` (runner_id 21, labels `self-hosted, gha-private-native`)** | `04_run_id.txt` |
| 08:52 → 09:08 | `actions/checkout@v4`: a cold full-history fetch, 848 s (AF-35) — watched, not aborted: the abort rule is "queued > 15 min", and this job was running, network-bound and progressing | host observation |
| 09:09:35 | Job completed **success** — 36 of 36 steps green, run duration 1,029 s | `06_run_evidence.txt` |
| 09:09:51 | Step 6: `gh workflow disable` — window open 17.5 minutes | `05_disable.txt` |
| after | Post-state: 20 × `disabled_manually`, runner online idle, 0 queued, exactly one run of the workflow since enabling, proof branch deleted | `09_post_state.txt` |

**Results, classified (§H10).** No step failed, so nothing needs classifying (a)/(b)/(c). `timing.billable = {}` — **the job cost no Actions minutes**. The cost signature, the runner identity and the queue latency all match what the protocol verified in advance on the public repo. Log scan: no secret used, three masked values (the checkout token), no token-like strings, no `/mnt/` reference; the user's real `~/.gitconfig` is unchanged (checkout copies it to a temp dir); the two standing tool caches written outside `_work` are `~/.cache/pip` and `~/actions_hugo` (AF-36).

**What this run proves, and what it does not.**

| Claim | Status after this run |
|---|---|
| A private push-gated workflow runs to completion on the self-hosted runner | **Proven** (`completed_verified`) for `content-governance-checks.yml` — one run |
| It costs no Actions minutes | **Proven** for this run (`billable = {}`) |
| PHB-07 "runner serves private jobs" | Upgraded: it *did* serve one. The container-per-job model remains disproved (AF-24) |
| The HC-20 fix works in CI | **Not proven live.** A dispatch diffs only `HEAD~1` (the plan-file commit): "No content files changed" |
| TC-15 evaluator-version-bump behaves as designed | **Not proven live.** "OK: … (or none changed)" — nothing was there to check |
| The concurrency guard cancels a superseded run | **Not exercised** (one run, one ref) |
| TC-14 / `skill-governance.yml`; scoped `llms` regeneration | **Not run** — stages 2 and 3 |
| A warm run's cost | **Not measured** — this was the cold run (AF-35) |

**Current state (as of ~09:15 UTC; re-verify).** All 20 private workflows `disabled_manually`; runner `alienware-m18-wsl2-private` online and idle, held up by the hidden `wsl.exe … sleep infinity` keepalive (AF-32) — it ends at logoff or reboot; nothing of ours open in either repo; local evidence in `reports/plan_state/MT069-…/evidence/hc02/` (gitignored).

**What each next stage needs (none is started; each needs its own go-ahead naming the workflow).**
- **Stage 1b (optional, cheap):** a second enable-window using a proof ref whose last commit touches locale-directory translations (for example `e63c268614`), so `HEAD~1` covers real content: it would exercise the HC-20 fix and the version-bump step live, and measure the warm checkout.
- **Stage 2 — `skill-governance.yml`:** proves TC-14 and the added `workflow_dispatch` and `scripts/ci/checks/tests/` step. Its `governance-tests-windows` job is GitHub-hosted and **billed** — expect a few Windows minutes.
- **Stage 3 — `llms-generation.yml`:** proves the scoped-regeneration cost fix (HC-12 context). GitHub-hosted.

**Operating rules learned.** A `workflow_dispatch` run's diff-dependent steps see only `HEAD~1`: choose the proof ref's last commit deliberately if those steps are what you want to exercise. A cold first checkout on this runner takes ~14 minutes and occupies its single slot — do not read it as a hang; check `git fetch` progress on the host (`.git` growth) before aborting. `gh workflow disable` is the step to do *first* once the run is complete, before evidence collection, to keep the window short.

### H18. Maintainer Decisions on the Remaining Billed Workflows and on Runner Uptime (2026-09-19)

**Authority (E-HUMAN, verbatim).** After the HC-02 report the maintainer wrote: *"Runner uptime: Let me know what I need to do to make it persistant."* — then, on `skill-governance.yml`: *"Can't we move it to linux like other. Or it has to be on windows. In any case, this needs to be either transfered to self-hoster runner or public repo."* — and on `llms-generation.yml`: *"it has to go to pubic repo."* The first is a request for instructions (answered below, not executed). The second and third are instructions to move the two workflows off billed private runners; they name the destinations (self-hosted or public for the first; public for the second) but not which of the first two.

**Decisions and answers.**

| Question / instruction | Answer, with how it was established |
|---|---|
| Can the Windows job of `skill-governance.yml` be Linux? | **No.** The job's own comment says its defect classes are Windows-only in their silent forms; all 15 of its test files already run on Linux in the sibling job (checked against the pre-change file), so what it adds is the OS. Confirmed empirically: on real `windows-latest` (`core.autocrlf=true`, `cp1252`) it exercises conditions Linux cannot |
| Self-hosted or public, for the Windows leg? | **Public repo** — the agent's choice within the maintainer's "either", recorded and reversible. Free real Windows; no job code under the maintainer's own Windows account; independent of the machine being on. A native Windows self-hosted runner would keep per-push timing and a real blocking check, at the price of running CI code under that account and needing the machine on |
| `llms-generation.yml` → public | Done: it is read-only in effect (no commit, deploy, artifact or secret), so it moves as a scheduled smoke test |
| Runner uptime → what to do | The exact, **tested, no-admin** steps are in `docs/operations/self-hosted-runner-setup.md` ("Both runners go `offline`…"): one per-user Scheduled Task starting a headless `wsl.exe … sleep infinity` at logon, with `-ExecutionTimeLimit 0` (the default would kill it after 72 h) and the battery switches off. Each element was validated with a dummy task that was created and deleted. **Not executed by the agent** — it changes what starts with the maintainer's machine |

**What was built (cards HC-21, HC-22; commit `c38cd936a4`).** `governance-tests-windows.yml` (public, daily 03:37 UTC + dispatch; workflows-repo `53bd46ca`) and `llms-generation.yml` (public, daily 04:11 UTC + dispatch; workflows-repo `ef724a9b`), both with a validated `ref` input, `persist-credentials: false`, an alert issue that opens and dedups on red and closes on green, and drift baselines (21/21 in sync). The Windows job was **removed** from the private `skill-governance.yml`; the private `llms-generation.yml` keeps its body with its trigger narrowed to `workflow_dispatch`.

**Where the four largest private minute consumers now go** (base: the maintainer's 2026-09-01→18 export, 1,494 minutes):

| Workflow / job | Private minutes | Destination now | Proof |
|---|---:|---|---|
| `content-governance-checks.yml` | 546 (36.5%) | self-hosted Linux runner | **Proven** — run `35433173048`, `billable = {}` |
| `llms-generation.yml` | 259 (17.3%) | public repo, `ubuntu-latest` | **Proven** — run `35441201382` green |
| `skill-governance.yml` — Windows job | 223 (14.9%) | public repo, `windows-latest` | **Proven to run** — `35441199525` (369 passed / 3 failed, the 3 = HC-23) |
| `skill-governance.yml` — Linux job | 103 (6.9%) | self-hosted Linux runner | **Not yet proven** — HC-02 stage 2 |
| **Total** | **1,131 (75.7%)** | zero private minutes **by design** | 3 of 4 proven to run at zero private cost. Real private minutes are already zero because every private workflow is disabled, so the saving can only be *measured* (PHB-08) after a re-enable |

**Tradeoffs the maintainer takes on with these moves (stated so they can be reversed):** both public workflows run daily and on dispatch, not per push (a generator crash or a Windows-only regression is seen within a day, not minutes); the Windows leg can no longer block anything, so the TC-SG-07 graduation ("flip to blocking") becomes "the public run is green across the soak and its alert issue stays closed" (HC-10); public run logs can quote lines of the private repo's scripts (the alert issues carry only a commit SHA and the run link).

**New finding from the move (AF-37 → HC-23).** The Windows leg's first run found 3 failing tests that also fail on Linux and on the dev machine: the pre-commit hook's step numbering has drifted, and the standing red had hidden it. **Do HC-23 before HC-02 stage 2**, or that stage will be red for a known reason.

**Current state (~12:07 UTC 2026-09-19).** All 20 private workflows `disabled_manually`; both runners `online` (held by the session keepalive, pid 50952, until the maintainer runs the Scheduled Task command); public issue #50 (`windows-governance-red`) open with the known cause commented; drift 21/21 in sync; ledger: HC-21, HC-22 `IMPLEMENTED`, HC-23 `TODO`.

**Next.** (1) **The maintainer:** run the persistence command (and decide on Windows auto-login and on sleeping on battery). (2) HC-23, then a public Windows dispatch with `ref` = the fix commit to watch #50 close by itself. (3) HC-02 stage 2 (`skill-governance.yml`, one Linux job, no billed minutes) with its own go-ahead. (4) HC-12's live proof needs no private enable now — a public dispatch is enough. (5) HC-10's criteria file must reflect the changed graduation. (6) Time-gated items unchanged.

### H19. HC-23 Fixed and HC-02 Stage 2 Executed (2026-09-19)

**Authority (E-HUMAN, verbatim).** Asked *"Order: should I fix HC-23 before HC-02 stage 2? It edits the live pre-commit hook every session commits through … I recommend HC-23 first, because otherwise stage 2 is red for a known reason."*, the maintainer answered **"YES"**. Asked *"Go-ahead: HC-02 stage 2 (skill-governance.yml, one Linux job, no billed minutes) needs its own go-ahead from you."*, the maintainer answered **"OK"**. **Scope recorded:** `skill-governance.yml` only, one dispatched run, then re-disable (the protocol's default; leaving it enabled is a separate decision not made). The maintainer also ran the runner-persistence command: the Scheduled Task "WSL keepalive (GitHub runners)" was present when checked (count 1, 12:34 UTC).

**HC-23 (commit `6b6b1d13d9`).** Done first, as ordered — see its card. It needed a governed override token (`scripts/pre-commit-audit.sh` is a protected path), created on the "YES" and consumed by the commit. The public Windows leg at the fix commit passed **372 tests** and closed alert #50 by itself.

**Stage 2 timeline (UTC, 2026-09-19).**

| Time | Step | Evidence (`evidence/hc02s2/`, local) |
|---|---|---|
| 12:34:30 | Pre-state: 20 × `disabled_manually`; runner online, idle; `origin/main` = `6b6b1d13d9`; the workflow at that SHA has one job, on the self-hosted runner, with `workflow_dispatch`; 0 queued | `01_pre_state.txt` |
| 12:34:46 / :49 | Proof ref `mt069-live-proof-s2-20260919` (started 0 runs); `gh workflow enable`; `gh workflow run --ref` | `02_enable_dispatch.txt` |
| 12:34:54 | Run `35443264874`, job `enforce-venv-python` took `alienware-m18-wsl2-private` (runner 21) 3 s after creation | `03_run_id.txt` |
| 12:36:30 | Job completed **failure** — 98 s, `billable = {}`; `actions/checkout` **7 s** (warm; AF-41) | `05_run_evidence.txt` |
| 12:36:48 | `gh workflow disable` — window open **2 minutes**; post-state 20 × `disabled_manually`, 0 queued | `04_disable.txt` |

**Classification (§H10), each with a reproduction and a control.**
- **11 failures, all in `test_check_commit_bash_hook.py`** → **(b) host state**, AF-39. Host as-is: 11 failed; with the global/system git config hidden: 50 passed. Fixed by scoping `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1` to the two test steps (a job-level setting breaks `actions/checkout` — measured).
- **A latent second defect**, not visible in the run → **(c) workflow bug**, AF-40: 12 `test_verify_deploy_trigger.py` tests need full history; the run passed them only because the workspace held history from stage 1. Fixed with `fetch-depth: 0`.
- **The "previously never run in CI" step was skipped** behind the failure → `if: always()`.
- **Replay of the workflow's own steps** (extracted from the YAML by script, so they cannot drift) on the host with full history and the step env: **1,700 passed, 0 failed**; without the env, exactly the live run's 11. Commit `6b1bbbda2c`.

**What stage 2 proves, and what it does not.** *Proven:* the required Linux job of `skill-governance.yml` runs on the self-hosted runner, at no billed minutes, with every skill/registry/provenance check green and TC-14's platform-capabilities checks passing inside the test suite. *Not proven:* that the workflow is **green** — the fix above is verified on the host but not yet in CI, so `skill-governance.yml` has not yet had a passing run on the runner. That needs **stage 2b: one more run, and the maintainer's go-ahead** (the "OK" covered one run).

**Current state (~12:45 UTC).** All 20 private workflows `disabled_manually`; both runners online; public Windows leg green (#50 closed); drift 21/21 in sync; ledger: HC-23 `IMPLEMENTED`, HC-02 `IN_PROGRESS`.

**Next.** (1) Stage 2b — one confirming run of `skill-governance.yml`, needs a go-ahead. (2) Stage 1b (optional): a `content-governance-checks.yml` run on a ref whose last commit touches translations, to exercise the HC-20 fix and the version-bump step live. (3) HC-12's live proof by public dispatch. (4) HC-10's criteria file. (5) Time-gated: Mon 2026-09-21 04:41 UTC telemetry (→ `PHB-03`) and the HC-14 fires; 2026-09-22 PHB-05; 2026-09-24 R-07; 2026-10-08 PHB-08.

**Operating rules learned.** (a) Test a proposed job-level `env:` against `actions/checkout` on the host before committing it. (b) On a persistent runner, "it passed" can depend on what another workflow left in the workspace — check what a test really needs (full history, tools, config) rather than what the last run happened to have. (c) Replay a workflow's own steps by *extracting them from the YAML* (`build_sg_replay.py`) instead of retyping them. (d) A harness that builds from `HEAD` cannot see an uncommitted edit; overlay it.

### H20. HC-02 Stage 2b — the Confirming Run, and Where the Cutover Stands (2026-09-19)

**Authority (E-HUMAN, verbatim).** Asked whether it may enable `skill-governance.yml` once more, dispatch one confirming run at the fix commit and re-disable it, the maintainer answered **"Yes: one confirming run, then re-disable (Recommended)"**. Scope: that workflow only, one run, re-disable; not covering leaving it enabled.

**What happened (UTC, 2026-09-19).** Pre-state 13:09:12 (20 × `disabled_manually`, runner online and idle, 0 queued, proof SHA `5151bd9d05`, which contains the fix `6b1bbbda2c`) → proof ref created (0 runs started) → enabled 13:09:37 → dispatched 13:09:39 → run `35444938440` took `alienware-m18-wsl2-private` (runner 21) 3 s after creation → completed **success** 13:14:41 → disabled 13:14:46 (window 5 min 9 s) → post-state 20 × `disabled_manually`, 0 queued, proof branch deleted.

**Result.** **17 of 17 steps green.** The governance suite: **1,700 passed, 45 skipped, 0 failed** (stage 2: 1,689 passed, 11 failed); `scripts/ci/checks/tests/`: **113 passed** (it ran this time — `if: always()`, and no failure to skip it); **0** identity-guard blocks; the checkout used `fetch-depth: 0` (12 s on the warm workspace); `timing.billable = {}` (no Actions minutes); 299 s in total, of which a **140 s post-step** is `actions/setup-python`'s pip-cache save (it holds the runner's single slot but bills nothing). Log scan: no secret referenced, no token-like string, no `/mnt/` reference. This is the first passing run of `skill-governance.yml` since 2026-09-06, and TC-14's platform-capabilities tests now pass in CI.

**Where the cutover stands.** *Proven live, in CI:* both private required checks run on the self-hosted runner at zero Actions cost — `content-governance-checks.yml` (green) and `skill-governance.yml` (green after two real fixes); the two largest workflows that could not stay private run on free public runners — the Windows leg (372 tests) and `llms-generation.yml`; alerting works in both directions (runner offline, drift, Windows-red — each opened and closed by the workflows themselves). *Not proven:* the HC-20 fix and TC-15's version-bump behaviour in CI, the concurrency guard cancelling, and anything about the *saving* (PHB-08: every private workflow is disabled, so private minutes are zero by construction until a re-enable). Those are HC-24 and PHB-08.

**Current state (~13:20 UTC).** All 20 private workflows `disabled_manually`; runner online (kept up by the maintainer's Scheduled Task); the alert issues are all closed; drift 21/21 in sync; ledger: HC-02 `IMPLEMENTED` (weakly verified), HC-24 `TODO`. **Nothing is left enabled** — leaving a workflow enabled is a decision the maintainer has not made; until then, pushes to `main` trigger no private CI.

**Decision for the maintainer (not taken by the agent).** *When should the two private checks be turned on for good?* The cutover is proven for both, and each is a single job on the self-hosted runner. What enabling changes: every matching push to `main` queues a job on the maintainer's machine (about 2–5 minutes each once warm, one at a time), and the checks resume gating in the sense the repo has always had (a red status after the push). Reasonable options are to keep both off until HC-24 and the first scheduled fires (Mon 2026-09-21) are in, to enable `content-governance-checks.yml` first (largest driver, green, no known issue), or to enable both now. The plan does not choose.

**Next.** (1) The maintainer's decision above. (2) HC-24 (optional, needs a go-ahead). (3) HC-12's live proof by public dispatch; HC-10's criteria file; HC-19; HC-18's agent part. (4) Time-gated: Mon 2026-09-21 04:41 UTC telemetry (→ `PHB-03`) and the four HC-14 fires; 2026-09-22 PHB-05; 2026-09-24 R-07; 2026-10-08 PHB-08.

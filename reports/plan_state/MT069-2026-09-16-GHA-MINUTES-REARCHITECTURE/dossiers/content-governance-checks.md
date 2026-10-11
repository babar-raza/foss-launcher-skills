# Dossier: content-governance-checks.yml

## 1. Identity and purpose
Primary push(main) governance gate for content/pipeline/skills changes — the broadest
scope of any workflow in the repo (~30 steps: blog hygiene, family icons, encoding
parity, API accuracy audit, grade integrity, evaluator freeze/version-bump, DAR
coverage, pipeline registration, mission-ledger checks, Hugo build verification).

## 2. Trigger and execution path
`push(main, 9-entry path filter)` + `workflow_dispatch`. 1 job, `ubuntu-latest`,
`timeout-minutes: 30`. `DIFF_BASE = github.event.before`.

## 3. Consumers and business importance
`P0_CRITICAL` (`analysis/importance_matrix.json`). Successor to the dead
`content-audit.yml`; the only live enforcement point for 18+ blocking checks per its
own header comment.

## 4. Historical usage
**#1 real cost driver**: 546 of 1,494 minutes (36.5%), 200 runs, Sept 2026
(`usage/usage_dataset.json`).

## 5. Outcome and failure analysis
49% Sept failure rate (98/200), 60.8% historical (271/446, back to March). **Root-caused,
not assumed**: 3 sampled failures = 3 different evaluators blocked by
`check_evaluator_version_bump.py` — a real, recurring authoring-discipline gap, not a
flaky or broken check (`analysis/failure_signatures.json`). **Fixed this mission**:
`TC-15` gave this check real pre-commit enforcement (Step 44). **Correction (TC-11
independent review, 2026-09-17)**: this line previously misattributed this workflow's
concurrency/cancel-in-progress guard to "`TC-14`/`TC-15` work" — that fix was actually
done via `/workflow-harden` (S-115) under `TC-03`, unrelated to `TC-14`/`TC-15` (which
fixed the platform-capabilities checker bug and the evaluator-version-bump shift-left,
respectively). It also previously said the concurrency fix "landed" — as of the same
review, `git status --porcelain` shows it is still an **uncommitted working-tree edit**,
not durable; it will not survive a `git checkout --` or another session's conflicting
edit until committed. Future failure rate should drop once the shift-left fix has time
to take effect — not yet observed live (workflow is disabled).

## 6. Secrets and permissions
`permissions: contents: read`. No `secrets.*` referenced.

## 7. Private/public data classification
Reads the full private checkout (content/, scripts/, knowledge/, data/). Not a
candidate for public execution regardless of secret exposure — see §9-11.

## 8. Current runner dependencies
`ubuntu-latest`, GitHub-hosted, no matrix.

## 9. Option A (remain private, GitHub-hosted) — pros/cons
Pro: no migration risk. Con: this is where the cost actually is; doing nothing leaves
the #1 driver unaddressed.

## 10. Option B (public repo) — pros/cons
**Rejected.** Push-gated, needs native integration with this repo's own commits, which
a workflow in another repo cannot provide without introducing polling latency (see the
open architectural question in `analysis/destination_decision_matrix.json` — not fully
evaluated, flagged for a future pass, not chosen here).

## 11. Option C (self-hosted) — pros/cons
**Selected.** Pro: zero marginal Actions cost; residual risk is operational
(single-machine resource contention), not code-injection (this repo's real flow is
direct push, not PR-from-fork). Con: real engineering effort (state machine, runner
lifecycle — see `design/self_hosted_architecture.md`); requires the concurrency fix to
be committed before cutover (see correction above — real, but currently uncommitted;
a precondition still open, not yet satisfied).

## 12. Optimization or retirement opportunity
Concurrency/cancel-in-progress guard (added via `/workflow-harden`/`TC-03`, **still
uncommitted** — see correction above); evaluator-version-bump shift-left (done, `TC-15`)
should reduce the real failure-driven re-run cost going forward.

## 13. Recommendation
`MOVE_TO_SELF_HOSTED_LINUX_ON_WINDOWS_HOST` (`analysis/destination_decision_matrix.json`,
confidence HIGH).

## 14. Rejected alternatives
Public migration (structurally unavailable); retire/consolidate (this is the primary
content-quality gate, not optional).

## 15. Expected savings
Up to 546 min/month (36.5% of total) removed from the private GitHub-hosted allowance,
pending real Phase B measurement — not yet observed live.

## 16. Migration complexity
HIGH — requires the full self-hosted runner design (`design/self_hosted_architecture.md`)
and the Phase B migration-run state machine, not a quick cutover.

## 17. Risks
Single-machine resource contention if the concurrency fix regresses; runner offline
during a push (mitigated by the `DEGRADED` alert design).

## 18. Tests
`TC-14`'s fix suite (12/12) + full `scripts/ci/tests/` (1102/1102, 1 unrelated skip) —
both already run and clean as of 2026-09-17.

## 19. Rollback
Re-enable on GitHub-hosted (reversing the self-hosted cutover) — no data loss, since the
concurrency-guard fix is independent and stays either way.

## 20. Evidence and confidence
HIGH confidence on cost/failure numbers (real data, two independent sources agree —
usage export and `gh api` run history). MEDIUM confidence on the self-host-vs-poll
architecture choice (the polling alternative genuinely wasn't fully evaluated).

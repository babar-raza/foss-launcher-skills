# Dossier: install-literal-sweep.yml

## 1. Identity and purpose
"Install Defect Sweep (durability)" — a full-corpus literal-install-instruction defect
sweep (the workflow's `name:` field was updated; the filename is stale/frozen because
`.github/workflows/` is T-00 non-renameable per this repo's own governance).

## 2. Trigger and execution path
`schedule(Monday 11:00 UTC)` + `workflow_dispatch`. 1 job, `ubuntu-latest`,
`timeout-minutes: 20`.

## 3. Consumers and business importance
`INSUFFICIENT_EVIDENCE` (`analysis/importance_matrix.json`) — correctly rated, but for
the benign reason resolved in §4 (too young to have a real track record), not because
whether it runs at all is in doubt.

## 4. Historical usage
Zero minutes in the Sept usage export, and zero recorded runs anywhere in the 172-day
retained `gh api` run history. **RESOLVED (TC-11 independent review, 2026-09-17,
re-verified independently a second time via `git log --follow --diff-filter=A -- .github/
workflows/install-literal-sweep.yml`)**: this workflow was added 2026-09-10 (commit
`f9cbe210fb`), not present for the earlier bulk of that 172-day history at all. Its
weekly Monday-11:00-UTC schedule means at most **one** firing (2026-09-14) was
structurally possible before the usage window closed on 2026-09-18 — and 2026-09-14 is
also the date `inventory/disabled_vs_running_anomaly.md` confirms as the last day other
workflows had successful runs before the mass-disable. Zero recorded runs is fully
explained by the file's young age plus the mass-disable's timing; it is not evidence of a
broken trigger, a `gh api` name-matching gap, or non-functionality.

## 5. Outcome and failure analysis
No data — no runs found to analyze.

## 6. Secrets and permissions
`permissions: contents: write, issues: write`. `secrets.GITHUB_TOKEN` referenced
explicitly (used for `git_plumb_commit.py`).

## 7. Private/public data classification
Would write repo-internal sweep reports; auto-commits today (not PR-gated).

## 8. Current runner dependencies
`ubuntu-latest`, GitHub-hosted.

## 9-11. Destination options
Not meaningfully evaluable without first confirming basic operability.

## 12. Optimization or retirement opportunity
Resolved (see §4) — the "does it actually fire" question is closed; it hasn't had a real
opportunity to fire more than once yet, not a broken trigger. Once workflows are
re-enabled, its first few real Monday runs are the way to confirm actual operability
going forward — no further archival investigation is needed.

## 13. Recommendation
`SPLIT_BETWEEN_PRIVATE_AND_PUBLIC` (`analysis/destination_decision_matrix.json`,
confidence LOW) — provisional, contingent on the user's separate open decision about
converting its auto-commit behavior to PR-gated, and on observing its first real runs
once re-enabled (not on a "does it run at all" mystery, which §4 resolved).

## 14. Rejected alternatives
None — genuinely unresolved rather than narrowed down.

## 15. Expected savings
Unknown — cannot estimate savings for a workflow with no observed real cost.

## 16. Migration complexity
Unknown pending the operability question.

## 17. Risks
Low — the "silently non-functional" risk this section originally flagged is
substantially de-risked by §4's resolution (the file simply hasn't had more than one
possible chance to run yet, not a sign of breakage). Residual risk: its one possible
firing (2026-09-14) landed the same day as the mass-disable, so it may not have actually
executed even that once — worth a quick confirmation once workflows are re-enabled, not
a mission blocker.

## 18. Tests
None run.

## 19. Rollback
N/A.

## 20. Evidence and confidence
HIGH confidence on the resolved "why zero runs" question (directly verified via git
history). LOW confidence remains on the destination/migration decision specifically —
that part is genuinely still provisional (see §13), but for the ordinary reason of an
open product decision plus no real-run track record yet, not an unresolved mystery.

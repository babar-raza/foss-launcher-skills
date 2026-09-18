# Dossier: launch-dashboard.yml

## 1. Identity and purpose
Reporting/observability dashboard over launch-readiness state (`phase_state.json`,
human-review reports, product registry, knowledge model status).

## 2. Trigger and execution path
`push(main, narrow path filter)` + `schedule(Monday 09:00 UTC)` + `workflow_dispatch`.
1 job, `ubuntu-latest`, `timeout-minutes: 10`.

## 3. Consumers and business importance
`P2_MEDIUM` — a reporting tool, not a gate; its absence doesn't block anything.

## 4. Historical usage
17 min/1.1% of total (Sept), 14 runs.

## 5. Outcome and failure analysis
**100% failure, both Sept (14/14) and full history (58/58) — has never once succeeded.**

**Correction history, both same day (2026-09-18) — record both passes, not just the
final one, since the first correction was itself wrong and that is worth learning
from:**

**Pass 1 (later found incomplete)**: verified `launch_dashboard.py` has zero
third-party imports and runs successfully in a genuinely bare local venv, producing a
real 33-product dashboard with 2 flagged gaps (`cells/typescript`, `imaging/net`).
Concluded the original "missing pip install" theory was wrong and the workflow was a
healthy gate, not broken. **This conclusion was itself wrong** — the local test ran
against this session's own working directory, which has locally-accumulated report
files never present in a real CI checkout.

**Pass 2 (the real root cause, verified against an actual fresh checkout)**: migrated
the schedule leg to `Aspose/aspose.org-workflows` and dispatched it for real. Result:
`Total: 33 products | READY: 0 | NOT READY: 0 | NO REPORT: 33 | Gaps: 99` — a
completely different, much worse outcome than the local test showed. Root cause:
`launch_dashboard.py`'s real inputs — `reports/phase_state.json`,
`reports/human-review/**`, `reports/**/readiness.md` — are git-ignored (`.gitignore:22:
reports/*`), cumulative, lock-protected local state built up over time by
`project_phase_store.py` (a checkpoint store explicitly designed for incremental local
mutation, e.g. `set <family> <platform> blog_done true --artifact <path>` — not
something regenerable in one CI run). **These files are never available in any fresh
checkout, public or private, self-hosted or GitHub-hosted — this is a data-availability
problem, not a hosting-location problem, and no migration destination fixes it.** A
second, related defect: 3 of this workflow's own 5 push-trigger path filters
(`reports/phase_state.json`, `reports/human-review/**`, `reports/**/readiness.md`) are
themselves gitignored and can structurally never appear in a real git push diff — those
3 filter entries are dead weight; only `data/products.json` and
`knowledge/**/merged/model.yaml` can ever actually fire the push trigger.

**"100% failure rate" is real and reflects a genuine, permanent structural limitation
in this workflow's design** (a local-development-machine progress dashboard, wired up
as if it were a stateless CI check) — not a quick-fix defect, and not (contrary to the
Pass-1 correction) a healthy gate either, since in real CI it cannot see the data it
needs to report anything meaningful at all.

## 6. Secrets and permissions
`permissions: contents: read`. No `secrets.*`.

## 7. Private/public data classification
Reads repo-internal state only; low sensitivity.

## 8. Current runner dependencies
`ubuntu-latest`, GitHub-hosted.

## 9-11. Destination options
**Not meaningfully migratable in its current form to ANY destination** — this is not a
hosting-location decision. Self-hosting doesn't help (a self-hosted runner also gets a
fresh `actions/checkout` into a clean directory by default). Public migration doesn't
help (proven live — `NO REPORT: 33`). Staying private doesn't help either, since the
private original's own real GitHub Actions runs face the identical fresh-checkout
constraint. The only things that would actually help are out of scope for a workflow
migration: (a) redesign `launch_dashboard.py` to derive its report from git-tracked
signals only (dropping the `phase_state.json`/`human-review` dependency), or (b) stop
treating this as a CI job at all and document it as a local-only developer diagnostic.

## 12. Optimization or retirement opportunity
No cheap fix exists. The originally-attempted "quick fix" (add a missing `pip install`
step) was based on an unverified assumption and would have changed nothing (confirmed —
the script has zero third-party dependencies). The schedule leg was briefly migrated to
`Aspose/aspose.org-workflows`, proven live to be useless there (identical root cause,
not a hosting artifact), and reverted to `workflow_dispatch`-only rather than left
running unattended and reporting misleading "Gaps: 99" every week.

## 13. Recommendation
`REQUIRES_REDESIGN` (reverted back from a same-day `SPLIT_BETWEEN_PRIVATE_AND_PUBLIC`
correction that was itself wrong once actually tested — see §5's two-pass history).
Confidence HIGH on the diagnosis (now verified against a real fresh checkout, not
assumed either way); the actual redesign (rebuild from git-tracked data, or retire as a
CI job) is not scoped or attempted here.

## 14. Rejected alternatives
Public migration (tried, proven not to help). Self-hosting (would face the identical
fresh-checkout constraint). "Fix the missing pip install" (there is nothing to
install).

## 15. Expected savings
None achievable via migration — the real fix is a script/design change, not a hosting
change, and is not estimated here.

## 16. Migration complexity
N/A — migration is not the right lever for this workflow's actual problem.

## 17. Risks
Low blast-radius (read-only, no downstream consumers), but a real risk of false
confidence: a maintainer glancing at "Gaps: 99" or a clean run without knowing this
history could draw the wrong conclusion in either direction.

## 18. Tests
Verified live, twice, with two different (and initially contradictory) results before
reaching the real root cause: a local working-directory run (misleadingly healthy-
looking) and a genuine fresh-checkout dispatch on the public repo (the real, broken-for-
CI-purposes result). The second test is the one that matters for any hosting decision.

## 19. Rollback
The public schedule-leg workflow was reverted to `workflow_dispatch`-only the same day
it was added (commit `6e6085f`) rather than left running — no rollback pending.

## 20. Evidence and confidence
HIGH confidence on the final diagnosis, specifically because it survived being tested
against a real fresh checkout rather than resting on a local-only result. LOW
confidence remains on what the actual fix should be (script redesign vs. retirement as
a CI job) — genuinely not decided here, flagged rather than guessed.

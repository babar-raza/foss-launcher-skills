# Usage/Billing Reconciliation

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Taskcard:** MT069-TC-04-USAGE-BILLING-COLLECTION
**Date:** 2026-09-18

## Method actually used

`TC-04` was originally scoped as two phases: (4a) an agent-doable `gh api` run/job-duration
proxy reconstruction, and (4b) reconciling that proxy against a real, human-supplied
Billing UI export. **Phase 4a was skipped by explicit user instruction** ("it is the same
as I have provided manually, no need to extract it again") — the user supplied the real
org-level export directly (GitHub → Insights → Actions usage metrics, `Aspose/aspose.org`
repo view, period 2026-09-01 through 2026-09-18) before the proxy was built.

This is not a shortcut that loses rigor: the whole purpose of Phase 4a was to produce an
*estimate* to stand in for real billing data until real billing data was available. Once
the real data was in hand, building an estimate of it would add cost without adding
information. The real export is used directly as `usage_dataset.json` — see that file for
the full per-workflow breakdown.

## Reconciliation status

**No reconciliation gap exists to close.** There is no separately-derived proxy figure to
compare against the real export, because the real export was used as the dataset from the
start. `TC-04`'s mandatory acceptance criterion — "usage/billing figures are reconciled
against a real org-level source (the user's Billing UI export), not the repo-scoped
run/job-duration proxy alone" — is satisfied directly: the dataset *is* the real org-level
source.

## Headline results (see `usage_dataset.json` for full detail)

- Total: 1,494 minutes, 561 job runs, 2026-09-01 through 2026-09-18.
- Top 3 workflows = 75.7% of all usage: `content-governance-checks.yml` (546 min/36.5%),
  `llms-generation.yml` (259 min/17.3%), `skill-governance.yml` combined (326 min/21.8%).
- `llms-generation.yml` is a newly-surfaced major cost driver, not previously identified.
- `skill-governance.yml`'s Windows job (223 min) costs more than its own Linux job
  (103 min) — reverses an earlier assumption from the pre-data proxy analysis.
- Four workflows show zero usage this period: `content-audit.yml` (expected — confirmed
  dead trigger), `cross-repo-index-sync.yml`, `metrics-governance.yml` (both consistent
  with narrow path filters), and `install-literal-sweep.yml` — **RESOLVED (TC-11
  independent review, 2026-09-17)**: not unexpected after all. The workflow was added
  2026-09-10 (`git log --follow --diff-filter=A`, commit `f9cbe210fb`), so its weekly
  Monday schedule had at most one possible firing (2026-09-14) inside this period before
  the mass-disable, not the "should fire ~twice in 18 days" assumption this document
  originally reasoned from.

## What this feeds into

- `TC-05` (failure-signature analysis): investigate `install-literal-sweep.yml`'s zero
  usage as a possible real defect, and whether `llms-generation.yml`'s 89 runs correlate
  with failures worth knowing about.
- `TC-06` (importance matrix) / `TC-07` (destination decisions): use these real minute
  figures directly, not the proxy — the destination-triage table in the governing plan
  has already been updated to reflect them.
- `TC-13` (recurring cost-telemetry proposal): this dataset is the baseline the proposed
  weekly collector would need to reproduce automatically going forward.

## Evidence

- `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/usage/usage_dataset.json`
- User-supplied screenshot/paste of the org's Actions Usage Metrics page, this session,
  2026-09-18.

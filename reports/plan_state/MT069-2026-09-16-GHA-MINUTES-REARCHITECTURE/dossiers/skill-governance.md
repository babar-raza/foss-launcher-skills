# Dossier: skill-governance.yml

## 1. Identity and purpose
Governance gate for the skill/automation system itself: venv/Python enforcement, skill
registry completeness, commit-skill-provenance, and (Windows job) OS-specific defect
classes.

## 2. Trigger and execution path
`push(main, 34-entry path filter)` + identical `pull_request` filter (likely dead per
`TC-03`'s HP-08, unconfirmed). 2 independent jobs: `enforce-venv-python` (ubuntu,
required) and `governance-tests-windows` (windows, job-level `continue-on-error: true`,
soft-launched).

## 3. Consumers and business importance
`P0_CRITICAL` (`analysis/importance_matrix.json`) — this repo's own automation safety
net; a silent failure here compounds across every other skill.

## 4. Historical usage
**#3 real cost driver, combined**: Windows job 223 min/14.9% + Linux job 103 min/6.9% =
326 min/21.8% (Sept 2026). The Windows job costs *more* than the required Linux job —
reverses an earlier proxy-based assumption that it was small.

## 5. Outcome and failure analysis
**100% Sept failure rate on the required Linux job** (40/40), 83.2% historical
(252/303). **Root-caused, not assumed**: a latent comparison bug in
`check_platform_capabilities.py::check_example_verification()` (added 2026-09-06),
producing 6 false-positive findings every run against a stale, pre-existing test
fixture — NOT real registry drift (`platform_capabilities.yaml` and
`registry.PLATFORM_CONTRACT` were fully in sync the whole time). **Fixed this mission**:
`TC-14` corrected the comparison logic and rescoped the stale test; 12/12 targeted tests
+ full suite (1102/1102) pass. Real failure rate should drop to near-zero once this
workflow runs live again — not yet observed (currently disabled).

## 6. Secrets and permissions
`permissions:` absent/default for both jobs. No `secrets.*` referenced.

## 7. Private/public data classification
Reads skills/, `.agents/skills/`, `.claude/commands/`, `scripts/ci/*.py` — private
governance surface, not a public-migration candidate (see §10).

## 8. Current runner dependencies
`ubuntu-latest` (required) + `windows-latest` (soft-launched), GitHub-hosted, no matrix.

## 9. Option A (remain private, GitHub-hosted) — pros/cons
Con: this is where a large share of the real cost is, and the false-positive failure
made every run wasted regardless of hosting.

## 10. Option B (public repo) — pros/cons
**Rejected** for the required Linux job — same reasoning as `content-governance-checks.yml`
(native push integration needed). Not evaluated for the Windows job either, since its own
disposition (§11) is separately unresolved.

## 11. Option C (self-hosted) — pros/cons
**Selected for the required Linux job.** Same reasoning as `content-governance-checks.yml`.
**Windows job: unresolved, MEDIUM confidence.** Real data shows it costs more than
expected (223 min); cheapest fix (demote trigger to schedule/dispatch via
`/workflow-harden`) not yet evaluated — see `design/self_hosted_architecture.md`.

## 12. Optimization or retirement opportunity
**Correction (TC-11 independent review, 2026-09-17)**: this line previously
misattributed this workflow's concurrency/cancel-in-progress guard to "`TC-14`/`TC-15`"
and called it "done." It was actually added via `/workflow-harden` (S-115) under
`TC-03`, and `git status --porcelain` confirms it is still an **uncommitted**
working-tree edit, not durable. The checker bug fix (done, `TC-14`) should
restore this workflow's actual governance value (it was providing zero signal while
100% broken); the Windows-job trigger-demotion option is a real, cheap lever not yet
taken.

## 13. Recommendation
`SPLIT_BETWEEN_HOSTED_AND_SELF_HOSTED` (`analysis/destination_decision_matrix.json`,
confidence MEDIUM — the Windows-job sub-decision keeps this from HIGH).

## 14. Rejected alternatives
Public migration for either job (structurally unavailable for the required job; not
evaluated for the Windows job pending its own disposition).

## 15. Expected savings
Up to 103 min/month (Linux job) from self-hosting; potentially the full 223 min/month
(Windows job) if trigger-demotion or self-hosting is applied there too — not yet decided.

## 16. Migration complexity
HIGH for the Linux job (same state-machine/runner-lifecycle work as
`content-governance-checks.yml`); LOW for the Windows-job trigger-demotion option
specifically (a one-line trigger change via `/workflow-harden`), if chosen.

## 17. Risks
Same single-machine contention risk as `content-governance-checks.yml` for the Linux
job. For the Windows job, self-hosting gives up GitHub-hosted Windows runners' VM
disposability for a narrow, soft-launched job — a real tradeoff, not free.

## 18. Tests
`TC-14`'s fix suite (12/12, includes a new regression-pinning test) + full
`scripts/ci/tests/` (1102/1102) — both run and clean.

## 19. Rollback
Re-enable on GitHub-hosted for either/both jobs independently — no data loss.

## 20. Evidence and confidence
HIGH confidence on the checker-bug root cause (read the actual code, traced the exact
git history, confirmed via direct logic tests). MEDIUM confidence on the Windows job's
final destination — genuinely undecided, not a placeholder.

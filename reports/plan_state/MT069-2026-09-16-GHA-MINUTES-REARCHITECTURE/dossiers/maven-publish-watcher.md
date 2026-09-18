# Dossier: maven-publish-watcher.yml

**1. Identity/purpose**: Daily Maven Central publish-status watcher for Java/Maven FOSS
packages; auto-applies registry changes and opens issues on new/updated publishes.
**2. Trigger**: `schedule(09:00 UTC)` + `workflow_dispatch`. 1 job, ubuntu, 10min timeout.
**3. Importance**: `P1_HIGH` — drives real, user-facing installation-instruction
accuracy.
**4. Usage**: 16 min/1.1% (Sept), 13 runs.
**5. Failure analysis**: 0% failure, Sept and full history (51/51) — healthy. Correctly
guards its `continue-on-error` consumption (checks `steps.watch.outcome`/`outputs`
before acting) — a positive example, not a defect. Missing pip cache (HP-12, minor,
inconsistent with sibling watchers).
**6. Secrets/permissions**: `contents: write, issues: write`. No explicit `secrets.*`
(default token via `github-script`).
**7. Data classification**: **auto-commits directly today** — the proven public pattern
only ever opens a PR. Migrating requires the user's still-open product decision (see
Human Decisions in the governing plan).
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: public migration mechanically clean, but blocked on the auto-commit
question; self-hosting not warranted for a low-cost, healthy schedule bot.
**12. Optimization**: add pip cache (cheap, minor); consolidation candidate alongside
the other 3 watcher bots into one scheduled matrix (checkout/venv overhead amortized).
**13. Recommendation**: `SPLIT_BETWEEN_PRIVATE_AND_PUBLIC` (confidence MEDIUM — pending
the user's decision).
**14. Rejected alternatives**: self-hosting (no reliability need, low cost).
**15. Expected savings**: ~16 min/month, plus shared consolidation savings if bundled
with its 3 siblings.
**16. Migration complexity**: MEDIUM — requires the auto-commit→PR-gated behavior
change, not a pure copy.
**17. Risks**: converting to PR-gated changes real operational behavior (registry
updates no longer land automatically) — a product decision, not a technical one.
**18. Tests**: none run (design-only, blocked on the pending decision).
**19. Rollback**: keep the private original enabled until the PR-gated version is proven.
**20. Evidence/confidence**: HIGH on cost/health; MEDIUM on destination pending the
human decision.

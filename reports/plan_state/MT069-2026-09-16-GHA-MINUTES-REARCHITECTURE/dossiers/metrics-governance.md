# Dossier: metrics-governance.yml

**1. Identity/purpose**: Governs the LLM-metrics subsystem's own code (schema, callsite
registry, no-secrets, taxonomy, docs propagation checks).
**2. Trigger**: `push(main)`/`pull_request`, identical 7-entry filter (HP-08, possibly
dead PR trigger). 1 job, ubuntu, 15min timeout.
**3. Importance**: `P2_MEDIUM`.
**4. Usage**: **0 minutes in the Sept export** — narrow path filter untouched this
period.
**5. Failure analysis**: no Sept data; **68.2% historical failure (7/22)** — a real,
concerning rate, but stale (no recent runs to confirm current status). Flagged for
attention if/when this workflow resumes firing regularly, not resolved here.
**6. Secrets/permissions**: `permissions:` absent/default. No `secrets.*` (has its own
"no secrets in metrics code" check, unrelated to this workflow's own credential use).
**7. Data classification**: push/PR-gated, needs native integration — private only.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: must stay private; too intermittent/low-cost to prioritize
self-hosting.
**12. Optimization**: the 68.2% historical failure rate deserves investigation before
this workflow is trusted, once it starts firing again — not attempted this mission
(out of `TC-05`'s sampled scope, which focused on the two highest-cost drivers).
**13. Recommendation**: `KEEP_PRIVATE_AND_OPTIMIZE` (confidence MEDIUM — the stale
historical failure rate is a real open item, not a confident HIGH).
**14. Rejected alternatives**: any migration (zero current cost to migrate).
**15. Expected savings**: none from migration.
**16. Migration complexity**: N/A.
**17. Risks**: if/when this workflow resumes firing, its real reliability is unverified.
**18. Tests**: none run.
**19. Rollback**: N/A.
**20. Evidence/confidence**: MEDIUM — current-period data is simply absent, not
reassuring.

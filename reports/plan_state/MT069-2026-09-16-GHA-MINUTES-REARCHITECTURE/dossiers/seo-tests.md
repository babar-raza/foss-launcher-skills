# Dossier: seo-tests.yml

**1. Identity/purpose**: Validates SEO pipeline scripts (`scripts/seo/tests`).
**2. Trigger**: `push(main, narrow 3-entry filter)` + `workflow_dispatch`. 1 job, ubuntu,
15min timeout.
**3. Importance**: `P2_MEDIUM`.
**4. Usage**: 83 min/5.6% (Sept), 41 runs — the largest "stay private, optimize only"
workflow by cost.
**5. Failure analysis**: 34.1% failure, Sept and full history consistently (27/41
success) — a real, moderate, unresolved failure rate, not yet root-caused this mission
(out of scope for `TC-05`'s sampled investigation, which focused on the two highest-cost
drivers).
**6. Secrets/permissions**: `contents: read`. No `secrets.*`.
**7. Data classification**: push-gated, needs native integration — private only.
**8. Runner**: ubuntu-latest, GitHub-hosted, no cache-dependency-path specified (minor
inconsistency vs. sibling workflows).
**9-11. Options**: must stay private; not a self-hosting priority (moderate, not top-3,
cost).
**12. Optimization/retirement**: the 34.1% failure rate deserves its own root-cause
investigation (not performed this mission — flagged, not resolved) since a third of
these 83 minutes are spent on failing runs.
**13. Recommendation**: `KEEP_PRIVATE_AND_OPTIMIZE` (confidence HIGH on destination,
open item on the failure-rate root cause).
**14. Rejected alternatives**: public/self-hosted migration.
**15. Expected savings**: none from migration; potentially meaningful (up to ~28 min/
month) if the 34.1% failure rate is root-caused and fixed — not attempted here.
**16. Migration complexity**: N/A (no migration recommended).
**17. Risks**: none from this dossier's own recommendation; the unresolved failure rate
is itself a risk to data quality about "true" cost once fixed.
**18. Tests**: none run.
**19. Rollback**: N/A.
**20. Evidence/confidence**: HIGH on cost; the failure-rate root cause is explicitly
flagged as unresolved, not silently assumed benign.

# Dossier: extraction-pipeline.yml

**1. Identity/purpose**: Tests the knowledge-extraction pipeline.
**2. Trigger**: `push(main)`/`pull_request`, identical 5-entry filter (HP-08, possibly
dead PR trigger). 1 job, ubuntu, 10min timeout.
**3. Importance**: `P1_HIGH`.
**4. Usage**: 8 min/0.5% (Sept), 5 runs.
**5. Failure analysis**: 0% Sept (5/5), 6.5% historical (58/62) — healthy.
**6. Secrets/permissions**: `permissions:` absent/default. No `secrets.*`.
**7. Data classification**: push/PR-gated, needs native integration — private only.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: must stay private; too low-cost to justify self-hosting or migration
engineering effort.
**12. Optimization**: none needed — smallest file (44 lines), already minimal.
**13. Recommendation**: `KEEP_PRIVATE_AND_OPTIMIZE` (confidence HIGH).
**14. Rejected alternatives**: any migration (not cost-justified at 0.5% of total).
**15. Expected savings**: none material.
**16. Migration complexity**: N/A.
**17. Risks**: none.
**18. Tests**: none run.
**19. Rollback**: N/A.
**20. Evidence/confidence**: HIGH.

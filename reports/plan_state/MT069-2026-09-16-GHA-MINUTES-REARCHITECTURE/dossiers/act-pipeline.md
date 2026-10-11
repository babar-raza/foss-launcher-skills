# Dossier: act-pipeline.yml

**1. Identity/purpose**: Tests Go/ACT-related content-pipeline pieces
(`check_go_code_blocks.py` and related).
**2. Trigger**: `push(main)`/`pull_request`, identical 26-entry filter (HP-08, possibly
dead PR trigger). 1 job, ubuntu, 20min timeout.
**3. Importance**: `P2_MEDIUM`.
**4. Usage**: 19 min/1.3% (Sept), 6 runs.
**5. Failure analysis**: 0% Sept (6/6), 20% historical (44/55) — real historical issues,
currently stable.
**6. Secrets/permissions**: `permissions:` absent/default. No `secrets.*`.
**7. Data classification**: push/PR-gated, needs native integration — private only.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: must stay private; too low-cost to prioritize.
**12. Optimization**: candidate for HP-08's possibly-dead-PR-trigger cleanup, alongside
`example-verification-tests.yml`, `extraction-pipeline.yml`, `metrics-governance.yml`,
`skill-governance.yml` — a repo-wide pattern, not unique to this file; needs per-file
human confirmation before removing any trigger, not a blind sweep.
**13. Recommendation**: `KEEP_PRIVATE_AND_OPTIMIZE` (confidence HIGH).
**14. Rejected alternatives**: any migration.
**15. Expected savings**: none material from destination change; a small amount if the
dead PR trigger is confirmed and removed repo-wide.
**16. Migration complexity**: N/A.
**17. Risks**: none.
**18. Tests**: none run.
**19. Rollback**: N/A.
**20. Evidence/confidence**: HIGH.

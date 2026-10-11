# Dossier: reference-index-structure.yml

**1. Identity/purpose**: Live backstop for reference-site index structure — exists
specifically because the same check in `content-audit.yml` (PR-triggered) never
actually ran (per its own header comment).
**2. Trigger**: `push(main, single-subtree filter)` + `workflow_dispatch`. 1 job, ubuntu,
10min timeout.
**3. Importance**: `P1_HIGH`.
**4. Usage**: 8 min/0.5% (Sept), 6 runs.
**5. Failure analysis**: 0% Sept (6/6), 0% historical (87/87) — fully healthy.
**6. Secrets/permissions**: `contents: read`. No `secrets.*`.
**7. Data classification**: push-gated, needs native integration — private only.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: must stay private; too low-cost to justify migration effort.
**12. Optimization**: HP-14 (informational only) — the same check also nominally exists
in the dead `content-audit.yml`; zero real cost impact, intentional backstop design, not
an accidental duplication worth cleaning up.
**13. Recommendation**: `KEEP_PRIVATE_AND_OPTIMIZE` (confidence HIGH).
**14. Rejected alternatives**: any migration.
**15. Expected savings**: none material.
**16. Migration complexity**: N/A.
**17. Risks**: none.
**18. Tests**: none run.
**19. Rollback**: N/A.
**20. Evidence/confidence**: HIGH.

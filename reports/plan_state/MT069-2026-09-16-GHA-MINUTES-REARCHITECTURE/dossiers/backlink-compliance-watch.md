# Dossier: backlink-compliance-watch.yml

**1. Identity/purpose**: Daily full-site backlink audit + compliance regression ratchet.
**2. Trigger**: `schedule(11:00 UTC)` + `workflow_dispatch`. 1 job, ubuntu, 15min timeout.
**3. Importance**: `P2_MEDIUM`.
**4. Usage**: 24 min/1.6% (Sept), 13 runs.
**5. Failure analysis**: 0% Sept and full history (22/22) — healthy. Static-review found
one fragility (HP-06: the regression-check step consumes the audit step's output without
checking its outcome first) — low-cost, deferred, not yet triggered in practice.
**6. Secrets/permissions**: `contents: read, issues: write`. No explicit secrets.
**7. Data classification**: audits public content; writes only an issue on regression.
Safe for public execution.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: same reasoning as `aspose-com-targets-watch.yml` — public clean, self-
host rejected (uptime), private-hosted works but wastes free public capacity.
**12. Optimization**: HP-06's unguarded consumption pattern is worth fixing eventually
(low priority, not blocking migration).
**13. Recommendation**: `MOVE_EXECUTION_TO_PUBLIC_REPO` (confidence HIGH).
**14. Rejected alternatives**: self-hosting.
**15. Expected savings**: ~24 min/month.
**16. Migration complexity**: LOW — second in the migration order after the canary.
**17. Risks**: minimal, same profile as the canary.
**18. Tests**: none run (design-only).
**19. Rollback**: same as canary.
**20. Evidence/confidence**: HIGH.

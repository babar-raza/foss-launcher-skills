# Dossier: package-publish-watch.yml

**1. Identity/purpose**: Daily publish-status watcher for pypi/nuget/npm/go/cargo
packages — same shape as `maven-publish-watcher.yml` for other ecosystems.
**2. Trigger**: `schedule(10:00 UTC)` + `workflow_dispatch`. 1 job, ubuntu, 10min timeout.
**3. Importance**: `P1_HIGH`.
**4. Usage**: 26 min/1.7% (Sept), 13 runs.
**5. Failure analysis**: 0% Sept (13/13), 37.8% historical (28/45) — moderate historical
failure, not catastrophic (publish-detection false negatives are the real risk, not
data corruption). HP-13: a real, now-fixed historical incident is documented in the
file's own comment (every scheduled run since at least 2026-08-08 crashed until the
missing pip install was added) — informational, already resolved.
**6. Secrets/permissions**: `contents: write, issues: write`. No explicit `secrets.*`.
**7. Data classification**: auto-commits today — same open product decision as
`maven-publish-watcher.yml`.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: same as `maven-publish-watcher.yml`.
**12. Optimization**: consolidation candidate alongside its 3 siblings.
**13. Recommendation**: `SPLIT_BETWEEN_PRIVATE_AND_PUBLIC` (confidence MEDIUM, pending
the user's decision).
**14. Rejected alternatives**: self-hosting.
**15. Expected savings**: ~26 min/month plus consolidation savings.
**16. Migration complexity**: MEDIUM (auto-commit→PR-gated change needed).
**17. Risks**: same product-decision risk as `maven-publish-watcher.yml`; the historical
37.8% failure rate is worth monitoring post-migration, not just assumed resolved.
**18. Tests**: none run (design-only, blocked on pending decision).
**19. Rollback**: keep private original enabled until proven.
**20. Evidence/confidence**: HIGH on cost/history; MEDIUM on destination.

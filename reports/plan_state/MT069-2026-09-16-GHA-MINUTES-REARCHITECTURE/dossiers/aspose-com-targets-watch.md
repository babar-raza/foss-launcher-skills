# Dossier: aspose-com-targets-watch.yml

**1. Identity/purpose**: Daily backlink-target-map drift watcher against aspose.com.
**2. Trigger**: `schedule(10:30 UTC)` + `workflow_dispatch`. 1 job, ubuntu, 15min timeout.
**3. Importance**: `P2_MEDIUM` — useful drift monitoring with a practical manual fallback.
**4. Usage**: 40 min/2.7% (Sept), 13 runs.
**5. Failure analysis**: 0% Sept (13/13), 97.6% historical success (41/42) — healthy.
**6. Secrets/permissions**: `contents: read, issues: write`. No explicit secrets (default
token via `github-script`).
**7. Data classification**: reads `data/aspose_com_targets.json` + public aspose.com
URLs; writes only an issue. No sensitive data — confirmed safe for public execution
(`analysis/threat_assessment.md`).
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9. Option A**: works, but this repo is offline overnight/unpredictably — a schedule
bot benefits from always-on execution GitHub-hosted or public provides.
**10. Option B (public)**: **Selected** — this mission's designated canary. Clean,
low-risk, safe secrets profile, reuses the proven SEO-template pattern.
**11. Option C (self-host)**: rejected — this machine isn't reliably on at 10:30 UTC.
**12. Optimization/retirement**: none needed beyond migration.
**13. Recommendation**: `MOVE_EXECUTION_TO_PUBLIC_REPO` (confidence HIGH).
**14. Rejected alternatives**: self-hosting (unreliable uptime for a schedule bot).
**15. Expected savings**: ~40 min/month moved off the private allowance entirely (public
minutes are free/unlimited).
**16. Migration complexity**: LOW — first canary, mechanism already fully designed
(`design/public_execution_boundary.md`).
**17. Risks**: minimal — read+report only, structurally incapable of corrupting the repo.
**18. Tests**: none run (design-only this taskcard; Phase B will prove it live).
**19. Rollback**: flip the public template back to disabled/delete; private original
stays intact and re-enableable.
**20. Evidence/confidence**: HIGH — real usage and failure data plus a completed threat
assessment.

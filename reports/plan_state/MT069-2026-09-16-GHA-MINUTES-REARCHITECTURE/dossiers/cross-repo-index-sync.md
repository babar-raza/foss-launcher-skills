# Dossier: cross-repo-index-sync.yml

**1. Identity/purpose**: Syncs a single index file from `aspose.org` to `aspose.net` on
change.
**2. Trigger**: `push(main, single-file path filter)` + `workflow_dispatch(reason
input)`. 1 job, ubuntu, 10min timeout. **This repo's one exemplary `concurrency:` block**
(`cancel-in-progress: false`, i.e. serializes rather than cancels — appropriate for a
cross-repo write).
**3. Importance**: `P1_HIGH` — silent breakage accumulates cross-repo drift unnoticed.
**4. Usage**: 0 minutes in the Sept export (consistent with its single-file filter being
rarely hit).
**5. Failure analysis**: 0% historical (11/11) — fully healthy.
**6. Secrets/permissions**: `contents: read`. `secrets.GH_TOKEN` explicitly referenced —
needed to push to the second private repo `Aspose/aspose.net`.
**7. Data classification**: must push to a second private repo with its own token —
structurally private, not a migration candidate under any option.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: Option A/optimize only — already exemplary; no lever to pull.
**12. Optimization**: none needed — this file is the model other workflows should
follow for concurrency discipline, not a target for change.
**13. Recommendation**: `KEEP_PRIVATE_AND_OPTIMIZE` (confidence HIGH).
**14. Rejected alternatives**: any migration (structurally impossible — cross-repo write
with its own credential).
**15. Expected savings**: none — already near-zero cost.
**16. Migration complexity**: N/A.
**17. Risks**: none identified.
**18. Tests**: none run.
**19. Rollback**: N/A.
**20. Evidence/confidence**: HIGH.

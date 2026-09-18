# Dossier: seo-analysis.yml

**1. Identity/purpose**: "SEO Weekly Analysis" — a distinct, lighter weekly SEO report
(NOT the same as the already-public `scripts/seo/workflows/seo-analysis.yml` template
deployed as "SEO Analysis Pipeline" — a real name collision, not a duplicate).
**2. Trigger**: `schedule(Monday 09:00 UTC)` + `workflow_dispatch`. 1 job, ubuntu, 15min.
**Undocumented schedule collision** with `launch-dashboard.yml` (both exactly 09:00
Monday, no offset comment unlike every other schedule pair in this repo — HP-09, low
priority).
**3. Importance**: `P2_MEDIUM`.
**4. Usage**: 3 min/0.2% (Sept), 1 run.
**5. Failure analysis**: 1/1 success in Sept; 85.7% historical failure (6/7) — small
sample, genuinely uncertain, not confidently rated either way.
**6. Secrets/permissions**: `contents: read, issues: write`. Uploads a workflow artifact
(`reports/seo/weekly_analysis_summary.{json,md}`).
**7. Data classification**: **one open item** — artifacts on a public-repo workflow are
publicly downloadable; content of the summary not yet verified for public-safety
(`analysis/threat_assessment.md`). Must be checked before migrating this specific one.
**8. Runner**: ubuntu-latest, GitHub-hosted.
**9-11. Options**: public migration otherwise clean-shaped, pending the rename (name
collision) and the artifact-content check above.
**12. Optimization**: rename before migrating; resolve the schedule collision with
`launch-dashboard.yml` (cosmetic).
**13. Recommendation**: `MOVE_EXECUTION_TO_PUBLIC_REPO` (confidence MEDIUM — two open
items, not HIGH).
**14. Rejected alternatives**: self-hosting.
**15. Expected savings**: ~3 min/month — small in isolation.
**16. Migration complexity**: MEDIUM (rename + artifact-content verification needed
first, unlike the two clean canaries).
**17. Risks**: public artifact exposure if the summary contains anything not meant for
public consumption — unverified, flagged for whoever executes this migration.
**18. Tests**: none run (design-only).
**19. Rollback**: same pattern as other public migrations.
**20. Evidence/confidence**: MEDIUM — real usage number is solid; the failure-rate
history and artifact-safety question are both small-sample/unverified.

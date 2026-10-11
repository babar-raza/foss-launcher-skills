# Dossier: ci-eval-consistency.yml

**1. Identity/purpose**: Evaluator-rerun-consistency check + onboarding-integrity check
(2 independent jobs).
**2. Trigger**: `push(main)`/`pull_request` (6/14-entry filters) + `schedule(Monday
06:00 UTC)`. **Finding**: the `consistency` job explicitly skips itself on the schedule
trigger (`if: github.event_name != 'schedule'`) — the scheduled run of that job is a
structural no-op today, only `onboarding-integrity` does real work on schedule.
**3. Importance**: `P2_MEDIUM`.
**4. Usage**: 26 min/1.7% (Sept), 11 runs, 2 jobs/run.
**5. Failure analysis**: 0% Sept (11/11), 18.3% historical (76/93) — real historical
issues, now stable/resolved recently.
**6. Secrets/permissions**: `permissions:` absent/default. No `secrets.*`.
**7. Data classification**: push/PR legs need native integration; the schedule leg
(effectively just `onboarding-integrity`, given the no-op above) is low-value to
migrate on its own.
**8. Runner**: ubuntu-latest, GitHub-hosted, both jobs.
**9-11. Options**: push/PR legs stay private (native integration); the schedule leg is
a genuine but low-value split candidate given the no-op finding — may not be worth the
file-split engineering effort for what it actually contributes.
**12. Optimization**: consider simply removing the schedule trigger's now-pointless
invocation of `consistency`, or restructuring so only `onboarding-integrity` runs on
schedule — cheaper than a full file split.
**13. Recommendation**: `SPLIT_BETWEEN_PRIVATE_AND_PUBLIC` (confidence MEDIUM — the
schedule leg's low real value makes this a marginal call, not a clear win).
**14. Rejected alternatives**: full migration (push/PR legs must stay private).
**15. Expected savings**: small — the schedule leg is a minor share of this workflow's
already-modest 1.7% total.
**16. Migration complexity**: MEDIUM (file split) or LOW (just fixing the no-op
scheduling instead) — the cheaper option deserves consideration before committing to
the split.
**17. Risks**: low.
**18. Tests**: none run (design-only).
**19. Rollback**: straightforward — no auto-commit behavior involved.
**20. Evidence/confidence**: HIGH on the numbers; MEDIUM on whether a split is even the
right lever here versus the cheaper no-op fix.

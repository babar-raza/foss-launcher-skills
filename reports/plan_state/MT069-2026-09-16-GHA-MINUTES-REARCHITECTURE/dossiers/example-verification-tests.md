# Dossier: example-verification-tests.yml

**1. Identity/purpose**: Verifies published code examples compile/run correctly across
languages — protects content quality directly.
**2. Trigger**: `push(main)`/`pull_request`, identical 6-entry path filter (HP-08,
possibly dead PR trigger, unconfirmed). 2 independent jobs, ubuntu + windows, same test
target on both (deliberate cross-platform duplication per the file's own comments).
**3. Importance**: `P1_HIGH`.
**4. Usage**: windows 61 min/4.1% + linux 30 min/2.0% = 91 min/6.1% (Sept). Windows costs
more than Linux here too, consistent with `skill-governance.yml`'s pattern.
**5. Failure analysis**: 0% failure, both jobs, Sept and full history — fully healthy.
**6. Secrets/permissions**: `permissions:` absent/default. No `secrets.*`.
**7. Data classification**: push/PR-gated, needs native integration — private only.
**8. Runner**: ubuntu-latest + windows-latest, GitHub-hosted, no matrix (2 explicit
jobs).
**9-11. Options**: must stay private (native integration); self-hosting not warranted
(healthy, moderate cost, no reliability driver).
**12. Optimization/retirement — real lever here**: the dual-OS duplication (91 min
combined) is a genuine, unresolved consolidation target. Not yet confirmed whether the
Windows leg tests anything genuinely OS-sensitive (e.g., CRLF/path handling) — if not,
demote it to schedule/dispatch like `skill-governance.yml`'s own soft-launch pattern.
**13. Recommendation**: `CONSOLIDATE_WITH_ANOTHER_WORKFLOW` (confidence MEDIUM — the
OS-sensitivity question is unverified, not the destination).
**14. Rejected alternatives**: public/self-hosted migration (both structurally
unavailable/unwarranted).
**15. Expected savings**: up to ~61 min/month if the Windows leg is demoted and proven
unnecessary on every push — not yet confirmed.
**16. Migration complexity**: LOW (a trigger change), contingent on the OS-sensitivity
verification.
**17. Risks**: demoting the Windows leg without confirming it's safe could silently drop
real OS-specific test coverage.
**18. Tests**: none run (design-only; the OS-sensitivity check itself wasn't performed
this taskcard).
**19. Rollback**: trivial — restore the original trigger if a regression is found.
**20. Evidence/confidence**: HIGH on cost; MEDIUM on the consolidation recommendation
pending the OS-sensitivity verification.

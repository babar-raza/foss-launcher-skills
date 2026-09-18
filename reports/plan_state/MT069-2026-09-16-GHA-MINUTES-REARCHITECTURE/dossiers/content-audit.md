# Dossier: content-audit.yml

**1. Identity/purpose**: Original API-accuracy audit gate, superseded by
`content-governance-checks.yml`. Its own header comment explicitly states it is
"SUPERSEDED" and instructs "do not weaken or repurpose it."
**2. Trigger**: `pull_request(content/**/*.md)` only — confirmed structurally dead
under this repo's real push-only production flow (no push, no schedule, no
`workflow_dispatch`).
**3. Importance**: `RETIREMENT_CANDIDATE` (`analysis/importance_matrix.json`) —
practical retirement already achieved; literal deletion blocked by T-00 governance.
**4. Usage**: **0 minutes in the Sept export** — confirmed dead, not just theoretically
so.
**5. Failure analysis**: 76.9% historical failure (3/13) from before the push-only
convention solidified — an artifact of an earlier era, not current risk.
**6. Secrets/permissions**: `permissions:` absent/default. No `secrets.*`. ~45 steps,
30min timeout — the file that content-governance-checks.yml's own header explains it
had to be split off from.
**7. Data classification**: N/A — never actually runs.
**8. Runner**: ubuntu-latest, GitHub-hosted (irrelevant given zero real execution).
**9-11. Options**: N/A — no destination decision is meaningful for a workflow that
never fires.
**12. Optimization/retirement**: **leave exactly as-is.** T-00 undeletable governance
path; the file's own header explicitly forbids modification. Deletion via DGR is a
human/operator action outside this mission's scope, not attempted here.
**13. Recommendation**: `RETIRE` — meaning "confirmed permanently dead by design," not
an action this mission takes.
**14. Rejected alternatives**: any active migration or fix — moot for a workflow that
never executes.
**15. Expected savings**: none — already zero cost.
**16. Migration complexity**: N/A.
**17. Risks**: none — the only risk would be someone mistakenly re-wiring its trigger,
which its own header explicitly warns against.
**18. Tests**: none run — no change made.
**19. Rollback**: N/A.
**20. Evidence/confidence**: HIGH — confirmed dead by both the real usage export and
this repo's own documentation.

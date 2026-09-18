# Dossier: llms-generation.yml

## 1. Identity and purpose
Regenerates `llms-output/` files on content or generator-script change; verifies
staleness; updates the txt inventory. Does not deploy (per its own header comment,
`aspose.org-workflows`'s per-site workflows regenerate again at deploy time).

## 2. Trigger and execution path
`push(main, content/**/*.md + scripts/generator/**)` only — no PR, no schedule, no
`workflow_dispatch` (the only file among the 20 with no manual-trigger option). 1 job,
`ubuntu-latest`, `timeout-minutes: 20`, no dependency cache (narrower footprint than
most workflows — installs only `pyyaml`).

## 3. Consumers and business importance
`P1_HIGH` (`analysis/importance_matrix.json`) — provides fast feedback before the more
expensive full regeneration in the deploy repo.

## 4. Historical usage
**#2 real cost driver, newly surfaced**: 259 of 1,494 minutes (17.3%), 89 runs, Sept
2026. Not previously identified by the pre-data proxy analysis.

## 5. Outcome and failure analysis
0% failure, both Sept (0/89) and full 172-day history (0/362) — fully healthy. The cost
concern here is pure volume/necessity, not reliability.

## 6. Secrets and permissions
`permissions:` absent/default. No `secrets.*` referenced.

## 7. Private/public data classification
Reads content/**/*.md and scripts/generator/** — private content, but the *output*
(llms-output files) is itself intended to be public-facing.

## 8. Current runner dependencies
`ubuntu-latest`, GitHub-hosted, no matrix.

## 9. Option A (remain private, GitHub-hosted) — pros/cons
Con: 17.3% of total cost. **Correction (TC-11 independent review, 2026-09-17,
re-verified independently a second time)**: the duplication question below is now
resolved, not open — leaving this workflow entirely as-is means continuing to pay for a
full regeneration that partly duplicates the deploy-time run.

## 10. Option B (public repo) — pros/cons
Not a fit even after resolving §12: this workflow gates every `push(main)` as a
fast-feedback check on the content/generator change itself, which requires running in
this repo, not a sibling one — the same structural reason `content-governance-checks.yml`
and `skill-governance.yml` can't move either.

## 11. Option C (self-hosted) — pros/cons
Possible once redesigned (see §12), but self-hosting the *current*, unredesigned full
regeneration would just move the duplicate cost rather than remove it — redesign first,
then decide hosting.

## 12. Optimization or retirement opportunity
**Correction (TC-11 independent review, 2026-09-17)**: this section previously called
the duplication question "the single highest-leverage open question ... not yet
resolved," and separately, wrongly, attributed this workflow's concurrency guard to
"`TC-14`/`TC-15` work." Both are corrected here, independently re-verified a second time
(not just accepted from the review's own say-so) before writing this:

- **Duplication — now resolved, with a caveat.** This workflow's own header/Summary text
  states the deploy repo re-runs the generator; live-checked directly via `gh api
  repos/Aspose/aspose.org-workflows/contents/.github/workflows/docs.aspose.org.yml` and
  confirmed it does invoke `llms-generator.py` at deploy time. **But** that deploy
  workflow is `workflow_dispatch`-only (manual staging/production trigger, not automatic
  per push) and does **not** run `detect_stale_llms.py --check-only` (confirmed absent by
  grep) — so this private workflow's actual distinct value, a fail-fast gate catching a
  broken generator or malformed content *before* a human manually triggers a deploy, is
  real and is **not** duplicated publicly. The regeneration computation duplicates; the
  gate does not. "Eliminate outright" would remove real value, not just redundant cost —
  the original framing's binary ("necessary gate, or fully duplicated work — pick one")
  was itself the flaw; both are simultaneously true of different parts of the same job.
- **Concurrency guard — misattributed and overstated as done.** This workflow's
  `concurrency:` block was added via `/workflow-harden` (S-115) under `TC-03`, not
  `TC-14`/`TC-15` (which fixed the platform-capabilities checker and the
  evaluator-version-bump shift-left, respectively — unrelated). `git status --porcelain`
  confirms it is still an **uncommitted** working-tree edit, not "landed."

## 13. Recommendation — UPDATED 2026-09-18, real fix implemented

**Second, deeper investigation (2026-09-18) found something more fundamental than the
2026-09-17 duplication finding**: the "Stale check gate" step is structurally close to
vacuous in ANY CI context, public or private, independent of the deploy-repo
duplication question. Traced `detect_stale_llms.py` in full: `detect_issues()` compares
the manifest's recorded source hash against the CURRENT source file's hash — but
`reports/agent-consumption/provenance-manifest.json` is gitignored and never persisted
across runs, and the workflow's own "Update provenance manifest" step rebuilds it from
scratch immediately before "Stale check gate" runs. Every run therefore checks a
manifest against the exact state it was just built from, seconds earlier — this cannot
ever detect real drift, with or without a preceding full regeneration. Left in place
(no false failures, and it does prove `llms-generator.py` didn't crash) but should not
be trusted as genuine staleness detection. Real fix (persist the manifest across runs,
e.g. via `actions/cache`, checked BEFORE regeneration overwrites it) is real
`scripts/generator/**` engineering, outside this mission's `.github/workflows/**` +
`scripts/ci/**` scope — flagged, not attempted.

**What WAS implemented and tested**: the actual, well-scoped cost fix. Confirmed live
(`llms-generator.py` line ~900) that `--clean-output` only wipes its OWN subdomain's
output directory, not the whole tree — so regeneration can safely scope to just the
subdomain(s) a push actually touched, instead of unconditionally running
`--all-subdomains` every time. Implemented a "Determine regeneration scope" step (git
diff against the pre-push SHA, with a safe on-demand fetch + full-regen fallback for an
unreachable/force-pushed SHA) and two conditional regeneration steps (scoped vs. full,
falling back to full whenever `scripts/generator/**` itself changed). Verified live in 3
scratch-repo scenarios before trusting it: single-domain change → scoped correctly;
`scripts/generator/**` change alongside content → correctly fell back to full; two
domains changed in one push → both correctly scoped. This directly cuts the real
duplicate-cost problem (most pushes touch one subdomain, not all five) without touching
the deploy-repo-duplication question at all — a fix that helps regardless of how that
question is eventually resolved.

Recommendation stays `REQUIRES_REDESIGN` (the manifest-persistence fix is real,
unimplemented, script-level work) but the highest-leverage, lowest-risk part of the
redesign — cutting the actual duplicate cost — is done, live, and tested.

## 14. Rejected alternatives
Full elimination — rejected, would remove the confirmed-real fail-fast gate value (see
§12). Leaving entirely as-is — rejected, would keep paying for confirmed-real duplicate
computation. Public migration / self-hosting the current unredesigned job — rejected,
treats a design problem as a hosting problem.

## 15. Expected savings
Not the full 259 min/month — that figure assumed pure duplication, now known to overstate
it (the gate itself has real, non-duplicated value and should be kept in some form). The
actual achievable saving is the delta between "full regeneration + gate" and "gate alone,"
which requires the redesign work in §13 to quantify — not asserted here without that work.

## 16. Migration complexity
Not a migration — a redesign of what runs push-time vs. deploy-time. Complexity depends
on whether `detect_stale_llms.py` can validate without a full prior regenerate (open
engineering question, not yet answered).

## 17. Risks
The risk this dossier originally flagged (eliminating this without confirming it serves
no independent purpose) is confirmed real, not hypothetical — the gate does serve a
purpose the deploy-time run doesn't cover. The opposite risk — leaving the full
regeneration in place indefinitely because the question got resolved partially — is now
the more likely failure mode if this redesign item isn't tracked forward.

## 18. Tests
None run for this workflow specifically — no code change was made to this workflow in
this pass (only the destination/analysis documents were corrected).

## 19. Rollback
N/A — no destination change made.

## 20. Evidence and confidence
HIGH confidence on the real usage number (17.3%, directly from the export) and on the
duplication/gate-independence finding (directly verified twice, live, against both
repos' actual workflow files — not inferred). MEDIUM (not HIGH) confidence on the
specific redesign direction — the diagnosis is solid, the exact fix is not yet built or
proven.

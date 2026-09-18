# Forensic Audit of `readme-refresh` (S-120) — Final Report

Mission: `readme-refresh-forensic-trust-audit-2026-08-25`. Audit-and-planning only; no
remediation performed. All 7 required deliverable categories are indexed below with exact
evidence paths, per the mission's own definition of done.

## 1. Executive verdict

**`readme-refresh` is not currently trustworthy for autonomous or low-oversight use, despite
being one of the most heavily-built-out skills in this repository (4,083 + 9,180 lines,
103 deterministic checks, 845+ scoped tests).** The gap is not in engineering effort — it
is that the deterministic check layer verifies *internal self-consistency* (does a citation
exist, does a disposition record have the right shape, does a JSON field validate) far more
reliably than it verifies *truth against source*. Manually re-reviewing all 31 registered
products against their real upstream repositories found **172 confirmed defects**, including
**12 BLOCKER-severity findings on 10 distinct products**, several already live in
publicly-published READMEs today — not merely candidate risk. The system's own closure
claim from five days prior ("30/30 clean," 2026-08-20) was independently re-verified and
found false at the moment this audit began. This is a system that produces genuinely
useful first-draft output and a genuinely useful deterministic safety net, neither of which
is sufficient on its own yet.

## 2. Implementation and dependency-closure map

`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/phase2-contract-matrix.md`
— full stage-by-stage table (skill surface, state machine verified live, all CLI verbs,
dependency extraction, sibling upstream-issue workflow, registries, output directories,
locking/resume), plus 11 confirmed drift/dead-code findings.

## 3. Intended-versus-implemented contract matrix

Section 9 of `phase2-contract-matrix.md` — 10-row table covering deterministic-fact-first
generation (fully implemented), the 103-check gate (implemented, doc-count-drifted),
example verification (real only for Python, opt-in), the dependency-verification-matrix
(implemented but dead), the surgical-scope convergence lock (implemented, never exercised),
push-live proof (real, but the code's own docstring says otherwise), portfolio health
checks (works scoped, not unscoped), human-in-the-loop approval (convention, not
code-enforced), and the republication-debt tripwire (advisory, not hard-gated).

## 4. Complete output inventory

`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/phase3-output-inventory.md`
— all 31 registered products (`data/products.json`), including the one registry-excluded
product refreshed under prior explicit authorization (`cells/typescript`). Every product
has a candidate; publication history cross-referenced against `data/readme_published_state.json`
and the corrected live `audit-portfolio` sweep. No product was dropped from the inventory
for any reason.

## 5. Product-by-product manual review matrix

`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/phase3-reviews/*.md` —
one complete four-way review (original / current-upstream / candidate / published, each
independently source-cross-checked and adversarially verified by a fresh reviewer) per
product, 31 files. Each carries a matching `AUD-P3-{family}-{platform}-4WAY` taskcard in
`taskcards.jsonl` summarizing its confirmed findings.

## 6. Original-content omissions ledger

Embedded per-product in each phase3-reviews file's "Content-Preservation Ledger" section.
Portfolio-wide pattern (Phase 5 Cluster A): disposition machinery tracks old-README units
it already recognized, but is structurally blind to (a) new candidate content with no
disposition trace at all (13/31 products, most commonly a "## Dependencies"/"### Native
and System Requirements" section present as template boilerplate in 29/30 products but
tracked in almost none), and (b) `merged_verbatim`/`preserved` labels applied without a
literal text-identity check, confirmed false on at least 7 products.

## 7. False or unsupported claims ledger

Embedded per-product in each phase3-reviews file's "Factual Accuracy" and "Verdict"
sections; consolidated by defect class in `phase4-validator-matrix.md`. Headline cluster
(Phase 5 Cluster C): `check_content_unit_evidence_resolves` proves a citation *exists*,
never that it *supports* the claim — the single largest defect class in the audit (10+
findings, 9+ products), including two of the ten most severe findings overall (`cells/java`'s
44.3%-wrong module-attribution claim, live; `words/net`'s non-compiling flagship code
example, live).

## 8. Presentation, SEO, dependency, example, API, link, and rendering findings

Distributed across each phase3-reviews file's dedicated sections (Presentation/SEO,
Dependency Accuracy, Example Verification, API Accuracy, Link/Rendering) and consolidated
by defect class in `phase4-validator-matrix.md` rows 11-22, 30-36. Notable: Navigation TOC
omits a real heading on 9/31 products (cheapest fix-to-impact ratio found in the audit);
`verified_by_run_id` is null on 31/31 products (100%, root-caused in Phase 5 Cluster H to a
dominant write path unconditionally clobbering two correctly-threaded call sites, not "never
threaded" as first appeared).

## 9. Validator-effectiveness matrix

`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/phase4-validator-matrix.md`
— ~40 defect-class rows covering all 172 confirmed findings. **Coverage result: ~53% of
confirmed real-world defects had zero targeting check of any kind; ~43% hit an existing,
wired check whose scope or logic did not reach the specific manifestation; ~4% are proof
the check battery works correctly when fed trustworthy input.** Raw counts of "103 checks,
101 wired in production" substantially overstate actual protection.

## 10. Tests and oracle coverage assessment

Covered in `phase2-contract-matrix.md` §§3-4 and referenced throughout `phase4-validator-matrix.md`'s
escape-cause column. 845+ scoped unit/integration tests exist (`test_readme_refresh_run.py`,
`test_readme_refresh_checks.py`, `test_readme_refresh_scope.py`) but example verification
(`verify-examples`) is a stub for every language except an opt-in Python-only path that only
checks `ast.parse` syntax — no test anywhere compiles or executes a non-Python example, which
directly let `words/net`'s live-broken C# example escape to production undetected by any
automated gate.

## 11. State, cache, recovery, idempotency, and evidence assessment

Covered in `phase2-contract-matrix.md` §8 (locks/leases/resume) and Phase 1 baseline
findings. Two genuine, independent performance defects confirmed live: an unscoped
`audit-portfolio` hang (>15 min, killed) and a severe, content-correlated per-product
runtime variance (0.3s–382.2s across the 31 products). The `readme_sha256`/`verified_by_run_id`
evidence-marker mechanism has two 100%-reproducible defects traced to one shared function
(Phase 5 Cluster H).

## 12. Systemic failure clusters

`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/phase5-root-cause-clusters.md`
— 8 clusters (A–H). Cluster A (disposition-ledger machinery validates shape not ground
truth) is the largest at 11 of 36 defect-class rows; Cluster E (no reconciliation loop
between a detected drift and a corrective action) contains the single most severe finding
in the audit — `font/python`'s entire prior publication silently erased by a GitLab-canonical/
GitHub-mirror architecture the pipeline does not control, invisible for 5+ days because the
publication ledger that might have flagged it (Cluster E1, 55% of the portfolio) has no
record of the merge either.

## 13. Root-cause analysis for every material occurrence

Embedded in each cluster's write-up in `phase5-root-cause-clusters.md`, citing exact
files/functions/line numbers, with the earliest causal stage named per the mission's own
taxonomy (stale clone, incorrect fact extraction, validator not registered, publication
mismatch, etc.). Where this audit found a sharper root cause than its own earlier analysis
(Cluster H's `verified_by_run_id` finding), the correction and its evidence are documented
explicitly rather than silently updated.

## 14. Prioritized remediation plan

`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/phase6-remediation-plan.md`
— 5 tiers: Immediate publication corrections (6 items, 3 already live-misleading), Shared
machinery blockers (17 items, one per Phase 5 cluster/sub-cluster), Required hardening
(8 items), Product-specific corrections (5 items), Deferred improvements (5 items). 31
`RC-*` remediation-candidate taskcards filed, all `status: TODO` — this mission fixes
nothing; every item is a candidate for a separate, future remediation mission.

## 15. Canary and rollout plan

Embedded in `phase6-remediation-plan.md` — a 10-step template (reproduce → failing
regression test → fix → one canary regenerated in scratch → full manual compare →
validators + executable examples → second unchanged generation → byte-identical
requirement → confirm unrelated sections unchanged → expand only to affected products)
applied to each of the 14 systemic fixes with a specifically-named canary product drawn
from this audit's own reviewed set (e.g. `pdf/net` for the version-currency hard gate,
`font/python` for the publication-target-authority check, `slides/java` for
bidirectional disposition coverage). Explicitly rejects any blind portfolio-wide
regeneration.

## 16. Exact paths to all audit reports and evidence

```
reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/
  mission_authority.yaml          — hand-authored mission contract (archive-shaped, root slot untouched)
  taskcards.jsonl                 — 83 records: 52 AUD-* (all CLOSED), 31 RC-* (all TODO)
  phase1-baseline.md              — corrected 31-product baseline, supersedes the stale "30/30" claim
  phase2-contract-matrix.md       — implementation map + contract matrix
  phase3-output-inventory.md      — full 31-product output inventory
  phase3-reviews/*.md             — 31 complete four-way manual reviews
  phase4-validator-matrix.md      — validator-effectiveness matrix, ~172 findings
  phase5-root-cause-clusters.md   — 8 systemic failure clusters + root-cause analysis
  phase6-remediation-plan.md      — 5-tier remediation plan, canary/rollout plan, go/no-go verdicts
  phase7-final-report.md          — this document
  baseline_audit_results.json     — raw per-product audit-portfolio output (31/31)
  slow_products_results.json      — bounded-timeout diagnostic re-runs (3d/python, html/python, slides/python)
  _file_taskcard.py               — reusable taskcard-filing helper (kept for any follow-on mission)
```

## 17. Go/no-go verdicts

From `phase6-remediation-plan.md`'s closing section, stated plainly:

1. **Continued local candidate generation** — **Conditional yes.** Deterministic-fact-first
   generation holds up structurally; treat every candidate as unverified until Tier-2
   hardening items 4-9 exist, and do not treat a clean `audit-portfolio` result as
   sufficient given Cluster A's proven false-pass instances.
2. **Human review of existing candidates** — **No, not as currently structured.**
   Reviewers are handed disposition-ledger self-reports shown, by direct mechanical
   re-execution, to be false on 20+/31 products. Reviewers must independently re-derive
   the true original and diff against it directly, as this audit's own methodology did.
3. **Republishing existing candidates** — **No.** Would compound already-live confirmed
   defects (words/net, cells/java) and a publication ledger blind on 55% of the portfolio.
   The narrow exception is Tier 1's own itemized single-file corrections, each gated on
   its own listed verification steps, not a blanket "republish is fine now."
4. **Autonomous scheduled execution** — **No.** The `approve` gate is human-gated by
   convention only, not code-enforced; every proven blind-spot cluster (A-E) would run
   unchecked, and a genuinely correct push can still be silently erased by an external
   mirror-sync with zero alerting (font/python, live evidence). Requires Tier-2 items
   1-3, 6-9, and 12-13 at minimum, plus code-level enforcement of the approval gate,
   before autonomous scheduling is revisited.

## 18. Confirmation: no target repository was modified

Verified directly (2026-08-26): `reports/repo_presenter_actions.jsonl` (the real push
ledger) still has exactly 2 rows, both pre-dating this mission; `reports/readme_refresh_runs/_scratch/`
contains only the 2 pre-existing scratch push-clones from prior missions (2026-08-15,
2026-08-18); no new `ACTIVE.json` run-state file was created during this mission; `git
status` inside sampled clone caches (`pdf/net`, `font/python`, `words/net`) shows zero
modifications; this repo's own `git status` shows zero changes under `content/`, `.agents/`,
`.kilocode/`, `.claude/`, or `data/` attributable to this mission (all pre-existing
modifications visible in git status belong to the concurrent, unrelated `MT037` mission,
confirmed present in the session's initial git status before this mission began). This
mission's only writes are the gitignored `reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/`
evidence tree documented above.

---

## Definition-of-done checklist

- [x] Every registered product (31/31) and every produced candidate accounted for.
- [x] Every applicable README manually reviewed (four-way, source-cross-checked, adversarially verified).
- [x] Material claims checked against current repository/source evidence.
- [x] Original-content preservation audited (Cluster A, per-product ledgers).
- [x] Published output compared with candidates where a real publication exists.
- [x] Recurring defects traced to causal machinery (Phase 5, 8 clusters).
- [x] Validator escapes explained (Phase 4 matrix, ~40 rows).
- [x] Tests and oracles assessed against real behavior (§10 above).
- [x] Systemic and product-specific gaps separated (every Phase 4/5/6 item tagged by scope).
- [x] Concrete, testable remediation plan exists (31 RC-* cards, all TODO).
- [x] System's readiness stated honestly (§1, §17 — three of four verdicts are "no"/conditional).
- [x] No target repository modified (§18).

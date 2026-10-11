# readme-refresh Remediation — Execution Roadmap

**Purpose**: one authoritative, dependency-ordered, executable sequence covering every
open item across `phase6-remediation-plan.md`, `phase6b-production-hardening-design.md`,
`phase6c-upstream-drift-hardening-assessment.md`, and `phase6d-freshness-reuse-deep-assessment.md`
— so execution doesn't require cross-referencing four documents to know what's next. This
document does not replace those analyses (their reasoning, evidence, and tradeoffs stay
there); it is the operational index over the current, reconciled taskcard ledger at
`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/taskcards.jsonl`.

**Governing sequencing principle (explicit user priority, stated multiple times)**: fix the
system/skill first; only then reuse the healed system to fix outcomes. Tier-1 content
corrections (Wave 7) are therefore sequenced *after* the system-hardening waves below, not
before — this is a deliberate reordering from `phase6-remediation-plan.md`'s original
Tier-1-first framing, per the user's explicit, repeated instruction in this mission's
follow-on conversation.

**Execution mission**: real code changes bind to `readme-refresh-production-hardening-remediation-2026-08-26`
(taskcards there track actual implementation progress). The `RC-*` candidates below live in
the CLOSED audit mission's ledger (`readme-refresh-forensic-trust-audit-2026-08-25`) as
planning records only — per that mission's own closeout proof, they must never advance past
`TODO`/`BLOCKED_*`/`OUT_OF_SCOPE` there. When an `RC-*` item is implemented, do what Stage 1a
did: file the real implementation taskcard under the execution mission, then mark the
originating `RC-*` card `OUT_OF_SCOPE` in the audit mission with a pointer to it (never
`IMPLEMENTED` in the audit mission's own ledger).

## Status snapshot (reconciled 2026-08-26)

- **1 done**: `TC-STAGE1A-CHEAP-WINS` (execution mission, `END_TO_END_VERIFIED`) — Navigation
  TOC parity check + Cluster H write-path marker fix. Commit `e27719470b`, pushed, verified.
- **1 superseded**: `RC-upstream-divergence-classifier` — would have duplicated
  `baseline_resolver.py`'s existing ancestry logic; replaced by items 17/18 below.
- **1 moved out of scope** (fully done, tracked under execution mission instead):
  `RC-verification-marker-write-path-fix`.
- **1 corrected in place** (partial completion noted, real work remains):
  `RC-candidate-self-consistency-checks` (Nav TOC sub-item done; numeric self-report +
  heading-word-split sub-items open — tracked as item 14 below).
- **1 corrected in place** (mechanism revised per phase6b's own critique):
  `RC-approve-gate-code-enforcement` (item 29 below).
- **1 newly filed** to close a real gap (phase6b §3.I had no executable card):
  `RC-disposition-content-addressed-identity` (item 10 below).
- **38 open TODO items**, organized into 8 waves below.

## Wave 1 — Small, independent, low-risk (no shared-infra blast radius)

No cross-dependencies within this wave or on anything below it. Safe to execute in any
order, in parallel, or interleaved with Wave 2/3. Start here.

| # | Task ID | One-line | Effort |
|---|---|---|---|
| 1 | `RC-readme-refresh-freshness-guard-compliance` | Call the existing `freshness_guard.is_generation_allowed()` gate in `plan_run()` | Small |
| 2 | `RC-clone-cache-directory-lock` | Lock the clone directory before `update_clone()`'s `git reset --hard` | Small |
| 3 | `RC-check-count-doc-drift-fix` | Fix "21"/"91" vs. real 103 check-count drift in 3 docs | Trivial |
| 4 | `RC-skill-description-placeholder-fix` | Replace S-120's "Skill description pending" placeholder | Trivial |
| 5 | `RC-registry-excluded-empty-result-messaging` | Explicit exclusion reason instead of silent empty result | Small |
| 6 | `RC-dead-code-depmatrix-resolution` | Wire in or remove `build_dependency_verification_matrix` | Small |
| 7 | `RC-unscoped-audit-portfolio-hang-fix` | Root-cause the indefinite unscoped-hang | Medium |
| 8 | `RC-audit-portfolio-runtime-variance-fix` | Root-cause the >1000x scoped-runtime spread | Medium |
| 9 | `RC-acceptance-registry-exercise-or-retire` | Prove the surgical-scope registry on one real product, or stop documenting it as live | Small |

**Recommended immediate next action**: items 1 and 2 (both directly informed by phase6d,
both proven-safe pure-reuse/small-contained fixes) — pick these up first.

## Wave 2 — Disposition identity + coverage (Cluster A)

Item 10 is foundational for this wave — do it first within the wave; 11-14 build on the
same identity scheme.

| # | Task ID | One-line | Depends on |
|---|---|---|---|
| 10 | `RC-disposition-content-addressed-identity` | Additive dual-key content-hash identity across all 4 unit ledgers | none (Wave 1 optional) |
| 11 | `RC-disposition-bidirectional-coverage` | Candidate-side completeness pass, not just old-unit-driven | none |
| 12 | `RC-disposition-text-diff-verification` | Literal text diff before accepting `merged_verbatim`/`preserved` | benefits from #10 |
| 13 | `RC-disposition-baseline-integrity-assert` | Assert the disposition baseline is git-verified pre-refresh | none |
| 14 | `RC-candidate-self-consistency-checks` (remaining) | Numeric self-report checks + heading word-split | none |

Canaries per phase6b: `pdf/net`/`slides/java` (positive path), `email/cpp` (negative/
`UNRESOLVED`-path test, deliberately not a general-purpose canary).

## Wave 3 — Scout-layer fixes (different skill: S-34/knowledge-enrich)

Independent track — can run in parallel with Wave 2. Not owned by readme-refresh's own
codebase; coordinate with whichever session/skill owns S-34.

| # | Task ID | One-line |
|---|---|---|
| 15 | `RC-cpp-scout-visibility-signal` | Real public/internal visibility field in the C++ scout |
| 16 | `RC-knowledge-layer-runtime-dispatch-verification` | Verify real dispatch wiring, not shallow existence-matching |

Item 24 (Wave 4) depends on #15 for its accessibility-claim tier specifically.

## Wave 4 — Freshness, publication reconciliation, and claim verification

The most interdependent wave — read the ordering carefully. Items 17-18 are the corrected,
reuse-based replacement for the superseded classifier; do not skip straight to 19+ without
17 landing, since several later items assume `freshness_guard`'s extended reach exists.

| # | Task ID | One-line | Depends on |
|---|---|---|---|
| 17 | `RC-freshness-guard-baseline-resolver-integration` | Extend `freshness_guard` degraded mode to consult `baseline_resolver`'s local reachability check | Wave 1 #1 conceptually; must pass all 4 existing consumers' test suites unchanged |
| 18 | `RC-sweep-auto-stale-write-on-orphaned-sha` | Sweep auto-writes `stale_since`+`orphaned_sha` for the unambiguous unreachable-SHA case | #17 (reuses its reachability extraction) |
| 19 | `RC-publication-ledger-reconciliation` | Scheduled live `gh api` reconciliation job for both publication ledgers | none |
| 20 | `RC-verification-timestamp-currency-gate` | Compare `last-verified.json` against knowledge-bundle freshness | none |
| 21 | `RC-upstream-issues-freshness-reverify` | Re-diff `upstream-issues.md`'s claims/SHA against current HEAD | none |
| 22 | `RC-clone-cache-freshness-gate` | Out-of-band live-HEAD freshness gate before `ingest-candidate` | **review for overlap with #17 before implementing — may be subsumed, not duplicated; do not build both independently without checking** |
| 23 | `RC-package-version-currency-hard-gate` | Verify Installation version claims against manifest AND live registry | none |
| 24 | `RC-claim-level-semantic-evidence-verification` | Tiered claim verification (count/support/accessibility) | Wave 3 #15 for the accessibility tier |
| 25 | `RC-live-published-regression-gate` | Block a regenerated candidate from regressing already-live content | none (independent of 17-24, but conceptually the same "live-awareness" family) |
| 26 | `RC-registry-drift-requeue-trigger` | Auto-requeue regeneration when a canonical-override target changes | none |
| 27 | `RC-republication-tripwire-hard-gate` | Promote the republication-debt tripwire to a hard gate | #19 (needs the reconciliation job's data first) |
| — | `RC-publication-target-authority-verification` | Verify target-repo mirror authority before trusting a push as durable | none — required before Wave 7's font/python item |

**Explicit open question to resolve before implementing #22**: does
`RC-clone-cache-freshness-gate`'s originally-envisioned mechanism become redundant once
#17 lands, or does it cover a distinct case? Flagged rather than silently merged or
duplicated, per this mission's own "do not overwrite plan items blindly" discipline.

## Wave 5 — Generation instrumentation + gate enforcement

| # | Task ID | One-line | Depends on |
|---|---|---|---|
| 28 | `RC-example-verification-coverage-expansion` | Broaden example verification beyond Java-only/Python-fenced | none |
| 29 | `RC-approve-gate-code-enforcement` | PR-merge-based publication gate (corrected mechanism, see determination) | #19's PR/merge-history reading capability |

## Wave 6 — Portfolio-wide regeneration (Stage 4)

**Gate, not a task list**: do not start this wave until representative canaries from Waves
1-5 are proven (per this mission's own canary/rollout template — reproduce, failing test,
fix, one canary in scratch, full manual compare, validators, second unchanged run,
byte-identical-or-verification-outcome-identical, expand only to affected products). This
is a separately-scoped follow-on effort, not a single taskcard.

## Wave 7 — Tier-1 content corrections (deferred, per explicit system-first priority)

These are narrow, single-file, human-reviewed content fixes to already-published READMEs.
Four are technically unblocked today (no system dependency); two are explicitly gated on
Wave 4 landing first. **All six are deliberately parked, not started, pending explicit
go-ahead** — this respects the user's repeatedly-stated "system first" priority rather than
unilaterally proceeding on the unblocked ones.

| Task ID | Product | Blocked on |
|---|---|---|
| `RC-words-net-shapes-chart-example` | words/net | none (unblocked, parked) |
| `RC-cells-java-module-narrative-correction` | cells/java | none (unblocked, parked) |
| `RC-html-python-idselector-table-gap` | html/python | none (unblocked, parked) |
| `RC-ee-link-batch-fix` | page/python + tex/python | none (unblocked, parked) |
| `RC-font-python-republish-regression` | font/python | Wave 4's `RC-publication-target-authority-verification` |
| `RC-pdf-net-version-currency-verification-and-refresh` | pdf/net | Wave 4 items 17-18-19 |

## Wave 8 — Close the loop (Stage 5)

Once Wave 7 executes (whenever the user authorizes it), re-verify all 6 Tier-1 corrections
through the by-then-hardened pipeline rather than treating the hand-patches as permanent —
this closes the mission's own Stage 5 requirement.

## How to use this document

1. Start with Wave 1 (any order, low risk).
2. Wave 2 and Wave 3 can proceed in parallel with each other and with the tail of Wave 1.
3. Wave 4 must respect its internal dependency notes (17 before 18; 19 before 27); item 22
   needs the overlap question resolved first.
4. Wave 5 depends on Wave 4 item 19 for item 29.
5. Do not enter Wave 6 without canary proof per this mission's own established discipline.
6. Wave 7 stays parked until the user explicitly authorizes it, regardless of how much of
   Waves 1-5 is complete — this is a go/no-go decision point, not an automatic unlock.
7. When any item here is actually implemented: file the real progress under the execution
   mission (`readme-refresh-production-hardening-remediation-2026-08-26`), then mark the
   originating `RC-*` card `OUT_OF_SCOPE` in the audit mission's ledger with a pointer —
   exactly the pattern this reconciliation pass just established for Stage 1a.

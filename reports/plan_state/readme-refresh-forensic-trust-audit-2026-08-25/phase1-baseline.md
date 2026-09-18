# Phase 1 — Corrected Portfolio Baseline (supersedes the 2026-08-20 "30/30 clean" claim)

Produced 2026-08-25 by `reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/_run_baseline_audit.py`
— one scoped `audit-portfolio --family X --platform Y --json` call per product (never
unscoped, which reproducibly hangs indefinitely — `AUD-P1-UNSCOPED-AUDIT-HANG`). Raw
output: `baseline_audit_results.json` (this directory).

## Headline

`docs/readme-refresh/current-operational-reference.md`'s "30/30 clean, 0 dirty" claim
(dated snapshot 2026-08-20) is **false today**. Corrected count: **6 of 31 products are
genuinely dirty**, 1 (`cells/typescript`) is registry-excluded and returns an empty
result from the scoped call, and 4 initially timed out at a 120s script-side limit —
one of those four (`pdf/python`) was confirmed clean on retry at ~208s elapsed; the
other three were still resolving as of this writing (see "Open items" below).

## Corrected per-product table

| Product | State | Findings |
|---|---|---|
| 3d/java | clean | — |
| 3d/net | clean | — (note: separately, `TC-REPUB-01` flags this product's *published* README as stale relative to a flat-topology diagram fix — a publication-currency gap, not a candidate-cleanliness gap; the two are different questions) |
| 3d/python | clean (confirmed via 400s retry — see slow-products run) | — |
| 3d/typescript | clean | — |
| barcode/python | clean | — |
| cells/cpp | clean | — |
| cells/go | clean | — |
| cells/java | clean | — |
| cells/net | clean | — |
| cells/python | clean | — |
| cells/rust | clean (`skipped_published`) | — |
| cells/typescript | **N/A — registry-excluded** | Scoped audit-portfolio call returns `total: 0` with no error/skip message explaining why. Minor UX gap: an operator scoping to an excluded product gets silent emptiness, not an explicit "excluded" reason. |
| email/cpp | clean (`skipped_published`) | — |
| email/net | clean (`skipped_published`) | — |
| email/python | clean | — |
| font/python | clean | — |
| html/python | clean (confirmed via 400s retry, 208.6s elapsed) | — |
| note/python | clean | — |
| **page/python** | **DIRTY (newly discovered — not in any prior audit)** | `enterprise_edition_link_resolves` (1), `enterprise_edition_anchor_matches_relationship` (1), `diagram_hybrid_reverification` (1) |
| **pdf/cpp** | **DIRTY** | `diagram_hybrid_reverification` (1) |
| **pdf/go** | **DIRTY** | `diagram_hybrid_reverification` (1) |
| **pdf/java** | **DIRTY** | `dev_test_artifacts_linked` (11) |
| **pdf/net** | **DIRTY (largest break in the portfolio)** | `dev_test_artifacts_linked` (1), `content_unit_disposition_coverage` (2), `content_unit_excerpt_matches_extraction` (167), `structural_unit_disposition_coverage` (1), `code_example_disposition_coverage` (1), `badge_disposition_coverage` (1) — 173 findings total |
| pdf/python | clean (confirmed via 400s retry, 208.6s elapsed) | — |
| slides/cpp | clean | — |
| slides/java | clean | — |
| slides/net | clean | — |
| slides/python | clean (confirmed via 400s retry, **382.2s elapsed** — the slowest single-product call observed in this audit) | — |
| **tex/python** | **DIRTY (newly discovered — not in any prior audit)** | `enterprise_edition_link_resolves` (1), `enterprise_edition_anchor_matches_relationship` (1) |
| words/net | clean (`skipped_published`) | — |
| words/python | clean | — |

## New finding: a second, previously-undetected systemic defect cluster

`page/python` and `tex/python` both fail the **same pair** of checks —
`enterprise_edition_link_resolves` and `enterprise_edition_anchor_matches_relationship`
— which no prior audit (including the 2026-08-20 "30/30" claim and the Phase-1 research
pass earlier in this mission, which only re-verified the already-known `pdf` family
findings) had surfaced. `page/python` additionally shares `diagram_hybrid_reverification`
with `pdf/cpp` and `pdf/go`, meaning it sits at the intersection of both known defect
clusters. This is filed as `AUD-P1-NEW-DIRTY-PRODUCTS` and is a priority target for
Phase 3's per-product review and Phase 4's validator-cluster mapping — the shared
check-pair strongly suggests one common root cause (most likely a stale or newly-invalid
Enterprise Edition backlink target in `data/aspose_com_targets.json`, or a canonical-
override entry in `data/backlinks/platform_canonical_overrides.yaml`, rather than two
independent per-product defects).

## Confirmed: scoped single-product calls can be genuinely slow, not just genuinely hung

The already-known defect is that **unscoped** `audit-portfolio` (no `--family`/`--platform`)
hangs indefinitely (reproduced: killed after >15 min with zero output). This baseline run
additionally found that 4 of 31 **scoped** single-product calls exceeded a 120s limit.
A bounded diagnostic re-run of `pdf/python` alone with a 400s timeout completed cleanly
in ~208s — confirming this specific case is severe slowness (roughly 20-40x the typical
<10s case), not an infinite hang. The other 3 (`3d/python`, `html/python`, `slides/python`)
were re-run with the same 400s allowance; see `slow_products_results.json` for their
resolution once available. This refines (does not retract) `AUD-P1-UNSCOPED-AUDIT-HANG`:
the audit tool has two distinct performance defects — a true unscoped hang, and a
severe-but-finite per-product slowdown affecting a specific, reproducible subset of
products (same 4 flagged independently by the earlier Phase-1 research pass's manual
spot-check) — both real, neither fixed inline per this mission's audit-only scope.

## New finding: severe, content-correlated runtime variance in `audit-portfolio` (not platform-specific)

Full per-product timing data (31/31 resolved) shows a >1000x spread: 0.3s (`cells/typescript`,
empty result) to 382.2s (`slides/python`). The slow tail is concentrated in specific
products, most visibly inside multi-platform families where non-`python` platforms are
uniformly fast and the `python` sibling is dramatically slower:

| Family | Fast platforms (range) | `python` platform |
|---|---|---|
| 3d | java 1.6s, net 0.8s, typescript 0.5s | **229.9s** (~150-450x) |
| slides | cpp 2.0s, java 2.4s, net 1.8s | **382.2s** (~160-210x) |
| pdf | cpp 1.4s, go 1.2s, java 25.4s, net 6.6s | **208.6s** (8-170x) |
| cells | cpp/go/java/net/rust/typescript all ≤2.2s | 35.2s (16-117x) |
| words | net 29.9s | 61.1s (~2x — much smaller gap) |
| email | cpp 0.8s, net 0.7s | 2.1s (negligible gap) |

But this is **not** a blanket "python platform is slow" rule: `barcode/python` (4.1s),
`note/python` (4.6s), `tex/python` (4.4s), and `email/python` (2.1s) — all python-only or
python-sibling products — are fast. The single-platform-only python products that ARE
slow (`font/python` 59.4s, `html/python` 208.6s, `page/python` 105.4s) are absolutely slow
regardless of having no sibling to compare against. The most plausible explanation,
consistent with `pdf/net` alone producing 167 individual findings under
`content_unit_excerpt_matches_extraction`, is that runtime scales with the volume of
original-README content units the candidate must be cross-checked against (likely an
O(n×m) or worse matching algorithm in one or more of the 103 checks) — not with platform
identity. This is filed as `AUD-P1-RUNTIME-VARIANCE` and is a Phase 4/5 root-cause target:
if confirmed as a specific check's algorithmic complexity, it is a shared-machinery
hardening item (affects every future audit run and every future candidate regeneration
for large-content products), not a per-product issue.

## Open items

None remaining — all 31 products resolved (24 clean/skipped-published, 6 dirty, 1
registry-excluded-empty). This document is now the current, complete, reproducible
baseline for the remainder of this mission.

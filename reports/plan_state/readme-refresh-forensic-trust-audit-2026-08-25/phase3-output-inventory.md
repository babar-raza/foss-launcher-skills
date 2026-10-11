# Phase 3a — Output Inventory (31 registered products)

Denominator: `data/products.json` (31 entries, `active: true` on all). One entry
(`cells/typescript`) is registry-excluded (`data/registry_exclusions.json`:
`BLOCKED_REPO_NOT_LAUNCHABLE`, no LICENSE, GitLab-boilerplate README, non-Aspose
package name) but was refreshed anyway under explicit prior user authorization and
carries a real candidate — it stays in-scope for this audit as an explicitly-authorized
exception, not silently dropped from the denominator. No product is omitted from this
table for any reason, including generation failure, per this mission's core principle.

Candidate presence confirmed via `reports/repo-presenter-regen-full/{family}/{platform}/`
directory listing (Phase 1 research): **31/31 have a candidate directory** with
`readme.md` + 4 disposition JSON files + `upstream-issues.md`; `last-verified.json`
present per-product from prior audit runs.

Publication history from `data/readme_published_state.json` (schema_version 1 — only
products with a *confirmed* publication event are listed; absence means "no confirmed
publication record," not "definitely never published," per the file's own stated design):

| Family/Platform | Registry status | Candidate present | Last known publication | Publication evidence | `audit-portfolio` state (this mission, 2026-08-25) |
|---|---|---|---|---|---|
| 3d/java | active | yes | 2026-08-11 | PR #1 + follow-up PR #2 merged | clean (1.6s) |
| 3d/net | active | yes | 2026-08-05 | PR #1 merged pre-MT024; **never republished with flat-topology fix** — live Mermaid clipping confirmed 2026-08-14; origin of open `TC-REPUB-01` (ex-TC-HARDEN-47) | clean (0.8s) — candidate-cleanliness and publication-currency are different questions; see `TC-REPUB-01` |
| 3d/python | active | yes | 2026-08-05 | Same pattern as 3d/net — never republished; origin of `TC-REPUB-01` (ex-TC-HARDEN-48) | clean (229.9s — `AUD-P1-RUNTIME-VARIANCE`) |
| 3d/typescript | active | yes | 2026-08-11 | PR #1 + follow-up PR #2 merged | clean (0.5s) |
| barcode/python | active | yes | none recorded | — | clean (4.1s) |
| cells/cpp | active | yes | none recorded | — | clean (1.8s) |
| cells/go | active | yes | 2026-08-10 | Published once, since further edited locally (W5 in-between state, disclosed) | clean (0.5s) |
| cells/java | active | yes | 2026-08-10 | Published once, since further edited locally (W5) | clean (2.0s) |
| cells/net | active | yes | 2026-08-10 | Published once, since further edited locally (W5) | clean (2.2s) |
| cells/python | active | yes | none recorded | — | clean (35.2s) |
| cells/rust | active | yes | none recorded (dry-run only, `repo_presenter_actions.jsonl`) | dry-run push rehearsed 2026-08-18, not a real publish | clean, `skipped_published` (1.4s) |
| cells/typescript | **excluded** (BLOCKED_REPO_NOT_LAUNCHABLE) | yes (explicit override) | none recorded | — | scoped call returns empty (`total: 0`, 0.3s) — silent, no explicit exclusion reason surfaced |
| email/cpp | active | yes | none recorded | — | clean, `skipped_published` (0.8s) |
| email/net | active | yes | none recorded | — | clean, `skipped_published` (0.7s) |
| email/python | active | yes | none recorded | — | clean (2.1s) |
| font/python | active | yes | none recorded | — | clean (59.4s) |
| html/python | active | yes | none recorded | — | clean (208.6s — `AUD-P1-RUNTIME-VARIANCE`) |
| note/python | active | yes | 2026-08-16 | PR #5 squash-merged (merge commit 41de2e8a) — the one fully-live, real, merged push in the whole portfolio | clean (4.6s) |
| page/python | active | yes | none recorded | — | **DIRTY, newly discovered** (105.4s): `enterprise_edition_link_resolves`, `enterprise_edition_anchor_matches_relationship`, `diagram_hybrid_reverification` — see `AUD-P1-NEW-DIRTY-PRODUCTS` |
| pdf/cpp | active | yes | 2026-08-17 | MT054: candidate byte-identical to live upstream (published-state bypass fires) | **DIRTY** (1.4s): 1× `diagram_hybrid_reverification` |
| pdf/go | active | yes | none recorded | — | **DIRTY** (1.2s): 1× `diagram_hybrid_reverification` |
| pdf/java | active | yes | none recorded | — | **DIRTY** (25.4s): 11× `dev_test_artifacts_linked` |
| pdf/net | active | yes | none recorded | — | **DIRTY, largest break** (6.6s): 173 findings across 6 check types, 167× `content_unit_excerpt_matches_extraction` |
| pdf/python | active | yes | none recorded | — | clean (208.6s — `AUD-P1-RUNTIME-VARIANCE`) |
| slides/cpp | active | yes | 2026-08-18 | MT056 reconciliation: canonical candidate byte-identical (stripped) to upstream | clean (2.0s) |
| slides/java | active | yes | none recorded | — | clean (2.4s) |
| slides/net | active | yes | none recorded | — | clean (1.8s) |
| slides/python | active | yes | none recorded | — | clean (382.2s — slowest in the portfolio, `AUD-P1-RUNTIME-VARIANCE`) |
| tex/python | active | yes | none recorded | — | **DIRTY, newly discovered** (4.4s): `enterprise_edition_link_resolves`, `enterprise_edition_anchor_matches_relationship` — see `AUD-P1-NEW-DIRTY-PRODUCTS` |
| words/net | active | yes | 2026-08-18 | MT056 reconciliation: canonical candidate byte-identical (stripped) to upstream | clean, `skipped_published` (29.9s) |
| words/python | active | yes | none recorded | — | clean (61.1s) |

**Status**: this table will be updated in place once the full 31-product scoped
`audit-portfolio` sweep (`_run_baseline_audit.py`, running in background as of
2026-08-25 ~13:55, per-product timeout 120s) completes and writes
`baseline_audit_results.json` in this same directory. Rows marked "pending baseline
sweep" carry no assumption either way — several (`pdf/python`, `slides/python`) are
known from Phase 1 research to intermittently time out even when scoped, which is
itself evidence for `AUD-P1-UNSCOPED-AUDIT-HANG`'s broader point that `audit_portfolio`'s
iteration/check logic has a real, unresolved performance defect, not just an unscoped-call
edge case.

## Preliminary denominator notes

- **31 total candidates**, all four-way-reviewable in Phase 3b/3c (original README history
  is reconstructable via git history / clone-cache prior commits + `upstream-issues.md`;
  current upstream README via clone cache; candidate via `repo-presenter-regen-full`;
  published README via the product's actual GitHub repo where `readme_published_state.json`
  or `repo_presenter_actions.jsonl` records a real push).
- **1 fully-live, real, merged publication** in the entire portfolio: `note/python` (PR #5).
  This is the strongest "previously-published README" canary candidate for Phase 3b.
- **4 currently-dirty products**, all in the `pdf` family, all discovered by this mission's
  own live re-verification (not by the stale 2026-08-20 snapshot) — confirmed positive
  controls for Phase 3b canary selection: `pdf/net` (factual/dependency-heavy/.NET),
  `pdf/java` (11 findings, different platform — second data point for product-specific vs.
  systemic), `pdf/go` and `pdf/cpp` (each 1 finding — the `diagram_hybrid_reverification`
  check specifically, shared between two different platforms, suggesting a shared-machinery
  cause rather than two independent product-specific defects).
- **2 products with open, previously-lost-then-recovered republication debt**: `3d/net` and
  `3d/python` (`TC-REPUB-01`, still `TODO` — the tripwire that should block this is wired
  advisory-only, `readme_refresh_run.py:2303`).

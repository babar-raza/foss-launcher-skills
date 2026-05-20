# Skill ID Cross-Reference: foss-launcher ↔ aspose.org

**Purpose**: Cross-reference table mapping foss-launcher skill IDs (authoritative) to their
corresponding aspose.org IDs (read-only reference). Required because after approximately S-42,
the two repos assigned IDs independently. The same S-XX number does NOT mean the same skill.

**Note**: All comparisons are by slug/name, not by ID. This table documents the mapping only.

---

## ID Divergence Point

- IDs S-01 through approximately S-42 were assigned concurrently; same IDs may refer to the
  same skill (by name) or diverge depending on timing.
- After S-42, IDs diverged completely: foss-launcher and aspose.org assigned independently.
- New foss-launcher skills (S-56+) have no aspose.org counterpart unless ported.

---

## Mapping Table

| foss-launcher ID | foss-launcher name | aspose.org ID | aspose.org name | Notes |
|---|---|---|---|---|
| S-01 | path-guard | S-01 | path-guard | Same |
| S-10 | project-phase-store | S-10 | project-phase-store | Same |
| S-12 | knowledge-diff | S-12 | knowledge-diff | Same |
| S-13 | stale-detect | S-13 | stale-detect | Same |
| S-14 | knowledge-update | S-14 | knowledge-update | Same |
| S-15 | embed-knowledge | S-15 | embed-knowledge | Same |
| S-16 | *(unassigned)* | S-16 | *(varies)* | Gap |
| S-17 | rubric-align | S-17 | rubric-align | Same |
| S-18 | page-plan | S-18 | page-plan | Same |
| S-19 | page-draft | S-19 | page-draft | Same |
| S-20 | page-update | S-20 | page-update | Same |
| S-21 | page-enhance | S-21 | page-enhance | Same |
| S-22 | faq-generate | S-22 | faq-generate | Same |
| S-23 | ground-check | S-23 | ground-check | Same |
| S-24 | evidence-cite | S-24 | evidence-cite | Same |
| S-25 | eval-page | S-25 | eval-page | Same |
| S-26 | heal-page | S-26 | heal-page | Same |
| S-27–S-29 | *(unassigned)* | *(varies)* | *(varies)* | Gap |
| S-30 | truth-sync | S-30 | truth-sync | Same |
| S-31 | truth-index | S-31 | truth-index | Same |
| S-32 | content-audit | S-32 | content-audit | Same |
| S-33 | change-guard | S-33 | change-guard | Same |
| S-34 | repo-scout | S-34 | repo-scout | Same |
| S-35 | truth-merge | S-35 | truth-merge | Same |
| S-36 | cross-platform | S-36 | cross-platform | Same |
| S-37 | corpus-scan | S-37 | corpus-scan | Same |
| S-38 | launch-product | S-38 | launch-product | Same (S-38 collision: truth-audit renumbered to S-47) |
| S-39 | discover-products | S-39 | discover-products | Same |
| S-40 | batch-remediate | S-40 | batch-remediate | Same |
| S-41 | batch-eval-fix | S-41 | batch-eval-fix | Same |
| S-42 | category-fix | S-42 | category-fix | Same (S-42 collision: evidence-verify renumbered to S-46) |
| S-43 | evidence-decide | S-43 | **gap-eval** | **DIVERGE** — different skills post-S-42 |
| S-44 | evidence-materialize | S-44 | gap-plan | DIVERGE |
| S-45 | mental-model | S-45 | gap-report | DIVERGE |
| S-46 | evidence-verify | S-46 | gap-apply | DIVERGE (foss: renumbered from S-42) |
| S-47 | truth-audit | S-47 | truth-audit | Same name (aspose: renumbered from S-38) |
| S-48 | content-eval | S-48 | family-sync | DIVERGE |
| S-49 | knowledge-bootstrap | S-49 | knowledge-bootstrap | Same |
| S-50 | content-check | S-50 | content-check | Same |
| S-51 | new-docs-page | S-51 | new-docs-page | Same |
| S-52 | new-blog-post | S-52 | **translate-page** | **DIVERGE** |
| S-53 | new-kb-howto | S-53 | **translate-batch** | **DIVERGE** |
| S-54 | new-kb-faq | S-54 | new-kb-faq | Same |
| S-55 | new-reference-page | S-55 | **no-downgrade-guard** | **DIVERGE** (aspose S-55 is internal) |
| S-56 | **no-downgrade-guard** | *(same aspose S-55)* | no-downgrade-guard | Foss-new ID (ported from aspose S-55) |
| S-57 | site-plan | S-47 | site-plan | Ported; aspose was S-47 pre-diverge renaming |
| S-58 | family-sync | S-48 | family-sync | Ported |
| S-59 | refresh-product-page | S-86 | refresh-product-page | Ported |
| S-60 | launch-rollback | S-79 | launch-rollback | Ported |
| S-61 | knowledge-enrich | S-37 | knowledge-enrich | Ported (aspose S-37 is knowledge-enrich) |
| S-62 | gap-eval | S-43 | gap-eval | Ported (aspose S-43 = gap-eval) |
| S-63 | gap-plan | S-44 | gap-plan | Ported |
| S-64 | gap-report | S-45 | gap-report | Ported |
| S-65 | gap-apply | S-46 | gap-apply | Ported |
| S-66 | new-products-page | S-61 | new-products-page | Ported |
| S-67 | batch-reference | S-62 | batch-reference | Ported |
| S-68 | code-smoke | S-63 | code-smoke | Ported |
| S-69 | getting-started | S-64 | getting-started | Ported |
| S-70 | link-validate | S-65 | link-validate | Ported |
| S-71 | register-human-content | S-66 | register-human-content | Ported |
| S-72 | diagnose-skill-failure | S-67 | diagnose-skill-failure | Ported |
| S-73 | update-registry | S-68 | update-registry | Ported |
| S-74 | new-kb-index | S-69 | new-kb-index | Ported |
| S-75 | new-docs-index | S-70 | new-docs-index | Ported |
| S-76 | new-reference-index | S-71 | new-reference-index | Ported |
| S-77 | evidence-repair | S-72 | evidence-repair | Ported |
| S-78 | manual-edit | S-73 | manual-edit | Ported |
| S-79 | causal-backtrack | S-74 | causal-backtrack | Ported |
| S-80 | *(unassigned)* | S-75 | locale-patch | Reserved |
| S-81 | commit | S-76 | commit | Ported |
| S-82 | session-start | S-77 | session-start | Ported |
| S-83 | evidence-enhance | S-78 | evidence-enhance | Ported |
| S-84 | refresh-product | S-84 | refresh-product | Ported (same ID — aligned by convention) |
| S-85 | coverage-reconcile | S-80 | coverage-reconcile | Ported |
| S-86 | knowledge-coverage-audit | S-81 | knowledge-coverage-audit | Ported |
| S-87 | delta-site-plan | S-82 | delta-site-plan | Ported |
| S-88 | page-retire | S-83 | page-retire | Ported |
| S-89 | *(unassigned)* | S-84 | *(see refresh-product)* | Reserved |
| S-90 | truth-audit-content | S-85 | truth-audit-content | Ported |
| S-91–S-92 | *(unassigned)* | S-87–S-89 | *(varies)* | Reserved |
| S-93 | system-heal | S-87 | system-heal | Ported |
| S-94 | heal-batch | S-89 | heal-batch | Ported |
| S-95 | publish-readiness-review | S-90 | publish-readiness-review | Ported |
| S-96 | plan-normalize | S-91 | plan-normalize | Ported |
| S-97 | triage-confirm | S-92 | triage-confirm | Ported |
| S-98 | backlog | S-88 | backlog | Ported |
| S-99 | translate-page | S-52 | translate-page | Ported |
| S-100 | translate-batch | S-53 | translate-batch | Ported |
| S-101 | locale-patch | S-75 | locale-patch | Ported |
| S-102 | repo-patrol | S-93 | repo-patrol | Ported 2026-04-27 |
| S-103 | change-sweep | S-94 | change-sweep | Ported 2026-04-27 |
| S-104 | discovery-triage | S-95 | discovery-triage | Ported 2026-04-27 |
| S-105 | section-enhance | S-96 | section-enhance | Ported 2026-04-27 |
| S-106 | cleanroom-regen | S-97 | cleanroom-regen | Ported; aspose S-97 |
| S-107 | translate | *(none)* | *(none)* | foss-only dispatcher skill |
| S-108 | content-enrich | S-83 | content-enrich | Ported; aspose S-83 |
| S-109 | seo-review | *(none)* | *(none)* | foss-only governance gate |

---

## Skills Unique to foss-launcher (no aspose.org counterpart)

| foss-launcher ID | Name | Notes |
|---|---|---|
| S-43 | evidence-decide | foss evidence pipeline (new) |
| S-44 | evidence-materialize | foss evidence pipeline (new) |
| S-45 | mental-model | foss evidence pipeline (new) |
| S-46 | evidence-verify | foss evidence pipeline (new) |
| S-48 | content-eval | foss multi-dimensional evaluator (new) |
| S-107 | translate | foss dispatcher: routes to translate-page or translate-batch |
| S-109 | seo-review | foss governance gate for SEO recommendations |

## Skills Unique to aspose.org (not ported to foss-launcher)

| aspose.org ID | Name | Notes |
|---|---|---|
| S-99 | pipeline-harden | Pipeline hardening/maintenance workflow (18.6KB); high relevance — port recommended |
| S-100 | blog-migrate | Blog migration workflow (7.65KB); lower relevance for standalone repo |

---

## Key Divergence Points

1. **S-43 post-diverge**: foss S-43 = `evidence-decide`; aspose S-43 = `gap-eval` — completely different
2. **S-52/S-53 post-diverge**: foss has `new-blog-post`/`new-kb-howto`; aspose has `translate-page`/`translate-batch`
3. **S-55 post-diverge**: aspose S-55 = `no-downgrade-guard` (internal); foss S-55 = `new-reference-page` (user-callable)
4. **S-56**: foss-new ID for `no-downgrade-guard` (ported from aspose S-55; assigned new ID to avoid collision)

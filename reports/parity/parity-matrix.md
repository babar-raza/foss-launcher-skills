# Parity Matrix — aspose.org ↔ foss-launcher

**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-011

## Assumption Verification Results

| # | Assumption | Status | Evidence |
|---|-----------|--------|----------|
| A1 | 82 shared slugs represent the same intended skill | UNPROVEN | Phase 4 content diff required |
| A2 | pipeline/config/registry.yaml maps all 84 skills to scripts | DISPROVEN | Only 33/84 (39.3%) have script bindings; 51 are agent-only by design |
| A3 | docs/id-mapping.md is complete and accurate | VERIFIED | id-mapping.md maps all foss IDs; 10 foss-only noted as exceptions |
| A4 | 4 foss CI checks are subset of aspose.org's 63 | LIKELY | Phase 4 confirmed 4 vs 63; overlap not deep-verified |
| A5 | blog-migrate and pipeline-harden are relevant | EVALUATED | pipeline-harden: high relevance (18.6KB, port); blog-migrate: lower relevance |
| A6 | aspose.org lib modules usable in foss with path adaptation | LIKELY | Path adaptation pattern established; deep verification in LB-* TCs |
| A7 | gap-eval profiles don't depend on Hugo-specific paths | FAILED | scripts/gap-eval/src/run.py has hardcoded aspose.org content paths — portability barrier |
| A8 | 10 foss-only skills have no aspose.org equivalents | VERIFIED | Cross-reference parity analysis: 0 aspose.org equivalents found for all 10 |

## Summary

| Category | Count |
|----------|-------|
| Total aspose.org skills | 84 |
| Total foss-launcher skills | 92 |
| Shared skill slugs | 82 |
| aspose.org-only skills | 2 |
| foss-launcher-only skills | 10 |
| CI checks in aspose.org | 63 |
| CI checks in foss-launcher | 4 |
| CI checks gap | 59 |
| Governance/workflow docs in aspose.org | 22 |
| Governance/workflow docs in foss-launcher | 0 |

## Shared Skills — Layer-by-Layer Status

| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Size% | L3 | L4 | L7 | Parity Status | Key Gaps |
|------|-----------|---------|-----------|---------|-------|----|----|----|----|----------|
| backlog | S-88 | S-98 | 54.39 | 4.13 | 8% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| batch-eval-fix | S-41 | S-41 | 3.2 | 2.68 | 84% | Y | Y | N | implemented_not_verified | missing_test_coverage |
| batch-reference | S-62 | S-67 | 13.29 | 7.94 | 60% | N | N | Y | governance_only | size_divergence, missing_governance |
| batch-remediate | S-40 | S-40 | 8.5 | 5.74 | 68% | Y | Y | N | implemented_not_verified | missing_test_coverage, size_divergence |
| category-fix | S-42 | S-42 | 4.92 | 3.43 | 70% | Y | Y | Y | partial_parity | size_divergence |
| causal-backtrack | S-74 | S-79 | 7.81 | 4.3 | 55% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| change-guard | S-33 | S-33 | 3.15 | 2.92 | 93% | Y | Y | N | implemented_not_verified | missing_test_coverage |
| change-sweep | S-94 | S-103 | 1.95 | 2.52 | 129% | Y | N | N | governance_only | missing_test_coverage |
| cleanroom-regen | S-97 | S-106 | 10.57 | 7.61 | 72% | Y | Y | N | implemented_not_verified | missing_test_coverage, missing_governance |
| code-smoke | S-63 | S-68 | 4.58 | 4.39 | 96% | N | N | N | governance_only | missing_test_coverage, missing_governance |
| commit | S-76 | S-81 | 20.97 | 7.24 | 35% | N | N | Y | governance_only | size_divergence, missing_governance |
| content-audit | S-32 | S-32 | 3.64 | 3.4 | 93% | Y | Y | N | implemented_not_verified | missing_test_coverage, missing_governance |
| content-check | S-23 | S-50 | 8.43 | 6.51 | 77% | N | N | N | governance_only | missing_test_coverage, missing_governance |
| content-enrich | S-98 | S-108 | 5.88 | 3.15 | 54% | N | N | Y | governance_only | size_divergence, missing_governance |
| content-eval | S-51 | S-48 | 4.34 | 2.52 | 58% | Y | N | Y | partial_parity | size_divergence, missing_governance |
| coverage-reconcile | S-80 | S-85 | 4.2 | 2.88 | 69% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| cross-platform | S-36 | S-36 | 5.94 | 2.35 | 40% | N | N | Y | governance_only | size_divergence, missing_governance |
| delta-site-plan | S-82 | S-87 | 3.65 | 2.65 | 73% | N | N | N | governance_only | missing_test_coverage |
| diagnose-skill-failure | S-67 | S-72 | 6.98 | 5.81 | 83% | N | N | N | governance_only | missing_test_coverage |
| discovery-triage | S-95 | S-104 | 3.27 | 3.73 | 114% | N | N | N | governance_only | missing_test_coverage |
| embed-knowledge | S-15 | S-15 | 6.29 | 1.57 | 25% | Y | Y | N | implemented_not_verified | missing_test_coverage, size_divergence |
| eval-page | S-25 | S-25 | 5.58 | 5.22 | 94% | Y | N | N | governance_only | missing_test_coverage |
| evidence-cite | S-24 | S-24 | 3.86 | 4.13 | 107% | Y | Y | N | implemented_not_verified | missing_test_coverage |
| evidence-enhance | S-78 | S-83 | 9.97 | 2.88 | 29% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| evidence-repair | S-72 | S-77 | 11.39 | 4.74 | 42% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| family-sync | S-48 | S-58 | 3.46 | 2.95 | 85% | N | N | N | governance_only | missing_test_coverage |
| faq-generate | S-22 | S-22 | 6.15 | 3.56 | 58% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| gap-apply | S-46 | S-65 | 7.49 | 2.8 | 37% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| gap-eval | S-43 | S-62 | 5.82 | 3.27 | 56% | N | N | Y | partial_parity | size_divergence |
| gap-plan | S-44 | S-63 | 4.16 | 2.32 | 56% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| gap-report | S-45 | S-64 | 4.76 | 2.08 | 44% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| getting-started | S-64 | S-69 | 8.34 | 4.64 | 56% | N | N | Y | partial_parity | size_divergence |
| heal-batch | S-89 | S-94 | 6.17 | 4.47 | 72% | N | N | N | governance_only | missing_test_coverage |
| heal-page | S-26 | S-26 | 10.85 | 4.36 | 40% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| knowledge-bootstrap | S-54 | S-49 | 5.93 | 3.84 | 65% | N | N | Y | partial_parity | size_divergence |
| knowledge-coverage-audit | S-81 | S-86 | 7.22 | 3.36 | 47% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| knowledge-diff | S-12 | S-12 | 5.44 | 1.9 | 35% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| knowledge-enrich | S-37 | S-61 | 6.22 | 2.26 | 36% | Y | Y | N | implemented_not_verified | missing_test_coverage, size_divergence |
| knowledge-update | S-14 | S-14 | 6.77 | 3.99 | 59% | Y | Y | Y | partial_parity | size_divergence, missing_governance |
| launch-product | S-49 | S-38 | 16.43 | 13.9 | 85% | N | N | Y | governance_only | missing_governance, missing_dependency |
| launch-rollback | S-79 | S-60 | 3.87 | 3.48 | 90% | N | N | Y | partial_parity | missing_governance |
| link-validate | S-65 | S-70 | 2.92 | 2.57 | 88% | N | N | N | governance_only | missing_test_coverage, missing_governance |
| locale-patch | S-75 | S-101 | 4.31 | 3.5 | 81% | N | N | N | governance_only | missing_test_coverage |
| manual-edit | S-73 | S-78 | 21.19 | 4.65 | 22% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| new-blog-post | S-57 | S-52 | 10.11 | 5.85 | 58% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| new-docs-index | S-70 | S-75 | 7.17 | 4.23 | 59% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| new-docs-page | S-56 | S-51 | 8.68 | 5.34 | 62% | N | N | Y | partial_parity | size_divergence |
| new-kb-faq | S-59 | S-54 | 6.76 | 5.32 | 79% | N | N | N | governance_only | missing_test_coverage |
| new-kb-howto | S-58 | S-53 | 7.66 | 5.09 | 66% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| new-kb-index | S-69 | S-74 | 6.94 | 4.06 | 59% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| new-products-page | S-61 | S-66 | 11.94 | 8.31 | 70% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| new-reference-index | S-71 | S-76 | 7.14 | 4.44 | 62% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| new-reference-page | S-60 | S-55 | 12.29 | 5.68 | 46% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| no-downgrade-guard | S-55 | S-56 | 3.71 | 3.01 | 81% | Y | Y | Y | partial_parity | — |
| page-draft | S-19 | S-19 | 7.16 | 4.51 | 63% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| page-enhance | S-21 | S-21 | 6.92 | 4.57 | 66% | N | N | Y | partial_parity | size_divergence |
| page-plan | S-18 | S-18 | 7.0 | 5.54 | 79% | N | N | N | governance_only | missing_test_coverage |
| page-retire | S-83 | S-88 | 3.92 | 3.29 | 84% | N | N | N | governance_only | missing_test_coverage |
| page-update | S-20 | S-20 | 11.89 | 3.67 | 31% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| path-guard | S-01 | S-01 | 2.15 | 1.96 | 91% | Y | Y | Y | partial_parity | — |
| plan-normalize | S-91 | S-96 | 13.93 | 4.28 | 31% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| project-phase-store | S-10 | S-10 | 2.28 | 3.02 | 132% | N | N | Y | partial_parity | — |
| publish-readiness-review | S-90 | S-95 | 18.03 | 4.17 | 23% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| refresh-product | S-84 | S-84 | 12.42 | 4.06 | 33% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| refresh-product-page | S-86 | S-59 | 4.83 | 2.57 | 53% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| register-human-content | S-66 | S-71 | 4.87 | 3.26 | 67% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| repo-patrol | S-93 | S-102 | 2.21 | 2.98 | 135% | Y | N | Y | documented_not_implemented | missing_governance, missing_dependency |
| repo-scout | S-34 | S-34 | 5.52 | 5.2 | 94% | Y | Y | Y | partial_parity | missing_governance |
| rubric-align | S-17 | S-17 | 3.62 | 4.05 | 112% | N | N | N | governance_only | missing_test_coverage |
| section-enhance | S-96 | S-105 | 21.75 | 7.62 | 35% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| session-start | S-77 | S-82 | 7.17 | 3.16 | 44% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| site-plan | S-47 | S-57 | 5.44 | 3.0 | 55% | N | N | Y | governance_only | size_divergence, missing_governance |
| stale-detect | S-13 | S-13 | 4.36 | 2.08 | 48% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| system-heal | S-87 | S-93 | 12.59 | 3.88 | 31% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| translate-batch | S-53 | S-100 | 7.17 | 3.23 | 45% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| translate-page | S-52 | S-99 | 5.68 | 3.79 | 67% | N | N | N | governance_only | missing_test_coverage, size_divergence |
| triage-confirm | S-92 | S-97 | 3.93 | 4.86 | 124% | N | N | N | governance_only | missing_test_coverage |
| truth-audit | S-38 | S-47 | 11.97 | 9.61 | 80% | N | N | Y | governance_only | missing_governance, missing_dependency |
| truth-audit-content | S-85 | S-90 | 8.47 | 4.42 | 52% | N | N | Y | governance_only | size_divergence, missing_governance |
| truth-index | S-31 | S-31 | 6.06 | 1.47 | 24% | Y | Y | Y | partial_parity | size_divergence, missing_governance |
| truth-merge | S-35 | S-35 | 5.32 | 2.26 | 42% | Y | Y | N | implemented_not_verified | missing_test_coverage, size_divergence |
| update-registry | S-68 | S-73 | 5.73 | 5.07 | 88% | N | N | N | governance_only | missing_test_coverage, missing_governance |

## aspose.org-Only Skills (missing_entirely in foss-launcher)

| Slug | Aspose ID | Aspose KB | Parity Status |
|------|-----------|-----------|---------------|
| blog-migrate | S-100 | 7.65 | missing_entirely |
| pipeline-harden | S-99 | 18.6 | missing_entirely |

## foss-launcher-Only Skills (foss_only)

| Slug | Foss ID | Foss KB | Notes |
|------|---------|---------|-------|
| corpus-scan | S-37 | 4.04 | No equivalent in aspose.org |
| discover-products | S-39 | 3.74 | No equivalent in aspose.org |
| evidence-decide | S-43 | 1.85 | No equivalent in aspose.org |
| evidence-materialize | S-44 | 1.97 | No equivalent in aspose.org |
| evidence-verify | S-46 | 2.04 | No equivalent in aspose.org |
| ground-check | S-23 | 5.49 | No equivalent in aspose.org |
| mental-model | S-45 | 1.75 | No equivalent in aspose.org |
| seo-review | S-109 | 2.59 | No equivalent in aspose.org |
| translate | S-107 | 2.66 | No equivalent in aspose.org |
| truth-sync | S-30 | 3.06 | No equivalent in aspose.org |

## Parity Status Distribution

| Status | Count |
|--------|-------|
| governance_only | 58 |
| partial_parity | 14 |
| foss_only | 10 |
| implemented_not_verified | 9 |
| missing_entirely | 2 |
| documented_not_implemented | 1 |

## CI Check Coverage Gap

aspose.org has 63 CI check scripts in `scripts/ci/checks/`. foss-launcher has 4.
Gap: **59 missing CI validation checks**. See `aspose-ci-checks-map.yaml` for full list.

## Governance Documentation Gap

aspose.org has 22 governance/workflow docs in `docs/governance/` and `docs/workflows/`.
foss-launcher has 0 external governance docs (governance inlined in AGENTS.md).
See `aspose-governance-map.yaml` for full list.
# Gap Report — foss-launcher vs aspose.org

**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-011

## Overview

Total gaps identified: **81** skills with ≥1 gap classification.

### Gap Classification Summary

| Gap Classification | Occurrences |
|-------------------|-------------|
| missing_test_coverage | 59 |
| size_divergence | 52 |
| missing_governance | 33 |
| missing_dependency | 18 |
| missing_skill | 2 |

## Critical Findings from Deep Analysis

### CF1: S-43 gap-eval — Portability Barrier (Assumption A7 FAILED)

`gap-eval` (aspose.org S-43) has **hardcoded aspose.org content paths** in
`scripts/gap-eval/src/run.py`. References include: `content/docs.aspose.org`,
`content/blog.aspose.org`, `content/kb.aspose.org`.

**Impact**: gap-eval cannot run in foss-launcher against non-aspose.org content repos
without refactoring to use `$CONTENT_REPO_PATH` parameterization.

**Gap classification**: `behavioral_mismatch`, `missing_config_support`
**Recommended fix**: Extract all hardcoded paths to a config-driven pattern (TC-SC-*).

### CF2: 3 CI Checks Are Website-Specific (Not Portable)

Of the 63 CI checks, **3 are non-portable** due to Hugo/aspose.org-specific logic:
- `check-blog-slugs.py` — hardcoded blog URL patterns
- `check_plugin_platform.py` — Hugo layout plugin structure
- `check_family_display_names.py` — aspose.org product family registry

**60/63 checks are portable** to foss-launcher.

### CF3: Assumption A2 Partially Confirmed

`pipeline/config/registry.yaml` maps only **33/84 skills** (39.3%) to scripts.
The remaining 51 are agent-only execution (no pipeline backing script).
This is by design — not all skills need a Python entrypoint.

## Systemic Gaps (Not Skill-Specific)

### G1: Missing CI Check Infrastructure (60 portable checks)

aspose.org runs 63 automated validation checks in `scripts/ci/checks/`. foss-launcher has 4.
60 of these are portable to foss-launcher. 3 are website-specific (see CF2 above).
The 59 missing portable checks cover: skill_validation, content_quality, knowledge, metrics,
pipeline, locale, link_integrity, provenance, governance, code_quality.
See `aspose-ci-checks-map.yaml` for the complete list with domain classification.

**Gap classification**: `missing_governance` (systemic)
**Recommended fix**: Port top-value checks by domain priority.

### G2: Missing Governance Documentation (22 docs)

aspose.org has `docs/governance/` (10 docs) and `docs/workflows/` (12 docs).
foss-launcher governance is inlined in AGENTS.md only.
Missing: evidence governance, launch gates, write boundaries, naming conventions,
DAR policy, causal backtracking, change triggers, heal policy, skill chains, etc.

**Gap classification**: `missing_documentation` (systemic)
**Recommended fix**: Create `docs/governance/` and `docs/workflows/` mirroring aspose.org structure.

### G3: Missing Shared Library Layer (scripts/pipeline/lib/)

aspose.org has 19 shared library modules in `scripts/pipeline/lib/`:
grade_writer, heal_controller, provenance, registry_loader, content_patcher, etc.
foss-launcher has no `scripts/pipeline/lib/` directory.
This means skills that depend on these libraries cannot function correctly.

**Gap classification**: `missing_helper_utility` (systemic)

## Per-Skill Gap Details

### Status: missing_entirely (2 skills)

| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Gap Classifications |
|------|-----------|---------|-----------|---------|---------------------|
| blog-migrate | S-100 | null | 7.65 | 0 | missing_skill |
| pipeline-harden | S-99 | null | 18.6 | 0 | missing_skill |

### Status: governance_only (58 skills)

| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Gap Classifications |
|------|-----------|---------|-----------|---------|---------------------|
| backlog | S-88 | S-98 | 54.39 | 4.13 | missing_test_coverage, size_divergence, missing_governance, missing_dependency |
| batch-reference | S-62 | S-67 | 13.29 | 7.94 | size_divergence, missing_governance, missing_dependency |
| causal-backtrack | S-74 | S-79 | 7.81 | 4.3 | missing_test_coverage, size_divergence, missing_governance |
| change-sweep | S-94 | S-103 | 1.95 | 2.52 | missing_test_coverage |
| code-smoke | S-63 | S-68 | 4.58 | 4.39 | missing_test_coverage, missing_governance, missing_dependency |
| commit | S-76 | S-81 | 20.97 | 7.24 | size_divergence, missing_governance, missing_dependency |
| content-check | S-23 | S-50 | 8.43 | 6.51 | missing_test_coverage, missing_governance, missing_dependency |
| content-enrich | S-98 | S-108 | 5.88 | 3.15 | size_divergence, missing_governance, missing_dependency |
| coverage-reconcile | S-80 | S-85 | 4.2 | 2.88 | missing_test_coverage, size_divergence, missing_governance, missing_dependency |
| cross-platform | S-36 | S-36 | 5.94 | 2.35 | size_divergence, missing_governance, missing_dependency |
| delta-site-plan | S-82 | S-87 | 3.65 | 2.65 | missing_test_coverage |
| diagnose-skill-failure | S-67 | S-72 | 6.98 | 5.81 | missing_test_coverage |
| discovery-triage | S-95 | S-104 | 3.27 | 3.73 | missing_test_coverage |
| eval-page | S-25 | S-25 | 5.58 | 5.22 | missing_test_coverage |
| evidence-enhance | S-78 | S-83 | 9.97 | 2.88 | missing_test_coverage, size_divergence, missing_governance |
| evidence-repair | S-72 | S-77 | 11.39 | 4.74 | missing_test_coverage, size_divergence |
| family-sync | S-48 | S-58 | 3.46 | 2.95 | missing_test_coverage |
| faq-generate | S-22 | S-22 | 6.15 | 3.56 | missing_test_coverage, size_divergence |
| gap-apply | S-46 | S-65 | 7.49 | 2.8 | missing_test_coverage, size_divergence |
| gap-plan | S-44 | S-63 | 4.16 | 2.32 | missing_test_coverage, size_divergence |
| gap-report | S-45 | S-64 | 4.76 | 2.08 | missing_test_coverage, size_divergence |
| heal-batch | S-89 | S-94 | 6.17 | 4.47 | missing_test_coverage |
| heal-page | S-26 | S-26 | 10.85 | 4.36 | missing_test_coverage, size_divergence |
| knowledge-coverage-audit | S-81 | S-86 | 7.22 | 3.36 | missing_test_coverage, size_divergence |
| knowledge-diff | S-12 | S-12 | 5.44 | 1.9 | missing_test_coverage, size_divergence |
| launch-product | S-49 | S-38 | 16.43 | 13.9 | missing_governance, missing_dependency |
| link-validate | S-65 | S-70 | 2.92 | 2.57 | missing_test_coverage, missing_governance, missing_dependency |
| locale-patch | S-75 | S-101 | 4.31 | 3.5 | missing_test_coverage |
| manual-edit | S-73 | S-78 | 21.19 | 4.65 | missing_test_coverage, size_divergence, missing_governance |
| new-blog-post | S-57 | S-52 | 10.11 | 5.85 | missing_test_coverage, size_divergence |
| new-docs-index | S-70 | S-75 | 7.17 | 4.23 | missing_test_coverage, size_divergence |
| new-kb-faq | S-59 | S-54 | 6.76 | 5.32 | missing_test_coverage |
| new-kb-howto | S-58 | S-53 | 7.66 | 5.09 | missing_test_coverage, size_divergence |
| new-kb-index | S-69 | S-74 | 6.94 | 4.06 | missing_test_coverage, size_divergence |
| new-products-page | S-61 | S-66 | 11.94 | 8.31 | missing_test_coverage, size_divergence, missing_governance, missing_dependency |
| new-reference-index | S-71 | S-76 | 7.14 | 4.44 | missing_test_coverage, size_divergence |
| new-reference-page | S-60 | S-55 | 12.29 | 5.68 | missing_test_coverage, size_divergence |
| page-draft | S-19 | S-19 | 7.16 | 4.51 | missing_test_coverage, size_divergence |
| page-plan | S-18 | S-18 | 7.0 | 5.54 | missing_test_coverage |
| page-retire | S-83 | S-88 | 3.92 | 3.29 | missing_test_coverage |
| page-update | S-20 | S-20 | 11.89 | 3.67 | missing_test_coverage, size_divergence |
| plan-normalize | S-91 | S-96 | 13.93 | 4.28 | missing_test_coverage, size_divergence |
| publish-readiness-review | S-90 | S-95 | 18.03 | 4.17 | missing_test_coverage, size_divergence |
| refresh-product | S-84 | S-84 | 12.42 | 4.06 | missing_test_coverage, size_divergence |
| refresh-product-page | S-86 | S-59 | 4.83 | 2.57 | missing_test_coverage, size_divergence |
| register-human-content | S-66 | S-71 | 4.87 | 3.26 | missing_test_coverage, size_divergence |
| rubric-align | S-17 | S-17 | 3.62 | 4.05 | missing_test_coverage |
| section-enhance | S-96 | S-105 | 21.75 | 7.62 | missing_test_coverage, size_divergence, missing_governance |
| session-start | S-77 | S-82 | 7.17 | 3.16 | missing_test_coverage, size_divergence |
| site-plan | S-47 | S-57 | 5.44 | 3.0 | size_divergence, missing_governance, missing_dependency |
| stale-detect | S-13 | S-13 | 4.36 | 2.08 | missing_test_coverage, size_divergence, missing_governance, missing_dependency |
| system-heal | S-87 | S-93 | 12.59 | 3.88 | missing_test_coverage, size_divergence, missing_governance, missing_dependency |
| translate-batch | S-53 | S-100 | 7.17 | 3.23 | missing_test_coverage, size_divergence |
| translate-page | S-52 | S-99 | 5.68 | 3.79 | missing_test_coverage, size_divergence |
| triage-confirm | S-92 | S-97 | 3.93 | 4.86 | missing_test_coverage |
| truth-audit | S-38 | S-47 | 11.97 | 9.61 | missing_governance, missing_dependency |
| truth-audit-content | S-85 | S-90 | 8.47 | 4.42 | size_divergence, missing_governance, missing_dependency |
| update-registry | S-68 | S-73 | 5.73 | 5.07 | missing_test_coverage, missing_governance, missing_dependency |

### Status: documented_not_implemented (1 skills)

| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Gap Classifications |
|------|-----------|---------|-----------|---------|---------------------|
| repo-patrol | S-93 | S-102 | 2.21 | 2.98 | missing_governance, missing_dependency |

### Status: implemented_not_verified (9 skills)

| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Gap Classifications |
|------|-----------|---------|-----------|---------|---------------------|
| batch-eval-fix | S-41 | S-41 | 3.2 | 2.68 | missing_test_coverage |
| batch-remediate | S-40 | S-40 | 8.5 | 5.74 | missing_test_coverage, size_divergence, missing_governance |
| change-guard | S-33 | S-33 | 3.15 | 2.92 | missing_test_coverage |
| cleanroom-regen | S-97 | S-106 | 10.57 | 7.61 | missing_test_coverage, missing_governance |
| content-audit | S-32 | S-32 | 3.64 | 3.4 | missing_test_coverage, missing_governance |
| embed-knowledge | S-15 | S-15 | 6.29 | 1.57 | missing_test_coverage, size_divergence, missing_governance |
| evidence-cite | S-24 | S-24 | 3.86 | 4.13 | missing_test_coverage |
| knowledge-enrich | S-37 | S-61 | 6.22 | 2.26 | missing_test_coverage, size_divergence, missing_governance |
| truth-merge | S-35 | S-35 | 5.32 | 2.26 | missing_test_coverage, size_divergence, missing_governance |

### Status: partial_parity (11 skills)

| Slug | Aspose ID | Foss ID | Aspose KB | Foss KB | Gap Classifications |
|------|-----------|---------|-----------|---------|---------------------|
| category-fix | S-42 | S-42 | 4.92 | 3.43 | size_divergence |
| content-eval | S-51 | S-48 | 4.34 | 2.52 | size_divergence, missing_governance |
| gap-eval | S-43 | S-62 | 5.82 | 3.27 | size_divergence |
| getting-started | S-64 | S-69 | 8.34 | 4.64 | size_divergence |
| knowledge-bootstrap | S-54 | S-49 | 5.93 | 3.84 | size_divergence |
| knowledge-update | S-14 | S-14 | 6.77 | 3.99 | size_divergence, missing_governance |
| launch-rollback | S-79 | S-60 | 3.87 | 3.48 | missing_governance |
| new-docs-page | S-56 | S-51 | 8.68 | 5.34 | size_divergence |
| page-enhance | S-21 | S-21 | 6.92 | 4.57 | size_divergence |
| repo-scout | S-34 | S-34 | 5.52 | 5.2 | missing_governance |
| truth-index | S-31 | S-31 | 6.06 | 1.47 | size_divergence, missing_governance |

## foss-launcher Advantages Over aspose.org

| Advantage | Detail |
|-----------|--------|
| 10 unique skills | corpus-scan, discover-products, evidence-decide, evidence-materialize, evidence-verify, ground-check, mental-model, seo-review, translate, truth-sync |
| pyproject.toml entry points | 6 console_scripts vs 0 in aspose.org — better CLI UX |
| Standalone deployment | No Hugo/website dependency — can run independently |
| Cleaner registry schema | skills/registry.yaml is simpler and more readable than aspose.org's registry.json |
| Integrated test suite | tests/ at repo root with clear organization |
| Better ID coverage | S-01 through S-109 with more skills defined |
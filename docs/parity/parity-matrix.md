# Capability Parity Matrix

**Comparison:** aspose.org (76 skills) vs foss-launcher-skills-gitlab (42 skills)
**Comparison method:** slug/name (NOT ID — IDs diverge after S-42)
**Date:** 2026-04-20

## Parity Status Legend

| Code | Meaning |
|------|---------|
| `EXACT` | Proven identical behavior and implementation |
| `FUNCTIONAL` | Different implementation, same practical outcome |
| `PARTIAL` | Overlapping but not equivalent coverage |
| `GOV_ONLY` | Governance reference only, no implementation |
| `UNVERIFIED` | Present in both but behavior not yet compared |
| `MISSING` | Absent from foss-launcher entirely |
| `NEW_FOSS` | Exists in foss-launcher but not aspose.org |
| `RENAMED` | Same skill under a different name in foss |

---

## Table A: Skills Present in Both Repos

Skills matched by slug. Where slugs differ, matched by description/purpose.

| Slug | aspose ID | foss ID | Internal (aspose) | Internal (foss) | Parity | Notes |
|------|-----------|---------|------------------|----------------|--------|-------|
| path-guard | S-01 | S-01 | YES | NO (gap) | UNVERIFIED | foss missing `internal` flag in registry |
| project-phase-store | S-10 | S-10 | YES | NO (gap) | UNVERIFIED | foss missing `internal` flag |
| knowledge-diff | S-12 | S-12 | NO | NO | UNVERIFIED | Compare skill bodies |
| stale-detect | S-13 | S-13 | NO | NO | UNVERIFIED | Compare skill bodies |
| knowledge-update | S-14 | S-14 | NO | NO | UNVERIFIED | Both have script bindings |
| embed-knowledge | S-15 | S-15 | NO | NO | UNVERIFIED | |
| rubric-align | S-17 | S-17 | YES | NO (gap) | PARTIAL | foss missing `internal` flag |
| page-plan | S-18 | S-18 | NO | NO | UNVERIFIED | |
| page-draft | S-19 | S-19 | NO | NO | UNVERIFIED | |
| page-update | S-20 | S-20 | NO | NO | UNVERIFIED | |
| page-enhance | S-21 | S-21 | NO | NO | UNVERIFIED | |
| faq-generate | S-22 | S-22 | NO | NO | UNVERIFIED | |
| content-check | S-23 | S-50 | NO | NO | FUNCTIONAL | Same slug, different IDs. Both are structural pre-commit checks. |
| evidence-cite | S-24 | S-24 | YES | NO (gap) | PARTIAL | foss missing `internal` flag; both have scripts |
| eval-page | S-25 | S-25 | NO | NO | UNVERIFIED | Both backed by content_eval |
| heal-page | S-26 | S-26 | NO | NO | UNVERIFIED | |
| truth-index | S-31 | S-31 | NO | NO | UNVERIFIED | |
| content-audit | S-32 | S-32 | NO | NO | UNVERIFIED | Both have script bindings |
| change-guard | S-33 | S-33 | YES | NO (gap) | PARTIAL | foss missing `internal` flag |
| repo-scout | S-34 | S-34 | NO | NO | UNVERIFIED | Both have scripts; foss uses tree-sitter |
| truth-merge | S-35 | S-35 | NO | NO | UNVERIFIED | Both have scripts |
| cross-platform | S-36 | S-36 | NO | NO | UNVERIFIED | Both are prompt-only |
| truth-audit | S-38 | S-47 | NO | NO | UNVERIFIED | ID DIFFERS (S-38 vs S-47) — same slug |
| batch-remediate | S-40 | S-40 | NO | NO | UNVERIFIED | Both backed by remediate.py |
| batch-eval-fix | S-41 | S-41 | NO | NO | UNVERIFIED | Both backed by remediate.py |
| category-fix | S-42 | S-42 | NO | NO | UNVERIFIED | Both backed by remediate.py |
| knowledge-bootstrap | S-54 | S-49 | YES | NO (gap) | PARTIAL | ID DIFFERS (S-54 vs S-49); foss missing `internal` |
| launch-product | S-49 | S-38 | NO | NO | UNVERIFIED | ID DIFFERS (S-49 vs S-38) — same slug |
| content-eval | S-51 | S-48 | NO | NO | PARTIAL | ID DIFFERS; foss version is richer (16 evaluators) |
| new-docs-page | S-56 | S-51 | NO | NO | UNVERIFIED | ID DIFFERS |
| new-blog-post | S-57 | S-52 | NO | NO | UNVERIFIED | ID DIFFERS |
| new-kb-howto | S-58 | S-53 | NO | NO | UNVERIFIED | ID DIFFERS |
| new-kb-faq | S-59 | S-54 | NO | NO | UNVERIFIED | ID DIFFERS |
| new-reference-page | S-60 | S-55 | NO | NO | UNVERIFIED | ID DIFFERS |

**Sub-count A:** 33 skills with equivalents in both repos (all marked UNVERIFIED or PARTIAL pending body-level comparison)

---

## Table B: Skills in aspose.org MISSING from foss-launcher

| Slug | aspose ID | Internal | Priority | Proposed foss ID |
|------|-----------|----------|----------|-----------------|
| no-downgrade-guard | S-55 | YES | P1 | S-56 |
| knowledge-enrich | S-37 | NO | P1 | S-57 |
| gap-eval | S-43 | NO | P1 | S-58 |
| gap-plan | S-44 | YES | P1 | S-59 |
| gap-report | S-45 | NO | P1 | S-60 |
| gap-apply | S-46 | NO | P1 | S-61 |
| site-plan | S-47 | NO | P1 | S-62 |
| family-sync | S-48 | NO | P2 | S-63 |
| translate-page | S-52 | NO | P3 | S-64 |
| translate-batch | S-53 | NO | P3 | S-65 |
| new-products-page | S-61 | NO | P2 | S-66 |
| batch-reference | S-62 | NO | P2 | S-67 |
| code-smoke | S-63 | NO | P1 | S-68 |
| getting-started | S-64 | NO | P1 | S-69 |
| link-validate | S-65 | NO | P1 | S-70 |
| register-human-content | S-66 | NO | P2 | S-71 |
| diagnose-skill-failure | S-67 | NO | P1 | S-72 |
| update-registry | S-68 | NO | P1 | S-73 |
| new-kb-index | S-69 | NO | P2 | S-74 |
| new-docs-index | S-70 | NO | P2 | S-75 |
| new-reference-index | S-71 | NO | P2 | S-76 |
| evidence-repair | S-72 | NO | P1 | S-77 |
| manual-edit | S-73 | NO | P1 | S-78 |
| causal-backtrack | S-74 | NO | P1 | S-79 |
| locale-patch | S-75 | NO | P3 | S-80 |
| commit | S-76 | NO | P1 | S-81 |
| session-start | S-77 | NO | P1 | S-82 |
| evidence-enhance | S-78 | NO | P1 | S-83 |
| launch-rollback | S-79 | NO | P3 | S-84 |
| coverage-reconcile | S-80 | NO | P1 | S-85 |
| knowledge-coverage-audit | S-81 | NO | P1 | S-86 |
| delta-site-plan | S-82 | NO | P1 | S-87 |
| page-retire | S-83 | NO | P2 | S-88 |
| refresh-product | S-84 | NO | P3 | S-89 |
| truth-audit-content | S-85 | NO | P1 | S-90 |
| refresh-product-page | S-86 | NO | P2 | S-91 |
| system-heal | S-87 | NO | P3 | S-92 |
| backlog | S-88 | NO | P1 | S-93 |
| heal-batch | S-89 | NO | P3 | S-94 |
| publish-readiness-review | S-90 | NO | P1 | S-95 |
| plan-normalize | S-91 | NO | P1 | S-96 |
| triage-confirm | S-92 | NO | P1 | S-97 |

**Sub-count B:** 42 skills MISSING from foss-launcher
(Note: `content-check` is NOT missing — it exists as foss S-50, only the ID differs. The 42 count excludes it.)

---

## Table C: Skills NEW in foss-launcher (not in aspose.org)

These are foss-launcher innovations. Must NOT be removed or regressed during migration.

| foss ID | Slug | Description | Status |
|---------|------|-------------|--------|
| S-23 | ground-check | Pre-write evidence fact verification gate | NEW_FOSS |
| S-30 | truth-sync | Import external knowledge into fl/ layer | NEW_FOSS |
| S-37 | corpus-scan | Build golden corpus profile for style anchoring | NEW_FOSS |
| S-39 | discover-products | GitHub org scanner for FOSS repo discovery | PARTIAL† |
| S-43 | evidence-decide | Per-page content action engine from PEF | NEW_FOSS |
| S-44 | evidence-materialize | Canonical Product Evidence File builder | NEW_FOSS |
| S-45 | mental-model | Capability tier + gap analysis from PEF | NEW_FOSS |
| S-46 | evidence-verify | Deterministic PEF-grounded verification | NEW_FOSS |

†`discover-products` overlaps with aspose's `update-registry` (S-68) but is a different approach. Both will coexist after migration.

---

## Table D: Infrastructure Parity

| Infrastructure | aspose.org | foss-launcher | Status |
|----------------|-----------|---------------|--------|
| Skill registry | JSON | YAML (better) | FUNCTIONAL |
| Internal skill designation | `_skill_constants.py` + JSON flag | MISSING | MISSING |
| Claude mirror sync | sync_providers.py (all mirrors) | sync_commands.py (.claude/ only) | PARTIAL |
| .agents/.kilocode sync | YES (sync_providers.py) | NO | MISSING |
| GitHub CI workflows | 4 workflows | NONE | MISSING |
| Git hooks | pre-commit + commit-msg | NONE | MISSING |
| Translator system | YES (6 modules) | NONE | MISSING |
| Gap-eval system | YES (13 files) | Replaced by evidence pipeline | REPLACED |
| SEO scripts | YES | NONE | MISSING |
| CI validation scripts | 28+ | 4 | PARTIAL |
| No-downgrade-guard script | YES | NONE | MISSING |
| Data directory | families/products/platforms JSON | configs/families.yaml only | PARTIAL |
| RUNBOOK.md | YES | NONE | MISSING |
| OPERATOR_GUIDE.md | YES | NONE | MISSING |
| Schema validation | NONE | YES (6 schemas) | NEW_FOSS |
| Evidence pipeline scripts | NONE | YES (4 scripts) | NEW_FOSS |
| Installer scripts | NONE | YES (sh + ps1) | NEW_FOSS |
| Standalone tests | PARTIAL (scattered) | YES (28 files, organized) | NEW_FOSS |

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Skills in both (any parity status) | 33 |
| Skills MISSING from foss-launcher | 42 |
| Skills NEW in foss-launcher (not in aspose) | 8 |
| Skills with PARTIAL parity (governance gap) | 5 |
| Infrastructure items MISSING from foss | 9 |
| Infrastructure items PARTIAL in foss | 4 |
| Infrastructure items NEW in foss (better) | 5 |

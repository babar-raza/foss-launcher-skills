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
| S-23 | ground-check | *(none)* | *(none)* | Corrected 2026-08-29 (SYNC-8): was mislabeled "Same" -- no ground-check exists anywhere in aspose.org's git history under skills/ or .claude/commands/. Actually foss-only; see "Skills Unique to foss-launcher" below. |
| S-24 | evidence-cite | S-24 | evidence-cite | Same |
| S-25 | eval-page | S-25 | eval-page | Same |
| S-26 | heal-page | S-26 | heal-page | Same |
| S-27–S-29 | *(unassigned)* | *(varies)* | *(varies)* | Gap |
| S-30 | truth-sync | *(none)* | *(none)* | Corrected 2026-08-29 (SYNC-8): was mislabeled "Same" -- same finding as S-23. Actually foss-only; see below. |
| S-31 | truth-index | S-31 | truth-index | Same |
| S-32 | content-audit | S-32 | content-audit | Same |
| S-33 | change-guard | S-33 | change-guard | Same |
| S-34 | repo-scout | S-34 | repo-scout | Same |
| S-35 | truth-merge | S-35 | truth-merge | Same |
| S-36 | cross-platform | S-36 | cross-platform | Same |
| S-37 | corpus-scan | *(none)* | *(none)* | Corrected 2026-08-29 (SYNC-8): was mislabeled "Same" -- same finding as S-23. Actually foss-only; see below. |
| S-38 | launch-product | S-38 | launch-product | Same (S-38 collision: truth-audit renumbered to S-47) |
| S-39 | discover-products | *(none)* | *(none)* | Corrected 2026-08-29 (SYNC-8): was mislabeled "Same" -- same finding as S-23. Actually foss-only; see below. |
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
| S-110 | pipeline-harden | *(none)* | pipeline-harden | Ported from aspose.org S-99; foss-new ID to avoid collision with translate-page |
| S-116 | llms-generate | S-LG-01 | llms-generate | Ported 2026-08-29; generalized to config.yaml sites: block instead of 5 hardcoded subdomains; new backing script (not source's scripts/generator/llms-generator.py) |
| S-117 | llms-coverage | S-LG-03 | llms-coverage | Ported 2026-08-29; same generalization as S-116 |
| S-118 | llms-fidelity | S-LG-04 | llms-fidelity | Ported 2026-08-29; same generalization as S-116 |
| S-119 | llms-verify | S-LG-02 | llms-verify | Ported 2026-08-29 (SYNC-6); config.yaml sites.{type}.base_url replaces source's URL-mapping file; proven with a real local HTTP server, not mocked |
| S-120 | llms-stale | S-LG-05 | llms-stale | Ported 2026-08-29 (SYNC-7); manifest reuses config.yaml's existing reports_path, no new config key |
| S-121 | workflow-harden | S-115 | workflow-harden | Ported 2026-08-29 (SYNC-3, partial); dropped GitHub-only assumption + source's checkpoint/taskcard infrastructure, kept the CI-agnostic 8-dimension probe. The other 5 SYNC-3 skills (plan-health-watchdog, blind-spot-audit, forensic-heal-sprint, regression-classification, triage-verdict-gate) remain unported -- they depend on source's TaskcardStore/MISSION_AUTHORITY/refresh-run/content_eval-grading infrastructure, not just the taskcard store alone |

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
| S-23 | ground-check | Corrected 2026-08-29 (SYNC-8, see note below) -- foss evidence pipeline (new) |
| S-30 | truth-sync | Corrected 2026-08-29 (SYNC-8) -- foss evidence pipeline (new) |
| S-37 | corpus-scan | Corrected 2026-08-29 (SYNC-8) -- foss corpus system (new) |
| S-39 | discover-products | Corrected 2026-08-29 (SYNC-8) -- foss product discovery (new) |

> **2026-08-29 correction note:** these 4 rows were previously listed in the
> main Mapping Table above as "Same" (implying an identical aspose.org
> counterpart). `scripts/pipeline/commands/ops/backfill_source_anchors.py`
> (built for TASK_BACKLOG.md SYNC-8) found zero matches for any of these 4
> names anywhere in aspose.org's git-tracked files (`skills/` or
> `.claude/commands/`), confirmed via `git ls-files`. Cross-checked against
> `docs/parity/README.md`'s own "8 foss-exclusive innovations" claim, which
> already listed exactly these 4 (among others) as standalone-only -- the
> main Mapping Table simply never reflected that. This is a genuine,
> previously-undetected inconsistency between two of this repo's own
> tracking documents, not a new decision -- moved here to make them agree.

## Skills Unique to aspose.org (not ported to foss-launcher)

| aspose.org ID | Name | Notes |
|---|---|---|
| S-100 | blog-migrate | Blog migration workflow (7.65KB); lower relevance for standalone repo |

---

## Key Divergence Points

1. **S-43 post-diverge**: foss S-43 = `evidence-decide`; aspose S-43 = `gap-eval` — completely different
2. **S-52/S-53 post-diverge**: foss has `new-blog-post`/`new-kb-howto`; aspose has `translate-page`/`translate-batch`
3. **S-55 post-diverge**: aspose S-55 = `no-downgrade-guard` (internal); foss S-55 = `new-reference-page` (user-callable)
4. **S-56**: foss-new ID for `no-downgrade-guard` (ported from aspose S-55; assigned new ID to avoid collision)

## 2026-08-30 decision: `ht-translate`/`ht-translate-batch` NOT adopted (TASK_BACKLOG.md SYNC-10)

aspose.org's `ht-translate`/`ht-translate-batch` (S-HT-01/02) are thin wrappers around an
**external, separate repository** (`hugo-translator`), hardcoded to an absolute path on one
specific machine (`C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/`), with its own
venv and site-profile YAML configuration system (`docs.aspose.org`/`kb.aspose.org`/etc. as
literal profile IDs). This is not a generalized evolution of the translate system — it's a
different architecture entirely (external tool + site profiles) than aspose.org's own prior
internal translator backend.

`translate-page`/`translate-batch` (S-99/S-100, this repo) already use that prior
architecture — an internal `scripts/translator/` backend package with LLM/Ollama/M2M100
adapters, ported and working (37 Python files, per `docs/parity/README.md`'s original
2026-05-14 closure). Adopting `ht-translate` would mean either porting an entire unrelated
external repository (out of scope — it isn't even part of aspose.org), or abandoning this
repo's own working, already-ported backend for no demonstrated benefit.

**Decision: keep this repo's own `translate-page`/`translate-batch` as-is. Not revisiting
unless `hugo-translator` itself becomes something this repo needs to depend on for an
unrelated reason.**

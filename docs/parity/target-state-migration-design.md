# Target-State Migration Design - Phase 5

Date: 2026-05-13

## Phase Goal

Design how each missing, partial, weakened, undocumented, and unverified capability should be added or reconciled in `foss-launcher-skills-gitlab` without blindly copying `aspose.org` structure.

## Inputs

- `docs/parity/parity-matrix-phase4.json`
- `docs/parity/gap-report-phase4.md`
- Phase 2 and Phase 3 inventory evidence

## Outputs

- `docs/parity/target-state-migration-design.json`
- This design document

## Exit Criteria Status

Met. Every Phase 4 aspose.org capability row is mapped to one or more target workstreams and a target design decision. Standalone-only capabilities are explicitly preserved for non-regression review.

## Architecture Principles

- Preserve aspose.org practical behavior, not legacy layout.
- Keep standalone repo cleaner through adapters, registries, tests, and compatibility shims.
- Do not couple standalone execution to in-repo Hugo content; use external content-root and redirected output-root contracts.
- Add wrappers only when needed for compatibility or discoverability.
- Do not write to aspose.org/content during verification.

## Target Workstreams

### WS-01 - Capability Registration And Command Surface

Expose user-facing aliases for practical outcomes that users previously invoked indirectly.

### WS-02 - Dependency Port Or Adapter Layer

Port required helper scripts/modules when they are skill-system behavior; otherwise add compatibility wrappers to clean standalone modules or document external content-repo responsibility.

### WS-03 - Compatibility Shims For Reorganized Code

Keep cleaner standalone organization, but add thin legacy-path wrappers or update skill docs/registry to point to the new canonical path.

### WS-04 - Prompt-Orchestration Entrypoint Coverage

For prompt-only skills, define an explicit execution contract and add smoke tests or wrapper entrypoints for representative outcomes.

### WS-05 - External Content Repo Adapter

Replace website-local assumptions with a documented `CONTENT_REPO_PATH`/config adapter, clone-cache resolver, output-root override, and metrics dry-run policy.

### WS-06 - Behavioral Contract Reconciliation

Inspect the aspose.org and standalone skill contracts, preserve required user outcomes, keep standalone wording only where behavior is equivalent or better, and add regression tests.

### WS-07 - Verification-Only Classification

No migration until a dry-run or fixture-based verification proves parity or reveals a concrete defect.

## Status Counts From Phase 4

- `implemented but not verified`: 1
- `missing entirely`: 2
- `partial parity`: 79
- `unclear, requires investigation`: 2

## Capability Target Design Matrix

| Capability | Phase 4 Status | Gap Categories | Workstreams | Target Design |
|---|---|---|---|---|
| `backlog` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `batch-eval-fix` | partial parity | missing config support, missing dependency, naming/structure mismatch | WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `batch-reference` | partial parity | missing config support, missing dependency | WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `batch-remediate` | partial parity | missing config support, missing dependency, naming/structure mismatch | WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `category-fix` | partial parity | missing config support, missing dependency | WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `causal-backtrack` | partial parity | behavioral mismatch, missing dependency, missing helper utility, naming/structure mismatch | WS-06, WS-02, WS-04, WS-03 | Triage referenced dependencies: port real skill behavior, replace site-only paths with adapters, and add wrappers for legacy references where users rely on them. |
| `change-guard` | partial parity | missing config support, missing dependency, naming/structure mismatch | WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `change-sweep` | partial parity | missing dependency | WS-02 | Triage referenced dependencies: port real skill behavior, replace site-only paths with adapters, and add wrappers for legacy references where users rely on them. |
| `cleanroom-regen` | partial parity | missing dependency | WS-02 | Triage referenced dependencies: port real skill behavior, replace site-only paths with adapters, and add wrappers for legacy references where users rely on them. |
| `code-smoke` | partial parity | missing config support, missing dependency | WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `commit` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility, naming/structure mismatch | WS-06, WS-05, WS-02, WS-04, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `content-audit` | partial parity | missing config support, missing dependency, naming/structure mismatch | WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `content-check` | partial parity | missing config support, missing dependency | WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `content-enrich` | missing entirely | missing skill | WS-01 | Create a standalone `content-enrich` skill backed by the enrichment pipeline if the feature remains current; otherwise add a documented deprecation/redirect to the cleaner evidence or gap pipeline after operator approval. |
| `content-eval` | partial parity | missing config support, missing dependency | WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `coverage-reconcile` | partial parity | behavioral mismatch, missing dependency, missing helper utility | WS-06, WS-02, WS-04 | Triage referenced dependencies: port real skill behavior, replace site-only paths with adapters, and add wrappers for legacy references where users rely on them. |
| `cross-platform` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `delta-site-plan` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `diagnose-skill-failure` | partial parity | missing config support, missing dependency, naming/structure mismatch | WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `discovery-triage` | implemented but not verified | - | WS-07 | Keep current implementation; add dry-run and registry/discoverability verification before claiming parity. |
| `embed-knowledge` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `eval-page` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `evidence-cite` | unclear, requires investigation | naming/structure mismatch | WS-03 | Keep the cleaner standalone path and add compatibility mapping or update all references to the canonical standalone location. |
| `evidence-enhance` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `evidence-repair` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `family-sync` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `faq-generate` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `gap-apply` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `gap-eval` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `gap-plan` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `gap-report` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `getting-started` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `heal-batch` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `heal-page` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility, naming/structure mismatch | WS-06, WS-05, WS-02, WS-04, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `knowledge-bootstrap` | partial parity | missing config support, missing dependency | WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `knowledge-coverage-audit` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `knowledge-diff` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `knowledge-enrich` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `knowledge-update` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `launch-product` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `launch-rollback` | partial parity | behavioral mismatch, missing dependency | WS-06, WS-02 | Triage referenced dependencies: port real skill behavior, replace site-only paths with adapters, and add wrappers for legacy references where users rely on them. |
| `link-validate` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `locale-patch` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `manual-edit` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-blog-post` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-docs-index` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-docs-page` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-kb-faq` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-kb-howto` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-kb-index` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-products-page` | partial parity | missing config support, missing dependency, naming/structure mismatch | WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-reference-index` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `new-reference-page` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `no-downgrade-guard` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `page-draft` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `page-enhance` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility, naming/structure mismatch | WS-06, WS-05, WS-02, WS-04, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `page-plan` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `page-retire` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `page-update` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility, naming/structure mismatch | WS-06, WS-05, WS-02, WS-04, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `path-guard` | partial parity | missing config support, missing dependency | WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `plan-normalize` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `project-phase-store` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `publish-readiness-review` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility, naming/structure mismatch | WS-06, WS-05, WS-02, WS-04, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `refresh-product` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `refresh-product-page` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `register-human-content` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `repo-patrol` | partial parity | missing dependency | WS-02 | Triage referenced dependencies: port real skill behavior, replace site-only paths with adapters, and add wrappers for legacy references where users rely on them. |
| `repo-scout` | partial parity | missing config support, missing dependency, naming/structure mismatch | WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `rubric-align` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `section-enhance` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `seo-review` | missing entirely | missing skill | WS-01 | Create a standalone governance-only/Claude utility skill only if SEO review is still required; keep it separate from evidence-grounded content generation and mark it non-content-writing by default. |
| `session-start` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `site-plan` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `stale-detect` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `system-heal` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `translate` | partial parity | hidden feature not surfaced cleanly, missing registration | WS-01 | Add a `/translate` compatibility dispatcher that routes to `translate-page` or `translate-batch` without duplicating translation logic. |
| `translate-batch` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `translate-page` | partial parity | behavioral mismatch, missing config support, missing dependency | WS-06, WS-05, WS-02 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `triage-confirm` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `truth-audit` | unclear, requires investigation | missing config support | WS-05 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `truth-audit-content` | partial parity | behavioral mismatch, missing config support, missing dependency, missing helper utility | WS-06, WS-05, WS-02, WS-04 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |
| `truth-index` | partial parity | behavioral mismatch | WS-06 | Run contract reconciliation against the aspose.org skill, then update standalone docs/scripts/tests to preserve practical behavior with cleaner structure. |
| `truth-merge` | partial parity | behavioral mismatch | WS-06 | Run contract reconciliation against the aspose.org skill, then update standalone docs/scripts/tests to preserve practical behavior with cleaner structure. |
| `update-registry` | partial parity | behavioral mismatch, missing config support, missing dependency, naming/structure mismatch | WS-06, WS-05, WS-02, WS-03 | Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content. |

## Standalone-Only Improvements To Preserve

- `corpus-scan`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.
- `discover-products`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.
- `evidence-decide`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.
- `evidence-materialize`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.
- `evidence-verify`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.
- `ground-check`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.
- `mental-model`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.
- `truth-sync`: Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.

## Migration Quality Rules

- Port behavior into clean standalone modules before adding compatibility wrappers.
- Use wrappers for legacy path compatibility only when a skill, doc, or user workflow still references that path.
- Treat `CONTENT_REPO_PATH`, output-root overrides, clone-cache resolution, and metrics dry-run behavior as shared adapter contracts.
- Any content-writing workflow must have dry-run or redirected-output verification before it is marked parity-proven.
- Website-only Hugo/theme/layout concerns should be represented as external-content-repo contracts, not copied as hard standalone dependencies.

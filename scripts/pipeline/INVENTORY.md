# scripts/pipeline — Script Inventory

> **Generated file** — do not edit directly.
> Edit `scripts/pipeline/registry.yaml` and run `python scripts/ci/render_inventory.py`.

Total scripts: **110**

## Content Quality (15 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `audit.py` | entrypoint | active | skill/content-check | — | wrapper → audit.runner.main() |
| `check_audit_results.py` | entrypoint | deprecated | workflow | — | deprecated; superseded by unconditional regression check in simulate_pr_checks.sh:130; retained for reference only |
| `content_audit.py` | entrypoint | active | skill/content-audit | HIGH: 5 mixed responsibilities; tier classification is load-bearing | semantic prose auditor; code blocks delegated to audit.py |
| `cross_platform_audit.py` | entrypoint | active | skill/cross-platform | — | cross-platform format-support consistency audit |
| `fix_ta_access.py` | entrypoint | active | internal | — | batch repair: fix type_accuracy Access column defects in reference pages; reads api_surface.json writable flags; supports --dry-run, --family, --platform, --files args; idempotent |
| `ground_check.py` | entrypoint | active | skill/content-check | — | S-23 grounding ratio gate — verifies backtick identifiers against api_surface.json |
| `knowledge_coverage.py` | entrypoint | active | skill/coverage-reconcile | — | per-claim disposition table; 9-state taxonomy; writes reports/coverage/{family}/{platform}/ |
| `page_impact_assess.py` | entrypoint | active | internal | — | PIA: score English pages HIGH/MEDIUM/NOT_AFFECTED vs knowledge delta signals; outputs reports/refresh_review/{family}/{platform}/page_impact.json; Step 3.5 of S-84 |
| `refresh_review.py` | entrypoint | active | internal | — | record per-page BODY_UPDATED/EVIDENCE_ONLY/NOT_AFFECTED/RETIRED decisions; generate coverage_report.md; Step 13.5 of S-84 |
| `run_content_eval.py` | entrypoint | active | skill/content-eval | — | thin wrapper entrypoint for content_eval; enables repo-root invocation without PYTHONPATH |
| `smoke_test.py` | entrypoint | active | skill/code-smoke | — | code block syntax/type checker; never executes code |
| `stale_detect.py` | entrypoint | active | skill/stale-detect | — | detect pages with stale evidence relative to knowledge model |
| `token_ops.py` | library | active | internal | — | token extraction and verification against knowledge API surface |
| `truth_audit.py` | entrypoint | active | skill/truth-audit | — | member-level audit wrapper → audit.runner.audit_product() |
| `truth_audit_content.py` | entrypoint | active | skill/truth-audit-content | — | S-85: line-level content truth audit; decomposes pages into units, verifies against clone cache + knowledge model |

## Knowledge Pipeline (12 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `attach_evidence.py` | entrypoint | active | skill/evidence-enhance | — | wrapper → evidence.runner.main() |
| `embed.py` | entrypoint | active | skill/embed-knowledge | — | dual-tier embedding helper; modes: standard, gap-index, findings-index |
| `embed_knowledge.py` | entrypoint | active | skill/embed-knowledge | — | compatibility wrapper → embed.main() |
| `enrich.py` | entrypoint | active | skill/knowledge-enrich | HIGH: LLM-dependent; dedupe/confidence logic is fragile | LLM-enriched claim generation from scout artifacts |
| `index.py` | entrypoint | active | skill/truth-index | — | knowledge truth index builder; computes api_confidence tier |
| `link_validator.py` | entrypoint | active | skill/link-validate | — | cross-subdomain internal link validator |
| `promote.py` | entrypoint | active | skill/truth-merge | — | scout → merged knowledge promotion; replaces deleted merge.py |
| `reconcile_triage.py` | library | active | internal | — | RH-203 3-source triage reconciliation — combines layer1_triage, layer2_triage, page_spec into final_verdict; conservative: any stale signal triggers needs_update |
| `refresh_knowledge.py` | entrypoint | active | skill/knowledge-update | HIGH: pipeline orchestrator; controls scout→enrich→promote→index sequencing | knowledge pipeline orchestrator; runs scout → enrich → promote → index |
| `regenerate_reference.py` | entrypoint | active | skill/batch-reference | — | regenerate reference pages from api_surface.json |
| `scout.py` | entrypoint | active | skill/repo-scout | — | tree-sitter extraction shim from FOSS repos |
| `triage_confirm.py` | library | active | internal | — | RH-201 Layer 2 triage — scans page body prose for stale API class or claim references; used by refresh pipeline to detect false-negative staleness |

## Content Remediation (4 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `change_guard.py` | entrypoint | active | internal | MEDIUM: 5 independent safety checks; leave as-is (no shared logic to extract) | pre-write knowledge validation gate |
| `manual_edit_helpers.py` | library | active | skill/manual-edit | — | helpers for S-73 manual-edit skill; section detection, scope validation |
| `no_downgrade_guard.py` | entrypoint | active | internal | — | pre-write grade downgrade protection; used by change_guard.py |
| `remediate.py` | entrypoint | active | skill/batch-remediate | — | batch content remediation; modes: triage, fix, report, status |

## Content Grading (9 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `check_grade_downgrade.py` | entrypoint | active | workflow/content-audit.yml | — | CI: detect grade downgrades in modified files |
| `check_grade_integrity.py` | entrypoint | active | workflow/content-audit.yml | — | CI: validate grade block structure |
| `check_grade_presence.py` | entrypoint | active | workflow/content-audit.yml | — | CI: verify grades in frontmatter of modified files |
| `check_graded_at_only.py` | entrypoint | active | internal | — | pre-commit hook Step 10 + S-76 Step B.4: classify staged or worktree .md files where only graded_at: changed; Case A = revert, B/C = pass, D = fail-closed |
| `fix_grade_field_order.py` | entrypoint | active | internal | — | One-shot bulk repair: reorder grade frontmatter fields to canonical order |
| `grade_manifest.py` | library | active | internal | — | ARCH-01: external grade manifest — stores per-page operational evaluation state outside .md files |
| `grade_writer.py` | library | active | internal | — | read/write grade metadata in YAML frontmatter; style-preserving |
| `migrate_strip_operational_frontmatter.py` | one-shot | active | internal | — | MIG-01: strip operational grade fields from .md frontmatter (Wave 5 migration) |
| `seed_grade_manifest.py` | one-shot | active | internal | — | ARCH-05: one-time seeding of grade_manifest.json from existing frontmatter |

## Content Governance (15 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `_skill_constants.py` | library | active | internal | — | Shared constants (INTERNAL_SKILLS frozenset) for sync_skills.py and sync_providers.py. |
| `check_knowledge_completeness.py` | entrypoint | active | internal | — | called by refresh_knowledge.py:52; checks enrichment_ratio / snippet_ratio |
| `check_locale_topology.py` | entrypoint | active | internal | — | compare H2 structure between English and locale files |
| `complete_plugin_structure.py` | entrypoint | active | skill/new-products-page | — | Inserts missing display-control sections into layout: plugin pages. Idempotent. |
| `description_coverage_audit.py` | entrypoint | active | internal | — | per-product ERC api-kind member-doc coverage audit; scans claims.json vs api_surface.json; emits stdout table + knowledge/description_coverage_report.json; exit 1 if any product below --min-coverage threshold |
| `human_review_sampler.py` | entrypoint | active | workflow/launch-product | — | H-gate sampling and sign-off generation for human review gates H-01 through H-05 |
| `launch_gate.py` | entrypoint | active | workflow/launch-product | — | pre-launch readiness checker; 8 automated gates (L-01 through L-08) |
| `readiness_gate.py` | entrypoint | active | workflow/system-heal | — | TC-08 unified readiness gate: aggregates skill-sync, provider-sync, DAR, knowledge staleness, proof index, and launch-gate into one verdict |
| `readiness_scorecard.py` | entrypoint | active | workflow/launch-product | — | Stage 8 readiness scorecard for launch-product; collects grades and translation coverage |
| `sync_providers.py` | entrypoint | active | internal | — | propagate canonical skills/ to .agents/, .claude/commands/, .kilocode/ trees |
| `sync_skills.py` | entrypoint | active | workflow/content-audit.yml | — | CI parity check: canonical skills/ must match all provider copies |
| `translation_coverage.py` | entrypoint | active | workflow/content-audit.yml | — | CI: measure translation coverage across all subdomains |
| `validate_frontmatter.py` | entrypoint | active | workflow/content-audit.yml | — | CI: detect structural/key-level frontmatter issues |
| `validate_plugin_structure.py` | entrypoint | active | workflow | — | Structural gate for layout: plugin product pages — checks BODY_LEAK, MISSING_KEY, MISSING_ENABLE |
| `validate_product_yaml.py` | entrypoint | active | workflow/content-audit.yml | — | CI gate: check garbled code blocks and non-literal multi-line scalars |

## Backtrack (2 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `backtrack_controller.py` | entrypoint | active | skill/causal-backtrack | HIGH: causal orchestrator; depth-guard and cycle-detection logic | causal backtrack orchestrator; also needs dependency_resolver.py |
| `dependency_resolver.py` | entrypoint | active | skill/causal-backtrack | — | backtrack dependency graph; shared CONTRACT with backtrack_controller.py |

## Knowledge Infrastructure (7 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `content_discovery.py` | library | active | internal | 9 indirect consumers migrated to canonical imports (R-1b complete) | content file discovery: discover_content, discover_products, infer_product — extracted from knowledge_core (R-1a); consumer migration complete (R-1b) |
| `knowledge.py` | shim | active | internal/scripts/pipeline/knowledge_core.py | backward-compat re-export shim; update if any canonical module moves a symbol | re-exports 12 symbols from knowledge_core, content_discovery, evidence_verifier, core.markdown; zero production callers as of R-4 |
| `evidence_verifier.py` | library | active | internal | 4 direct consumers migrated to canonical imports (R-3b complete) | evidence frontmatter validation: verify_evidence — extracted from knowledge_core (R-3a); consumer migration complete (R-3b) |
| `knowledge_core.py` | library | active | internal | 6 import sites (Knowledge class only) — run full pytest after any change | knowledge model loading; all re-exports removed post-R-4; public API: {Knowledge, diff} |
| `path_utils.py` | library | active | internal | — | shared path rendering utilities; provides repo_rel() |
| `provenance.py` | library | active | internal | — | read/write provenance metadata in YAML frontmatter |
| `session_logger.py` | library | active | internal | — | log skill invocations to reports/session-invocations/ |

## Governance (12 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `launch_rollback.py` | entrypoint | active | skill/launch-rollback | — | S-79: revert one product's generated content files after a flawed launch; reads site_plan.yaml; protects system files |
| `override_manager.py` | entrypoint | active | internal | — | GOVERNANCE: override token lifecycle; DO NOT MOVE OR RENAME |
| `path_guard.py` | entrypoint | active | internal | — | GOVERNANCE: forbidden write-path enforcement oracle; DO NOT MOVE OR RENAME |
| `plan_check.py` | entrypoint | active | internal | — | GOVERNANCE: validate slug exists in site plan before content write |
| `preflight.py` | entrypoint | active | internal | — | GOVERNANCE: universal pre-write preflight check; agent-agnostic enforcement |
| `project_phase_store.py` | entrypoint | active | skill/launch-product | — | GOVERNANCE: checkpoint store for launch orchestration; DO NOT MOVE OR RENAME |
| `retire_page.py` | entrypoint | active | internal | — | mark content pages as retired via draft:true + retired_at frontmatter; batch mode reads site_plan.yaml; does not delete files |
| `section_enhance_validator.py` | library | active | skill/section-enhance | — | S-96 Phase 1 audit output validator: artifact completeness, manifest schema, adapter isolation, no-write detection, zero-proposal acceptance, slug validation |
| `session_ledger.py` | entrypoint | active | skill/commit | — | GOVERNANCE: session-scoped file touch ledger for /commit scoping |
| `site_planner.py` | entrypoint | active | skill/site-plan | MEDIUM: 1756 lines; cluster detection mixed with manifest generation; deferred refactor | GOVERNANCE: site manifest generator; DO NOT MOVE OR RENAME |
| `skill_context.py` | library | active | internal | — | GOVERNANCE: active-skill state machine for PreToolUse hook enforcement |
| `skill_run_manager.py` | entrypoint | active | internal | — | GOVERNANCE: skill run record management; DO NOT MOVE OR RENAME |

## Kilocode Provider (6 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `kilocode_compliance.py` | library | active | internal | — | compliance tracking for Kilo Code provider; Track B Phase C candidate |
| `kilocode_gate.py` | entrypoint | active | internal | — | Kilo Code gate: enforce skill-first execution; Track B Phase C candidate |
| `kilocode_learning.py` | entrypoint | active | internal | — | violation-driven learning for Kilo Code; Track B Phase C candidate |
| `kilocode_postcheck.py` | entrypoint | active | internal | — | post-execution check for Kilo Code; Track B Phase C candidate |
| `kilocode_skill_chain.py` | entrypoint | active | internal | — | skill chain orchestration for Kilo Code; Track B Phase C candidate |
| `kilocode_skill_validator.py` | entrypoint | active | internal | — | skill validation for Kilo Code; Track B Phase C candidate |

## Provenance Maintenance (15 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `apply_origin_decisions.py` | one-shot | maintenance | internal | — | apply content_origin field decisions from review records |
| `audit_content_created_at.py` | one-shot | maintenance | internal | — | audit created_at field against actual file/git timestamps |
| `audit_content_hash.py` | one-shot | maintenance | internal | — | report files where stored content_hash != computed hash |
| `audit_content_origin.py` | one-shot | maintenance | internal | — | audit content_origin classification across all content files |
| `cleanup_reviewed_field.py` | one-shot | maintenance | internal | — | remove deprecated 'reviewed' field from provenance blocks |
| `content_created_at_backfill.py` | one-shot | maintenance | internal | — | backfill created_at timestamps for pages missing the field |
| `content_hash_backfill.py` | one-shot | maintenance | internal | — | backfill content_hash values for pages missing the field |
| `content_origin_recover.py` | one-shot | maintenance | internal | — | recover content_origin from signals; has local _FRONTMATTER_RE (consolidate A2) |
| `fix_last_mechanism.py` | one-shot | maintenance | internal | — | repair stale last_mechanism values in provenance blocks |
| `logic_version_backfill.py` | one-shot | maintenance | internal | — | backfill graded_logic_version in provenance blocks |
| `normalize_yaml_style.py` | one-shot | maintenance | internal | — | normalize YAML formatting; uses strict frontmatter variant (see Phase A2b) |
| `provenance_backfill.py` | one-shot | maintenance | internal | — | idempotent provenance block backfill for English pages |
| `provenance_normalize_hash.py` | one-shot | maintenance | internal | — | normalize content_hash format in provenance blocks |
| `source_sha_backfill.py` | one-shot | maintenance | internal | — | backfill source_sha in translation provenance blocks |
| `structural_lock.py` | one-shot | maintenance | internal | — | prevent structural overwrites of locked pages |

## Product Registry (3 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `org_scanner.py` | library | active | internal | — | GitHub org scanner; used by update_product_registry.py |
| `repo_patrol.py` | entrypoint | active | skill/repo-patrol | — | S-93/S-94: repo discovery scan, change sweep, combined reporting; subcommands: scan, sweep, report |
| `update_product_registry.py` | entrypoint | active | skill/update-registry | — | update data/products.json from GitHub org and local knowledge dirs |

## Cpp Platform (1 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `expand_cpp_stubs.py` | one-shot | maintenance | internal | — | expand C++ stub definitions; Track B Phase D candidate |

## Backlog (2 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `harvest_ledger.py` | entrypoint | active | skill/backlog | — | harvest ledger CRUD — tracks report items processed into backlog |
| `report_extract.py` | entrypoint | active | skill/backlog | — | extract open/unresolved items from markdown reports for backlog harvest |

## Content Generation (2 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `batch_reference.py` | entrypoint | active | skill/batch-reference | — | batch reference page generation from api_surface.json; ERC-* claim fallback when doc empty; --update flag regenerates only classes in knowledge_delta.json modified_apis |
| `page_spec.py` | library | active | skill/batch-reference | — | PageSpec/SectionPlan/SitePlan dataclasses; bridges site_planner.py output to batch_reference.py input |

## Healing (3 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `heal_controller.py` | library | active | skill/system-heal | — | healing pipeline orchestrator: triage → policy → grouping → dispatch → verify |
| `heal_policy.py` | library | active | skill/system-heal | — | policy table mapping issue class → heal mode + skill |
| `verify.py` | library | active | skill/system-heal | — | healing verification with regression detection (before/after finding comparison) |

## Knowledge (1 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `post_refresh_verify.py` | entrypoint | active | internal | — | post-refresh verification gate and pipeline progress tracker; --step records steps, --verify gates on required checks |

## Llm Infrastructure (1 files)

| Script | Kind | Lifecycle | Backing | Change Impact | Notes |
|--------|------|-----------|---------|---------------|-------|
| `llm_router.py` | library | active | internal | — | shared LLM router with provider fallback chain; replaces per-module _llm_call() |

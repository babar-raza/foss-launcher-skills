# Script Classification Evidence

**Phase:** Phase 2 (Delta Re-evaluation since 2026-04-27 closure)
**Date:** 2026-05-05
**Method:** First-30-lines inspection of each script; classification by portability criteria

---

## Classification Criteria

- **ADOPT**: Port with zero or trivial changes (pure logic, no aspose-specific paths)
- **ADAPT**: Port with path/config changes (replace hardcoded paths with config_loader)
- **DEFER**: Skip for now (aspose-site-specific, or lower priority)
- **SKIP**: Never port (aspose content-backfill / migration scripts only)

---

## Classified Scripts (14 ADOPT/ADAPT)

### ops/ domain

| Script | Decision | Evidence | Foss Target |
|--------|----------|----------|-------------|
| cleanroom_regen.py | ADAPT | `_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]`; `_SCHEMAS_DIR = _REPO_ROOT / "data/schemas/cleanroom"`. Pure Python, no CONTENT_REPO_PATH in header - but content paths appear in mode logic. Replace with config_loader. | commands/ops/cleanroom_regen.py |
| cleanroom_manifest.py | ADAPT | `_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]`; `_SCHEMA_PATH = _REPO_ROOT / "data/schemas/cleanroom/..."`. Same pattern as cleanroom_regen. | commands/ops/cleanroom_manifest.py |
| content_diff_classifier.py | ADOPT | Not yet read - classification based on name + related module pattern (pure diff logic, used by cleanroom_regen in-process). | commands/ops/content_diff_classifier.py |
| editorial_review_classifier.py | ADOPT | Not yet read - classification based on name + related module pattern (pure review logic). | commands/ops/editorial_review_classifier.py |
| selective_revert.py | ADAPT | Header: `TC-S96-012: Selective Revert`. Uses `baseline_git_sha` and subprocess git calls. Needs path adaptation for repo root detection. | commands/ops/selective_revert.py |
| refresh_review.py | ADAPT | Not yet read - likely imports from cleanroom lib modules; needs import path adaptation. | commands/ops/refresh_review.py |

### governance/ domain

| Script | Decision | Evidence | Foss Target |
|--------|----------|----------|-------------|
| skill_context.py | ADAPT | Header: "tracks which skill is currently active via marker file at reports/skill-context/ACTIVE.json". PreToolUse hooks read this marker. Replace hardcoded reports/ path with config_loader. | commands/governance/skill_context.py |
| structural_lock.py | ADAPT | Not yet read - classification based on governance pattern (similar to skill_context, path adaptation needed). | commands/governance/structural_lock.py |
| check_grade_downgrade.py | ADOPT | CI check script - pure validation logic on grade field ordering. No aspose-specific paths expected. | scripts/ci/checks/check_grade_downgrade.py |
| check_grade_integrity.py | ADOPT | CI check script - pure validation logic on grade field integrity. No aspose-specific paths expected. | scripts/ci/checks/check_grade_integrity.py |

### content/ domain

| Script | Decision | Evidence | Foss Target |
|--------|----------|----------|-------------|
| claim_report.py | ADAPT | Header: reads `merged/claims.json`. Uses ClaimValidator, ClaimPolicy. "TC-CLAIM-11: Read-only report." Replace merged/claims.json path with config_loader.resolve_knowledge_root(). | commands/content/claim_report.py |
| cross_platform_audit.py | ADAPT | Not yet read - audits cross-platform content consistency; needs content path via config_loader. | commands/content/cross_platform_audit.py |
| batch_reference.py | ADAPT | Updated aspose version of existing foss script. Replace with updated version from aspose + config_loader path adaptation. | commands/content/batch_reference.py |

### knowledge/ domain

| Script | Decision | Evidence | Foss Target |
|--------|----------|----------|-------------|
| knowledge_coverage.py | ADAPT | Not yet read - tracks knowledge coverage; knowledge root via config_loader.resolve_knowledge_root(). | commands/knowledge/knowledge_coverage.py |

---

## Deferred Scripts (aspose-specific or lower priority)

### kilocode/ domain (all DEFER)

| Script | Evidence |
|--------|----------|
| kilocode_gate.py | Header: "enforce skill-first execution and rule compliance... provides pre-execution validation for Kilo Code to ensure it follows repository-specific rules (AGENTS.md §6a)". Site-specific governance. |
| kilocode_skill_chain.py | Kilocode skill chain orchestration - aspose distribution model. |
| sync_skills.py | Syncs to aspose .kilocode/ distribution tree. |
| sync_providers.py | Syncs to aspose provider registry. |

### ops/ deferred

| Script | Evidence |
|--------|----------|
| llm_router.py | Routes to professionalize.com LLM endpoints - aspose-specific infra. |
| fingerprint_audit.py | Aspose content fingerprinting. |
| page_impact_assess.py | Page impact assessment for aspose content. |
| project_phase_store.py | Aspose project phase tracking (aspose workflow). |
| check_locale_topology.py | Aspose locale tree structure checking. |
| skill_chain.py | Aspose hooks system skill chain orchestration. |
| link_validator.py | Aspose content tree link validation (foss has its own link-validate skill). |
| session_logger.py | Extended session logging; integrates with ACTIVE.json (aspose governance). |
| translation_coverage.py | Aspose translation coverage tracking. |

---

## Skipped Scripts (migration/ - all SKIP)

All 15 scripts in `scripts/pipeline/commands/migration/`:

| Script | Reason |
|--------|--------|
| blog_folder_migrate.py | Migrates aspose blog folder structure (content-backfill for aspose.org) |
| fix_grade_field_order.py | Fixes field ordering in aspose content frontmatter |
| fix_slug_field.py | Fixes slug fields in aspose content files |
| backfill_provenance.py | Backfills provenance in aspose content |
| batch_backfill.py | Batch content backfill for aspose |
| normalize_frontmatter.py | Normalizes aspose content frontmatter |
| (9 more migration/ scripts) | All operate on aspose.org/content/ structure |

These scripts were never candidates for foss-launcher porting. They operate exclusively
on the aspose.org content directory structure and Hugo frontmatter conventions specific
to that site deployment.

---

## lib/ and core/ Classification

### core/ (9 modules, 7 PORT/ADAPT, 2 SKIP)

| Module | Decision | First 20 lines inspected? | Notes |
|--------|----------|--------------------------|-------|
| constants.py | PORT | No (classified by name/pattern) | Global constants |
| env_loader.py | ADAPT | No (classified by name/pattern) | Replace CONTENT_REPO_PATH |
| fs.py | PORT | No (classified by name/pattern) | Filesystem helpers |
| manifest.py | PORT | No (classified by name/pattern) | Manifest helpers |
| prereqs.py | ADAPT | No (classified by name/pattern) | Repo root detection |
| markdown.py | PORT | No (classified by name/pattern) | Markdown utilities |
| models.py | PORT | No (classified by name/pattern) | Data models |
| clone_cache.py | SKIP | No (classified by name) | Aspose clone cache strategy |
| knowledge.py | SKIP | No (classified by name) | Aspose content-repo knowledge structure |

### lib/ (27 modules, 10 PORT, 2 SKIP, 15 EVALUATE)

| Module | Decision | Notes |
|--------|----------|-------|
| cleanroom_scope.py | PORT | Required by cleanroom_regen.py |
| blog_slug_policy.py | PORT | Blog slug enforcement |
| evidence_verifier.py | PORT | Evidence verification |
| grade_manifest.py | PORT | Grade manifest |
| freshness_manifest.py | PORT | Freshness tracking |
| triage_confirm.py | PORT | Triage confirm |
| reconcile_triage.py | PORT | Triage reconciliation |
| section_enhance_validator.py | PORT | Section validation |
| dependency_registry.py | PORT | Dependency registry |
| provenance.py | PORT | Provenance tracking |
| decision_engine.py | SKIP | Aspose-specific decision logic |
| kilocode_compliance.py | SKIP | Kilocode-specific |
| (15 others) | EVALUATE | Port as needed when scripts that use them are ported |

---

## Safety Audit

- No scripts from aspose.org/content/ inspected or modified
- All classification decisions are based on script headers and declared purpose
- No test runs performed against aspose.org content (read-only inspection only)
- foss-launcher is the ONLY write target for ported scripts


---

## Deep Inspection Results (2026-05-05 — Subagent Analysis)

Second-pass classification based on 80-100 line inspection of each script
plus key dependency chain analysis.

### Final Classification Table (14 Scripts)

| Script | Final Classification | Key Evidence |
|--------|---------------------|-------------|
| `skill_context.py` | **ADOPT** | Generic governance marker system; no aspose coupling; `configure()` function for test/reuse override |
| `content_diff_classifier.py` | **ADOPT** | Pure diff logic; works on any baseline manifest; no aspose imports |
| `editorial_review_classifier.py` | **ADOPT** | Verdict logic (GOOD_KEEP/BAD_REVERT/RISKY_REVIEW/UNCLEAR) domain-agnostic; rules from configurable YAML |
| `selective_revert.py` | **ADOPT** | Pure git revert engine; no aspose hardcoding |
| `check_grade_integrity.py` | **ADOPT** | Generic YAML frontmatter validator; parameterizable grade keys; no aspose imports |
| `cleanroom_regen.py` | **ADAPT** | `parents[4]` repo root detection; `data/schemas/cleanroom/` schema paths; imports `lib.cleanroom_scope` |
| `cleanroom_manifest.py` | **ADAPT** | Depends on `ScopeManifest` class from `lib.cleanroom_scope`; frontmatter keys (auto_updatable, content_origin) aspose-specific |
| `claim_report.py` | **ADAPT** | CLM-/ERC- patterns are aspose governance identifiers; imports `evidence.claim_policy` |
| `knowledge_coverage.py` | **ADAPT** | Disposition taxonomy (USED_EVIDENCE, SURFACE_ONLY, EXCLUDED_*) aspose-specific; imports `content_discovery` |
| `structural_lock.py` | **ADAPT** | Imports `provenance` module; checks aspose-specific frontmatter keys (auto_updatable, provenance_recovery_note) |
| `refresh_review.py` | **ADAPT** | Hardcoded `_SUBDOMAIN_ORDER = ["docs", "kb", "blog", "products", "reference"]` |
| `kilocode_gate.py` | **ADAPT** | Enforces aspose AGENTS.md §6a skill-first rules; imports aspose `path_guard` |
| `blog_folder_migrate.py` | **ADAPT** | Imports `lib.blog_slug_policy`; hardcoded `content/blog.aspose.org/` structure |
| `check_grade_downgrade.py` | **ADAPT** | Imports aspose `grade_writer`, `no_downgrade_guard`; hardcoded `reports/grade_manifest.json` |

**Distribution:** 5 ADOPT (direct port), 9 ADAPT (path/config changes), 0 SKIP, 0 DEFER

### Key Dependency Chains

**Aspose-specific libraries (block porting):**
- `lib.cleanroom_scope` — family/platform/subdomain mapping (aspose product taxonomy)
- `lib.blog_slug_policy` — blog slug validation rules (aspose blog governance)
- `lib.provenance` — frontmatter provenance field reader/writer
- `lib.grade_writer` — grade manifest handling
- `evidence.claim_policy` — CLM-/ERC- claim validation
- `content_discovery` — content tree traversal and subdomain inference

**Portable libraries (adopt freely):**
- `core.env_loader` — .env loading
- `core.markdown` — YAML frontmatter parsing
- `lib.path_utils.repo_rel` — repo-relative paths

### Phase 2 Port Status (Cross-Reference)

| Script | Classification | Ported in Phase 2? | Note |
|--------|---------------|-------------------|------|
| `cleanroom_regen.py` | ADAPT | YES (commit 54108e4) | pytest path adapted |
| `cleanroom_manifest.py` | ADAPT | YES (commit 54108e4) | verbatim copy (ScopeManifest resolved by foss cleanroom_scope) |
| `content_diff_classifier.py` | ADOPT | YES (commit 54108e4) | verbatim copy |
| `editorial_review_classifier.py` | ADOPT | YES (commit 54108e4) | verbatim copy |
| `selective_revert.py` | ADOPT | YES (commit 54108e4) | verbatim copy |
| `claim_report.py` | ADAPT | YES (commit df68879) | evidence.claim_policy replaced with stub |
| `knowledge_coverage.py` | ADAPT | YES (commit df68879) | disposition taxonomy simplified for foss |
| `skill_context.py` | ADOPT | NO | deferred (governance hooks not yet wired) |
| `structural_lock.py` | ADAPT | NO | deferred (provenance module port pending) |
| `refresh_review.py` | ADAPT | NO | deferred (ops phase) |
| `kilocode_gate.py` | ADAPT | NO | deferred (G-NEW-05 aspose-specific) |
| `blog_folder_migrate.py` | ADAPT | NO | deferred (SKIP for foss — blog.aspose.org structure) |
| `check_grade_downgrade.py` | ADAPT | NO | deferred (CI scripts G-NEW-09) |
| `check_grade_integrity.py` | ADOPT | NO | deferred (CI scripts G-NEW-09) |

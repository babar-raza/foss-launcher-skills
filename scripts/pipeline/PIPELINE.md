# pipeline/ — Entry Points vs. Library Modules

`scripts/pipeline/` is the core content pipeline. Its root directory contains **69 Python files** at a flat level (tracked in `registry.yaml`; rendered to `INVENTORY.md`). This document classifies every file so maintainers know at a glance what to call vs. what to import.

## PYTHONPATH note

CI and git hooks invoke pipeline scripts with `PYTHONPATH=scripts/pipeline` set. This lets scripts import each other by short name (e.g., `import knowledge_core`). Do **not** move files out of this directory without updating all import sites, the CI workflow (`.github/workflows/content-audit.yml`), and the git hook scripts.

## Sub-packages (internal, properly encapsulated)

These directories are Python packages with `__init__.py`. They are used as libraries by the entry-point scripts above. Do not call them directly from CLI unless they have their own entry point.

| Package | Role |
|---------|------|
| `core/` | Foundation: constants, models, filesystem, manifest, clone-cache, env-loader, knowledge shim |
| `audit/` | Audit engine: runner, link checker, snippet checker, report generator |
| `content_eval/` | Multi-dimensional content evaluation: evaluators, remediation fixers, reporters, cross-page checks |
| `evidence/` | Evidence block attachment: runner, section breakdown |
| `extraction/` | Claim extraction from FOSS source |
| `verification/` | API claim verification: extractor, verifier |
| `scout_enrichers/` | Tree-sitter doc parsers: XML doc, Javadoc, Doxygen |
| `reports/` | Report artifact storage |
| `tests/` | Pytest suite: conftest, fixtures, content_eval tests |

## Entry-point scripts — CALL THESE from CLI/CI/hooks/skills

These scripts have a `if __name__ == "__main__"` block. Invoke them directly.

### Tier 1 — Stable, hardcoded in CI / git hooks / skills / docs (do not rename/move)

| Script | Purpose | Key callers |
|--------|---------|-------------|
| `audit.py` | API accuracy audit; delegates to `audit/runner.py` | CI, pre-commit hook, 10+ skills, OPERATOR_GUIDE |
| `attach_evidence.py` | Evidence block generation; delegates to `evidence/runner.py` | Skills, OPERATOR_GUIDE |
| `change_guard.py` | Protect content from unsafe changes | change-guard skill |
| `check_grade_downgrade.py` | Block grade regressions (S-55 no-downgrade guard) | CI workflow |
| `check_grade_integrity.py` | Validate grade block structure | CI workflow |
| `check_grade_presence.py` | Require grade blocks on content pages | CI workflow |
| `content_audit.py` | Semantic content auditor (imports `knowledge_core`, `token_ops`) | content-audit skill |
| `cross_platform_audit.py` | Cross-platform consistency audit | cross-platform skill |
| `embed.py` | Standard knowledge embedding | embed-knowledge skill |
| `embed_knowledge.py` | Knowledge embedding (extended mode) | embed-knowledge skill |
| `enrich.py` | LLM knowledge enrichment | knowledge-enrich skill |
| `index.py` | Knowledge index generation | truth-index skill, `refresh_knowledge.py` |
| `link_validator.py` | Internal link validation | link-validate skill |
| `no_downgrade_guard.py` | Grade downgrade protection guard | no-downgrade-guard (internal skill) |
| `override_manager.py` | Forbidden-path override token lifecycle (`create` / `validate-for-path` / `consume`) | pre-commit hook, post-commit hook, CI |
| `path_guard.py` | Forbidden write path enforcement oracle | pre-commit hook, CLAUDE.md (protected) |
| `promote.py` | Knowledge promotion workflow | truth-merge skill, `refresh_knowledge.py` |
| `provenance_backfill.py` | Idempotent provenance backfill for English pages | RUNBOOK, CI |
| `refresh_knowledge.py` | Orchestrates scout → enrich → promote → index | knowledge-update, knowledge-diff skills, OPERATOR_GUIDE |
| `remediate.py` | Automatic content remediation | batch-remediate skill |
| `scout.py` | Tree-sitter extraction from FOSS repo | repo-scout skill, `refresh_knowledge.py` |
| `site_planner.py` | Pre-generation site manifest | site-plan skill |
| `skill_run_manager.py` | Skill run record management (`find-pending` / `validate` / `get-declared-skills`) | commit-msg hook |
| `smoke_test.py` | Quick pipeline validation checks | CI, diagnostics |
| `stale_detect.py` | Stale knowledge detection | stale-detect skill |
| `sync_skills.py` | Skill registry parity check | CI workflow |
| `translation_coverage.py` | Translation coverage reporting | CI workflow |
| `truth_audit.py` | Member-level API verification | truth-audit skill |
| `update_product_registry.py` | Product registry update | update-registry skill |
| `validate_frontmatter.py` | Frontmatter structure validation | CI workflow |
| `validate_product_yaml.py` | Product YAML schema validation | CI, validation workflows |
| `project_phase_store.py` | Store/retrieve project phase checkpoints (`set`/`get`) | launch-product skill |

### Tier 2 — Operator-invoked or internal utilities (callable, but lower blast radius)

| Script | Purpose |
|--------|---------|
| `check_knowledge_completeness.py` | Check for missing knowledge artifacts |
| `check_locale_topology.py` | Check locale directory topology consistency |
| `normalize_yaml_style.py` | Normalize YAML formatting in knowledge files |
| `plan_check.py` | Validate plan files |
| `regenerate_reference.py` | Regenerate reference pages from knowledge |
| `session_logger.py` | Session logging utilities |
| `sync_providers.py` | Provider registry synchronization |

### Dual-purpose (library + CLI)

| Script | Note |
|--------|------|
| `knowledge_core.py` | **Heavily imported library** (10+ importers) that also exposes a CLI mode via `main()`. Treat as a library; only use the CLI for diagnostics. Do not move without auditing all import sites. |

## Pure library modules — IMPORT THESE, do not invoke directly

These files have **no `__main__` block**. They are utility modules meant to be imported by entry-point scripts.

| Module | Exports / role |
|--------|---------------|
| `__init__.py` | Package marker (empty or minimal) |
| `grade_writer.py` | Grade block writing utilities |
| `org_scanner.py` | Org/repo scanning helpers |
| `path_utils.py` | `repo_rel()` and other path utilities |
| `provenance.py` | Provenance data model and helpers (used by `provenance_backfill.py` and `audit/`) |
| `token_ops.py` | Token extraction and verification utilities; imported by `knowledge_core.py` and `content_eval/` |

## New File Protocol

When adding a new `.py` file to `scripts/pipeline/`:

1. Determine `kind` and `lifecycle` from the registry schema in `registry.yaml`
2. Add an entry to `scripts/pipeline/registry.yaml`
3. Run `python scripts/ci/render_inventory.py` → regenerates `INVENTORY.md`
4. If `kind=entrypoint` and `cli_contract=stable`: add or update the skill CONTRACT tag
5. If `kind=entrypoint`: create `scripts/pipeline/tests/test_{name}.py`
6. If skills changed: run `sync_providers.py` in a **separate commit** scoped to those files
7. Run `python scripts/ci/check_pipeline_path_integrity.py` → must exit 0
8. Run `python scripts/ci/check_pipeline_registration.py` → must exit 0 (once Phase G is complete)

## Known technical debt

- **Partial migration**: `knowledge_core.py` exists at the pipeline root and `core/knowledge.py` is a re-export shim for it. The intent was to move `knowledge_core` into `core/`, but the migration stalled. Both files exist; do not create a third. The shim (`core/knowledge.py`) means code importing `from core.knowledge import ...` is forward-compatible.

- **Flat root size**: 69 files at one level is intentional for this codebase. A namespace sub-package refactor (`kilocode/`, `ops/`) was considered (Track B) and closed: the registry's `owner_domain` field already provides logical grouping, and moving CLI entrypoints into sub-packages adds shim complexity with no operational benefit. Do not reopen this unless there is a concrete correctness or testability argument.

- **Strict frontmatter variant** (resolved — Phase A2b, 2026-04-06): `normalize_yaml_style.py` and `validate_product_yaml.py` previously used a strict `\n---\s*\n` closing-fence pattern that silently skipped files ending with `---` at EOF. Both files now use `split_frontmatter()` / `extract_frontmatter_body()` from `core/markdown.py` (tolerant `(?:\n|$)`). Behavioral tests in `test_normalize_yaml_style.py` and `test_validate_product_yaml.py` document and prove the fix.

- **Test coverage**: All pipeline tests now live in `scripts/pipeline/tests/`. Run via `pytest scripts/pipeline/tests/ -q`.

## knowledge_core.py — Public API Census (R-0a, 2026-04-06)

This census documents every symbol currently exported by `knowledge_core.py`.
It is the gate for Phase R extractions — do not begin R-1 until this is committed.
See `test_knowledge_core_api_surface.py` for the machine-verifiable baseline.

| Symbol | Type | Line | External fan-in | Move target | Status |
|--------|------|------|----------------|-------------|--------|
| `Knowledge` | class | 64 | 14 (highest fan-in) | stays in `knowledge_core.py` | **never move** |
| `KNOWLEDGE_ROOT` | constant | 39 | 2 | `core/constants.py` (pending R-0c check) | candidate R-4 |
| `PLATFORM_MAP` | constant | 44 | 2 | `core/constants.py` | candidate R-4 |
| `PLATFORM_RMAP` | constant | 45 | 1 | `core/constants.py` | candidate R-4 |
| `SITE_PATHS` | constant | 48 | 1 | `core/constants.py` | candidate R-4 |
| `LOCALE_RE` | constant | 57 | 3 | `core/constants.py` | candidate R-4 |
| `discover_content` | function | 433 | 4 | `content_discovery.py` (R-1) | ready for R-1a |
| `discover_products` | function | 469 | 4 | `content_discovery.py` (R-1) | ready for R-1a |
| `infer_product` | function | 451 | 3 | `content_discovery.py` (R-1) | ready for R-1a |
| `parse_frontmatter` | function | 490 | 3 | remove; redirect to `core.markdown` | R-2 |
| `verify_evidence` | function | 502 | 3 | `evidence_verifier.py` (R-3) | ready for R-3a |
| `_FRONTMATTER_RE` | private re-import | 487 | 2 | remove alias; update `audit/links.py` | R-0b (deferred) |
| `diff` | function | 584 | 0 (tests only) | stays in `knowledge_core.py` | **never move** |

**Notes:**
- `_FRONTMATTER_RE` is itself a re-import: `from core.markdown import _FRONTMATTER_READER_RE as _FRONTMATTER_RE`. The alias should be removed once `audit/links.py` and `core/knowledge.py` import from `core.markdown` directly (R-0b, separate sprint).
- `parse_frontmatter` is a thin wrapper around `core.markdown._FRONTMATTER_RE` — essentially a duplicate. Direct consumers should use `core.markdown.parse_frontmatter` (R-2).
- Constants (`PLATFORM_MAP`, `PLATFORM_RMAP`) are intentionally empty dicts (API compatibility). Move only if R-0c circular import check passes.

**Import site count by file (non-test):**

| File | Symbols imported |
|------|----------------|
| `audit/__init__.py` | `Knowledge`, `discover_content`, `discover_products`, `infer_product`, `parse_frontmatter`, `verify_evidence` |
| `audit/links.py` | `_FRONTMATTER_RE` |
| `audit/runner.py` | `Knowledge`, `discover_content`, `discover_products`, `infer_product`, `parse_frontmatter`, `verify_evidence` |
| `change_guard.py` | `Knowledge`, `PLATFORM_MAP` |
| `check_grade_downgrade.py` | `LOCALE_RE` |
| `check_grade_presence.py` | `LOCALE_RE`, `discover_content`, `discover_products` |
| `content_audit.py` | `Knowledge`, `discover_content`, `discover_products`, `infer_product`, `PLATFORM_MAP` |
| `content_eval/cli.py` | `Knowledge`, `discover_content`, `discover_products` |
| `content_eval/evaluators/api_accuracy.py` | `Knowledge`, `verify_evidence` |
| `content_eval/loader.py` | `Knowledge`, `discover_content`, `discover_products`, `infer_product` |
| `core/knowledge.py` | `KNOWLEDGE_ROOT`, `PLATFORM_MAP`, `PLATFORM_RMAP`, `SITE_PATHS`, `LOCALE_RE`, `_FRONTMATTER_RE`, `Knowledge`, `discover_content`, `discover_products`, `infer_product`, `parse_frontmatter`, `verify_evidence` |
| `evidence/mapper.py` | `KNOWLEDGE_ROOT` |
| `evidence/runner.py` | `Knowledge`, `discover_content`, `discover_products`, `infer_product`, `parse_frontmatter`, `verify_evidence` |
| `no_downgrade_guard.py` | `Knowledge`, `infer_product`, `parse_frontmatter`, `verify_evidence` |
| `stale_detect.py` | `Knowledge`, `LOCALE_RE`, `parse_frontmatter` |
| `token_ops.py` | `Knowledge` |

## Maintainer Navigation Guide

| If you need to… | Start here | Run after change |
|-----------------|-----------|-----------------|
| Change knowledge loading / model access | `knowledge_core.py` | full pytest (21 consumers) |
| Change content file discovery | `knowledge_core.py` (→ `content_discovery.py` after R-1) | full pytest |
| Change evidence validation | `knowledge_core.py` (→ `evidence_verifier.py` after R-3) | full pytest |
| Change pre-write content gate | `change_guard.py` | `test_change_guard.py` |
| Change post-write audit | `audit.py` → `audit/` package | `test_audit.py` |
| Change site launch readiness | `site_planner.py`, `launch_gate.py` | `test_site_planner*.py` |
| Change the embedding pipeline | `embed.py` | `test_embed.py` |
| Change content evaluation | `content_eval/` (subpackage), `remediate.py` | content_eval test suite |
| Add a one-shot maintenance utility | `kind=one-shot, lifecycle=maintenance` | set `lifecycle=deprecated` after use |
| Add a new shared library module | `kind=library` at root; only if 3+ consumers | new `test_*.py` required |

### Owner-domain → canonical file cross-reference

| owner_domain | Canonical entry points |
|---|---|
| `content-quality` | `audit.py`, `validate_product_yaml.py`, `validate_frontmatter.py` |
| `knowledge-pipeline` | `scout.py`, `enrich.py`, `promote.py`, `index.py`, `refresh_knowledge.py` |
| `content-remediation` | `remediate.py`, `normalize_yaml_style.py` |
| `content-grading` | `check_grade_downgrade.py`, `check_grade_integrity.py`, `check_grade_presence.py`, `no_downgrade_guard.py` |
| `content-governance` | `change_guard.py`, `override_manager.py`, `path_guard.py` |
| `knowledge-infrastructure` | `knowledge_core.py`, `embed.py`, `embed_knowledge.py`, `stale_detect.py` |
| `governance` | `sync_skills.py`, `skill_run_manager.py`, `smoke_test.py` |
| `provenance-maintenance` | `provenance_backfill.py` + 15 `kind=one-shot` provenance scripts |

## Governance-Sensitive Files

Changes to these files require extra care — a mistake here affects the entire session or all CI runs:

| File | Why sensitive | Extra step required |
|------|--------------|---------------------|
| `registry.yaml` | CI governance source of truth; wrong entry breaks CI | Run `python scripts/ci/render_inventory.py` + `check_pipeline_registration.py` |
| `override_manager.py` | Write-path bypass token control | Manual review of token lifecycle logic |
| `scripts/ci/check_pipeline_registration.py` | Self-referential CI check; must self-verify | Run with `--self-check` after any edit |
| `launch_gate.py` | Pre-launch readiness; false-negative causes bad deploy | Run full launch test suite |
| `AGENTS.md` | All agent behavior; changes affect every session | Override token required (see `path_guard.py`) |

## Shared Module Rules

These rules govern when to create a new `kind=library` module at root:

- **3+ scripts** need the same function → extract to `kind=library` at root (registered, tested)
- **2 scripts** need it → duplicate and comment; no module for a single use
- **Never** create a new `core/` module for logic that depends on `knowledge_core`; `core/` has a zero-dep rule. Only `core/knowledge.py` is grandfathered.
- **Never** expand `knowledge_core.py`; it is a tracked hotspot (21 fan-in, 661 lines). Pending split in Phase R.
- New `kind=library` modules must set `requires_test: true` and have a matching `test_*.py` in `tests/`.

## One-Shot Lifecycle Enforcement

One-shot maintenance scripts follow this lifecycle:

1. **Create** with `kind=one-shot, lifecycle=maintenance` — the correct pattern (NOT `lifecycle: one-shot`)
2. **Execute** the script for its intended one-time operation
3. **Deprecate** in the same sprint: set `lifecycle=deprecated` in `registry.yaml`
4. CHECK 5 in `check_pipeline_registration.py` flags `lifecycle=deprecated` entries as advisory reminders
5. CHECK 1 confirms the file still exists on disk (deprecated entries are kept for reruns)

Do not delete deprecated one-shot scripts — they are retained for audit trail and potential reruns.

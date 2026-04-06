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

- **Flat root size**: 69 files at one level makes discovery harder than ideal. A future sprint may separate entry-point scripts from library modules via sub-packages (`kilocode/`, `ops/`) — but this requires updating skill files, CI, and all hook scripts simultaneously. Track B in the restructuring plan covers this.

- **Strict frontmatter variant**: `normalize_yaml_style.py` and `validate_product_yaml.py` use a strict `\n---\s*\n` closing-fence pattern vs. the tolerant `\n---\s*(?:\n|$)` in `core/markdown.py`. Consolidation is deferred to phase-A2b pending a behavioral verification test.

- **Test coverage**: All pipeline tests now live in `scripts/pipeline/tests/`. Run via `pytest scripts/pipeline/tests/ -q`.

# PIPELINE.md — Scripts/Pipeline Architecture

This document describes the `scripts/pipeline/` package: its modules, their roles,
and how they connect in the content generation and validation pipelines.

## Overview

The pipeline package contains the Python backend for all skill operations.
Scripts are invoked directly by skills (via Claude Code slash commands) or
run in CI workflows.

```
scripts/pipeline/
├── __init__.py
├── audit.py                  # Backwards-compat shim → commands/content/audit_legacy.py
├── attach_evidence.py        # Backwards-compat shim → commands/content/attach_evidence.py
├── backtrack_controller.py   # Backwards-compat shim → commands/healing/backtrack_controller.py
├── change_guard.py           # Backwards-compat shim → commands/diagnostics/change_guard.py
├── check_audit_results.py    # Backwards-compat shim → commands/diagnostics/check_audit_results.py
├── content_eval/             # Multi-dimensional quality grader (S-25, S-48)
│   ├── __init__.py
│   ├── __main__.py           # CLI entry point
│   ├── cli.py
│   ├── config.py
│   ├── loader.py
│   ├── models.py
│   ├── evaluators/           # 20+ individual evaluators
│   ├── reporters/            # Markdown + JSON reporters
│   ├── remediation/          # Fixers, planner, runner, triage
│   └── cross_page/           # Consistency + platform alignment
├── scout_enrichers/          # Scout enricher plugins (Doxygen, Javadoc, XML doc)
└── commands/                 # Organized sub-packages for all CLI scripts
    ├── content/              # Content audit, evidence, remediation
    │   ├── audit.py          # PRIMARY pre-write gate (S-23); exposes audit_files() + main()
    │   ├── audit_legacy.py   # Legacy full-content audit (backwards compat)
    │   ├── attach_evidence.py # Evidence frontmatter population (S-24)
    │   ├── remediate.py      # Batch content remediation (S-40/41/42)
    │   ├── ground_check.py   # Ground-check helper
    │   ├── batch_reference.py # Bulk reference page scaffold (S-67)
    │   ├── cross_platform_audit.py # Cross-platform consistency audit
    │   └── validate_frontmatter.py # Frontmatter schema validator
    ├── diagnostics/          # Diagnostics and CI checks
    │   ├── change_guard.py   # Pre-write knowledge gate (S-33)
    │   ├── check_audit_results.py # CI audit result checker
    │   ├── smoke_test.py     # Smoke test runner
    │   ├── repo_patrol.py    # GitHub org patrol helper
    │   └── truth_audit_content.py # Line-level truth audit helper
    ├── enrichment/           # Content enrichment
    │   └── content_enrich.py # Post-launch enrichment (S-108)
    ├── governance/           # Quality and governance guards
    │   ├── no_downgrade_guard.py # Quality regression prevention (S-56)
    │   ├── plan_check.py     # Plan quality gate
    │   └── skill_context.py  # Skill context resolver
    ├── healing/              # Heal policy and dependency resolution
    │   ├── backtrack_controller.py # Causal backtrack orchestrator (S-79)
    │   ├── dependency_resolver.py  # Backtrack dependency graph
    │   ├── heal_policy.py    # Heal routing policy table
    │   └── retire_page.py    # Page retirement helper (S-88)
    ├── knowledge/            # Knowledge pipeline scripts
    │   ├── refresh_knowledge.py # Full knowledge refresh orchestrator (S-14)
    │   ├── enrich.py         # LLM semantic enrichment (S-61)
    │   ├── embed.py          # Vector embedding helper (S-15)
    │   ├── index.py          # Knowledge index builder (S-31)
    │   ├── knowledge_core.py # Knowledge model loader (shared)
    │   ├── knowledge_coverage.py # Coverage audit helper (S-86)
    │   ├── promote.py        # Scout → merged promotion step
    │   └── truth_audit.py    # Member-level API verification (S-47)
    ├── launch/               # Launch orchestration
    │   ├── launch_gate.py    # Launch-readiness gate enforcer
    │   ├── launch_rollback.py # Launch rollback helper (S-60)
    │   ├── site_planner.py   # Site plan generator (S-57)
    │   └── readiness_scorecard.py # Publish readiness scorecard (S-95)
    ├── migration/            # Migration utilities
    │   ├── complete_plugin_structure.py
    │   └── provenance_backfill.py
    └── ops/                  # Operational and session management
        ├── cleanroom_regen.py # Cleanroom regeneration workflow (S-106)
        ├── cleanroom_manifest.py
        ├── content_diff_classifier.py
        ├── editorial_review_classifier.py
        ├── harvest_ledger.py # Backlog harvest state tracking
        ├── link_validator.py # Internal link validator (S-70)
        ├── override_manager.py # Forbidden-path override tokens
        ├── page_impact_assess.py
        ├── post_refresh_verify.py # Post-refresh verification gate
        ├── project_phase_store.py # Phase store helper (S-10)
        ├── refresh_review.py
        ├── report_extract.py # Report → backlog item extractor
        ├── selective_revert.py
        ├── session_ledger.py # Session file-touch tracker
        ├── skill_run_manager.py # Skill run record lifecycle
        ├── stale_detect.py   # Stale knowledge detection
        ├── sync_skills.py    # Skills mirror sync helper
        ├── token_ops.py      # API token operations
        └── update_product_registry.py # Product registry updater
```

> **Note on backwards-compat shims:** Several files in `scripts/pipeline/` (such as `audit.py`)
> are compatibility shims that delegate to their real implementations under `commands/`. These
> shims exist for import compatibility only. Always invoke the real script path for CLI use.
> The canonical pre-write audit script is `scripts/pipeline/commands/content/audit.py`.

## Core Concepts

### Knowledge Model

The knowledge model for a product lives at `knowledge/{family}/{platform}/merged/`.
It is produced by the scout→enrich→promote pipeline and contains:

- `api_surface.json` — API classes, methods, properties
- `claims.json` — enriched semantic claims
- `formats.json` — supported file formats
- `model.yaml` — metadata: SHA, version, enrichment_status

### Content Repository

Content lives in a separate repository, referenced via `$CONTENT_REPO_PATH`.
The pipeline scripts use this env variable (or `config.yaml`) to locate content.

### Evidence Frontmatter

Every content file carries an `evidence:` block in its YAML frontmatter:
```yaml
evidence:
  model_sha: abc123
  claims:
    - claim-id-001
    - claim-id-002
  apis:
    - ClassName.method_name
```

This block is populated by `commands/content/attach_evidence.py` and validated by `commands/content/audit.py`.

## Pipeline Stages

### Knowledge Bootstrap (S-34 → S-12 → S-14 → S-13)

```
repo-scout → knowledge-update → knowledge-enrich → stale-detect
```

Scripts: `scripts/discover.py` → `commands/knowledge/refresh_knowledge.py` → `commands/knowledge/enrich.py` → `commands/ops/stale_detect.py`

### Content Generation (S-08 → S-18 → S-19 → S-20 → S-23)

```
site-plan → page-plan → page-draft → page-update → content-check
```

Scripts: skill prompts; deterministic site-planner CLI is not currently shipped in this repo

### Quality Validation (S-25 → S-48 → S-23)

```
eval-page → content-eval → content-check
```

Scripts: `content_eval/cli.py` → `commands/content/audit.py`

### Healing Pipeline (S-26 → S-21 → S-23)

```
heal-page → page-enhance → content-check
```

Scripts: `commands/healing/heal_policy.py` routes findings to correct healing mode → skill prompts

### Batch Remediation (S-40 → S-41 → S-46 → S-23)

```
gap-eval → gap-plan → gap-apply → content-check
```

Scripts: `commands/content/remediate.py` (handles gap-apply waves)

### Causal Backtracking (S-74)

```
causal-backtrack → dependency-resolution → source-fix → re-evaluate
```

Scripts: `commands/healing/backtrack_controller.py` + `commands/healing/dependency_resolver.py`

## Testing

All pipeline scripts have tests in `tests/`. Isolation pattern:

```python
# In test setup
from scripts.pipeline import some_module
some_module.configure(repo_root=tmp_path, knowledge_root=tmp_path / "knowledge")

# In teardown
some_module.configure()  # Reset to defaults
```

See AGENTS.md §16 (Testing Seam Contract) for the full tiered policy.

## Configuration

Scripts resolve paths via:

1. `configure()` function arguments (tests / CI override)
2. `$CONTENT_REPO_PATH` environment variable (content repo location)
3. `$KNOWLEDGE_ROOT` environment variable (knowledge root override)
4. `config.yaml` in repo root (fallback for local dev)
5. Built-in defaults: `knowledge/` and `content/` relative to repo root

## CI Integration

CI workflows in `.github/workflows/`:

| Workflow | Trigger | Checks |
|----------|---------|--------|
| `skill-governance.yml` | Push to skills/ | validate_skills.py + sync check |
| `skill-registry-audit.yml` | Push to skills/ | Registry integrity |
| `pipeline-tests.yml` | Push to scripts/pipeline/ | pytest tests/ |
| `eval-consistency.yml` | Push to content_eval/ | Evaluator tests |

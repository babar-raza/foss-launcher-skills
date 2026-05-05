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
├── audit.py                  # Content audit (FAIL/WARN findings)
├── attach_evidence.py        # Evidence frontmatter population
├── backtrack_controller.py   # Causal backtrack orchestrator
├── change_guard.py           # Pre-write knowledge gate
├── check_audit_results.py    # CI audit result checker
├── content_audit.py          # Full content audit runner
├── content_eval/             # Multi-dimensional quality grader
│   ├── __init__.py
│   ├── cli.py
│   ├── runner.py
│   └── evaluators/
├── dependency_resolver.py    # Backtrack dependency graph
├── enrich.py                 # LLM semantic enrichment
├── harvest_ledger.py         # Backlog harvest state tracking
├── heal_policy.py            # Heal routing policy table
├── knowledge_core.py         # Knowledge model loader
├── launch_gate.py            # Launch-readiness gate enforcer
├── no_downgrade_guard.py     # Quality regression prevention
├── org_scanner.py            # GitHub org product scanner
├── override_manager.py       # Forbidden-path override tokens
├── plan_check.py             # Plan quality gate
├── post_refresh_verify.py    # Post-refresh verification gate
├── refresh_knowledge.py      # Knowledge refresh orchestrator
├── remediate.py              # Batch content remediation
├── report_extract.py         # Report → backlog item extractor
├── scout_enrichers/          # Scout plugin modules
├── session_ledger.py         # Session file-touch tracker
├── skill_run_manager.py      # Skill run record lifecycle
├── stale_detect.py           # Stale knowledge detection
├── token_ops.py              # API token operations
├── truth_audit.py            # Member-level API verification
├── update_product_registry.py # Product registry updater
└── config_loader.py          # Path and environment config
```

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

This block is populated by `attach_evidence.py` and validated by `audit.py`.

## Pipeline Stages

### Knowledge Bootstrap (S-34 → S-12 → S-14 → S-13)

```
repo-scout → knowledge-update → knowledge-enrich → stale-detect
```

Scripts: `org_scanner.py` → `refresh_knowledge.py` → `enrich.py` → `stale_detect.py`

### Content Generation (S-08 → S-18 → S-19 → S-20 → S-23)

```
site-plan → page-plan → page-draft → page-update → content-check
```

Scripts: `scripts/pipeline/site_planner.py` (if present) + skill prompts

### Quality Validation (S-25 → S-48 → S-23)

```
eval-page → content-eval → content-check
```

Scripts: `content_eval/cli.py` → `audit.py`

### Healing Pipeline (S-26 → S-21 → S-23)

```
heal-page → page-enhance → content-check
```

Scripts: `heal_policy.py` routes findings to correct healing mode → skill prompts

### Batch Remediation (S-40 → S-41 → S-46 → S-23)

```
gap-eval → gap-plan → gap-apply → content-check
```

Scripts: `remediate.py` (handles gap-apply waves)

### Causal Backtracking (S-74)

```
causal-backtrack → dependency-resolution → source-fix → re-evaluate
```

Scripts: `backtrack_controller.py` + `dependency_resolver.py`

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

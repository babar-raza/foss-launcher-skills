# scripts/ — Navigation Index

This directory contains all Python scripts, shell hooks, and tooling for the Aspose.org Hugo monorepo. Scripts are organized by domain; the table below is the entry point for any maintainer.

## Subdirectory Map

| Directory | Purpose | Audience | Stability | Entry points |
|-----------|---------|----------|-----------|--------------|
| [`ci/`](ci/) | GitHub Actions CI validators — governance, grade checks, skill registry, override compliance | CI pipeline (`.github/workflows/`) | Stable | 28 scripts (all callable) |
| [`pipeline/`](pipeline/) | Core content pipeline — audit, knowledge indexing, scout, evidence, remediation, provenance, grading | Operators, skills, git hooks | Stable | ~35 entry-point scripts + internal sub-packages |
| [`translator/`](translator/) | Multi-language content translation (Ollama, M2M, SQLite cache) | Operators via `translate` skill | Stable | `cli.py` (single entry point) |
| [`gap-eval/`](gap-eval/) | Content gap evaluation and fix-spec generation (S-43, S-44, S-45) | Operators via gap-eval/gap-apply/gap-report skills | Active | `run.py`, `synthesize.py` |
| [`seo/`](seo/) | SEO keyword extraction and analysis via Google Gemini | Operators | Tooling | `get_keywords.py`, `review_keywords.py` |
| [`generator/`](generator/) | LLM-ready markdown generation for `llms.txt` artifacts | Operators | Tooling | `llms-generator.py` |
| [`maintenance/`](maintenance/) | One-off migration and recovery scripts; **not called by CI or git hooks** | Human operators (run once) | Maintenance | all files |
| [`website/`](website/) | Ad hoc website scanning utilities | Human operators | Tooling | `find_steps.py`, `clean_locales.py` |

## Root-Level Files

| File | Purpose |
|------|---------|
| `commit-msg-skills.sh` | Git commit-msg hook; validates skill IDs and pending skill run records |
| `install-hooks.sh` | Installs all git hooks into `.git/hooks/` |
| `post-commit-override.sh` | Git post-commit hook; consumes active override tokens after commit |
| `pre-commit-audit.sh` | Git pre-commit hook; runs path-guard, audit, and plugin-platform checks |
| `requirements.txt` | Top-level Python dependencies (covers `pipeline/`, `ci/`) |
| `ph_dev_guide.txt` | Developer reference guide for pipeline conventions and internals |

## Key Conventions

**PYTHONPATH**: Most `scripts/pipeline/` scripts are invoked with `PYTHONPATH=scripts/pipeline` set so they can import each other by short name (e.g., `import knowledge_core`). Do not move files out of `pipeline/` without updating all import sites and the CI workflow.

**Entry points vs. library modules**: The `pipeline/` root mixes runnable entry-point scripts (call these from CLI/CI/hooks) with importable library modules (import these; do not call directly). See [`pipeline/PIPELINE.md`](pipeline/PIPELINE.md) for the complete classification.

**One-off scripts — two categories:**
- `scripts/maintenance/` — standalone operator-run mutations (content repairs, schema migrations) run manually and **never called by CI or skills**. Register each script in `scripts/maintenance/registry.yaml`. Use naming convention `{verb}_{what}_{scope}.py` (e.g. `repair_stale_claims_cells.py`).
- `scripts/pipeline/` `kind=one-shot` — pipeline-orchestrated one-shots that **import from the pipeline package or are invoked by a skill chain**. These require the full 8-step New File Protocol in `pipeline/PIPELINE.md`.

When in doubt, prefer `scripts/maintenance/`. See `AGENTS.md §4b` for the full placement decision tree.

**Blast radius warning**: The paths of CI validators (`ci/*.py`) and pipeline entry points (`pipeline/*.py`) are hardcoded in `.github/workflows/content-audit.yml`, git hooks, AGENTS.md, and 47+ skill files. Do not rename or move these without a coordinated update across all callers.

---

## Metrics Pipeline (METRICS-PLAN-001)

Pipeline entry points that call `llm.professionalize.com` carry a mandatory metrics obligation.
See `AGENTS.md §15` for full requirements.

### Infrastructure files (`scripts/pipeline/commands/ops/`)

| File | Purpose |
|------|---------|
| `professionalize_client.py` | Canonical transport wrapper — all professionalize HTTP calls |
| `metrics_schema.py` | `MetricsEvent` + `MetricsRow` dataclasses, `validate_event()`, `validate_row()` |
| `metrics_event_ledger.py` | Per-run JSONL event ledger (`MetricsEventLedger`) |
| `metrics_payload_builder.py` | `aggregate_events()` + `build_run_row()` aggregation helpers |
| `run_metrics.py` | `RunMetrics` context manager — captures events and builds row |
| `metrics_submitter.py` | `MetricsSubmitter` — dry-run / test / production posting |
| `submit_metrics.py` | CLI entry point for manual submission |

### Config files (`scripts/pipeline/config/`)

| File | Purpose |
|------|---------|
| `metrics_taxonomy.yaml` | Agent names, job types, products, posting modes, boundaries |
| `metrics_callsite_registry.yaml` | All approved professionalize call sites (CS-001 to CS-009) |

### CI governance checks (`scripts/ci/checks/`)

| Check | Purpose |
|-------|---------|
| `check_professionalize_call_sites.py` | Blocks unregistered direct professionalize calls |
| `check_metrics_taxonomy.py` | Validates taxonomy structure and required entries |
| `check_metrics_no_secrets.py` | Scans for committed tokens or keys |
| `check_metrics_test_post_limit.py` | Enforces ≤2 test rows/sprint, hard limit 3 |
| `check_metrics_event_ledger_schema.py` | Validates per-call JSONL event files |
| `check_metrics_sheet_payload_schema.py` | Validates 17-field MetricsRow payloads |
| `check_metrics_docs_propagation.py` | Checks metrics clause propagation in docs and skills |

### Environment variables (set locally, never commit)

```
AGENT_METRICS_ENDPOINT=<Google Apps Script URL>
AGENT_METRICS_TOKEN=<bearer token>
```

Default mode is **dry-run**. Production posting requires `owner_approved=True` and both env vars set.
Token usage (`token_usage`) and API call counts (`api_calls_count`) cover only
`llm.professionalize.com` calls — Gemini, Ollama, and M2M are excluded.

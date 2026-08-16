# Testing And CI

Status: Current
Audience: Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

## Pytest Configuration

`pytest.ini` defines:

| Setting | Value |
|---|---|
| `testpaths` | `tests`, `scripts/pipeline/tests` |
| `pythonpath` | `scripts/pipeline` |

(`scripts/translator` was removed from both settings 2026-08-16 — the translator
subsystem is retired; see [governance gates](../reference/governance-gates.md) and
`translator/__init__.py`'s own compatibility-shim docstring.)

**Known gap**: `tests/test_enrichment_schemas.py` imports `jsonschema`, which is not
declared in any `requirements*.txt` in this repo. A clean bootstrap that installs
only the documented requirements files will fail `pytest --collect-only` on this file.
Run `scripts/ci/checks/repo_doctor.py` to confirm before assuming your environment is
sound — this is a repo-level gap, not something an individual `pip install` fixes.

## Test Selection

Run focused tests first, then broaden when the change touches shared contracts.

Common surfaces:

| Surface | Example tests |
|---|---|
| Clone cache | `scripts/pipeline/tests/test_clone_cache.py` |
| Audit | `scripts/pipeline/tests/test_audit.py` |
| Evidence | `scripts/pipeline/tests/test_attach_evidence_behavior.py` |
| Content eval | `scripts/pipeline/tests/content_eval/` |
| Metrics | `scripts/pipeline/tests/test_metrics_event_ledger.py`, `test_run_metrics.py` |
| Site planning | `scripts/pipeline/tests/test_site_planner.py` |
| Hooks | `scripts/ci/tests/` |

## CI Coverage

`content-audit.yml` is retained but permanently inert (`pull_request`-only trigger,
never fires against this repo's push-to-main workflow). The checks below reflect the
**live**, push-triggered workflows. See [governance gates](../reference/governance-gates.md)
for what each one covers in detail.

## Local/CI Parity

Run `scripts/ci/checks/repo_doctor.py` first — it checks Python/venv/Hugo/git-hooks/
env-vars/repo-state readiness before you try to run any of the commands below.

Push-triggered gate workflows and their canonical local equivalent:

| CI job (`.github/workflows/…`) | Canonical local command | Gap |
|---|---|---|
| `content-governance-checks.yml` | `bash scripts/ci/hooks/simulate_pr_checks.sh` | Simulator omits Hugo-build-triggering path filters and the exact `DIFF_BASE` computation CI uses for multi-commit pushes; close enough for a single local commit's diff |
| `skill-governance.yml` | `bash scripts/pre-push-audit.sh` | None — this script was written specifically to mirror this workflow's test suite exactly (TC-CIR-06) |
| `extraction-pipeline.yml` | `PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest scripts/pipeline/tests/test_format_cross_reference.py -v --tb=short` | None |
| `ci-eval-consistency.yml` | `PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest scripts/pipeline/tests/test_eval_rerun_consistency.py -v --tb=short` — plus, if you touched an onboarding doc (this file, AGENTS.md, CLAUDE.md, RUNBOOK.md, OPERATOR_GUIDE.md, docs/QUICKSTART.md): `.venv/Scripts/python scripts/ci/checks/check_onboarding_integrity.py` | The `onboarding-integrity` job only ever runs on `pull_request` in CI, which this repo doesn't use — run the check script directly, it has no CI-only dependency |
| `metrics-governance.yml` | `.venv/Scripts/python scripts/ci/checks/check_professionalize_call_sites.py` then the other `check_metrics_*.py` scripts named in the workflow, then `PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest scripts/pipeline/tests/test_metrics_submitter.py scripts/pipeline/tests/test_metrics_ci_checks.py scripts/pipeline/tests/test_run_metrics.py scripts/pipeline/tests/test_professionalize_client.py scripts/pipeline/tests/test_metrics_schema.py -v --tb=short` | None |
| `launch-dashboard.yml` | `.venv/Scripts/python scripts/pipeline/commands/diagnostics/launch_dashboard.py --ci` | None |
| `llms-generation.yml` | `.venv/Scripts/python scripts/generator/llms-generator.py --input content --output llms-output --all-subdomains --mode hierarchical --mapping scripts/generator/mapping.json --clean-output` then `scripts/generator/detect_stale_llms.py --check-only` | Mutates `llms-output/` locally — don't run this against a working tree you don't want touched |
| `reference-index-structure.yml` | `PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/ci/checks/check_reference_index_structure.py` | None |
| `act-pipeline.yml` | `PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest tests/test_shadow_pilot.py tests/test_product_state.py tests/test_autonomous_runner.py tests/test_fact_graph.py tests/test_page_plan_compiler.py tests/test_external_signals.py tests/test_schema_validators.py -v --tb=short` | CI additionally clones a live upstream FOSS repo (`aspose-pdf-foss-for-go`) to populate the clone cache for its Go-code-block check — not reproduced locally by this command alone |
| `cross-repo-index-sync.yml` | none | Pushes to a *different* repo (`aspose.net`) on a match; not meaningfully runnable or safe to run locally |

CI-only, not locally reproducible (scheduled watchers, not gates — nothing here blocks
a push): `maven-publish-watcher.yml`, `package-publish-watch.yml`,
`aspose-com-targets-watch.yml`, `upstream-monitor.yml`, `seo-analysis.yml`.

# pipeline/ — Architecture and Developer Reference

`scripts/pipeline/` is the core content pipeline. After the scripts transition
architecture migration, all entry-point scripts live under `commands/{domain}/`
and shared libraries under `lib/`. The pipeline root contains only bootstrap
infrastructure.

## Directory Structure

```
scripts/pipeline/
├── _bootstrap.py                   shared path/config/env bootstrap
├── __init__.py
├── requirements.txt
├── PIPELINE.md                     this file
├── README.md
├── migration_manifest.yaml         migration source of truth (archival)
│
├── commands/                       domain-organized entry-point scripts
│   ├── knowledge/     (12)         scout, enrich, promote, index, embed, ...
│   ├── content/       (17)         audit, remediate, batch_reference, ...
│   ├── governance/    (11)         path_guard, change_guard, override_manager, ...
│   ├── ops/           (18)         session_ledger, skill_run_manager, llm_router, ...
│   ├── healing/       (5)          backtrack_controller, dependency_resolver, ...
│   ├── launch/        (8)          site_planner, launch_gate, preflight, ...
│   ├── diagnostics/   (8)          smoke_test, truth_audit, repo_patrol, ...
│   ├── migration/     (14)         provenance_backfill, seed_grade_manifest, ...
│   └── kilocode/      (4)          kilocode_gate, kilocode_postcheck, ...
│
├── lib/                            shared library modules
│   ├── content_discovery.py        content file discovery
│   ├── grade_writer.py             grade block writing
│   ├── heal_controller.py          heal plan orchestration
│   ├── knowledge_core.py           re-export from commands/knowledge/
│   ├── llm_router.py               re-export from commands/ops/
│   ├── provenance.py               provenance data model
│   ├── token_ops.py                token extraction/verification
│   └── ...                         (19 total)
│
├── config/                         machine-readable config
│   ├── registry.yaml               script registry (CI enforcement)
│   └── llm_registry.yaml           LLM provider registry
│
├── tools/                          migration infrastructure
│
│  # Internal packages — unchanged
├── audit/                          audit engine
├── content_eval/                   content evaluation
├── core/                           foundation: constants, models, env
├── evidence/                       evidence block attachment
├── extraction/                     claim extraction
├── verification/                   API claim verification
├── scout_enrichers/                tree-sitter doc parsers
├── tests/                          pytest suite
└── reports/                        report artifacts
```

## PYTHONPATH Note

CI and git hooks invoke pipeline scripts with `PYTHONPATH=scripts/pipeline` set.
This lets `commands/` scripts import from `lib/` and `core/` by short name
(e.g., `from lib.grade_writer import read_grade`).

## Domain Reference

See [commands/DOMAINS.md](commands/DOMAINS.md) for domain descriptions and
script counts. The authoritative script-level inventory is in `config/registry.yaml`
and rendered to `INVENTORY.md`.

## Adding New Scripts

All new scripts follow this protocol:

### 1. Choose the right location

| Script type | Location | Example |
|-------------|----------|---------|
| CLI entry point (has `if __name__ == "__main__"`) | `commands/{domain}/` | `commands/ops/my_tool.py` |
| Shared library (imported by 3+ scripts) | `lib/` | `lib/my_helpers.py` |
| Machine-readable config | `config/` | `config/my_config.yaml` |

### 2. Use the standard header

Every `commands/` script must start with the bootstrap header:

```python
import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
```

### 3. Register the script

1. Add an entry to `scripts/pipeline/config/registry.yaml`
2. Run `python scripts/ci/checks/check_pipeline_registration.py` — must exit 0
3. Run `python scripts/ci/checks/check_new_script_placement.py` — must exit 0

### 4. Add tests

For `kind: entrypoint` or `kind: library` with `lifecycle: active`:

**Option A — Add tests:**
1. Create `scripts/pipeline/tests/test_{module_name}.py`
2. Add path to `test_targets` in registry.yaml
3. Set `requires_test: true` in registry.yaml

**Option B — Document exemption:**
1. Set `test_exempt_reason` to a non-empty string
2. Leave `test_targets: []`

### 5. If skills changed

Run `scripts/pipeline/commands/ops/sync_providers.py` in a separate commit.

## CI Enforcement

These CI checks enforce the migration architecture:

| Check | What it enforces |
|-------|-----------------|
| `check_pipeline_root_clean.py` | Only `_bootstrap.py` and `__init__.py` at pipeline root |
| `check_new_script_placement.py` | New scripts in recognized domain dirs; all have docstrings |
| `check_stale_path_refs.py` | No old root-level paths in docs/skills/workflows |
| `check_pipeline_registration.py` | Every script registered; backing skills exist; shim integrity |

## Root Budget

After migration, only these items may exist at pipeline root:

| Item | Type |
|------|------|
| `_bootstrap.py` | infrastructure |
| `__init__.py` | package marker |
| `requirements.txt` | dependencies |
| `PIPELINE.md`, `README.md`, `INVENTORY.md` | documentation |
| `migration_manifest.yaml` | archival |
| `commands/`, `lib/`, `config/`, `tools/` | directories |
| `audit/`, `content_eval/`, `core/`, `evidence/`, `extraction/`, `scout_enrichers/`, `verification/` | internal packages |
| `tests/`, `reports/` | test/report dirs |

Any new root-level `.py` file is blocked by `check_pipeline_root_clean.py`.

## Shared Module Rules

- **3+ scripts** need the same function → extract to `lib/` (registered, tested)
- **2 scripts** need it → duplicate and comment; no module for single use
- **Never** create a new `core/` module depending on `knowledge_core`; `core/` has a zero-dep rule
- **Never** expand `knowledge_core.py`; public API is `{Knowledge, diff}` only
- New `lib/` modules must set `requires_test: true` in the registry

## One-Shot Lifecycle

1. Create with `kind=one-shot, lifecycle=maintenance` in registry
2. Execute the script
3. Set `lifecycle=deprecated` in the same sprint
4. Do not delete — retained for audit trail and reruns

## Runtime Architecture

### Grade Data: Two-Layer Model (ARCH-04)

**Layer 1 — Frontmatter** (display fields in `.md` files):
`grade`, `graded_at`, `graded_content_hash`, `grade_reasons`

**Layer 2 — Grade Manifest** (`reports/grade_manifest.json`):
`content_hash`, `enrichment_status`, `evaluator_versions`, `logic_version`, `model_sha`

Entrypoints: `lib/grade_writer.py` (frontmatter), `lib/grade_manifest.py` (manifest),
`content_eval/runner.py` (reads manifest for skip gate; writes both layers).

### Per-Evaluator Skip Gate (ARCH-02)

`content_eval evaluate ... --skip-graded` uses manifest-first skip gate.
See `content_eval/runner.py._filter_already_graded()` for implementation.

### Enrichment Status Signal (TC-4)

`commands/knowledge/refresh_knowledge.py` writes `enrichment_status` to
`knowledge/{family}/{platform}/merged/model.yaml`. Values: `"full"` or `"scout-only"`.

Downstream consumers: `commands/knowledge/stale_detect.py`,
`commands/launch/site_planner.py`, `content_eval/runner.py`.

### Heal Depth Accumulation (FIX-01)

`commands/content/remediate.py heal` prevents infinite heal loops via depth guard.
Escalates to `human_group` after 3 failed attempts. Sidecar persistence via
`{eval_report.stem}-heal.json`.

## Autonomous Content Tooling (ACT)

ACT is a dry-run-only shadow pipeline for generating and validating content candidates
without touching `content/`. All writes go to `reports/` shadow directories.

### ACT Modules (lib/)

| Module | Purpose |
|--------|---------|
| `fact_graph.py` | FactGraph schema, I/O, deterministic Fact records |
| `product_state.py` | State machine: phases, transitions, stop reasons |
| `external_signals.py` | Advisory external signal schema (never overrides source facts) |
| `content_quality.py` | 10-gate deterministic quality scorer for shadow candidates |
| `agent_decision_board.py` | APPROVED/REPAIR/QUARANTINE decisions per candidate |
| `candidate_repair.py` | Deterministic multi-pass auto-fix (up to 3 passes) |
| `controlled_draft_writer.py` | Safe write layer — currently locked dry_run=True |
| `llm_candidate_enricher.py` | LLM-based stub expansion via llm.professionalize.com |

### ACT Entry Points (commands/)

| Script | Location | Mode |
|--------|----------|------|
| `fact_graph_compiler.py` | `commands/knowledge/` | Reads merged/ → fact_graph.json |
| `page_plan_compiler.py` | `commands/content/` | fact_graph → page_plan.json |
| `autonomous_runner.py` | `commands/ops/` | Orchestrates pipeline; dry-run only |

### ACT Runner Modes

```
python autonomous_runner.py --dry-run --mode single --family {f} --platform {p}
python autonomous_runner.py --dry-run --mode shadow --family {f} --platform {p}
python autonomous_runner.py --dry-run --mode agent-review --family {f} --platform {p}
python autonomous_runner.py --dry-run --mode draft-write-dry-run --family {f} --platform {p}
```

### ACT Product State Phases

```
DISCOVERED → SNAPSHOT_CAPTURED → FACTS_EXTRACTED → FACTS_VERIFIED
  → PLAN_COMPILED → CONTENT_GENERATED → CLAIMS_VERIFIED
  → QUALITY_EVALUATED → REGRESSION_PASSED → READY_FOR_REVIEW
  → AGENT_REVIEWED → APPROVED_FOR_DRAFT_WRITE → DRAFT_WRITTEN
```

### ACT Safety Invariants

- `controlled_draft_writer.py` has a permanent live-write lock (`dry_run must be True` at line ~107)
- All candidate files carry `shadow_candidate: true` in frontmatter
- Write guard checks 5 conditions before any file operation
- RollbackManifest records every write with SHA256 for full reversal
- **Rollback path guard** (`ALLOWED_ROLLBACK_ROOTS`): `rollback()` validates all target paths
  before touching any file. Rejects path traversal, absolute paths, and paths outside
  `content/{reference,docs,products,blog,kb}.aspose.org/`. Raises `RollbackPathError` on violation.
- writer version `1.1.0` since addition of rollback path guard

### ACT Readiness Levels

| Level | Meaning | Current |
|-------|---------|---------|
| Shadow ready | Candidates generated in reports/ | YES |
| Agent-review ready | 10-gate agent board evaluates all candidates | YES |
| Draft-write-dry-run ready | Full pipeline in dry-run mode | YES |
| CI ready | `.github/workflows/act-pipeline.yml` runs on push/PR | YES |
| Live-write blocked | `dry_run=True` locked; needs human authorization | BLOCKED |
| Publish/deploy blocked | draft:true; needs PROD_AWS_* and explicit step | BLOCKED |

### ACT Tests

All ACT tests live in the root-level `tests/` directory (covered by pytest.ini testpaths):

```
tests/test_fact_graph.py          (19 tests)
tests/test_product_state.py       (27 tests)
tests/test_page_plan_compiler.py  (12 tests)
tests/test_external_signals.py    (10 tests)
tests/test_autonomous_runner.py   (12 tests)
tests/test_schema_validators.py   (27 tests)
tests/test_shadow_pilot.py        (85 tests)  ← Wave 2 + rollback guard tests
```

Total: 192 tests. Run all:
```
.venv/Scripts/python -m pytest tests/test_shadow_pilot.py tests/test_product_state.py \
  tests/test_autonomous_runner.py tests/test_fact_graph.py tests/test_page_plan_compiler.py \
  tests/test_external_signals.py tests/test_schema_validators.py
```

CI: `.github/workflows/act-pipeline.yml` (scoped to ACT paths, no secrets, no deploy steps)

### ACT LLM Call Site

`llm_candidate_enricher.py` is registered as CS-014 in
`scripts/pipeline/config/metrics_callsite_registry.yaml`.
Uses `PROFESSIONALIZE_API_KEY` env var. Model: `gpt-oss`.

## Migration History

The `scripts/` directory was reorganized in April 2026 (Waves 0–11).
All entry-point scripts now live under `commands/{domain}/`, library
modules under `lib/`, and configuration under `config/`. The pipeline root
contains only `_bootstrap.py` and `__init__.py`.

Status: Operationally closed with 4 known LOW issues (non-blocking).
See `reports/migration/final_clean_room_proof/final_closure_seal.md` for details
and `commands/DOMAINS.md` for domain assignments.

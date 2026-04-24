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
| `description_coverage_audit.py` | Per-product ERC api-kind member-doc coverage audit; run after `enrich --mode member-doc` and before `batch_reference` to verify ≥20% coverage; writes `knowledge/description_coverage_report.json` |
| `normalize_yaml_style.py` | Normalize YAML formatting in knowledge files |
| `plan_check.py` | Validate plan files |
| `regenerate_reference.py` | Regenerate reference pages from knowledge |
| `report_extract.py` | Extract open/unresolved items from markdown reports for backlog harvest (`parse_report`/`--json`/`--count-only`) |
| `harvest_ledger.py` | Harvest ledger CRUD — tracks report items processed into backlog (`status`/`retry-failed`/`waive`/`reset`) |
| `session_ledger.py` | Session-scoped file touch ledger for `/commit` scoping (`init`/`record`/`candidates`/`groups`) |
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

- **knowledge_core.py file location** (deferred, not blocking): `knowledge_core.py` lives at the pipeline root; `core/knowledge.py` is a re-export shim. Phase R symbol extraction is complete — all 11 extracted symbols now live in their canonical homes (`content_discovery.py`, `evidence_verifier.py`, `core/markdown.py`). The public API of `knowledge_core.py` is now `{Knowledge, diff}` only. Physically moving the file into `core/` was considered but deferred indefinitely; the shim makes both import paths equivalent. Do not create a third copy. Do not reopen the physical relocation unless there is a concrete correctness argument.

- **Flat root size**: 69 files at one level is intentional for this codebase. A namespace sub-package refactor (`kilocode/`, `ops/`) was considered (Track B) and closed: the registry's `owner_domain` field already provides logical grouping, and moving CLI entrypoints into sub-packages adds shim complexity with no operational benefit. Do not reopen this unless there is a concrete correctness or testability argument.

- **Strict frontmatter variant** (resolved — Phase A2b, 2026-04-06): `normalize_yaml_style.py` and `validate_product_yaml.py` previously used a strict `\n---\s*\n` closing-fence pattern that silently skipped files ending with `---` at EOF. Both files now use `split_frontmatter()` / `extract_frontmatter_body()` from `core/markdown.py` (tolerant `(?:\n|$)`). Behavioral tests in `test_normalize_yaml_style.py` and `test_validate_product_yaml.py` document and prove the fix.

- **Test coverage**: All pipeline tests now live in `scripts/pipeline/tests/`. Run via `pytest scripts/pipeline/tests/ -q`.

## knowledge_core.py — Public API Census (post-R-4, 2026-04-07)

Phase R decomposition is complete. `knowledge_core.py` public API is now `{Knowledge, diff}`.
See `test_knowledge_core_api_surface.py` for the machine-verifiable baseline.

**Current public surface (2 symbols):**

| Symbol | Type | Line | External fan-in | Notes |
|--------|------|------|----------------|-------|
| `Knowledge` | class | 42 | 6 | Core model loader; highest fan-in; must remain stable |
| `diff` | function | 420 | 0 (tests only) | CLI helper; retained in `knowledge_core.py` |

**Removed symbols and canonical homes (post-R-4):**

| Symbol | Removed from `knowledge_core` | Canonical home | Sprint |
|--------|------------------------------|----------------|--------|
| `discover_content` | R-1b | `content_discovery.py` | R-1a |
| `discover_products` | R-1b | `content_discovery.py` | R-1a |
| `infer_product` | R-1b | `content_discovery.py` | R-1a |
| `parse_frontmatter` | R-2b | `core/markdown.py` | R-2a |
| `_FRONTMATTER_RE` | R-2b | `core/markdown.py` | R-0b |
| `verify_evidence` | R-3b | `evidence_verifier.py` | R-3a |
| `KNOWLEDGE_ROOT` | R-4 | `content_discovery.py` | R-4 |
| `PLATFORM_MAP` | R-4 | `content_discovery.py` | R-4 |
| `PLATFORM_RMAP` | R-4 | `content_discovery.py` | R-4 |
| `SITE_PATHS` | R-4 | `content_discovery.py` | R-4 |
| `LOCALE_RE` | R-4 | `content_discovery.py` | R-4 |

**Import site count by file (non-test, post-R-4):**

| File | Symbols imported from `knowledge_core` |
|------|---------------------------------------|
| `audit/__init__.py` | `Knowledge` |
| `audit/runner.py` | `Knowledge` |
| `content_audit.py` | `Knowledge` |
| `content_eval/evaluators/api_accuracy.py` | `Knowledge` |
| `content_eval/loader.py` | `Knowledge` |
| `token_ops.py` | `Knowledge` |

Fan-in reduced from 21 to 6 (Knowledge-only callers). All 11 removed symbols are imported
from their canonical homes by all consumers. Verified by `test_constants_not_in_knowledge_core`
and zero grep matches on removed-symbol import patterns.

## Maintainer Navigation Guide

| If you need to… | Start here | Run after change |
|-----------------|-----------|-----------------|
| Change knowledge loading / model access | `knowledge_core.py` | full pytest (6 consumers) |
| Change content file discovery | `content_discovery.py` | full pytest |
| Change evidence validation | `evidence_verifier.py` | full pytest |
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
| `governance` | `sync_skills.py`, `skill_run_manager.py`, `smoke_test.py`, `session_ledger.py` |
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
- **Never** expand `knowledge_core.py`; it is a tracked module with 6 fan-in. Public API is `{Knowledge, diff}` (post-R-4).
- New `kind=library` modules must set `requires_test: true` and have a matching `test_*.py` in `tests/`.
- **Before extracting a symbol, run a fresh grep for all its import patterns** — `from <module> import <symbol>` and multi-import block variants. Consumer counts from prior documentation are estimates; 3 consumers were missed in R-1b because the grep was done at plan time, not execution time. Never rely on pre-counted lists.

## One-Shot Lifecycle Enforcement

One-shot maintenance scripts follow this lifecycle:

1. **Create** with `kind=one-shot, lifecycle=maintenance` — the correct pattern (NOT `lifecycle: one-shot`)
2. **Execute** the script for its intended one-time operation
3. **Deprecate** in the same sprint: set `lifecycle=deprecated` in `registry.yaml`
4. CHECK 5 in `check_pipeline_registration.py` flags `lifecycle=deprecated` entries as advisory reminders
5. CHECK 1 confirms the file still exists on disk (deprecated entries are kept for reruns)

Do not delete deprecated one-shot scripts — they are retained for audit trail and potential reruns.

**Distinction between pipeline one-shots and maintenance scripts:**
`scripts/pipeline/` `kind=one-shot` is for pipeline-orchestrated one-shot operations that
import from the pipeline package and are invoked by skill chains or CI. They require full
registration and the 8-step New File Protocol above.
`scripts/maintenance/` is for standalone operator-run mutations (content repairs, data
migrations) that are run manually and never called by automation. They require only a
1-line entry in `scripts/maintenance/registry.yaml`. When in doubt, prefer
`scripts/maintenance/`.


## Registry Schema: `test_exempt_reason` field

Optional string. When present and non-empty, suppresses CHECK 4b warnings for this entry
and documents why no test is needed. Valid exempt reasons:
- One-shot maintenance scripts with no production callers
- Thin wrappers whose backing module has full test coverage (cite the test file)
- Scripts requiring live external APIs that cannot be mocked offline without a full harness
- Phase-deferred scripts not yet in the active CI path

Entries with neither `test_targets` nor `test_exempt_reason` will fail CHECK 4b
once `--fail-test-gaps` is active in `content-audit.yml`.

Example:
```yaml
- path: scripts/pipeline/embed_knowledge.py
  test_targets: []
  test_exempt_reason: "thin wrapper: calls embed.main() which has full coverage in test_embed.py"
```

## Test file requirements

For every new `kind: entrypoint` or `kind: library` with `lifecycle: active`:

**Option A — Add tests:**
1. Create `scripts/pipeline/tests/test_{module_name}.py`
2. Add path to `test_targets` in registry.yaml
3. Set `requires_test: true` in registry.yaml

**Option B — Document exemption:**
1. Set `test_exempt_reason` to a non-empty string justifying the exemption
2. Leave `test_targets: []`

Test file location is non-negotiable:
- `scripts/pipeline/` scripts → `scripts/pipeline/tests/test_{module}.py`
- `scripts/translator/` scripts → `scripts/translator/tests/test_{module}.py`
- Root `tests/` → end-to-end integration spanning multiple subsystems only
- Naming: `test_{module}.py` matching the source filename exactly
- Sub-packages use flat naming: `test_prereqs.py` not `core/test_prereqs.py`

### Testing seam requirements

Tests MUST comply with AGENTS.md §16 (Tiered Monkeypatch Policy):
- **T1 (path constants):** Use `configure()` seams, never `monkeypatch.setattr` or `patch.object`
- **T2 (internal functions):** Use dependency injection (constructor, parameter, callback)
- **T3 (I/O boundaries):** Annotate with `# T3-MOCK: target=... reason=... removal=...`
- **T4 (env/dict):** Permitted without annotation

When a module is renamed, deleted, or split: rename/delete/split its test file and update
`test_targets` in registry.yaml accordingly. The registry is the enforcement contract.

---

## Runtime Architecture (Phase 2 — Production-Proven)

This section documents behavioral contracts that are NOT derivable from the module classification
above. These were implemented in Phase 1 (TC-1 through TC-5) and verified live in Phase 2
(VER-01a through VER-04). All behaviors are confirmed by the Phase 2 Verification Matrix in the
planning document (`lazy-mixing-wirth.md`).

---

### Grade Data: Two-Layer Model (ARCH-04)

Grade data is split across two layers with distinct roles.

**Layer 1 — Frontmatter** (display fields only; written to each `.md` file):

| Field | Description |
|-------|-------------|
| `grade` | Letter grade: A/B/C/D/F |
| `graded_at` | ISO-8601 timestamp of last grading |
| `graded_content_hash` | 32-char SHA-256 prefix of content at grading time |
| `grade_reasons` | List of up to 5 human-readable grade reasons |

These fields are safe to render on the site. They do not contain skip-gate or versioning data.
`graded_evaluator_versions` is NOT a frontmatter field; it was removed when ARCH-04 was adopted.

**Layer 2 — Grade Manifest** (`reports/grade_manifest.json`; operational/skip-gate fields):

| Field | Description |
|-------|-------------|
| `content_hash` | 32-char SHA-256 prefix (current content at grade time) |
| `enrichment_status` | `"full"` or `"scout-only"` |
| `evaluator_versions` | Dict: `{"evaluator_name": "version_string", ...}` for all evaluators run |
| `logic_version` | Global `EVALUATOR_LOGIC_VERSION` string (MIG-02 fallback key) |
| `model_sha` | Knowledge repo SHA at grade time |
| `grade`, `grade_reasons` | Duplicated from frontmatter for manifest-only consumers |

The manifest is the authoritative source for skip-gate decisions. Frontmatter is the authoritative
source for display. Neither layer is a subset of the other.

**Entrypoints involved**: `grade_writer.py` (frontmatter), `grade_manifest.py` (manifest),
`content_eval/runner.py` (reads manifest for skip gate; writes both layers via `_write_grades()`).

---

### Per-Evaluator Skip Gate (ARCH-02 / TC-5)

`content_eval evaluate ... --skip-graded` engages the ARCH-02 manifest-first skip gate.

**How it works** (implemented in `content_eval/runner.py._filter_already_graded()`):

1. Load `reports/grade_manifest.json` once per run.
2. For each page, call `grade_manifest.manifest_skip_check()`:
   - If no manifest entry exists: not skippable → MIG-02 frontmatter fallback (see below).
   - If content hash changed: not skippable.
   - If enrichment status changed: not skippable.
   - For each evaluator name in the current run: if `manifest["evaluator_versions"][ev] != EVALUATOR_VERSIONS[ev]`, not skippable.
   - All checks pass: skippable. `pages_evaluated` is NOT incremented for skipped pages.
3. **MIG-02 fallback** (pre-manifest legacy pages): if no manifest entry, fall back to frontmatter
   `logic_version` comparison using the global `EVALUATOR_LOGIC_VERSION`. This covers pages graded
   before ARCH-04 was adopted.

**Staleness semantics**: Staleness is per-page per-evaluator-version. A page is stale if ANY
evaluator's stored version in the manifest does not match the current `EVALUATOR_VERSIONS` dict.
Whether an evaluator produced findings on a prior run is irrelevant to staleness.

**Observable signal**: `Evaluation complete: Pages: N` in stderr.
- `Pages: N > 0` when pages are re-evaluated (stale or no manifest entry).
- `Pages: 0` when all pages are current (all versions match).

**Which evaluators are checked**: Only evaluators in `DEFAULT_EVALUATORS` (the default set used
when `--evaluators` is not specified). Evaluators not in this set (e.g., `api_backtick`) do not
affect the skip gate.

**Verified live** (VER-04, 2026-04-25): `description_completeness` bumped from "1" to "2";
Step 3a `Pages: 80` (all stale); Step 3b `Pages: 0` (all current); 80 manifest entries updated.

---

### Enrichment Status and Downstream Signal (TC-4)

`refresh_knowledge.py` writes `enrichment_status` to `knowledge/{family}/{platform}/merged/model.yaml`.

| Value | Meaning |
|-------|---------|
| `"full"` | LLM enrichment completed successfully |
| `"scout-only"` | LLM enrichment was skipped (`--skip-enrich`) or failed; knowledge is scout-only |

**Downstream consumers surface enrichment degradation through these paths**:

1. **`stale_detect.py`**: Annotates affected pages with `enrichment_degraded:{status}` in output.
2. **`site_planner.py`**: Prints `SITE-PLAN: WARNING enrichment_status='{status}'` to stderr;
   adds `enrichment_warning` key to the output plan YAML.
3. **`content_eval` runner**: Prints once per `(family, platform)` to stderr:
   ```
   [content_eval] WARNING: enrichment_status='scout-only' for {family}/{platform}
   — claim-based evaluators may report false gaps
   ```
   Dedup via `enrichment_warned_keys` set; fires only when at least one page is evaluated
   (not when all pages are skipped by the skip gate).

**Operator action**: If `enrichment_status: scout-only` appears in `model.yaml`, run
`refresh_knowledge.py {family} {platform}` (without `--skip-enrich`) to perform full enrichment.
Claim-based evaluators (`AA`, `PC`, `FC`, `PT`, `CP`, `RL`) may report false negatives until
enrichment is restored.

**Verified live** (VER-01a + VER-01b, 2026-04-25): `--skip-enrich` writes `scout-only`; full
refresh writes `full`; all three downstream consumers surface the degradation signal.

---

### Heal Depth Accumulation and Sidecar Persistence (FIX-01 / TC-3)

`remediate.py heal {eval_report} [--json]` plans healing for evaluation findings. The depth guard
prevents infinite heal loops by escalating a finding to `human_group` after three failed attempts.

**Depth semantics**:

| State | `depth` value |
|-------|--------------|
| Finding newly seen; never healed | 0 |
| Healed once; still unresolved | 1 |
| Healed twice; still unresolved | 2 |
| Healed three times; still unresolved | 3 |
| Round 4 load: depth >= 3 | Escalate to `human_group` |

Escalation gate: `if loaded_depth >= MAX_HEAL_DEPTH (3)` → routed to `human_group`.

**Sidecar persistence** (cross-run accumulation):

`_cmd_heal()` reads and writes a sidecar file alongside the eval report:
```
{eval_report.stem}-heal.json
```
Example: `reports/note-python-eval.json` → sidecar at `reports/note-python-eval-heal.json`.

The sidecar stores the persistent depth_map under the top-level `"depth_map"` key:
```json
{
  "depth_map": {
    "CE-abc12345": 1,
    "CE-def67890": 3
  }
}
```

- **Before `plan()`**: loaded from sidecar if it exists; defaults to `{}` on first run.
- **After heal cycle** (non-dry-run): written back to sidecar with incremented depths.
- **`--json` mode**: sidecar receives the full JSON data dict (same as stdout).
- **`--dry-run` mode**: sidecar is NOT written (cycle did not execute).
- **Depth increment**: only for findings routed to `auto`, `llm`, or `regen` groups.
  Findings routed to `human` (policy or escalated) do NOT increment.

**Round 4 escalation** happens when `loaded_depth >= 3`. Stored depth stays at 3 after escalation
(no further increment for already-escalated findings).

**Verified live** (VER-02, 2026-04-25): 4-round lifecycle proven with finding CE-746dc7dc;
rounds 1-3 in `llm` group; round 4 in `human` group; fresh-start (sidecar deleted) resets to depth 1.

---

### Release Gate: Required Verifications Before VER-05

Before running `VER-05` (end-to-end dry-run) and issuing a production GO:

| Taskcard | Claim | Status |
|----------|-------|--------|
| VER-01a | `refresh_knowledge` writes `enrichment_status` correctly | Complete (2026-04-25) |
| VER-01b | stale_detect / site_planner / content_eval surface enrichment signal | Complete (2026-04-25) |
| VER-02 | Heal depth accumulates across runs; escalates on round 4 | Complete (2026-04-25) |
| VER-03 | Backtrack visited URLs are not re-processed in subsequent runs | Complete (2026-04-25) |
| VER-04 | Per-evaluator skip gate works: stale→re-eval, current→skip | Complete (2026-04-25) |
| VER-05 | End-to-end dry-run on note/python + 3d/typescript | **Pending** |

VER-05 is the final integration proof. After VER-05 passes, the revised Go/No-Go statement is
issued and the system is considered production-ready.

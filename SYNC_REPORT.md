# SYNC_REPORT.md — foss-launcher-skills Sync 2026-04-17

**Source repo (read-only)**: `aspose.org` (production Hugo/content workflow implementation)
**Target repo (all writes)**: `foss-launcher-skills` (reusable, generalized skills library)
**Synced by**: Claude Sonnet 4.6 operating under aspose.org governance

---

## What Was Synced

### Phase A: Infrastructure Upgrades

**`tools/distribute.py`** (upgraded)
- Added `INTERNAL_SKILLS` support: path-guard, rubric-align, evidence-cite, change-guard are
  excluded from `.claude/commands/` but distributed to codex and kilocode
- Added `generate_registry()`: writes `skills/registry.json` with id, name, description, internal per skill
- Added `verify_parity()`: checks canonical ↔ distributed dirs for drift; reports MISSING/DRIFT/UNEXPECTED
- Added `--verify` CLI flag, `--dry-run` flag, `--registry` flag

**`scripts/skill_constants.py`** (new)
- Exports `INTERNAL_SKILLS` frozenset shared between distribute.py and tests

### Phase B: Upgraded Skill

**`skills/heal-page.md`** (upgraded, S-26)
- Two-pass healing with ground-check between passes
- Auto-refresh knowledge (`python scripts/merge.py`) if stale flag set
- Update `provenance.last_mechanism: heal-page` after each modifying pass
- Escalation: after 2 failed passes → S-73 (manual-edit) named as sanctioned path
- Finding-type fix strategy table
- Preserved target's golden-conformance step (not in source)

### Phase C: New Skills (High Portability)

| File | ID | Description |
|------|----|-------------|
| `skills/code-smoke.md` | S-63 | Syntax/type-check Python code blocks without executing |
| `skills/page-retire.md` | S-83 | Retire outdated pages (set draft:true, retired_at) |
| `skills/session-start.md` | S-77 | Session gate: read governance, init ledger, backlog briefing |
| `skills/diagnose-skill-failure.md` | S-67 | 5-class failure taxonomy for broken skill invocations |
| `skills/register-human-content.md` | S-66 | Register human-authored pages in provenance tracking |
| `skills/evidence-repair.md` | S-72 | Fix broken/malformed evidence frontmatter blocks |
| `skills/evidence-enhance.md` | S-78 | Improve evidence coverage on passing pages |
| `skills/link-validate.md` | S-65 | Validate cross-site internal links |
| `skills/batch-eval-fix.md` | S-41 | Eval + deterministic auto-fix (no LLM) |

### Phase D: New Skills (Config-Driven / Medium Portability)

| File | ID | Description |
|------|----|-------------|
| `skills/commit.md` | S-76 | Full commit workflow: inspect → scope → stage → test → commit |
| `skills/backlog.md` | S-88 | Unified backlog management across sessions |
| `skills/manual-edit.md` | S-73 | Operator-directed targeted content edit under full governance |
| `skills/truth-audit.md` | S-90 | Member-level API verification (see ID note below) |
| `skills/truth-audit-content.md` | S-85 | Line-level content truth audit |
| `skills/coverage-reconcile.md` | S-80 | Knowledge unit disposition report |
| `skills/knowledge-coverage-audit.md` | S-81 | Per-claim 9-state disposition table |

**ID note**: Source uses S-38 for truth-audit, but target's S-38 = launch-product. Assigned S-90 to avoid collision.

### Phase E: Distribution

Ran `tools/distribute.py` to propagate all 48 skills to:
- `.claude/commands/` — 44 files (44 public skills; 4 internal excluded)
- `.agents/skills/` — 48 files (all skills)
- `.kilocode/skills/` — 48 files (all skills)
- `skills/registry.json` — 48 entries

Parity confirmed via `tools/distribute.py --verify`.

### Phase F: Tests

- Updated `tests/test_distribute.py`: fixed skill count assertions for INTERNAL_SKILLS exclusion;
  added tests for INTERNAL_SKILLS exclusion, registry.json, --verify mode
- Updated `tests/test_distribute_integration.py`: fixed count assertion for INTERNAL_SKILLS
- Created `tests/test_new_skills.py`: portability + structure checks for all 17 new/upgraded skills
- Created `tests/fixtures/portability/banned_strings.txt`: Aspose-specific strings that must
  not appear in reusable skill bodies

**Result: 277/277 tests pass.**

### Phase G: Documentation

- Updated `README.md`: skill count 32 → 48; added new skills to catalog table
- Updated `AGENTS.template.md`: added §2 session-start gate, §7 manual-edit escalation path,
  session recording and backlog sections; renumbered all sections
- Created `SYNC_REPORT.md` (this file)

---

## Generalization Principles Applied

| Source assumption | Target generalization |
|---|---|
| `PYTHONPATH=scripts/pipeline python scripts/pipeline/*.py` | `python scripts/*.py` or agent-executed |
| `content/docs.aspose.org/en/{family}/{platform}/` | `{content-path}` from config.yaml sites |
| `knowledge/{family}/{platform}/merged/` | Same (already correct) |
| `scripts/pipeline/skill_context.py begin/end` | Optional context gate — "if script exists" |
| Aspose subdomain list for link-validate | `config.yaml sites` keys |
| `author: "Aspose"` frontmatter rule | Removed (not a generic constraint) |
| Section detection from `.aspose.org/` path prefix | Config-driven section detection |
| `scripts/pipeline/attach_evidence.py` | evidence-enhance skill (S-78) |
| `scripts/pipeline/audit.py` | ground-check skill (S-23) |
| `scripts/pipeline/path_guard.py` | path-guard skill (S-01) |
| `.venv/Scripts/python scripts/pipeline/...` | `python scripts/...` (optional, agent-executed fallback) |

---

## What Was NOT Ported (Deferred)

The following items were reviewed and deferred. Each is documented as a taskcard below.

| TC | Title | Reason |
|----|-------|--------|
| TC-01 | Gap eval/report/apply (S-43-46) | Three-tier architecture (clone cache + vectors + LLM) not in target |
| TC-02 | Translation workflow (S-52-53) | Locale management system not yet in target |
| TC-03 | Site plan + delta-site-plan (S-47, S-82) | Complex deterministic manifest infrastructure |
| TC-04 | Heal-batch + batch-remediate (S-89, S-40) | Content eval pipeline not yet in target |
| TC-05 | System heal (S-87) | Depends on full pipeline maturity |
| TC-06 | Family sync (S-48) | Depends on site-plan for scope |
| TC-07 | Causal backtrack (S-74) | Dependency graph infrastructure not in target |
| TC-08 | New index page skills (S-69-71) | Low priority; easy to add later |
| TC-09 | smoke_test.py backing script | Would upgrade code-smoke from agent-executed to script-backed |
| TC-10 | retire_page.py backing script | Would upgrade page-retire from agent-executed to script-backed |

**Rejected (out of scope, source-specific)**:
- `sync_providers.py` / `sync_skills.py` — Aspose's canonical→mirror propagation; target has `distribute.py`
- `locale-patch` (S-75) — source-specific text patching
- `seo-review` — interactive gate specific to Aspose editorial workflow
- `update-registry` (S-68) — products.json Aspose org scan
- `new-products-page` (S-61) — Aspose products subdomain specific
- `batch-reference` (S-62) — deferred (template-based batch gen)

---

## Deferred Taskcards

### TC-01: Gap Eval / Report / Apply (S-43-46)

**What it does**: Evaluates content accuracy gaps against clone cache; produces gap reports;
applies wave-based gap remediation (W0→W4).

**Why deferred**: The three-tier gap architecture requires a local clone cache at
`runs/.clone_cache/{family}_{platform}/`, a vector index, and a specialized
`content_eval.py` pipeline. None of these exist in the target.

**Recommended next action**: Design a target-native gap architecture using the existing
knowledge model as the truth source (without clone cache). Implement `scripts/gap_eval.py`
that compares content evidence blocks against `claims.json` and `api_surface.json`.
Port S-43, S-44, S-45, S-46 after this script exists.

---

### TC-02: Translation Workflow (S-52-53)

**What it does**: Translates English content pages to locale variants using LLM; manages
locale frontmatter; validates translated pages.

**Why deferred**: Locale management system (locale path conventions, locale index, translation
memory) is not yet in the target.

**Recommended next action**: Design locale-aware content path system. Define `config.yaml`
`locales` section. Implement `scripts/translate_page.py`. Port translate-page + translate-batch.

---

### TC-03: Site Plan + Delta-Site-Plan (S-47, S-82)

**What it does**: Generates a deterministic site manifest (which pages to create/update/retire
per product launch). Delta-site-plan computes changes since last launch.

**Why deferred**: The site planner in the source is a 1,756-line implementation with complex
cluster analysis, coverage thresholds, and multi-product reconciliation. Significant
infrastructure not yet in the target.

**Recommended next action**: Build a simplified `scripts/site_planner.py` for the target that
uses `config.yaml` page type templates and `claims.json` cluster analysis. Port S-47 after
this exists.

---

### TC-04: Heal-Batch + Batch-Remediate (S-89, S-40)

**What it does**: Runs heal-page across an entire product's content in a single batch;
batch-remediate applies a multi-pass remediation queue.

**Why deferred**: Depends on `content_eval.py` evaluator pipeline (16 evaluators, grading
infrastructure) not yet in the target.

**Recommended next action**: Port the evaluator pipeline first (`scripts/content_eval.py` +
key evaluators). Once eval-page (S-25) has a backing script, heal-batch and
batch-remediate become feasible.

---

### TC-05: System Heal (S-87)

**What it does**: System-wide orchestration that discovers all below-threshold pages across
all products and routes them through a prioritized healing queue.

**Why deferred**: Depends on both TC-01 (gap eval pipeline) and TC-04 (batch heal).

**Recommended next action**: Implement after TC-01 and TC-04 are complete.

---

### TC-06: Family Sync (S-48)

**What it does**: Cross-platform content reconciliation — ensures a change made for
`{family}/python` is reflected across `{family}/java`, `{family}/net`, etc.

**Why deferred**: The scope requires site-plan manifests (TC-03) for each platform to
determine which pages exist and which are affected.

**Recommended next action**: Implement after TC-03.

---

### TC-07: Causal Backtrack (S-74)

**What it does**: Given a content defect, traces it to its root cause in the knowledge
pipeline (scout → merge → generation → eval → heal).

**Why deferred**: Requires a dependency graph infrastructure (skill invocation DAG) not
in the target.

**Recommended next action**: Design `scripts/backtrack_controller.py` for the target using
skill run logs. Port S-74 after this infrastructure exists.

---

### TC-08: New Index Page Skills (S-69-71)

**What it does**: Generates `_index.md` landing pages for docs, KB, and reference sections
from existing child pages.

**Why deferred**: Low priority; these are short, simple skills.

**Recommended next action**: Port directly from source after the current sync is validated.
No infrastructure dependencies.

---

### TC-09: smoke_test.py Backing Script

**What it does**: Would provide a Python-backed smoke test runner for code-smoke (S-63),
replacing the current agent-executed approach.

**Why deferred**: Code-smoke works agent-executed; the backing script is an optimization.

**Recommended next action**: Implement `scripts/smoke_test.py` that extracts Python code
blocks, runs `py_compile`, and runs `mypy`. Update S-63 to call it when available.

---

### TC-10: retire_page.py Backing Script

**What it does**: Would provide a Python-backed page retirement script for page-retire (S-83),
replacing the current agent-executed frontmatter modification.

**Why deferred**: Page-retire works agent-executed; the backing script is an optimization.

**Recommended next action**: Implement `scripts/retire_page.py` that sets `draft: true` and
`retired_at: YYYY-MM-DD` in frontmatter. Update S-83 to call it when available.

---

## Verification Results

```
tests/    277 passed, 0 failed
distribute --verify: 48 skills, parity confirmed
portability check: 0 banned strings in new skill bodies
registry.json: 48 entries
```

All readiness criteria satisfied:
- [x] No writes made to source repo
- [x] All 17 new skill files created in `skills/`
- [x] `heal-page.md` upgraded with two-pass, provenance, ground-check-between-passes
- [x] `tools/distribute.py` upgraded with INTERNAL_SKILLS, registry.json, --verify, --dry-run
- [x] `python -m pytest tests/ -v` passes (277/277)
- [x] `tests/test_new_skills.py` passes (portability + structure checks)
- [x] No banned Aspose-specific strings in new skill bodies
- [x] `skills/registry.json` generated and valid (48 entries)
- [x] `README.md` updated with new skill catalog entries
- [x] `SYNC_REPORT.md` written with full audit trail
- [x] 10 deferred taskcards documented above

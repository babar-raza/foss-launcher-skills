---
name: pipeline-harden
id: S-110
description: Run deep investigation and systematic hardening of the content pipeline for a family/platform
category: ops
internal: false
---

# S-110: Pipeline Harden — Parameterized Pipeline Hardening Sprint

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform} [--investigate-only] [--resume] [--dry-run] [--max-gaps N]`

- `family` — product family (e.g. `font`, `cells`, `slides`)
- `platform` — runtime (e.g. `python`, `java`, `net`)
- `--investigate-only` — Phase 0 only; produce investigation artifacts, no execution
- `--resume` — Resume from last checkpoint in `reports/sprint/{family}-{platform}-hardening/phase_state.json`
- `--dry-run` — Investigation + taskcards but no execution
- `--max-gaps N` — Maximum gap count before escalation (default: 30)

## Purpose

Execute a full pipeline hardening sprint for one `{family}/{platform}`. Performs deep investigation of pipeline code paths exercised by that product (batch_reference, launch_gate, healing subsystem, knowledge layer, content evaluation), discovers hidden problems, produces a gap taxonomy, generates taskcards, and executes them in dependency-ordered phases. Produces a complete evidence bundle.

**Not a content skill.** Never writes to `content/`. Modifies pipeline code, tests, fixtures, and governance docs only.

**Complementary to S-93 (system-heal)**: S-93 heals content; S-110 hardens the pipeline code that produces content.

## Skill Context Gate

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin \
  --skill S-110 \
  --scope "scripts/pipeline/**,scripts/ci/**,docs/governance/**,docs/workflows/**,docs/registries/**,reports/sprint/**"
```

## Pre-conditions

1. Clone cache exists at `runs/.clone_cache/aspose_{family}_{platform}/` — if missing, HALT; run S-34 first
2. Knowledge not stale: `knowledge/{family}/{platform}/merged/model.yaml` has `stale_since: null` — if stale, HALT; run S-14 first
3. `launch_gate.py` runnable: `.venv/Scripts/python scripts/pipeline/commands/launch/launch_gate.py {family} {platform}` exits without import error
4. Test suite baseline: `pytest scripts/pipeline/tests/ -q` passes (record count as `baseline_test_count`)
5. Page count baseline: count `.md` files in `content/reference.aspose.org/en/{family}/{platform}/` (record as `baseline_page_count`)
6. Git working tree clean for sprint scope files

## Hard Limits

- **Max gaps**: Default 30. Phase 0 gap count exceeding this -> HALT and escalate
- **Page count invariant**: `baseline_page_count` must not change at any checkpoint
- **Test regression**: Fewer passing tests than baseline at any checkpoint -> HALT and revert
- **False gate FAIL**: Gate that was PASS becoming FAIL -> HALT and revert
- **No content/ writes**: Skill context scope excludes `content/`

---

## PHASE 0: Investigation (Read-Only)

**Checkpoint**: `investigation_complete`

9 steps, all read-only. Produces the execution plan.

### Step 0.1 — State Verification

Read and record current state of all pipeline layers for `{family}/{platform}`:

| Layer | What to check | Record as |
|-------|--------------|-----------|
| Clone cache | Exists, last git SHA | `clone_sha` |
| Scout report | `knowledge/{family}/{platform}/scout/` | `scout_exists` |
| Knowledge: api_surface | Entry count in merged/ | `api_surface_count` |
| Knowledge: claims | Claim count in merged/ | `claims_count` |
| Knowledge: model | version, stale_since | `model_version` |
| Knowledge: snippets | File count in merged/snippets/ | `snippet_count` |
| Content: 5 subdomains | File counts per subdomain | `content_counts` |
| Denominator | api_surface eligible vs pages on disk | `denominator_gap` |

Write: `reports/sprint/{family}-{platform}-hardening/preflight/state_snapshot.json`

### Step 0.2 — Prior Claim Audit

Enumerate prior claims from S-93, S-43, S-95 runs, or scout reports as C-01..C-NN. For each:

1. Read the claim text
2. Verify against actual state (code, files, test output)
3. Assign verdict: `VERIFIED | PARTIALLY_VERIFIED | CONTRADICTED | UNVERIFIED | TOO_WEAK_TO_ACCEPT`
4. Record evidence

Write: `reports/sprint/{family}-{platform}-hardening/preflight/claim_audit.json`

### Step 0.3 — Hidden Problem Discovery

For each pipeline component in the product's code path, apply the **8-probe checklist**:

| Probe | Question |
|-------|----------|
| P-01: Doc-code match | Does code behavior match documentation? |
| P-02: Edge cases | Are boundary conditions handled? |
| P-03: Test coverage | What percentage of functions are tested? |
| P-04: Contract compliance | Does code satisfy its CONTRACT/docstring promises? |
| P-05: Error path safety | Do error paths fail safely (no partial writes, no silent failures)? |
| P-06: Input validation | Are arguments validated before use? |
| P-07: Idempotency | Is the operation repeatable without side effects? |
| P-08: Cross-component consistency | Do assumptions match reality in upstream/downstream? |

**Components to probe** (dynamic — include any `scripts/pipeline/` file that touches `{family}` or `{platform}`):
- `batch_reference.py`, `launch_gate.py`, knowledge core, `denominator_reconciler.py`, `lib/healing/`, `site_planner.py`, relevant `content_eval/` evaluators

Record each problem as HP-NN with: component, probe, title, detail, severity, line numbers, evidence.

Write: `reports/sprint/{family}-{platform}-hardening/preflight/hidden_problems.json`

### Step 0.4 — Root Cause Model

Synthesize claim verdicts + hidden problems into root causes (RC-01..RC-NN). Each maps contributing claims, contributing problems, and affected components.

Write: `reports/sprint/{family}-{platform}-hardening/preflight/root_causes.json`

### Step 0.5 — Gap Taxonomy

Catalog all structural weaknesses as G-01..G-NN across 4 tiers:

| Tier | Criteria |
|------|----------|
| CRITICAL | Data loss risk, silent corruption, write-before-validate |
| HIGH | Missing test coverage for critical paths, broken invariants |
| MEDIUM | Missing documentation, inconsistent naming, weak validation |
| LOW | Style issues, missing convenience features |

**Hard stop**: gap count > `--max-gaps` -> HALT.

Write: `reports/sprint/{family}-{platform}-hardening/preflight/gap_taxonomy.json`

### Step 0.6 — Preserve/Redesign/Deprecate Matrix

Classify each pipeline component: `PRESERVE | HARDEN | REDESIGN | DEPRECATE`

Write: `reports/sprint/{family}-{platform}-hardening/preflight/component_matrix.json`

### Step 0.7 — Fixture Architecture Design

Design test fixtures needed. Standard categories:
- `fixtures/knowledge/golden/{family}_{platform}/` — valid api_surface, model, claims, formats
- `fixtures/knowledge/stale/{family}_{platform}/` — stale model
- `fixtures/knowledge/corrupted/{family}_{platform}/` — missing required fields
- `fixtures/naming/edge_cases.json` — slug sanitization vectors (extend if exists)

Write: `reports/sprint/{family}-{platform}-hardening/preflight/fixture_design.json`

### Step 0.8 — Taskcard Generation

Generate taskcards TC-00..TC-NN from gap taxonomy. Required fields per taskcard:

```json
{
  "taskcard_id": "TC-00",
  "title": "...",
  "category": "FIXTURE | CODE_FIX | TEST | GATE | HEALING | DOCS | MANIFEST",
  "phase": 1,
  "files_to_create": [],
  "files_to_modify": [],
  "verification_criteria": { "test_file": "...", "expected_pass_count": 0, "invariants": [] },
  "related_gaps": [],
  "dependencies": [],
  "specification": "..."
}
```

**Phase assignment rules:**
- Phase 1 (parallel): Fixtures, independent code fixes, test infrastructure
- Phase 2: Manifests and reconcilers (depend on Phase 1)
- Phase 3: Healing infrastructure (depend on Phase 2)
- Phase 4: Gate additions (depend on Phase 2)
- Phase 5: Documentation sync (depend on all prior phases)

**Constraint**: Every gap must map to at least one taskcard.

Write: `reports/sprint/{family}-{platform}-hardening/preflight/taskcards.json`

### Step 0.9 — Blocker Resolution

Identify and resolve execution blockers. All must be RESOLVED before Phase 1.

Write: `reports/sprint/{family}-{platform}-hardening/preflight/blocker_resolution.json`

**If `--investigate-only` or `--dry-run`**: Stop here.

**Save checkpoint**: `phase_state.json` with `investigation_complete: true`

---

## PHASES 1-5: Execution

### Standard Taskcard Execution Protocol (all phases)

For each taskcard in phase order:

1. **Pre-check**: All dependency taskcards are VERIFIED_CLOSED
2. **Create/modify files**: Per taskcard specification
3. **Run verification**: `pytest {test_file} -v` -> confirm expected pass count
4. **Check invariants**:
   - `pytest scripts/pipeline/tests/ -q` count >= `baseline_test_count`
   - Content page count == `baseline_page_count`
   - No new launch gate FAILs vs baseline
5. **Record**: Update taskcard JSON -> `current_state: VERIFIED_CLOSED`
6. **On failure**: Revert taskcard changes -> `current_state: FAILED`. Skip dependent taskcards.

### Phase 1 — Parallel Foundation

Typical taskcards: fixtures (TC-00 pattern), code fixes (TC-01 pattern), test infrastructure (TC-05a pattern).

**Checkpoint**: `phase_1_complete`

### Phase 2 — Manifests and Reconcilers

Typical: generation manifest in batch_reference (TC-02 pattern), denominator_reconciler module.

**Checkpoint**: `phase_2_complete`

### Phase 3 — Healing Infrastructure

Typical: `lib/healing/detector.py` (8 detection functions), `classifier.py`, `verifier.py` + tests.

**Note**: If `lib/healing/` already exists from a prior sprint, add family-specific detectors rather than recreating.

**Checkpoint**: `phase_3_complete`

### Phase 4 — Gate Additions

Typical: new gates in `launch_gate.py` following existing `_gate_lNN()` pattern, registered in `_ALL_GATES`.

**Checkpoint**: `phase_4_complete`

### Phase 5 — Documentation Sync

Typical: `docs/governance/launch-gates.md`, `docs/governance/naming-conventions.md`, `docs/workflows/evaluator-changes.md`.

**Checkpoint**: `phase_5_complete`

---

## POST-EXECUTION: Evidence Bundle

### Verification Steps

1. **Final test suite**: `pytest scripts/pipeline/tests/ -q` -> record final counts
2. **Page count invariant**: recount all 5 subdomains -> must match baseline
3. **Launch gate comparison**: run gates -> no PASS-to-FAIL transitions
4. **Denominator reconciliation**: gap must be 0 or unchanged

### Evidence Bundle Structure

```
reports/sprint/{family}-{platform}-hardening/
  preflight/
    state_snapshot.json          # Step 0.1
    claim_audit.json             # Step 0.2
    hidden_problems.json         # Step 0.3
    root_causes.json             # Step 0.4
    gap_taxonomy.json            # Step 0.5
    component_matrix.json        # Step 0.6
    fixture_design.json          # Step 0.7
    taskcards.json               # Step 0.8 (initial)
    blocker_resolution.json      # Step 0.9
  taskcards/
    TC-{NN}.json                 # Per-taskcard execution evidence
  evidence/
    denominator_report.json      # Reconciliation result
    test_summary.json            # Before/after test counts
    gate_comparison.json         # Before/after gate results
  phase_state.json               # Checkpoint state
  final_verdict.md               # Human-readable sprint summary
```

### Final Verdict Format

```markdown
# Sprint Verdict: {Family}/{Platform} Pipeline Hardening

**Date**: {ISO date}
**Sprint ID**: {family}-{platform}-hardening
**Verdict**: EXECUTION_COMPLETE | PARTIAL_EXECUTION | INVESTIGATION_ONLY

## Summary
- Taskcards: {executed}/{total}
- Test results: {passed} passed, {failed} failed, {new} new tests added
- Page count: {count} (unchanged)
- Denominator gap: {gap}

## Files Modified / Files Created / Gaps Addressed / Pre-existing Issues / Acceptance Criteria
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-01 | Existing tests pass | `final_passed >= baseline_test_count` |
| AC-02 | New test modules pass | All taskcard verification_criteria met |
| AC-03 | Page count unchanged | `baseline_page_count == final_page_count` |
| AC-04 | No new gate FAIL | Gate comparison: no PASS->FAIL |
| AC-05 | Denominator gap stable | `final_gap <= baseline_gap` |
| AC-06 | Healing: 0 CRITICAL | If healing module created, 0 CRITICAL findings |
| AC-07 | Docs updated | Phase 5 taskcards VERIFIED_CLOSED |
| AC-08 | All gaps addressed | Every G-NN maps to a VERIFIED_CLOSED taskcard |
| AC-09 | Evidence bundle complete | All required files exist |

---

## Stop Conditions

| Condition | Action |
|-----------|--------|
| Gap count > `--max-gaps` | HALT at Step 0.5 |
| Unresolved blocker in Step 0.9 | HALT before Phase 1 |
| Test regression at any checkpoint | REVERT last taskcard; HALT |
| Page count change | REVERT; HALT unconditionally |
| Gate PASS->FAIL | REVERT; investigate |
| `content/` write attempted | BLOCKED by skill context |
| Taskcard FAILED + downstream depends | SKIP dependents; PARTIAL_EXECUTION |

---

## Error Handling

| Failure | Action |
|---------|--------|
| Clone cache missing | HALT; run S-34 first |
| Knowledge stale | HALT; run S-12 first |
| `launch_gate.py` import error | HALT; fix environment |
| Pytest baseline fails | HALT; fix pre-existing failures first |
| Git dirty for sprint scope | HALT; stash or commit first |
| Component not found in Step 0.3 | SKIP; record "not applicable" |
| File already exists from prior sprint | Abort taskcard; record with diff |
| Phase has 0 taskcards | Skip phase; proceed |

---

## State Management

### Phase State Schema

```json
{
  "family": "{family}",
  "platform": "{platform}",
  "sprint_id": "{family}-{platform}-hardening",
  "baseline_test_count": 0,
  "baseline_page_count": 0,
  "baseline_gate_results": {},
  "current_phase": 0,
  "phases": {
    "investigation": "COMPLETE | IN_PROGRESS | NOT_STARTED",
    "phase_1": "...", "phase_2": "...", "phase_3": "...", "phase_4": "...", "phase_5": "..."
  },
  "taskcards_closed": [],
  "taskcards_failed": [],
  "taskcards_skipped": [],
  "updated_at": "ISO-8601"
}
```

### Allowed State Transitions

```
NOT_STARTED -> IN_PROGRESS -> COMPLETE
                             -> FAILED (revert triggered)
                             -> SKIPPED (no taskcards for phase)
```

Blocked: `COMPLETE -> IN_PROGRESS` (no re-entry); `FAILED -> COMPLETE` (must restart); phase N before phase N-1.

### Taskcard State Machine

```
NOT_STARTED -> IN_PROGRESS -> VERIFIED_CLOSED (evidence + verification passed)
                             -> FAILED (revert + skip dependents)
                             -> SKIPPED (dependency failed)
```

**Closure rule**: A taskcard may NOT close unless all `files_to_create` exist, all `files_to_modify` changed, `pytest {test_file}` passes with >= `expected_pass_count`, invariants hold, and evidence JSON is written.

### Resume Behavior

On `--resume`: read `phase_state.json`, find first non-COMPLETE phase, re-validate baselines. If baselines shifted, HALT with "baselines shifted; re-run from Phase 0".

---

## Shared Infrastructure (Reuse, Not Duplicate)

| Component | Path | How |
|-----------|------|-----|
| Evidence builder | `scripts/pipeline/evidence/writer.py` | Import for frontmatter ops |
| Checkpoint/resume | `scripts/pipeline/commands/governance/skill_context.py` | Standard begin/end |
| Phase state store | `scripts/pipeline/commands/ops/project_phase_store.py` | get/set for checkpoints |
| Gap taxonomy model | `scripts/pipeline/lib/healing/detector.py` | Import `HealingFinding`, `IssueType`, `Severity` |
| Claim audit model | `scripts/pipeline/lib/triage_confirm.py` | Call `triage_confirm()` |
| Launch gate evaluator | `scripts/pipeline/commands/launch/launch_gate.py` | Call twice; diff results inline |

---

## Skill Context Close

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end \
  --skill S-110 --status completed
```

Use `--status failed` if halted due to error.
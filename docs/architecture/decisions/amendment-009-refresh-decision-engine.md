# Amendment 009 — Refresh Decision Engine Governance

**Status**: APPROVED
**Approved by**: Human operator (2026-05-29)
**Implemented in**: `data/refresh-feature-flags.json`, `scripts/pipeline/lib/decision_engine.py`, `scripts/pipeline/commands/ops/semantic_refresh_guard.py`
**Backlog item**: REFRESH-ARCH-001 (CLOSED)

---

## Approved Governance Change

The refresh decision engine (S-14 knowledge-update downstream) is now **agent-autonomous**.
Agents inspect the delta report, page impact, and test results and decide independently whether to proceed — no human approval gate required unless the agent encounters a BLOCKED verdict or regeneration scope exceeds 20% of product pages.

This replaces the prior requirement for explicit human approval before each refresh run.

---

## Enablement Sequence

Phase 1 through Phase 5 must be applied sequentially. Each phase requires all refresh harness tests to pass before advancing.

### Phase 1 — Decision Engine (ENABLED 2026-05-29)

| Flag | Value |
|------|-------|
| `refresh_decision_engine_enabled` | **true** |
| All other flags | unchanged (false) |

**Verify**: `pytest scripts/pipeline/tests/test_refresh_harness.py -v` → 100% pass
**Effect**: Decision engine runs and writes decision log to `reports/refresh/decision_log.json`. No content writes. Shadow mode preserved.

### Phase 2 — Manifest Writes (ENABLED 2026-05-29)

| Flag | Value |
|------|-------|
| `refresh_manifest_write_enabled` | **true** |

**Verified**: DRY_RUN_PASS on canary cells/java; 35/35 harness tests pass.
**Effect**: Enables the manifest write path; manifests written to `runs/manifests/` when decision is FRESH and reconciliation_enforced is also True.

### Phase 3 — Reconciliation Enforcement (ENABLED 2026-05-29)

| Flag | Value |
|------|-------|
| `refresh_reconciliation_enforced` | **true** |

**Verified**: DRY_RUN_PASS on canary cells/java; 35/35 harness tests pass (test assertions updated to reflect Phases 1-3).
**Effect**: Completes the manifest write circuit (Phase 2 + Phase 3 together enable actual manifest writes).

### Phase 4 — Generation Manifest Writes (ENABLED 2026-05-29)

| Flag | Value |
|------|-------|
| `refresh_generation_manifest_write_enabled` | **true** |

**Verified**: DRY_RUN_PASS on canary cells/java; 35/35 harness tests pass.
**Effect**: Generation state tracked in manifest; prevents orphaned manifests.

### Phase 5 — Content Writes (NOT YET IMPLEMENTED)

| Flag | Value |
|------|-------|
| `refresh_content_write_enabled` | false (leave off — not yet implemented) |

**Status**: Implementation not yet built. The harness hard-blocks this flag (`HARD_BLOCK` in `_maybe_write_manifest()`). No code path reads this flag to enable content regeneration. Leave `false` until the content-write pipeline is implemented and wired to this flag.

---

## Agent Decision Protocol (replaces human approval gate)

```
1. Run refresh pipeline with new knowledge delta
2. Read reports/refresh/decision_log.json:
   - If all decisions are FRESH or VALIDATE_ONLY → proceed automatically
   - If REGENERATE_* count < 20% of product pages → proceed after logging
   - If REGENERATE_* count > 20% OR any BLOCKED → halt and escalate to human
3. Run scripts/pipeline/commands/ops/semantic_refresh_guard.py (Step 11.5):
   - Exit 0 → proceed
   - Exit 1/4 → halt; report GUARD_BLOCKED with evidence
4. Run pytest scripts/pipeline/tests/test_semantic_refresh_guard.py → must be 100% pass
```

Agents write a brief decision record (`reports/refresh/agent_decision.json`) before proceeding, documenting: timestamp, product, REGENERATE count, decision rationale, guard exit code.

---

## Implementation Files

| File | Role |
|------|------|
| `data/refresh-feature-flags.json` | Phase-by-phase flag store |
| `scripts/pipeline/lib/decision_engine.py` | Decision engine logic |
| `scripts/pipeline/commands/ops/semantic_refresh_guard.py` | Step 11.5 guard |
| `scripts/pipeline/tests/test_refresh_harness.py` | Regression harness |
| `scripts/pipeline/tests/test_semantic_refresh_guard.py` | Guard tests |
| `scripts/pipeline/tests/test_refresh_validation.py` | Full validation suite |

---

## Phase Advancement Protocol

To advance from Phase N to Phase N+1:
1. Run `pytest scripts/pipeline/tests/test_refresh_harness.py -v` → must be 100%
2. Run a full refresh dry-run on canary (cells/java) → 0 errors
3. Update `data/refresh-feature-flags.json` for the next phase flag
4. Document the advance in the commit message with: `feat(refresh): advance REFRESH-ARCH-001 to Phase N+1`

Phases 2–4 applied 2026-05-29 (peppy-marinating-manatee v3). Phase 5 (content writes) deferred — implementation not yet built; harness hard-blocks the flag as defense-in-depth.

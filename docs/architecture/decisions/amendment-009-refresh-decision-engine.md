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

### Phase 5 — Content Writes (CODE-COMPLETE 2026-05-30; flag pending canary)

| Flag | Value |
|------|-------|
| `refresh_content_write_enabled` | **false** (pending canary run) |

**Status**: Implementation complete. `_dispatch_content_write()` added to `refresh_harness.py`; Gate 3b dispatches `batch_reference.py --update` for `REGENERATE_UPSTREAM`/`REGENERATE_GENERATOR` decisions when the flag is True. Hard-block guards removed. 35/35 harness tests pass (6 new Phase 5 tests added). Full test suite: 5799 pass, 0 fail.

**Design decisions made (2026-05-30)**:
- Scope: reference subdomain only (batch_reference.py --update). Docs/blog regeneration deferred to Phase 6+.
- Decision triggers: `REGENERATE_UPSTREAM` and `REGENERATE_GENERATOR` only. Metadata/policy decisions do not trigger content writes.
- Scope per run: product-by-product (safest; consistent with Phases 1-4).
- Semantic guard integration: `semantic_refresh_verdict.json` is read before each dispatch; exit-2 verdicts abort the run; exit-1 verdicts block the write (run continues); exit-0 verdicts allow the write.
- Passing verdicts (exit 0): `BODY_UPDATED_VERIFIED`, `EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED`, `SEMANTIC_NOOP_PROVEN`, `GRADING_REMEDIATION_REQUIRED`.
- Abort verdicts (exit 2): `CLAIM_EXTRACTION_MISSED_DELTA`, `PAGE_MAPPING_MISSED_IMPACT`.

**To enable**: Set `refresh_content_write_enabled: true` in `data/refresh-feature-flags.json` after:
1. Running `semantic_refresh_guard.py` on cells/java → exit 0
2. Running `refresh_knowledge.py cells java` in dry-run → 0 errors
3. Verifying content pages regenerated correctly
4. Updating this document with canary results

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

Phases 2–4 applied 2026-05-29 (peppy-marinating-manatee v3). Phase 5 implementation complete 2026-05-30 (peppy-marinating-manatee v5 sprint); flag remains false pending canary run on cells/java.

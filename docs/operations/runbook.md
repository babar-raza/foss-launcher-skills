# Operations Runbook

Status: Current
Audience: Operator
Canonical reference: `docs/reference/cli.md`
Last code-backed audit: 2026-05-30

## Recurring Operations

| Operation | Guide |
|---|---|
| Launch product | [Launch a product](../guides/launch-product.md) |
| Refresh product | [Refresh a product](../guides/refresh-product.md) |
| Discovery scan/change sweep | [Discovery and change sweep](../guides/discovery-and-change-sweep.md) |
| Content audit/evaluation | [Content audit and evaluation](../guides/content-audit-and-evaluation.md) |
| Evidence repair | [Evidence repair](../guides/evidence-repair.md) |
| Hard-stop recovery | [Hard-stop recovery](hard-stop-recovery.md) |

## Verification

Use the guide-specific verification checklist and the canonical references for commands, paths, and gates.

---

## Grade Write Process Guard (WP-01)

> Added: A13 sprint, 2026-06-02. Root cause: A12 anomaly where
> `products/cells/cpp/_index.md` was incorrectly written as grade A during a session
> with transient knowledge state (formats.json temporarily inconsistent).

### Background

`grade_writer.py:_should_write_canonical_grade()` fires a grade write on any
**grade-band-crossing** (e.g., C→A), even if FAIL findings exist. This is by design
for normal operation, but creates an operational risk: if `--write-grade-if-policy-met`
is called while knowledge artifacts are being regenerated, content-eval may return a
transiently high grade. The write happens, persisting an incorrect grade.

### Required 2-Step Process

```bash
# Step 1: Evaluate WITHOUT writing — confirm 0 FAIL findings
PYTHONPATH="scripts/pipeline;scripts/pipeline/lib" .venv/Scripts/python \
    -m content_eval evaluate --files content/{path/to/page.md}

# Step 2: Write grade ONLY if Step 1 shows FAIL: 0
PYTHONPATH="scripts/pipeline;scripts/pipeline/lib" .venv/Scripts/python \
    -m content_eval evaluate --files content/{path/to/page.md} \
    --write-grade-if-policy-met
```

**Do NOT run Step 2 if Step 1 shows any FAIL findings.** The grade-band-crossing
trigger fires regardless of FAILs, so Step 1 is a mandatory pre-flight check.

### High-Risk Moments

Perform this 2-step check after any of the following, before writing grades:

- `refresh_knowledge.py` or `scout.py` re-run (regenerates formats.json, claims.json)
- `promote.py` run (merges scout + enriched artifacts into merged/)
- Manual edits to `knowledge/*/merged/*.json`

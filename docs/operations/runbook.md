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

---

## Post-Sprint Checklist (WP-02)

> Added: snuggly-doodling-waffle sprint, 2026-06-05.
> Root cause: HANDOFF.md was stale twice (2026-06-03, pre-healing; 2026-06-05, post-healing)
> because no protocol enforced supervisor re-run after healing sprints. Grade manifest
> regeneration was also undocumented as a required post-sprint step.

Run these steps after **every healing sprint** or batch content operation before the next session:

### Step 1 — Refresh HANDOFF.md

```bash
PYTHONPATH="$(pwd)/scripts/pipeline:$(pwd)/scripts/pipeline/lib" .venv/Scripts/python \
  scripts/maintenance/supervisor/orchestrate.py --execute
```

Verify: `backlog/HANDOFF.md` does **not** reference items that were just closed/healed.

### Step 2 — Regenerate Grade Manifest

```bash
# Dry-run first to confirm entry count is sane (~4,000+ entries expected):
PYTHONPATH="$(pwd)/scripts/pipeline:$(pwd)/scripts/pipeline/lib" .venv/Scripts/python \
  scripts/pipeline/commands/migration/seed_grade_manifest.py --dry-run

# Write for real:
PYTHONPATH="$(pwd)/scripts/pipeline:$(pwd)/scripts/pipeline/lib" .venv/Scripts/python \
  scripts/pipeline/commands/migration/seed_grade_manifest.py
```

Verify: `reports/grade_manifest.json` timestamp is newer than the healing sprint commit.

### Step 3 — Verify Grade Summary

```bash
PYTHONPATH="$(pwd)/scripts/pipeline:$(pwd)/scripts/pipeline/lib" .venv/Scripts/python \
  -m content_eval grade-summary --json
```

Expected: `distribution.D == 0`, `distribution.F == 0` after a successful healing sprint.

### Step 4 — Content Check and Link Validate

```bash
PYTHONPATH="$(pwd)/scripts/pipeline:$(pwd)/scripts/pipeline/lib" .venv/Scripts/python \
  scripts/pipeline/commands/content/audit.py --all
```

Expected: FAIL: 0. Any FAIL blocks commit.

### Step 5 — Commit

Use `/commit` skill — never `git commit` directly.

> **Note on supervisor vs. grade-manifest discrepancy**: The supervisor (`orchestrate.py`)
> reads eval JSON reports in `reports/content_eval/` — it does NOT read `grade_manifest.json`.
> After a healing sprint that writes grades via `grade_writer.py` (frontmatter update only),
> the supervisor will still show healed pages as "needing heal" until `content-eval` is re-run
> to regenerate fresh eval reports. This is tracked in SUPERVISOR-STALE-EVAL-001. The
> grade_manifest is the production truth for content quality; the supervisor view is informational.

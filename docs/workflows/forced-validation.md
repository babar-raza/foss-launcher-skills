# Forced Validation — Harness Modes and Synthetic Override Workflow

**Plan**: `serene-jingling-rain` (TC-PROD-006, Amendment 8, 2026-05-05)
**Status**: Implementation complete. All modes operational in shadow/dry-run context.

---

## Overview

The forced validation harness (`refresh_harness.py`) provides controlled execution of the
refresh decision engine for testing, validation, and advisory runs. It never writes to
`content/` and defaults to no-write mode.

---

## Harness Modes

| Mode | Description | Writes? |
|------|-------------|---------|
| `dry-run` | Collect fingerprints and decisions only | No |
| `validate-only` | Run validators on existing content | No |
| `force-reconcile` | Ignore stored manifest; check all expected vs actual | No |
| `synthetic-input-change` | Inject in-memory fingerprint overrides | No |

All modes respect `--no-write` (default). Any output goes to `--scratch-root`, never `content/`.

---

## Safety Gates

### TC-CHALLENGE-003: validate_for_fresh() in write path

Before a FRESH decision is finalized, the harness calls `validate_for_fresh()` from
`scripts/pipeline/lib/freshness_manifest.py`. This catches cases where the decision
engine returns FRESH but a required fingerprint is None (because None is excluded from
the changed-set comparison in `decision_engine.py` line 134).

If `validate_for_fresh()` returns violations:
- Decision is overridden to BLOCKED
- Violations are printed to stderr with `[TC-CHALLENGE-003]` prefix
- BLOCKED is recorded in the ledger record

This gate is **required before any manifest write path is enabled**
(`refresh_manifest_write_enabled=true`).

### TC-HEAL-003: Collection error surfacing

When `_collect_fingerprints_with_overrides()` raises an exception, errors are:
1. Logged to stderr
2. Stored in `_collection_errors` in the fingerprint dict
3. Extracted and appended to the ledger record explanation

Collection errors are never silently discarded.

---

## Running the Harness

### Dry run (shadow mode, no writes)

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_harness.py   --product cells/java   --mode dry-run   --no-write
```

### Validate only (check existing content, no regen)

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_harness.py   --product cells/java   --mode validate-only   --no-write
```

### Synthetic input change (test decision routing)

```bash
# Simulate upstream SHA change (TC-108: REGENERATE_UPSTREAM expected)
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_harness.py   --product cells/java   --mode synthetic-input-change   --fingerprint upstream_repo_sha=SYNTHETIC_TC108   --triage-case TC-108   --scratch-root runs/harness-scratch/tc108   --no-write
```

### Force reconcile (ignore stored manifest)

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_harness.py   --product cells/java   --mode force-reconcile   --scratch-root runs/harness-scratch/recon01   --no-write
```

---

## Synthetic Override Safety

Synthetic overrides are **in-memory only**. They are never written to:
- `content/`
- `knowledge/`
- Production manifest files
- Any file tracked by git

The override dict is passed directly to `_collect_fingerprints_with_overrides()` and
merges with live-collected fingerprints in memory for the duration of the run only.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success: PASS or DRY_RUN_PASS |
| 1 | Failure: FAIL or BLOCKED |
| 2 | Configuration error (invalid mode, missing registry) |

---

## Enforced Mode (Not Yet Active)

`refresh_reconciliation_enforced=false` in production flags (Amendment 8 confirmed).

Before enforced mode can be activated:
1. TC-CHALLENGE-003 gate implemented (done — this sprint)
2. No-write enforced-mode dry run verified
3. 16/16 ALIGNED shadow comparison (freshly reproduced)
4. Human explicit approval per product/surface
5. Git tag created before any content write
6. Temp flags file only — never commit `refresh_reconciliation_enforced=true`

---

## Related Documents

- [refresh-architecture.md](refresh-architecture.md) — Architecture overview and decision routing
- `scripts/pipeline/commands/ops/refresh_harness.py` — Implementation
- `scripts/pipeline/lib/freshness_manifest.py` — `validate_for_fresh()` implementation

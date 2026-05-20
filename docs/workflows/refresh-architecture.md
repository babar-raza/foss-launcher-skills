# Refresh Architecture — Manifest-Driven Per-Surface Freshness

**Plan**: `serene-jingling-rain` (Amendment 8, 2026-05-05)
**Status**: Advisory/shadow mode active. Enforced mode behind flag (default off).

---

## Overview

The refresh architecture replaces the single global SHA-equality gate in `site_planner.py`
with a per-surface decision engine backed by durable freshness manifests. Each surface
(reference, products, docs, blog, kb) gets an independent decision: FRESH, REGENERATE_*,
RECONCILE_*, VALIDATE_ONLY, or BLOCKED.

The old SHA gate remains active by default. The new engine runs in shadow mode alongside it.

---

## Core Components

| Component | File | Role |
|-----------|------|------|
| Freshness manifest schema | `data/schemas/freshness-manifest-schema.json` | JSON schema for per-surface state |
| Manifest lib | `scripts/pipeline/lib/freshness_manifest.py` | Load, save, validate, compute output hash |
| Dependency registry | `data/refresh-dependencies.json` | Per-surface config: generator, fingerprints, content root |
| Registry loader | `scripts/pipeline/lib/dependency_registry.py` | Parse and validate registry entries |
| Fingerprint collector | `scripts/pipeline/lib/fingerprint_collector.py` | Collect live input fingerprints per surface |
| Decision engine | `scripts/pipeline/lib/decision_engine.py` | Route decisions based on fingerprint comparison |
| Reconciliation ledger | `scripts/pipeline/lib/reconciliation_ledger.py` | Per-run ledger of surface outcomes |
| Refresh harness | `scripts/pipeline/commands/ops/refresh_harness.py` | Orchestrate collection -> decision -> ledger |
| Fingerprint audit | `scripts/pipeline/commands/ops/fingerprint_audit.py` | Live audit of all required fingerprints |
| Feature flags | `data/refresh-feature-flags.json` | Runtime on/off switches for all new behavior |

---

## Manifest Location

```
runs/state/{family}/{platform}/{subdomain}/freshness-manifest.json
```

Example: `runs/state/cells/java/reference/freshness-manifest.json`

The `runs/` directory is gitignored. Manifests are durable within a run directory
but are not committed to the repository.

---

## Decision Routing

```
For each (product, subdomain):
  1. Collect input fingerprints via fingerprint_collector.py
  2. Load stored manifest (if any)
  3. Inspect current output state
  4. Call decision_engine.decide() -> returns Decision
  5. If decision is FRESH: call validate_for_fresh() as a safety gate (TC-CHALLENGE-003)
     - If violations: override decision to BLOCKED, log to stderr
  6. Record in reconciliation ledger
```

### Decision values

| Decision | Meaning |
|----------|---------|
| `FRESH` | All fingerprints match, output current, validate_for_fresh passes |
| `REGENERATE_UPSTREAM` | upstream_repo_sha or local_knowledge_sha changed |
| `REGENERATE_GENERATOR` | generator_code_hash or template_hash changed |
| `REGENERATE_METADATA` | products_json_hash changed |
| `REGENERATE_POLICY` | config_hash changed |
| `VALIDATE_ONLY` | No stored manifest or BASELINED_UNPROVEN; run validators only |
| `RECONCILE_MISSING` | Expected output files do not exist |
| `RECONCILE_DRIFTED` | Output content hash differs from stored |
| `BLOCKED` | Required dependency missing, collection failure blocked, or validate_for_fresh violation |

---

## Feature Flags

All flags live in `data/refresh-feature-flags.json`. Safe defaults are shown.

```json
{
  "refresh_decision_engine_enabled": false,
  "refresh_decision_engine_shadow": true,
  "refresh_reconciliation_shadow": true,
  "refresh_reconciliation_enforced": false,
  "refresh_manifest_write_enabled": false,
  "refresh_content_write_enabled": false,
  "refresh_run_type_label_enabled": true
}
```

**`refresh_reconciliation_enforced` must remain `false` until Amendment 9 completes.**

---

## Five Surfaces

| Surface | Status | Generator | Notes |
|---------|--------|-----------|-------|
| reference | supported | `batch_reference.py` (script) | Full fingerprint suite |
| products | validate_only | Agent (S-61/S-48) | No generator_code_hash; skill_version_hash N/A |
| docs | validate_only | Agent (S-20) | No generator_code_hash; skill_version_hash N/A |
| blog | validate_only | Agent (S-20) | No `/en/` prefix; `.yml` config; skill_version_hash N/A |
| kb | validate_only | Agent (S-20) | No generator_code_hash; skill_version_hash N/A |

---

## Safety Rules

1. **Never write to `content/`** from the harness unless `refresh_content_write_enabled=true`
   and an explicit scratch root is provided.
2. **`validate_for_fresh()` is mandatory** before any FRESH manifest write (TC-CHALLENGE-003).
3. **Collection errors are logged** to stderr and surfaced in ledger record explanation (TC-HEAL-003).
4. **Manifests with placeholder output_content_hash** (`sha256:[A-Z_]+`) are provisional
   and must not be used as FRESH closure evidence.
5. **`refresh_reconciliation_enforced=false`** must be confirmed in production flags before
   any enforced-mode activation.

---

## Running the Harness

```bash
# Dry-run (no writes): cells/java, all surfaces
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_harness.py   --product cells/java   --mode dry-run   --no-write

# Fingerprint audit: all 16 products, reference surface
.venv/Scripts/python scripts/pipeline/commands/ops/fingerprint_audit.py
```

---

## Related Documents

- [forced-validation.md](forced-validation.md) — Harness modes and synthetic override workflow
- `scripts/pipeline/lib/freshness_manifest.py` — `validate_for_fresh()` policy
- `data/refresh-dependencies.json` — Per-surface registry entries

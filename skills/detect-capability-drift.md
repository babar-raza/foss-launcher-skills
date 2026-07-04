---
name: detect-capability-drift
id: S-114
description: >
  Detect stale generated adapters by SHA-256 hash comparison between canonical skill
  bodies and deployed adapter files. Emits .governance/generated/drift-report.yaml.
args: "[--check]"
---

# S-114: Detect Capability Drift — Stale Adapter Detection

**Arguments**: $ARGUMENTS
```
[--check]   Exit 1 if any drift detected
```

**Examples:**
```
/detect-capability-drift
/detect-capability-drift --check
```

---

## Purpose

Detect cases where deployed adapters have drifted from the canonical skill contracts.
Drift occurs when the canonical `skills/{name}.md` is updated but adapters are not
regenerated.

Use in CI and pre-commit to enforce that adapters remain synchronized.

## Pre-conditions

- `skills/registry.yaml` must exist
- `pyyaml` must be installed

## Steps

1. **Load registry** — Read all skills from `skills/registry.yaml`.

2. **For each capability with existing adapters**:
   - Compute SHA-256 hash of canonical body (frontmatter stripped from `skills/{name}.md`)
   - Compute SHA-256 hash of each adapter body
   - If hashes differ: record as DRIFT

3. **Emit drift report** — Write `.governance/generated/drift-report.yaml` with:
   - Per-adapter drift entries (capability_id, adapter_type, adapter_path, canonical_hash, adapter_hash)
   - Summary: total adapters checked, drift count

4. **Print summary**:
   ```
   PASS: all N adapters in sync    (no drift)
   DRIFT: M adapters out of sync   (with file list)
   ```

5. **Exit code** — Exit 0 if no drift; exit 1 if `--check` and drift found.

## Implementation

```bash
python tools/capability_sync/detect_adapter_drift.py --sync
python tools/capability_sync/detect_adapter_drift.py --check
```

## Output

- `.governance/generated/drift-report.yaml`
- Console summary

## Repair

If drift is detected:
```bash
python tools/capability_sync/run_sync.py
# or
/sync-capabilities
```

## Idempotency

Read-only detection — running twice produces identical drift reports.

# TC-P6-0001 - Freeze Current Parity Inputs

## Purpose

Create a stable baseline of Phase 1-5 artifacts before migration work starts.

## Exact Scope

Record checksums for inventories, parity matrix, gap report, and target design. Do not change capabilities.

## Inputs

- `docs/parity/inventories/aspose-skill-inventory.json`
- `docs/parity/inventories/foss-launcher-skill-inventory.json`
- `docs/parity/parity-matrix-phase4.json`
- `docs/parity/target-state-migration-design.json`

## Files/Areas Allowed To Change

- `docs/parity/evidence/**`
- `docs/parity/taskcards/**`

## Files/Areas Forbidden To Change

- `D:/onedrive/Documents/GitHub/aspose.org/content/**`
- `D:/onedrive/Documents/GitHub/aspose.org/** unless explicitly read-only`
- `C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab/.git/**`
- `Any production credentials, tokens, or metrics secrets`

## Dependencies

- Phase 5 complete

## Implementation Steps

1. Compute SHA256 checksums for Phase 1-5 input artifacts.
2. Write `docs/parity/evidence/phase6-baseline-checksums.txt`.
3. Record current git status for `docs/parity/**` only.

## Verification Steps

1. Recompute one checksum manually and confirm it matches the baseline file.
2. Confirm no files under `aspose.org/content` changed.

## Expected Artifacts

- `docs/parity/evidence/phase6-baseline-checksums.txt`

## Risk Notes

Low risk. This is read-only except for evidence output.

## Rollback Notes

Delete the generated checksum evidence file.

## Done Criteria

Baseline checksums exist and reference every Phase 1-5 input artifact.

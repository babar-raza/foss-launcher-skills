# TC-P6-0086 - Reconcile truth-index Capability

## Purpose

Resolve Phase 4 parity status for `truth-index` without weakening standalone maintainability.

## Exact Scope

Inspect `truth-index` in both inventories and implement or document the target design: Run contract reconciliation against the aspose.org skill, then update standalone docs/scripts/tests to preserve practical behavior with cleaner structure.

## Inputs

- `docs/parity/inventories/aspose-skill-inventory.json`
- `docs/parity/inventories/foss-launcher-skill-inventory.json`
- `docs/parity/parity-matrix-phase4.json`
- `docs/parity/target-state-migration-design.json`
- `skills/truth-index.md`
- `.agents/skills/truth-index/SKILL.md`

## Files/Areas Allowed To Change

- `skills/truth-index.md`
- `.agents/skills/truth-index/SKILL.md`
- `.claude/commands/truth-index.md`
- `.kilocode/skills/truth-index/SKILL.md`
- `skills/registry.yaml`
- `scripts/**`
- `tests/**`
- `docs/parity/evidence/**`

## Files/Areas Forbidden To Change

- `D:/onedrive/Documents/GitHub/aspose.org/content/**`
- `D:/onedrive/Documents/GitHub/aspose.org/** unless explicitly read-only`
- `C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab/.git/**`
- `Any production credentials, tokens, or metrics secrets`

## Dependencies

- TC-P6-0001
- TC-P6-0002 for config-related work
- TC-P6-0003 for shim-related work

## Implementation Steps

1. Read the aspose.org and standalone records for `truth-index` from the inventories.
2. Classify each gap category for `truth-index` as true missing behavior, intentional standalone redesign, stale reference, or verification-only.
3. If implementation is required, make the smallest additive change in standalone.
4. Update registry/provider/docs references consistently.
5. Add or update focused tests, fixtures, or smoke checks.
6. Record evidence in `docs/parity/evidence/`.

## Verification Steps

1. Run `python scripts/validate_skills.py`.
2. Run targeted tests for changed scripts/docs where available.
3. Run a dry-run or fixture-based command if this capability can write content.
4. Confirm no writes target `D:/onedrive/Documents/GitHub/aspose.org/content/**`.

## Expected Artifacts

- `Updated standalone skill/docs/scripts/tests as needed`
- `docs/parity/evidence/truth-index-parity-verification.md`

## Risk Notes

Phase 4 status: `partial parity`. Gap categories: behavioral mismatch. Workstreams: WS-06. Avoid copying website-only coupling.

## Rollback Notes

Revert the capability-specific files changed by this taskcard. Do not revert unrelated dirty worktree changes.

## Done Criteria

`truth-index` is reclassified as parity-proven, intentionally standalone-different with evidence, or blocked with a precise next action.

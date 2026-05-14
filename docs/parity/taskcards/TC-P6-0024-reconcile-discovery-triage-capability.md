# TC-P6-0024 - Reconcile discovery-triage Capability

## Purpose

Resolve Phase 4 parity status for `discovery-triage` without weakening standalone maintainability.

## Exact Scope

Inspect `discovery-triage` in both inventories and implement or document the target design: Keep current implementation; add dry-run and registry/discoverability verification before claiming parity.

## Inputs

- `docs/parity/inventories/aspose-skill-inventory.json`
- `docs/parity/inventories/foss-launcher-skill-inventory.json`
- `docs/parity/parity-matrix-phase4.json`
- `docs/parity/target-state-migration-design.json`
- `skills/discovery-triage.md`
- `.agents/skills/discovery-triage/SKILL.md`

## Files/Areas Allowed To Change

- `skills/discovery-triage.md`
- `.agents/skills/discovery-triage/SKILL.md`
- `.claude/commands/discovery-triage.md`
- `.kilocode/skills/discovery-triage/SKILL.md`
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

1. Read the aspose.org and standalone records for `discovery-triage` from the inventories.
2. Classify each gap category for `discovery-triage` as true missing behavior, intentional standalone redesign, stale reference, or verification-only.
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
- `docs/parity/evidence/discovery-triage-parity-verification.md`

## Risk Notes

Phase 4 status: `implemented but not verified`. Gap categories: verification-only. Workstreams: WS-07. Avoid copying website-only coupling.

## Rollback Notes

Revert the capability-specific files changed by this taskcard. Do not revert unrelated dirty worktree changes.

## Done Criteria

`discovery-triage` is reclassified as parity-proven, intentionally standalone-different with evidence, or blocked with a precise next action.

# TC-P6-0096 - Preserve Standalone Improvement truth-sync

## Purpose

Ensure standalone-only capability `truth-sync` is not regressed while importing aspose.org parity behavior.

## Exact Scope

Review docs, registry, tests, and user outcome for this standalone-only capability.

## Inputs

- `docs/parity/target-state-migration-design.json`
- `skills/truth-sync.md`
- `.agents/skills/truth-sync/SKILL.md`

## Files/Areas Allowed To Change

- `skills/truth-sync.md`
- `.agents/skills/truth-sync/SKILL.md`
- `.claude/commands/truth-sync.md`
- `.kilocode/skills/truth-sync/SKILL.md`
- `tests/**`
- `docs/parity/evidence/**`

## Files/Areas Forbidden To Change

- `D:/onedrive/Documents/GitHub/aspose.org/content/**`
- `D:/onedrive/Documents/GitHub/aspose.org/** unless explicitly read-only`
- `C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab/.git/**`
- `Any production credentials, tokens, or metrics secrets`

## Dependencies

- TC-P6-0001

## Implementation Steps

1. Confirm `truth-sync` is registered and discoverable.
2. Identify the practical user outcome this standalone-only skill provides.
3. Add a preservation note or regression test if the outcome is valuable.
4. If obsolete, document the deprecation recommendation for operator approval.

## Verification Steps

1. Run `python scripts/validate_skills.py`.
2. Run any existing tests covering the capability.
3. Confirm no aspose.org content write is involved.

## Expected Artifacts

- `docs/parity/evidence/truth-sync-preservation-review.md`

## Risk Notes

Standalone-only does not mean optional; losing these may regress the standalone repo's intended improvements.

## Rollback Notes

Revert only files touched for this preservation review.

## Done Criteria

`truth-sync` has a documented preserve, test, or deprecate decision.

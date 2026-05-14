# TC-P6-0092 - Preserve Standalone Improvement evidence-materialize

## Purpose

Ensure standalone-only capability `evidence-materialize` is not regressed while importing aspose.org parity behavior.

## Exact Scope

Review docs, registry, tests, and user outcome for this standalone-only capability.

## Inputs

- `docs/parity/target-state-migration-design.json`
- `skills/evidence-materialize.md`
- `.agents/skills/evidence-materialize/SKILL.md`

## Files/Areas Allowed To Change

- `skills/evidence-materialize.md`
- `.agents/skills/evidence-materialize/SKILL.md`
- `.claude/commands/evidence-materialize.md`
- `.kilocode/skills/evidence-materialize/SKILL.md`
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

1. Confirm `evidence-materialize` is registered and discoverable.
2. Identify the practical user outcome this standalone-only skill provides.
3. Add a preservation note or regression test if the outcome is valuable.
4. If obsolete, document the deprecation recommendation for operator approval.

## Verification Steps

1. Run `python scripts/validate_skills.py`.
2. Run any existing tests covering the capability.
3. Confirm no aspose.org content write is involved.

## Expected Artifacts

- `docs/parity/evidence/evidence-materialize-preservation-review.md`

## Risk Notes

Standalone-only does not mean optional; losing these may regress the standalone repo's intended improvements.

## Rollback Notes

Revert only files touched for this preservation review.

## Done Criteria

`evidence-materialize` has a documented preserve, test, or deprecate decision.

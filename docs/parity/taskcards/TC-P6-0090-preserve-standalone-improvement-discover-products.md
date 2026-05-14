# TC-P6-0090 - Preserve Standalone Improvement discover-products

## Purpose

Ensure standalone-only capability `discover-products` is not regressed while importing aspose.org parity behavior.

## Exact Scope

Review docs, registry, tests, and user outcome for this standalone-only capability.

## Inputs

- `docs/parity/target-state-migration-design.json`
- `skills/discover-products.md`
- `.agents/skills/discover-products/SKILL.md`

## Files/Areas Allowed To Change

- `skills/discover-products.md`
- `.agents/skills/discover-products/SKILL.md`
- `.claude/commands/discover-products.md`
- `.kilocode/skills/discover-products/SKILL.md`
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

1. Confirm `discover-products` is registered and discoverable.
2. Identify the practical user outcome this standalone-only skill provides.
3. Add a preservation note or regression test if the outcome is valuable.
4. If obsolete, document the deprecation recommendation for operator approval.

## Verification Steps

1. Run `python scripts/validate_skills.py`.
2. Run any existing tests covering the capability.
3. Confirm no aspose.org content write is involved.

## Expected Artifacts

- `docs/parity/evidence/discover-products-preservation-review.md`

## Risk Notes

Standalone-only does not mean optional; losing these may regress the standalone repo's intended improvements.

## Rollback Notes

Revert only files touched for this preservation review.

## Done Criteria

`discover-products` has a documented preserve, test, or deprecate decision.

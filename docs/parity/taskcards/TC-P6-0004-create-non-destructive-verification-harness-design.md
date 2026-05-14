# TC-P6-0004 - Create Non-Destructive Verification Harness Design

## Purpose

Define the fixture, temporary worktree, redirected output, and no-write checks needed for Phase 8.

## Exact Scope

Verification design only; implementation follows later.

## Inputs

- `docs/parity/target-state-migration-design.md`
- `tests/fixtures/**`

## Files/Areas Allowed To Change

- `docs/parity/verification/**`
- `docs/parity/evidence/**`

## Files/Areas Forbidden To Change

- `D:/onedrive/Documents/GitHub/aspose.org/content/**`
- `D:/onedrive/Documents/GitHub/aspose.org/** unless explicitly read-only`
- `C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab/.git/**`
- `Any production credentials, tokens, or metrics secrets`

## Dependencies

- TC-P6-0001
- TC-P6-0002

## Implementation Steps

1. Create `docs/parity/verification/non-destructive-verification-harness.md`.
2. Define inventory, registry, docs-to-code, config, helper dependency, dry-run, redirected output, and safety checks.
3. Specify how to prove `aspose.org/content` remains untouched.

## Verification Steps

1. Confirm the harness design covers every verification category requested by the operator.
2. Confirm all proposed content writes target temp directories or fixture repos.

## Expected Artifacts

- `docs/parity/verification/non-destructive-verification-harness.md`

## Risk Notes

High value because it controls migration safety.

## Rollback Notes

Revert only the verification design document.

## Done Criteria

Harness design is complete enough to decompose into Phase 8 tasks.

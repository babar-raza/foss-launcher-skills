# TC-P6-0003 - Create Compatibility Shim Policy

## Purpose

Define when legacy aspose.org paths should get wrappers versus when skill docs should move to standalone canonical paths.

## Exact Scope

Policy and mapping format only; no shims implemented.

## Inputs

- `docs/parity/gap-report-phase4.md`
- `docs/parity/target-state-migration-design.md`

## Files/Areas Allowed To Change

- `docs/parity/design/**`
- `docs/parity/evidence/**`

## Files/Areas Forbidden To Change

- `D:/onedrive/Documents/GitHub/aspose.org/content/**`
- `D:/onedrive/Documents/GitHub/aspose.org/** unless explicitly read-only`
- `C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab/.git/**`
- `Any production credentials, tokens, or metrics secrets`

## Dependencies

- TC-P6-0001

## Implementation Steps

1. Create `docs/parity/design/compatibility-shim-policy.md`.
2. Define wrapper eligibility, naming, deprecation notes, and test requirements.
3. Define a mapping table schema for old path to new path.

## Verification Steps

1. Confirm the policy prevents copying site-only coupling into standalone.
2. Confirm every shim must have at least one test or smoke check.

## Expected Artifacts

- `docs/parity/design/compatibility-shim-policy.md`

## Risk Notes

Medium risk if wrappers hide broken migrations. Require tests.

## Rollback Notes

Revert only the policy document.

## Done Criteria

Shim policy is ready to drive implementation taskcards.

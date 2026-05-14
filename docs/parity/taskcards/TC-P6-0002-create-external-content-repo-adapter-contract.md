# TC-P6-0002 - Create External Content Repo Adapter Contract

## Purpose

Define the shared standalone contract for content root, clone cache, output root, dry-run mode, and metrics dry-run handling.

## Exact Scope

Design and document adapter behavior only; implementation is a later taskcard.

## Inputs

- `docs/parity/target-state-migration-design.md`
- `config.yaml`
- `scripts/config_loader.py`

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

1. Create `docs/parity/design/external-content-repo-adapter-contract.md`.
2. Specify `CONTENT_REPO_PATH`, `content_root`, `output_root`, clone-cache resolution, and metrics dry-run behavior.
3. Define fail-closed behavior for missing content root and forbidden `aspose.org/content` writes.

## Verification Steps

1. Check the contract names every required config key.
2. Check it includes a non-destructive verification section.

## Expected Artifacts

- `docs/parity/design/external-content-repo-adapter-contract.md`

## Risk Notes

Medium risk if the contract overfits aspose.org. Keep it adapter-oriented.

## Rollback Notes

Revert only the contract document.

## Done Criteria

Adapter contract is explicit enough to implement and test.

# TC-TS-004: Add test coverage for cleanroom-regen

**ID**: TS-004
**Title**: Add test coverage for cleanroom-regen
**Purpose**: Add at least one test file covering the core contract of cleanroom-regen

## Scope
Create tests/test_cleanroom_regen.py with basic contract tests.

## Inputs
- skills/cleanroom-regen.md
- scripts/pipeline/commands/ops/cleanroom_regen.py

## Allowed Changes
- tests/test_cleanroom_regen.py

## Forbidden Changes
- skills/
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read skills/cleanroom-regen.md to understand expected inputs/outputs
2. Read scripts/pipeline/commands/ops/cleanroom_regen.py to understand implementation contract
3. Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()
4. Add edge case test for invalid inputs

## Verification Steps
1. pytest tests/test_cleanroom_regen.py exits 0
2. All new tests pass

## Expected Artifacts
- tests/test_cleanroom_regen.py

**Risk**: LOW — tests only, no production code changes
**Rollback**: Delete tests/test_cleanroom_regen.py

## Done Criteria
- [ ] tests/test_cleanroom_regen.py exists
- [ ] At least 3 test functions defined
- [ ] pytest passes
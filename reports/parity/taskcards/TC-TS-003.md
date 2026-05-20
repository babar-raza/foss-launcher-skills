# TC-TS-003: Add test coverage for change-guard

**ID**: TS-003
**Title**: Add test coverage for change-guard
**Purpose**: Add at least one test file covering the core contract of change-guard

## Scope
Create tests/test_change_guard.py with basic contract tests.

## Inputs
- skills/change-guard.md
- scripts/pipeline/commands/diagnostics/change_guard.py

## Allowed Changes
- tests/test_change_guard.py

## Forbidden Changes
- skills/
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read skills/change-guard.md to understand expected inputs/outputs
2. Read scripts/pipeline/commands/diagnostics/change_guard.py to understand implementation contract
3. Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()
4. Add edge case test for invalid inputs

## Verification Steps
1. pytest tests/test_change_guard.py exits 0
2. All new tests pass

## Expected Artifacts
- tests/test_change_guard.py

**Risk**: LOW — tests only, no production code changes
**Rollback**: Delete tests/test_change_guard.py

## Done Criteria
- [ ] tests/test_change_guard.py exists
- [ ] At least 3 test functions defined
- [ ] pytest passes
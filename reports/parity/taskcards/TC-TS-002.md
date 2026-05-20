# TC-TS-002: Add test coverage for batch-remediate

**ID**: TS-002
**Title**: Add test coverage for batch-remediate
**Purpose**: Add at least one test file covering the core contract of batch-remediate

## Scope
Create tests/test_batch_remediate.py with basic contract tests.

## Inputs
- skills/batch-remediate.md
- scripts/pipeline/commands/content/remediate.py

## Allowed Changes
- tests/test_batch_remediate.py

## Forbidden Changes
- skills/
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read skills/batch-remediate.md to understand expected inputs/outputs
2. Read scripts/pipeline/commands/content/remediate.py to understand implementation contract
3. Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()
4. Add edge case test for invalid inputs

## Verification Steps
1. pytest tests/test_batch_remediate.py exits 0
2. All new tests pass

## Expected Artifacts
- tests/test_batch_remediate.py

**Risk**: LOW — tests only, no production code changes
**Rollback**: Delete tests/test_batch_remediate.py

## Done Criteria
- [ ] tests/test_batch_remediate.py exists
- [ ] At least 3 test functions defined
- [ ] pytest passes
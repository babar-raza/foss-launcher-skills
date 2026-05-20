# TC-TS-005: Add test coverage for content-audit

**ID**: TS-005
**Title**: Add test coverage for content-audit
**Purpose**: Add at least one test file covering the core contract of content-audit

## Scope
Create tests/test_content_audit.py with basic contract tests.

## Inputs
- skills/content-audit.md
- scripts/pipeline/commands/content/audit.py

## Allowed Changes
- tests/test_content_audit.py

## Forbidden Changes
- skills/
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read skills/content-audit.md to understand expected inputs/outputs
2. Read scripts/pipeline/commands/content/audit.py to understand implementation contract
3. Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()
4. Add edge case test for invalid inputs

## Verification Steps
1. pytest tests/test_content_audit.py exits 0
2. All new tests pass

## Expected Artifacts
- tests/test_content_audit.py

**Risk**: LOW — tests only, no production code changes
**Rollback**: Delete tests/test_content_audit.py

## Done Criteria
- [ ] tests/test_content_audit.py exists
- [ ] At least 3 test functions defined
- [ ] pytest passes
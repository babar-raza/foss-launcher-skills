# TC-VF-001: Add CONTENT_REPO_PATH safety guard to test suite

**ID**: VF-001
**Title**: Add CONTENT_REPO_PATH safety guard to test suite
**Purpose**: Prevent any test from accidentally writing to aspose.org content

## Scope
Add a pytest fixture or conftest.py check that aborts if CONTENT_REPO_PATH points to aspose.org root.

## Inputs
- tests/conftest.py (if exists)
- AGENTS.md (forbidden paths)

## Allowed Changes
- tests/conftest.py

## Forbidden Changes
- Any skill files
- scripts/
- aspose.org repo

## Dependencies
- CF-001

## Implementation Steps
1. Check if tests/conftest.py exists; create or edit it
2. Add a session-scoped fixture that checks os.environ.get('CONTENT_REPO_PATH', '')
3. If CONTENT_REPO_PATH contains 'aspose.org', raise pytest.fail with clear message
4. Add comment explaining the safety purpose

## Verification Steps
1. Run pytest tests/test_validate_skills.py — must pass
2. Temporarily set CONTENT_REPO_PATH to aspose.org path and run a test — must abort with clear error

## Expected Artifacts
- tests/conftest.py with safety guard

**Risk**: LOW — test infrastructure only
**Rollback**: Remove the guard from conftest.py

## Done Criteria
- [ ] conftest.py has CONTENT_REPO_PATH guard
- [ ] Guard triggers correctly on forbidden path
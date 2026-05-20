# TC-TS-007: Add test coverage for evidence-cite

**ID**: TS-007
**Title**: Add test coverage for evidence-cite
**Purpose**: Add at least one test file covering the core contract of evidence-cite

## Scope
Create tests/test_evidence_cite.py with basic contract tests.

## Inputs
- skills/evidence-cite.md
- scripts/pipeline/commands/content/attach_evidence.py

## Allowed Changes
- tests/test_evidence_cite.py

## Forbidden Changes
- skills/
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read skills/evidence-cite.md to understand expected inputs/outputs
2. Read scripts/pipeline/commands/content/attach_evidence.py to understand implementation contract
3. Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()
4. Add edge case test for invalid inputs

## Verification Steps
1. pytest tests/test_evidence_cite.py exits 0
2. All new tests pass

## Expected Artifacts
- tests/test_evidence_cite.py

**Risk**: LOW — tests only, no production code changes
**Rollback**: Delete tests/test_evidence_cite.py

## Done Criteria
- [ ] tests/test_evidence_cite.py exists
- [ ] At least 3 test functions defined
- [ ] pytest passes
# TC-TS-008: Add test coverage for knowledge-enrich

**ID**: TS-008
**Title**: Add test coverage for knowledge-enrich
**Purpose**: Add at least one test file covering the core contract of knowledge-enrich

## Scope
Create tests/test_knowledge_enrich.py with basic contract tests.

## Inputs
- skills/knowledge-enrich.md
- scripts/pipeline/commands/knowledge/enrich.py

## Allowed Changes
- tests/test_knowledge_enrich.py

## Forbidden Changes
- skills/
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read skills/knowledge-enrich.md to understand expected inputs/outputs
2. Read scripts/pipeline/commands/knowledge/enrich.py to understand implementation contract
3. Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()
4. Add edge case test for invalid inputs

## Verification Steps
1. pytest tests/test_knowledge_enrich.py exits 0
2. All new tests pass

## Expected Artifacts
- tests/test_knowledge_enrich.py

**Risk**: LOW — tests only, no production code changes
**Rollback**: Delete tests/test_knowledge_enrich.py

## Done Criteria
- [ ] tests/test_knowledge_enrich.py exists
- [ ] At least 3 test functions defined
- [ ] pytest passes
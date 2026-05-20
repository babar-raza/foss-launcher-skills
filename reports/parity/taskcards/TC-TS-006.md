# TC-TS-006: Add test coverage for embed-knowledge

**ID**: TS-006
**Title**: Add test coverage for embed-knowledge
**Purpose**: Add at least one test file covering the core contract of embed-knowledge

## Scope
Create tests/test_embed_knowledge.py with basic contract tests.

## Inputs
- skills/embed-knowledge.md
- scripts/embed.py

## Allowed Changes
- tests/test_embed_knowledge.py

## Forbidden Changes
- skills/
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read skills/embed-knowledge.md to understand expected inputs/outputs
2. Read scripts/embed.py to understand implementation contract
3. Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()
4. Add edge case test for invalid inputs

## Verification Steps
1. pytest tests/test_embed_knowledge.py exits 0
2. All new tests pass

## Expected Artifacts
- tests/test_embed_knowledge.py

**Risk**: LOW — tests only, no production code changes
**Rollback**: Delete tests/test_embed_knowledge.py

## Done Criteria
- [ ] tests/test_embed_knowledge.py exists
- [ ] At least 3 test functions defined
- [ ] pytest passes
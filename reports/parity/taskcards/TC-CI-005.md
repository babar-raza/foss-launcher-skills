# TC-CI-005: Port knowledge CI checks (3 checks)

**ID**: CI-005
**Title**: Port knowledge CI checks (3 checks)
**Purpose**: Add 3 knowledge validation checks from aspose.org to foss-launcher

## Scope
Create or extend scripts/ci/check_knowledge.py with checks ported from aspose.org.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_clone_cache_refs.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_knowledge_staleness.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_stale_path_refs.py
- ... (see aspose-ci-checks-map.yaml)

## Allowed Changes
- scripts/ci/check_knowledge.py

## Forbidden Changes
- skills/
- docs/
- tests/

## Dependencies
- VF-001

## Implementation Steps
1. For each of the 3 knowledge checks, read aspose.org source
2. Identify logic that is portable vs. aspose.org-specific
3. Extract portable check logic into check functions
4. Write scripts/ci/check_knowledge.py with main() and individual check functions
5. Add --check-only flag for non-destructive CI mode
6. Integrate with scripts/validate_skills.py or standalone CI runner

## Verification Steps
1. python scripts/ci/check_knowledge.py --check-only returns 0 on clean repo
2. All {len(checks)} check functions exist in the module
3. No aspose.org-specific paths hardcoded

## Expected Artifacts
- scripts/ci/check_knowledge.py

**Risk**: MEDIUM — new CI checks may catch new issues
**Rollback**: Delete scripts/ci/check_knowledge.py

## Done Criteria
- [ ] scripts/ci/check_knowledge.py exists with 3 check functions
- [ ] --check-only mode works non-destructively
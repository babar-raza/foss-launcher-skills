# TC-CI-002: Port content_quality CI checks (6 checks)

**ID**: CI-002
**Title**: Port content_quality CI checks (6 checks)
**Purpose**: Add 6 content quality validation checks from aspose.org to foss-launcher

## Scope
Create or extend scripts/ci/check_content_quality.py with checks ported from aspose.org.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_audit_regression.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_content_filenames.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_evaluator_freeze.py
- ... (see aspose-ci-checks-map.yaml)

## Allowed Changes
- scripts/ci/check_content_quality.py

## Forbidden Changes
- skills/
- docs/
- tests/

## Dependencies
- LB-001
- LB-002

## Implementation Steps
1. For each of the 6 content_quality checks, read aspose.org source
2. Identify logic that is portable vs. aspose.org-specific
3. Extract portable check logic into check functions
4. Write scripts/ci/check_content_quality.py with main() and individual check functions
5. Add --check-only flag for non-destructive CI mode
6. Integrate with scripts/validate_skills.py or standalone CI runner

## Verification Steps
1. python scripts/ci/check_content_quality.py --check-only returns 0 on clean repo
2. All {len(checks)} check functions exist in the module
3. No aspose.org-specific paths hardcoded

## Expected Artifacts
- scripts/ci/check_content_quality.py

**Risk**: MEDIUM — new CI checks may catch new issues
**Rollback**: Delete scripts/ci/check_content_quality.py

## Done Criteria
- [ ] scripts/ci/check_content_quality.py exists with 6 check functions
- [ ] --check-only mode works non-destructively
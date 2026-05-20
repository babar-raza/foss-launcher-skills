# TC-CI-009: Port other CI checks (19 checks)

**ID**: CI-009
**Title**: Port other CI checks (19 checks)
**Purpose**: Add 19 other validation checks from aspose.org to foss-launcher

## Scope
Create or extend scripts/ci/check_other.py with checks ported from aspose.org.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_dar_coverage.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_family_display_names.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_forbidden_overrides.py
- ... (see aspose-ci-checks-map.yaml)

## Allowed Changes
- scripts/ci/check_other.py

## Forbidden Changes
- skills/
- docs/
- tests/

## Dependencies
- VF-001

## Implementation Steps
1. For each of the 19 other checks, read aspose.org source
2. Identify logic that is portable vs. aspose.org-specific
3. Extract portable check logic into check functions
4. Write scripts/ci/check_other.py with main() and individual check functions
5. Add --check-only flag for non-destructive CI mode
6. Integrate with scripts/validate_skills.py or standalone CI runner

## Verification Steps
1. python scripts/ci/check_other.py --check-only returns 0 on clean repo
2. All {len(checks)} check functions exist in the module
3. No aspose.org-specific paths hardcoded

## Expected Artifacts
- scripts/ci/check_other.py

**Risk**: MEDIUM — new CI checks may catch new issues
**Rollback**: Delete scripts/ci/check_other.py

## Done Criteria
- [ ] scripts/ci/check_other.py exists with 19 check functions
- [ ] --check-only mode works non-destructively
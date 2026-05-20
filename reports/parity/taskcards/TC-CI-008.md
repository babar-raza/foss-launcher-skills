# TC-CI-008: Port link_integrity CI checks (1 checks)

**ID**: CI-008
**Title**: Port link_integrity CI checks (1 checks)
**Purpose**: Add 1 link integrity validation checks from aspose.org to foss-launcher

## Scope
Create or extend scripts/ci/check_link_integrity.py with checks ported from aspose.org.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_anchor_compatibility.py
- ... (see aspose-ci-checks-map.yaml)

## Allowed Changes
- scripts/ci/check_link_integrity.py

## Forbidden Changes
- skills/
- docs/
- tests/

## Dependencies
- VF-001

## Implementation Steps
1. For each of the 1 link_integrity checks, read aspose.org source
2. Identify logic that is portable vs. aspose.org-specific
3. Extract portable check logic into check functions
4. Write scripts/ci/check_link_integrity.py with main() and individual check functions
5. Add --check-only flag for non-destructive CI mode
6. Integrate with scripts/validate_skills.py or standalone CI runner

## Verification Steps
1. python scripts/ci/check_link_integrity.py --check-only returns 0 on clean repo
2. All {len(checks)} check functions exist in the module
3. No aspose.org-specific paths hardcoded

## Expected Artifacts
- scripts/ci/check_link_integrity.py

**Risk**: MEDIUM — new CI checks may catch new issues
**Rollback**: Delete scripts/ci/check_link_integrity.py

## Done Criteria
- [ ] scripts/ci/check_link_integrity.py exists with 1 check functions
- [ ] --check-only mode works non-destructively
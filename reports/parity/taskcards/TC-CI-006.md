# TC-CI-006: Port metrics CI checks (6 checks)

**ID**: CI-006
**Title**: Port metrics CI checks (6 checks)
**Purpose**: Add 6 metrics validation checks from aspose.org to foss-launcher

## Scope
Create or extend scripts/ci/check_metrics.py with checks ported from aspose.org.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_metrics_docs_propagation.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_metrics_event_ledger_schema.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_metrics_no_secrets.py
- ... (see aspose-ci-checks-map.yaml)

## Allowed Changes
- scripts/ci/check_metrics.py

## Forbidden Changes
- skills/
- docs/
- tests/

## Dependencies
- VF-001

## Implementation Steps
1. For each of the 6 metrics checks, read aspose.org source
2. Identify logic that is portable vs. aspose.org-specific
3. Extract portable check logic into check functions
4. Write scripts/ci/check_metrics.py with main() and individual check functions
5. Add --check-only flag for non-destructive CI mode
6. Integrate with scripts/validate_skills.py or standalone CI runner

## Verification Steps
1. python scripts/ci/check_metrics.py --check-only returns 0 on clean repo
2. All {len(checks)} check functions exist in the module
3. No aspose.org-specific paths hardcoded

## Expected Artifacts
- scripts/ci/check_metrics.py

**Risk**: MEDIUM — new CI checks may catch new issues
**Rollback**: Delete scripts/ci/check_metrics.py

## Done Criteria
- [ ] scripts/ci/check_metrics.py exists with 6 check functions
- [ ] --check-only mode works non-destructively
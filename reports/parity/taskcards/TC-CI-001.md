# TC-CI-001: Port skill_governance CI checks (14 checks)

**ID**: CI-001
**Title**: Port skill_governance CI checks (14 checks)
**Purpose**: Add 14 skill governance validation checks from aspose.org to foss-launcher

## Scope
Create or extend scripts/ci/check_skill_governance.py with checks ported from aspose.org.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_agent_governance_surface.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_agents_md_size.py
- D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/check_commit_skill_provenance.py
- ... (see aspose-ci-checks-map.yaml)

## Allowed Changes
- scripts/ci/check_skill_governance.py

## Forbidden Changes
- skills/
- docs/
- tests/

## Dependencies
- VF-001

## Implementation Steps
1. For each of the 14 skill_governance checks, read aspose.org source
2. Identify logic that is portable vs. aspose.org-specific
3. Extract portable check logic into check functions
4. Write scripts/ci/check_skill_governance.py with main() and individual check functions
5. Add --check-only flag for non-destructive CI mode
6. Integrate with scripts/validate_skills.py or standalone CI runner

## Verification Steps
1. python scripts/ci/check_skill_governance.py --check-only returns 0 on clean repo
2. All {len(checks)} check functions exist in the module
3. No aspose.org-specific paths hardcoded

## Expected Artifacts
- scripts/ci/check_skill_governance.py

**Risk**: MEDIUM — new CI checks may catch new issues
**Rollback**: Delete scripts/ci/check_skill_governance.py

## Done Criteria
- [ ] scripts/ci/check_skill_governance.py exists with 14 check functions
- [ ] --check-only mode works non-destructively
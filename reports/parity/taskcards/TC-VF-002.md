# TC-VF-002: Run full parity verification and update parity-matrix.md

**ID**: VF-002
**Title**: Run full parity verification and update parity-matrix.md
**Purpose**: Re-run parity analysis after all implementation taskcards complete

## Scope
Re-execute _build_parity_matrix.py and verify all gaps are closed.

## Inputs
- All TC artifacts
- reports/parity/parity-matrix.md

## Allowed Changes
- reports/parity/parity-matrix.md
- reports/parity/gap-report.md
- reports/parity/verification-evidence.md

## Forbidden Changes
- skills/
- scripts/
- docs/

## Dependencies
- All other TCs

## Implementation Steps
1. Run python reports/parity/_build_parity_matrix.py
2. Verify parity status distribution improved vs baseline
3. Check no new missing_entirely or documented_not_implemented skills
4. Write reports/parity/verification-evidence.md with final metrics

## Verification Steps
1. All acceptance criteria from PAR-011 plan met
2. Zero 'missing_entirely' skills
3. Governance docs all exist
4. CI check coverage improved

## Expected Artifacts
- reports/parity/verification-evidence.md
- Updated parity-matrix.md

**Risk**: LOW — analysis only
**Rollback**: No rollback needed (analysis only)

## Done Criteria
- [ ] parity-matrix.md shows no missing_entirely skills
- [ ] All GV-* taskcards reflected in governance map
- [ ] CI check count increased from 4
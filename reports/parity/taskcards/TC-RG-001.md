# TC-RG-001: Verify docs/id-mapping.md completeness for all 84 aspose.org skills

**ID**: RG-001
**Title**: Verify docs/id-mapping.md completeness for all 84 aspose.org skills
**Purpose**: Ensure every aspose.org skill ID has a correct foss-launcher mapping entry

## Scope
Cross-reference aspose-inventory.yaml against docs/id-mapping.md. Add missing entries, fix wrong ones.

## Inputs
- reports/parity/aspose-inventory.yaml
- reports/parity/foss-inventory.yaml
- docs/id-mapping.md

## Allowed Changes
- docs/id-mapping.md

## Forbidden Changes
- skills/registry.yaml
- Any skill .md files

## Dependencies
- None

## Implementation Steps
1. For each of 84 aspose.org skills, verify mapping entry exists in docs/id-mapping.md
2. For each of 82 shared slugs, verify both aspose_id and foss_id are correct
3. For 2 aspose-only slugs (blog-migrate, pipeline-harden), add 'not-in-foss' entries
4. For 10 foss-only slugs, verify 'aspose-equiv: none' entries exist
5. Fix any wrong ID mappings found

## Verification Steps
1. Count entries in docs/id-mapping.md — should cover all 84+10 skills
2. Spot-check 10 shared slugs against both registries

## Expected Artifacts
- docs/id-mapping.md updated and complete

**Risk**: LOW — documentation only
**Rollback**: git revert docs/id-mapping.md

## Done Criteria
- [ ] docs/id-mapping.md has entries for all 84 aspose.org skills
- [ ] docs/id-mapping.md has entries for all 10 foss-only skills
- [ ] Every shared skill has correct aspose_id ↔ foss_id mapping
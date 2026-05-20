# TC-SK-021: Batch update remaining 32 skill content files

**ID**: SK-021
**Title**: Batch update remaining 32 skill content files
**Purpose**: Close content depth gaps for remaining 32 size-diverged skills

## Scope
For each remaining skill with size divergence, add missing sections.

## Inputs
- reports/parity/parity-matrix.md (size% column)
- D:/onedrive/Documents/GitHub/aspose.org/skills/

## Allowed Changes
- skills/*.md (32 specific files)

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- SK-001 through SK-020 (to establish pattern)

## Implementation Steps
1. Read parity-matrix.md to identify remaining 32 skills by size%
2. For each: diff aspose.org vs foss-launcher version
3. Add missing sections in batches of 5
4. Run sync after each batch of 5

## Verification Steps
1. validate_skills.py passes
2. All 32 updated skills within 20% of aspose size

## Expected Artifacts
- Updated skill files

**Risk**: LOW — documentation only
**Rollback**: git revert affected skills/*.md files

## Done Criteria
- [ ] All 32 remaining skills within 20% of aspose.org equivalent
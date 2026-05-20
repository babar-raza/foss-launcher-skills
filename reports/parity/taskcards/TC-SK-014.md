# TC-SK-014: Update skill content: batch-reference (+5.3KB gap)

**ID**: SK-014
**Title**: Update skill content: batch-reference (+5.3KB gap)
**Purpose**: Close content depth gap for batch-reference (foss 7.94KB vs aspose 13.29KB)

## Scope
Add missing sections from aspose.org batch-reference.md to foss-launcher batch-reference.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/batch-reference.md
- skills/batch-reference.md

## Allowed Changes
- skills/batch-reference.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/batch-reference.md
2. Read foss-launcher version: skills/batch-reference.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/batch-reference.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/batch-reference.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/batch-reference.md

## Done Criteria
- [ ] skills/batch-reference.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
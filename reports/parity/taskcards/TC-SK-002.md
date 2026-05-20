# TC-SK-002: Update skill content: manual-edit (+16.5KB gap)

**ID**: SK-002
**Title**: Update skill content: manual-edit (+16.5KB gap)
**Purpose**: Close content depth gap for manual-edit (foss 4.65KB vs aspose 21.19KB)

## Scope
Add missing sections from aspose.org manual-edit.md to foss-launcher manual-edit.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/manual-edit.md
- skills/manual-edit.md

## Allowed Changes
- skills/manual-edit.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/manual-edit.md
2. Read foss-launcher version: skills/manual-edit.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/manual-edit.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/manual-edit.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/manual-edit.md

## Done Criteria
- [ ] skills/manual-edit.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
# TC-SK-016: Update skill content: gap-apply (+4.7KB gap)

**ID**: SK-016
**Title**: Update skill content: gap-apply (+4.7KB gap)
**Purpose**: Close content depth gap for gap-apply (foss 2.8KB vs aspose 7.49KB)

## Scope
Add missing sections from aspose.org gap-apply.md to foss-launcher gap-apply.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/gap-apply.md
- skills/gap-apply.md

## Allowed Changes
- skills/gap-apply.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/gap-apply.md
2. Read foss-launcher version: skills/gap-apply.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/gap-apply.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/gap-apply.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/gap-apply.md

## Done Criteria
- [ ] skills/gap-apply.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
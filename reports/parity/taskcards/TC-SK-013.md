# TC-SK-013: Update skill content: heal-page (+6.5KB gap)

**ID**: SK-013
**Title**: Update skill content: heal-page (+6.5KB gap)
**Purpose**: Close content depth gap for heal-page (foss 4.36KB vs aspose 10.85KB)

## Scope
Add missing sections from aspose.org heal-page.md to foss-launcher heal-page.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/heal-page.md
- skills/heal-page.md

## Allowed Changes
- skills/heal-page.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/heal-page.md
2. Read foss-launcher version: skills/heal-page.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/heal-page.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/heal-page.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/heal-page.md

## Done Criteria
- [ ] skills/heal-page.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
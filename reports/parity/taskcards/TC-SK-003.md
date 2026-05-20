# TC-SK-003: Update skill content: section-enhance (+14.1KB gap)

**ID**: SK-003
**Title**: Update skill content: section-enhance (+14.1KB gap)
**Purpose**: Close content depth gap for section-enhance (foss 7.62KB vs aspose 21.75KB)

## Scope
Add missing sections from aspose.org section-enhance.md to foss-launcher section-enhance.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/section-enhance.md
- skills/section-enhance.md

## Allowed Changes
- skills/section-enhance.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/section-enhance.md
2. Read foss-launcher version: skills/section-enhance.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/section-enhance.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/section-enhance.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/section-enhance.md

## Done Criteria
- [ ] skills/section-enhance.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
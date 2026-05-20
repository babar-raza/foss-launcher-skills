# TC-SK-007: Update skill content: system-heal (+8.7KB gap)

**ID**: SK-007
**Title**: Update skill content: system-heal (+8.7KB gap)
**Purpose**: Close content depth gap for system-heal (foss 3.88KB vs aspose 12.59KB)

## Scope
Add missing sections from aspose.org system-heal.md to foss-launcher system-heal.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/system-heal.md
- skills/system-heal.md

## Allowed Changes
- skills/system-heal.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/system-heal.md
2. Read foss-launcher version: skills/system-heal.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/system-heal.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/system-heal.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/system-heal.md

## Done Criteria
- [ ] skills/system-heal.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
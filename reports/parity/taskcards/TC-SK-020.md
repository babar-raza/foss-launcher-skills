# TC-SK-020: Update skill content: session-start (+4.0KB gap)

**ID**: SK-020
**Title**: Update skill content: session-start (+4.0KB gap)
**Purpose**: Close content depth gap for session-start (foss 3.16KB vs aspose 7.17KB)

## Scope
Add missing sections from aspose.org session-start.md to foss-launcher session-start.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/session-start.md
- skills/session-start.md

## Allowed Changes
- skills/session-start.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/session-start.md
2. Read foss-launcher version: skills/session-start.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/session-start.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/session-start.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/session-start.md

## Done Criteria
- [ ] skills/session-start.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
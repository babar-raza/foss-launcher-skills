# TC-SK-019: Update skill content: truth-audit-content (+4.1KB gap)

**ID**: SK-019
**Title**: Update skill content: truth-audit-content (+4.1KB gap)
**Purpose**: Close content depth gap for truth-audit-content (foss 4.42KB vs aspose 8.47KB)

## Scope
Add missing sections from aspose.org truth-audit-content.md to foss-launcher truth-audit-content.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/truth-audit-content.md
- skills/truth-audit-content.md

## Allowed Changes
- skills/truth-audit-content.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/truth-audit-content.md
2. Read foss-launcher version: skills/truth-audit-content.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/truth-audit-content.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/truth-audit-content.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/truth-audit-content.md

## Done Criteria
- [ ] skills/truth-audit-content.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
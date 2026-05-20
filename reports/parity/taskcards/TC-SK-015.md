# TC-SK-015: Update skill content: embed-knowledge (+4.7KB gap)

**ID**: SK-015
**Title**: Update skill content: embed-knowledge (+4.7KB gap)
**Purpose**: Close content depth gap for embed-knowledge (foss 1.57KB vs aspose 6.29KB)

## Scope
Add missing sections from aspose.org embed-knowledge.md to foss-launcher embed-knowledge.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/embed-knowledge.md
- skills/embed-knowledge.md

## Allowed Changes
- skills/embed-knowledge.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/embed-knowledge.md
2. Read foss-launcher version: skills/embed-knowledge.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/embed-knowledge.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/embed-knowledge.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/embed-knowledge.md

## Done Criteria
- [ ] skills/embed-knowledge.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
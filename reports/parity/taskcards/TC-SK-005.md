# TC-SK-005: Update skill content: commit (+13.7KB gap)

**ID**: SK-005
**Title**: Update skill content: commit (+13.7KB gap)
**Purpose**: Close content depth gap for commit (foss 7.24KB vs aspose 20.97KB)

## Scope
Add missing sections from aspose.org commit.md to foss-launcher commit.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/commit.md
- skills/commit.md

## Allowed Changes
- skills/commit.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/commit.md
2. Read foss-launcher version: skills/commit.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/commit.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/commit.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/commit.md

## Done Criteria
- [ ] skills/commit.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
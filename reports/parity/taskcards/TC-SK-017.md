# TC-SK-017: Update skill content: truth-index (+4.6KB gap)

**ID**: SK-017
**Title**: Update skill content: truth-index (+4.6KB gap)
**Purpose**: Close content depth gap for truth-index (foss 1.47KB vs aspose 6.06KB)

## Scope
Add missing sections from aspose.org truth-index.md to foss-launcher truth-index.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/truth-index.md
- skills/truth-index.md

## Allowed Changes
- skills/truth-index.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/truth-index.md
2. Read foss-launcher version: skills/truth-index.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/truth-index.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/truth-index.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/truth-index.md

## Done Criteria
- [ ] skills/truth-index.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
# TC-SK-010: Update skill content: evidence-enhance (+7.1KB gap)

**ID**: SK-010
**Title**: Update skill content: evidence-enhance (+7.1KB gap)
**Purpose**: Close content depth gap for evidence-enhance (foss 2.88KB vs aspose 9.97KB)

## Scope
Add missing sections from aspose.org evidence-enhance.md to foss-launcher evidence-enhance.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/evidence-enhance.md
- skills/evidence-enhance.md

## Allowed Changes
- skills/evidence-enhance.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/evidence-enhance.md
2. Read foss-launcher version: skills/evidence-enhance.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/evidence-enhance.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/evidence-enhance.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/evidence-enhance.md

## Done Criteria
- [ ] skills/evidence-enhance.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
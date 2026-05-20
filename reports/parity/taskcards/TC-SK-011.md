# TC-SK-011: Update skill content: evidence-repair (+6.7KB gap)

**ID**: SK-011
**Title**: Update skill content: evidence-repair (+6.7KB gap)
**Purpose**: Close content depth gap for evidence-repair (foss 4.74KB vs aspose 11.39KB)

## Scope
Add missing sections from aspose.org evidence-repair.md to foss-launcher evidence-repair.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/evidence-repair.md
- skills/evidence-repair.md

## Allowed Changes
- skills/evidence-repair.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/evidence-repair.md
2. Read foss-launcher version: skills/evidence-repair.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/evidence-repair.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/evidence-repair.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/evidence-repair.md

## Done Criteria
- [ ] skills/evidence-repair.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
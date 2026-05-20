# TC-SK-012: Update skill content: new-reference-page (+6.6KB gap)

**ID**: SK-012
**Title**: Update skill content: new-reference-page (+6.6KB gap)
**Purpose**: Close content depth gap for new-reference-page (foss 5.68KB vs aspose 12.29KB)

## Scope
Add missing sections from aspose.org new-reference-page.md to foss-launcher new-reference-page.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/new-reference-page.md
- skills/new-reference-page.md

## Allowed Changes
- skills/new-reference-page.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/new-reference-page.md
2. Read foss-launcher version: skills/new-reference-page.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/new-reference-page.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/new-reference-page.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/new-reference-page.md

## Done Criteria
- [ ] skills/new-reference-page.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
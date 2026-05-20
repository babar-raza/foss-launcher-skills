# TC-GV-004: Port naming conventions doc from aspose.org

**ID**: GV-004
**Title**: Port naming conventions doc from aspose.org
**Purpose**: Create docs/governance/naming-conventions.md adapted from aspose.org equivalent

## Scope
Port the naming-conventions.md governance doc from aspose.org, removing Hugo-specific references.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/docs/governance/naming-conventions.md

## Allowed Changes
- docs/governance/naming-conventions.md

## Forbidden Changes
- AGENTS.md
- skills/
- scripts/

## Dependencies
- RG-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/docs/governance/naming-conventions.md
2. Remove all Hugo-specific paths, references to /content/, themes/, layouts/
3. Adapt CONTENT_REPO_PATH references for standalone repo
4. Write docs/governance/naming-conventions.md
5. Verify docs/ directory exists; create docs/{category}/ if needed

## Verification Steps
1. Verify docs/governance/naming-conventions.md exists
2. Verify no Hugo-specific paths remain
3. Verify document is self-contained and references only foss-launcher paths

## Expected Artifacts
- docs/governance/naming-conventions.md

**Risk**: LOW — documentation only
**Rollback**: Delete docs/governance/naming-conventions.md

## Done Criteria
- [ ] docs/governance/naming-conventions.md exists
- [ ] No Hugo-specific content
- [ ] Reviewable by operator
# TC-GV-002: Port write boundaries doc from aspose.org

**ID**: GV-002
**Title**: Port write boundaries doc from aspose.org
**Purpose**: Create docs/governance/write-boundaries.md adapted from aspose.org equivalent

## Scope
Port the write-boundaries.md governance doc from aspose.org, removing Hugo-specific references.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/docs/governance/write-boundaries.md

## Allowed Changes
- docs/governance/write-boundaries.md

## Forbidden Changes
- AGENTS.md
- skills/
- scripts/

## Dependencies
- RG-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/docs/governance/write-boundaries.md
2. Remove all Hugo-specific paths, references to /content/, themes/, layouts/
3. Adapt CONTENT_REPO_PATH references for standalone repo
4. Write docs/governance/write-boundaries.md
5. Verify docs/ directory exists; create docs/{category}/ if needed

## Verification Steps
1. Verify docs/governance/write-boundaries.md exists
2. Verify no Hugo-specific paths remain
3. Verify document is self-contained and references only foss-launcher paths

## Expected Artifacts
- docs/governance/write-boundaries.md

**Risk**: LOW — documentation only
**Rollback**: Delete docs/governance/write-boundaries.md

## Done Criteria
- [ ] docs/governance/write-boundaries.md exists
- [ ] No Hugo-specific content
- [ ] Reviewable by operator
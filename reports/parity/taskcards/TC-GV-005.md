# TC-GV-005: Port DAR policy doc from aspose.org

**ID**: GV-005
**Title**: Port DAR policy doc from aspose.org
**Purpose**: Create docs/governance/dar-policy.md adapted from aspose.org equivalent

## Scope
Port the dar-policy.md governance doc from aspose.org, removing Hugo-specific references.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/docs/governance/dar-policy.md

## Allowed Changes
- docs/governance/dar-policy.md

## Forbidden Changes
- AGENTS.md
- skills/
- scripts/

## Dependencies
- RG-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/docs/governance/dar-policy.md
2. Remove all Hugo-specific paths, references to /content/, themes/, layouts/
3. Adapt CONTENT_REPO_PATH references for standalone repo
4. Write docs/governance/dar-policy.md
5. Verify docs/ directory exists; create docs/{category}/ if needed

## Verification Steps
1. Verify docs/governance/dar-policy.md exists
2. Verify no Hugo-specific paths remain
3. Verify document is self-contained and references only foss-launcher paths

## Expected Artifacts
- docs/governance/dar-policy.md

**Risk**: LOW — documentation only
**Rollback**: Delete docs/governance/dar-policy.md

## Done Criteria
- [ ] docs/governance/dar-policy.md exists
- [ ] No Hugo-specific content
- [ ] Reviewable by operator
# TC-GV-001: Port evidence governance doc from aspose.org

**ID**: GV-001
**Title**: Port evidence governance doc from aspose.org
**Purpose**: Create docs/governance/evidence-governance.md adapted from aspose.org equivalent

## Scope
Port the evidence-governance.md governance doc from aspose.org, removing Hugo-specific references.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/docs/governance/evidence-governance.md

## Allowed Changes
- docs/governance/evidence-governance.md

## Forbidden Changes
- AGENTS.md
- skills/
- scripts/

## Dependencies
- RG-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/docs/governance/evidence-governance.md
2. Remove all Hugo-specific paths, references to /content/, themes/, layouts/
3. Adapt CONTENT_REPO_PATH references for standalone repo
4. Write docs/governance/evidence-governance.md
5. Verify docs/ directory exists; create docs/{category}/ if needed

## Verification Steps
1. Verify docs/governance/evidence-governance.md exists
2. Verify no Hugo-specific paths remain
3. Verify document is self-contained and references only foss-launcher paths

## Expected Artifacts
- docs/governance/evidence-governance.md

**Risk**: LOW — documentation only
**Rollback**: Delete docs/governance/evidence-governance.md

## Done Criteria
- [ ] docs/governance/evidence-governance.md exists
- [ ] No Hugo-specific content
- [ ] Reviewable by operator
# TC-GV-008: Port docs/workflows/claim-injection.md

**ID**: GV-008
**Title**: Port docs/workflows/claim-injection.md
**Purpose**: Create docs/workflows/claim-injection.md adapted from aspose.org workflow doc

## Scope
Port claim-injection.md from aspose.org workflows, adapting for standalone repo.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/claim-injection.md

## Allowed Changes
- docs/workflows/claim-injection.md

## Forbidden Changes
- AGENTS.md
- skills/
- scripts/

## Dependencies
- GV-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/claim-injection.md
2. Remove Hugo-specific references
3. Adapt skill IDs using docs/id-mapping.md
4. Write docs/workflows/claim-injection.md

## Verification Steps
1. Verify docs/workflows/claim-injection.md exists
2. Verify skill IDs use foss-launcher numbering

## Expected Artifacts
- docs/workflows/claim-injection.md

**Risk**: LOW — documentation only
**Rollback**: Delete docs/workflows/claim-injection.md

## Done Criteria
- [ ] docs/workflows/claim-injection.md exists
- [ ] Skill IDs adapted to foss-launcher scheme
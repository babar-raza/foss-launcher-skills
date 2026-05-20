# TC-GV-009: Port docs/workflows/completion-verification.md

**ID**: GV-009
**Title**: Port docs/workflows/completion-verification.md
**Purpose**: Create docs/workflows/completion-verification.md adapted from aspose.org workflow doc

## Scope
Port completion-verification.md from aspose.org workflows, adapting for standalone repo.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/completion-verification.md

## Allowed Changes
- docs/workflows/completion-verification.md

## Forbidden Changes
- AGENTS.md
- skills/
- scripts/

## Dependencies
- GV-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/completion-verification.md
2. Remove Hugo-specific references
3. Adapt skill IDs using docs/id-mapping.md
4. Write docs/workflows/completion-verification.md

## Verification Steps
1. Verify docs/workflows/completion-verification.md exists
2. Verify skill IDs use foss-launcher numbering

## Expected Artifacts
- docs/workflows/completion-verification.md

**Risk**: LOW — documentation only
**Rollback**: Delete docs/workflows/completion-verification.md

## Done Criteria
- [ ] docs/workflows/completion-verification.md exists
- [ ] Skill IDs adapted to foss-launcher scheme
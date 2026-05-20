# TC-GV-006: Port docs/workflows/causal-backtracking.md

**ID**: GV-006
**Title**: Port docs/workflows/causal-backtracking.md
**Purpose**: Create docs/workflows/causal-backtracking.md adapted from aspose.org workflow doc

## Scope
Port causal-backtracking.md from aspose.org workflows, adapting for standalone repo.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/causal-backtracking.md

## Allowed Changes
- docs/workflows/causal-backtracking.md

## Forbidden Changes
- AGENTS.md
- skills/
- scripts/

## Dependencies
- GV-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/causal-backtracking.md
2. Remove Hugo-specific references
3. Adapt skill IDs using docs/id-mapping.md
4. Write docs/workflows/causal-backtracking.md

## Verification Steps
1. Verify docs/workflows/causal-backtracking.md exists
2. Verify skill IDs use foss-launcher numbering

## Expected Artifacts
- docs/workflows/causal-backtracking.md

**Risk**: LOW — documentation only
**Rollback**: Delete docs/workflows/causal-backtracking.md

## Done Criteria
- [ ] docs/workflows/causal-backtracking.md exists
- [ ] Skill IDs adapted to foss-launcher scheme
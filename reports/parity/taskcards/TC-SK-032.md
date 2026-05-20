# TC-SK-032: Port missing skill: pipeline-harden (18.6KB)

**ID**: SK-032
**Title**: Port missing skill: pipeline-harden (18.6KB)
**Purpose**: Create skills/pipeline-harden.md ported from aspose.org

## Scope
Port aspose.org skills/pipeline-harden.md to foss-launcher, adapting for standalone repo.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/pipeline-harden.md

## Allowed Changes
- skills/pipeline-harden.md
- skills/registry.yaml

## Forbidden Changes
- scripts/

## Dependencies
- RG-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/skills/pipeline-harden.md
2. Remove Hugo-specific references
3. Adapt script paths and ID references for foss-launcher
4. Write skills/pipeline-harden.md
5. Add entry to skills/registry.yaml (assign next available ID)
6. Run python scripts/sync_commands.py --sync && python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. skills/pipeline-harden.md exists
3. Mirror sync check passes

## Expected Artifacts
- skills/pipeline-harden.md
- Updated skills/registry.yaml

**Risk**: LOW — new file, no changes to existing
**Rollback**: Delete skills/pipeline-harden.md; remove registry entry

## Done Criteria
- [ ] skills/pipeline-harden.md exists
- [ ] Registry entry for pipeline-harden added with valid ID
- [ ] validate_skills.py passes
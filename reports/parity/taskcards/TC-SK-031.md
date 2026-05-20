# TC-SK-031: Port missing skill: blog-migrate (7.65KB)

**ID**: SK-031
**Title**: Port missing skill: blog-migrate (7.65KB)
**Purpose**: Create skills/blog-migrate.md ported from aspose.org

## Scope
Port aspose.org skills/blog-migrate.md to foss-launcher, adapting for standalone repo.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/blog-migrate.md

## Allowed Changes
- skills/blog-migrate.md
- skills/registry.yaml

## Forbidden Changes
- scripts/

## Dependencies
- RG-001

## Implementation Steps
1. Read D:/onedrive/Documents/GitHub/aspose.org/skills/blog-migrate.md
2. Remove Hugo-specific references
3. Adapt script paths and ID references for foss-launcher
4. Write skills/blog-migrate.md
5. Add entry to skills/registry.yaml (assign next available ID)
6. Run python scripts/sync_commands.py --sync && python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. skills/blog-migrate.md exists
3. Mirror sync check passes

## Expected Artifacts
- skills/blog-migrate.md
- Updated skills/registry.yaml

**Risk**: LOW — new file, no changes to existing
**Rollback**: Delete skills/blog-migrate.md; remove registry entry

## Done Criteria
- [ ] skills/blog-migrate.md exists
- [ ] Registry entry for blog-migrate added with valid ID
- [ ] validate_skills.py passes
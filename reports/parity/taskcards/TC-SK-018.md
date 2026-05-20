# TC-SK-018: Update skill content: new-blog-post (+4.3KB gap)

**ID**: SK-018
**Title**: Update skill content: new-blog-post (+4.3KB gap)
**Purpose**: Close content depth gap for new-blog-post (foss 5.85KB vs aspose 10.11KB)

## Scope
Add missing sections from aspose.org new-blog-post.md to foss-launcher new-blog-post.md.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/new-blog-post.md
- skills/new-blog-post.md

## Allowed Changes
- skills/new-blog-post.md

## Forbidden Changes
- skills/registry.yaml
- scripts/

## Dependencies
- None

## Implementation Steps
1. Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/new-blog-post.md
2. Read foss-launcher version: skills/new-blog-post.md
3. Diff the two versions section by section
4. Identify sections present in aspose.org but absent or truncated in foss-launcher
5. Add missing sections, preserving foss-launcher's organization
6. Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync

## Verification Steps
1. python scripts/validate_skills.py exits 0
2. python scripts/sync_commands.py --check exits 0
3. wc -c skills/new-blog-post.md is within 20% of aspose.org version

## Expected Artifacts
- Updated skills/new-blog-post.md

**Risk**: LOW — documentation only, mirrors synced after
**Rollback**: git revert skills/new-blog-post.md

## Done Criteria
- [ ] skills/new-blog-post.md size is within 20% of aspose.org equivalent
- [ ] validate_skills.py passes
- [ ] Mirror sync passes
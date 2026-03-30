---
name: knowledge-update
id: S-14
description: >
  Refresh the knowledge model from source using scout, enrich, promote, and index.
args: "{family} {platform} {repo-path}"
---

# S-14: Knowledge Update

Mirror of the canonical contract in `skills/knowledge-update.md`.

Current pipeline:
```bash
python scripts/pipeline/scout.py {family} {platform} {repo-path} knowledge/{family}/{platform}/scout/
python scripts/pipeline/enrich.py {family} {platform}
python scripts/pipeline/promote.py {family} {platform}
python scripts/pipeline/index.py {family} {platform}
python scripts/pipeline/site_planner.py {family} {platform} --mode update
```

After the pipeline completes, review the site planner delta output:
- `pages_to_add`: create new pages using `/new-docs-page`, `/new-kb-howto`, or `/new-blog-post` as appropriate
- `pages_to_update`: re-run the relevant generation skill for each affected page
- `pages_to_remove`: review manually before deleting — removals require human judgment

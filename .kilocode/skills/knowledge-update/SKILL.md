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
```

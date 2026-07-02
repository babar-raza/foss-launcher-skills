---
name: semantic-diff
id: S-104
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-104: Semantic Diff

Converts knowledge_delta.json string arrays into typed semantic change objects
(API_ADDED, API_MODIFIED, API_REMOVED, FEATURE_ADDED, FEATURE_REMOVED, etc.).

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.knowledge.semantic_diff {family} {platform}
```

Output: `reports/refresh_review/{family}/{platform}/semantic_changes.json`

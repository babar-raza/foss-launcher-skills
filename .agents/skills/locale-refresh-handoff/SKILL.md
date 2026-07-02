---
name: locale-refresh-handoff
id: S-107
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-107: Locale Refresh Handoff

After body updates, identifies locale equivalents requiring re-translation.
Routes pages with <3 changed sentences to S-75 and >=3 sentences to S-56.

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.locale_refresh_handoff \
    {family} {platform} --receipts reports/refresh_review/{family}/{platform}/receipts/
```

Output: `reports/refresh_review/{family}/{platform}/locale_handoff.yaml`

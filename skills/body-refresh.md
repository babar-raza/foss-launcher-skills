---
name: body-refresh
id: S-105
description: >
  Execute body prose updates for docs/KB/blog pages based on semantic changes.
args: "{family} {platform} [--dry-run|--execute] [--page path]"
---

# S-105: Body Refresh

Executes body prose updates for docs/KB/blog pages. Reads body_impact.json and
semantic_changes.json, applies surgical updates, and writes content via
safe_content_write() with S-73 context.

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.body_refresh {family} {platform} --dry-run
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.body_refresh {family} {platform} --execute
```

Output: `reports/refresh_review/{family}/{platform}/receipts/*.yaml`

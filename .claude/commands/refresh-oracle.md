---
name: refresh-oracle
id: S-106
description: >
  Skill description pending
---

# S-106: Refresh Oracle

Validates refreshed content against source truth. Composes prose_stale_scan.py
to detect stale prose, checks API symbol validity, and runs cross-page propagation.

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.refresh_oracle \
    {family} {platform} --receipts reports/refresh_review/{family}/{platform}/receipts/
```

Output: `reports/refresh_review/{family}/{platform}/oracle_verdicts/*.yaml`

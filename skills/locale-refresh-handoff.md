---
name: locale-refresh-handoff
id: S-107
description: >
  Queue locale equivalents for re-translation after body refresh updates.
args: "{family} {platform} [--receipts path]"
---

# S-107: Locale Refresh Handoff

After body updates, identifies locale equivalents requiring re-translation.
Routes pages with <3 changed sentences to S-75 and >=3 sentences to S-56.

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.locale_refresh_handoff \
    {family} {platform} --receipts reports/refresh_review/{family}/{platform}/receipts/
```

Output: `reports/refresh_review/{family}/{platform}/locale_handoff.yaml`

## Quality Gate (RG-004)

After locale propagation completes, run the topology check before committing locale files:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/check_locale_topology.py \
  --source content/{site}/{family}/{platform}/_index.md \
  --locales content/{site}/*/{{family}}/{platform}/_index.md \
  --json
```

Expected: `"mismatches": []`. Any mismatch indicates a locale file is missing or has
extra H2 headings compared to the English source. Fix via S-75 (locale-patch) or
re-translation before committing.

---
name: locale-refresh-handoff
id: S-107
description: >
  Skill description pending
---

# S-107: Locale Refresh Handoff

After body updates, identifies locale equivalents requiring re-translation.
Routes pages with <3 changed sentences to S-75, >=3 sentences to S-HT-01, and any
locale whose H2 heading structure no longer matches English (RG-004 mismatch) to
S-HT-01 as `STRUCTURAL_DRIFT` — regardless of text-diff size, since a removed or
restructured section has no literal text for S-75 to patch against, and S-75's own
safety rules refuse locale files that have diverged structurally from source.

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.locale_refresh_handoff \
    {family} {platform} --receipts reports/refresh_review/{family}/{platform}/receipts/
```

Output: `reports/refresh_review/{family}/{platform}/locale_handoff.yaml`

## Quality Gate (RG-004)

The H2-topology check now runs automatically, per locale, inside every S-107 run —
any locale entry with `handoff_status: STRUCTURAL_DRIFT` and a `topology_detail`
field already failed this check; route it to `S-HT-01`, never to `S-75`. The
standalone CLI below remains available as an independent spot-check or CI gate
(e.g. to verify zero mismatches after a translation pass completes):

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/check_locale_topology.py \
  --source content/{site}/{family}/{platform}/_index.md \
  --locales content/{site}/*/{{family}}/{platform}/_index.md \
  --json
```

Expected: `"mismatches": []`. Any mismatch indicates a locale file is missing or has
extra H2 headings compared to the English source.

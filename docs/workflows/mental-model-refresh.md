# Mental Model Refresh Protocol

> Source: AGENTS.md §3
> Status: Current (restored from archive 2026-06-24)
> Override token: 20260624-113217-docs-workflows-mental-model-refresh-md

Before editing any content page for `{family}/{platform}`:

1. **Read** `knowledge/{family}/{platform}/merged/model.yaml`
2. **Check stale_since**: If `stale_since` is not null — the knowledge model is outdated.
   Do **not** edit content until a knowledge-diff (S-12) and knowledge-update (S-14) have been run.
3. **Read** `knowledge/{family}/{platform}/merged/claims.json` — verify claims are current
4. **Read** `knowledge/{family}/{platform}/merged/api_surface.md` — for API grounding
5. Only then proceed to content tasks

## Plan Normalization

If resuming a plan last modified >7 days ago, or any plan with archive/postmortem/sprint sections,
run `/plan-normalize {plan-file}` (S-91) before executing it.

## Quick Check (bash)

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -c "
import yaml
m = yaml.safe_load(open('knowledge/{family}/{platform}/merged/model.yaml'))
stale = m.get('stale_since')
print('STALE' if stale else 'CURRENT', '—', stale or 'ok')
"
```

## Related Skills

| Need | Skill |
|------|-------|
| Detect upstream repo changes | `/knowledge-diff {family} {platform}` (S-12) |
| Re-extract knowledge from FOSS repo | `/knowledge-update {family} {platform}` (S-14) |
| Session start checklist | `/session-start` (S-77) |

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/mental-model-refresh.md](../_archive/pre-refactor/workflows/mental-model-refresh.md)

---
name: gap-apply
id: S-65
description: >
  Execute the wave-ordered remediation plan produced by gap-plan (S-63). Applies
  Wave 1 auto-fixes, Wave 2 LLM-planned substitutions, Wave 3 page generation,
  and halts at Wave 4 human-required fixes.
args: "{family} {platform} [--waves 1,2,3] [--dry-run]"
---

# S-65: Gap Apply — Execute Wave-Ordered Fix Specs

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--waves 1,2,3] [--dry-run]`

## Purpose

Execute the wave-ordered remediation plan produced by S-63 (gap-plan). Applies Wave 1
auto-fixes via batch scripts, Wave 2 LLM-planned substitutions from the fix spec file,
Wave 3 page generation via S-19 (page-draft), and halts at Wave 4 (human-required fixes).

This closes the handoff gap between S-63 (plan generation) and actual content repair.
Full gap remediation pipeline: `S-62 → S-63 → S-65 → S-23 → S-56 → write`.

## Pre-conditions

1. `reports/agents/remediation/{family}-{platform}/plan.md` must exist (run `/gap-plan {family} {platform}` first)
2. `reports/agents/remediation/{family}-{platform}/fix_specs.json` must exist
3. Knowledge bootstrap confirmed passing for `{family} {platform}`

## Steps

### Wave 1 — Auto-fixes (deterministic)

```bash
python scripts/gap-eval/apply_wave1.py {family} {platform} [--dry-run]
```

Wave 1 applies deterministic fixes: wrong API names, format strings, structural corrections.
All Wave 1 fixes are idempotent and safe to re-run.

### Wave 2 — LLM substitutions

```bash
python scripts/gap-eval/apply_wave2.py {family} {platform} [--dry-run]
```

Wave 2 applies pre-computed old→new substitutions from `fix_specs.json`.
Each substitution is verified by running the ground-check (S-23) after application.

### Wave 3 — Page generation

For each missing page identified in the plan:
```bash
/page-draft {family} {platform} {slug}
```

### Wave 4 — Halt and escalate

Wave 4 findings are items that require human judgment. Print each item:
```
WAVE 4 — HUMAN REQUIRED
File: {path}
Finding: {description}
Reason: {why automated fix is not safe}
Recommended action: {suggested next step}
```

## Verification after all waves

1. Re-run gap-eval to confirm findings are resolved:
   ```bash
   /gap-eval {family} {platform}
   ```
   Expected: PUBLICATION READY or CONDITIONAL (no M-findings remaining)

2. Run audit on modified files:
   ```bash
   python scripts/pipeline/audit.py --files {modified-files}
   ```

## Post-conditions

- Wave 1 fixes applied (deterministic, idempotent)
- Wave 2 substitutions applied and verified
- Wave 3 new pages generated
- Wave 4 items documented and escalated to human
- Gap-eval re-run confirms no remaining M-findings

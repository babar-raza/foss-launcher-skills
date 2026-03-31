---
name: gap-plan
id: S-44
description: >
  Wave-ordered remediation planning from gap-eval findings
args: "{family} {platform} [--wave 1|2|3|4|all]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-44: Gap Plan — Wave-Ordered Remediation Planning

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--dry-run]`

## Purpose
Convert S-43 gap-eval findings into an exact, wave-ordered remediation plan. Uses LLM to generate precise old->new substitutions for each finding, grounded in clone cache evidence. Produces a machine-applicable plan ready for S-40/S-41.

## Pre-conditions
1. `reports/gap-analysis/{family}-{platform}.json` must exist (run `/gap-eval {family} {platform}` first)
2. Clone cache at `{FOSS_LAUNCHER_PATH}/runs/.clone_cache/aspose_{family}_{platform}/` (for evidence retrieval)
3. `LLM_API_KEY` env var recommended for best fix quality (falls back to Ollama llama3.2)

## Steps

### Step 1: Classify findings by wave

```bash
python scripts/gap-eval/fix_spec.py {family} {platform} --dry-run
```

This shows the wave breakdown without writing files. Review wave assignments before proceeding.

### Step 2: Generate full remediation plan

```bash
python scripts/gap-eval/fix_spec.py {family} {platform}
```

Outputs:
- `reports/agents/remediation/{family}-{platform}/plan.md` — wave-ordered plan with exact fix specs
- `reports/agents/remediation/{family}-{platform}/fix_specs.json` — machine-readable fix specs

### Step 3: Apply Wave 1 fixes (auto)

Wave 1 findings have `strategy: auto` — scripted, safe to run in bulk using S-40:

```bash
/batch-eval-fix {family} {platform}
```

Or apply specific category fixes:
```bash
/category-fix {family} {platform} {fixer_name}
```

### Step 4: Apply Wave 2 fixes (LLM-planned)

Review each fix spec in `plan.md`. Apply file-by-file using the exact `old` -> `new` substitutions.
Each fix is bounded to a single content block — no side effects.

### Step 5: Rerun gap-eval to verify

```bash
python scripts/gap-eval/run.py {family} {platform}
```

Delta section will show all prior findings as `fixed` with 0 regressions if applied correctly.

### Step 6: Wave 3 (page generation)

For missing-section findings, use the appropriate page generation skill:
```bash
/page-draft {family} {platform} {section}
```

## Post-conditions
- `reports/agents/remediation/{family}-{platform}/plan.md` written with wave-ordered fixes
- `reports/agents/remediation/{family}-{platform}/fix_specs.json` written for machine application
- All Wave 2 NEEDS_HUMAN_EDIT blocks identified with partial evidence

## Wave Order

| Wave | Strategy | Trigger | Condition |
|------|----------|---------|-----------|
| 1 | Auto-fix | S-40/S-41 bulk scripts | finding_type in {wrong-package, broken-link, structural-reference-page, internal-class-wrong-package} |
| 2 | LLM-planned | Manual apply per plan | finding_type in {phantom-api, wrong-api-name, wrong-claim, wrong-unit, unimplemented-as-working} |
| 3 | Plan-only | Page generation skills | finding_type = missing-section |
| 4 | Human | Manual review | LLM unavailable or unknown finding type |

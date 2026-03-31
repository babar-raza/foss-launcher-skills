---
name: gap-apply
description: >
  Execute wave-ordered fix specs from gap-plan output (Wave 1 auto, Wave 2 LLM-planned substitutions, Wave 3 page generation, Wave 4 human escalation)
args: "{family} {platform} [--waves 1,2,3] [--dry-run]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-46: Gap Apply — Execute Wave-Ordered Fix Specs

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--waves 1,2,3] [--dry-run]`

## Purpose

Execute the wave-ordered remediation plan produced by S-44 (gap-plan). Closes the handoff
gap between plan generation and actual content repair.

Pipeline position: `S-43 → S-44 → S-46 → S-23 → S-01 → write`

## Pre-conditions

1. `reports/agents/remediation/{family}-{platform}/fix_specs.json` must exist (run `/gap-plan` first)
2. Knowledge bootstrap confirmed for `{family} {platform}` (run `/knowledge-bootstrap`)

## Wave Summary

| Wave | Strategy | How |
|------|----------|-----|
| 1 | Auto-fix | `/batch-eval-fix {family} {platform}` |
| 2 | LLM-planned substitutions | Apply `old` → `new` from fix_specs.json |
| 3 | Page generation | `/page-draft {family} {platform} {section}` |
| 4 | Human | Emit escalation list; halt |

## Steps

### Step 1: Validate plan
Confirm `fix_specs.json` exists and is from the latest gap-eval run. If stale, re-run S-44.

### Step 2: Wave 1 — auto-fixes
```bash
/batch-eval-fix {family} {platform}
```
Then verify: `python scripts/pipeline/audit.py {family} {platform}`

### Step 3: Wave 2 — apply pre-computed substitutions
For each fix in `fix_specs.json` where `wave == 2`:
- Locate the `old` text exactly in the target file
- Replace with `new` text
- If `old` not found: log `SKIP - source changed` (do not fabricate)
- If audit FAIL after apply: revert that file; add to Wave 4 escalation

### Step 4: Wave 3 — generate missing pages
```bash
/page-draft {family} {platform} {section}
```
One invocation per missing-section item in the plan.

### Step 5: Wave 4 — escalation list
Write `reports/agents/remediation/{family}-{platform}/wave4-escalation.md` listing all
items that require human review. Halt; do not apply ad hoc fixes.

### Step 6: Verify
```bash
python scripts/gap-eval/run.py {family} {platform}
```
Delta must show prior Wave 1/2 findings as `fixed`, 0 regressions.

## Post-conditions
- All applicable wave fixes applied
- Wave 4 escalation list written (if any Wave 4 items exist)
- Execution log at `reports/gap-apply/{family}-{platform}-{timestamp}.json`
- Gap-eval delta confirms no regressions

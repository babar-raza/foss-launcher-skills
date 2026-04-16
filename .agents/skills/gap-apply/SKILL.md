---
name: gap-apply
id: S-46
description: >
  Execute wave-ordered fix specs from gap-plan output (Wave 1 auto, Wave 2 LLM-planned substitutions, Wave 3 page generation, Wave 4 human escalation)
args: "{family} {platform} [--waves 1,2,3] [--dry-run]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-46: Gap Apply — Execute Wave-Ordered Fix Specs

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--waves 1,2,3] [--dry-run]`

## Purpose

Execute the wave-ordered remediation plan produced by S-44 (gap-plan). Applies Wave 1
auto-fixes via batch scripts, Wave 2 LLM-planned substitutions from the fix spec file,
Wave 3 page generation via S-19 (page-draft), and halts at Wave 4 (human-required fixes).

This skill closes the handoff gap between S-44 (plan generation) and actual content repair.
It is the final step in the gap remediation pipeline: `S-43 → S-44 → S-46 → S-23 → S-01 → write`.

## Pre-conditions

1. `reports/agents/remediation/{family}-{platform}/plan.md` must exist (run `/gap-plan {family} {platform}` first)
2. `reports/agents/remediation/{family}-{platform}/fix_specs.json` must exist
3. Knowledge bootstrap confirmed passing for `{family} {platform}` (run `/knowledge-bootstrap {family} {platform}`)
4. `LLM_API_KEY` recommended for Wave 2 verification (not required — substitutions are pre-computed in fix_specs.json)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-46 --scope "*"
> ```


### Step 1: Validate plan exists

```bash
.venv/Scripts/python -c "
import json, sys
from pathlib import Path
specs = Path('reports/agents/remediation/{family}-{platform}/fix_specs.json')
if not specs.exists():
    print('ERROR: fix_specs.json not found — run /gap-plan {family} {platform} first')
    sys.exit(1)
data = json.loads(specs.read_text())
waves = {item['wave'] for item in data.get('fixes', [])}
print(f'Plan found: {len(data[\"fixes\"])} fixes across waves {sorted(waves)}')
"
```

If the plan is missing or stale (older than the latest gap-eval run), re-run S-44 first.

### Step 2: Apply Wave 1 fixes (auto)

Wave 1 findings have `strategy: auto` — deterministic scripted fixes, safe to apply in bulk:

```bash
/batch-eval-fix {family} {platform}
```

Or apply by category code if you want finer control:
```bash
/category-fix {family} {platform} {fixer_name}
```

After Wave 1, verify no regressions:
```bash
.venv/Scripts/python scripts/pipeline/audit.py {family} {platform}
```

### Step 3: Apply Wave 2 fixes (LLM-planned substitutions)

Wave 2 has pre-computed `old` → `new` substitutions in `fix_specs.json`. Apply each fix:

For each fix in `fix_specs.json` where `wave == 2`:
1. Locate the target file at `path`
2. Confirm the `old` text is present exactly as specified (byte-for-byte)
3. Replace with `new` text
4. If `old` text not found: log as `SKIP - source changed` and continue (do not fabricate)

After all Wave 2 substitutions, run S-23 (content-check):
```bash
.venv/Scripts/python scripts/pipeline/audit.py --files {modified_files}
```

If audit FAILs on a Wave 2 page: revert that specific file's change and add it to the Wave 4 (human) escalation list.

### Step 4: Wave 3 — Generate missing pages

For each fix in `fix_specs.json` where `wave == 3` (finding_type = missing-section or missing-page):

```bash
/page-draft {family} {platform} {section}
```

Follow the standard generation chain for each missing page. Mark each as complete in a
local checklist before proceeding to the next.

### Step 5: Collect Wave 4 escalation list

Wave 4 items (`wave == 4`, or any items that failed Wave 2 application) require human review.

Emit an escalation report:

```markdown

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-46 --status completed
> ```

## Wave 4 Escalation — {family}/{platform}

Files requiring human review (LLM unavailable, ambiguous fix, or application failed):

| File | Finding | Reason |
|------|---------|--------|
| ... | ... | ... |

Save as: reports/agents/remediation/{family}-{platform}/wave4-escalation.md
```

Halt and route these items to the human maintainer. For each Wave 4 item requiring a targeted
content change, the operator must invoke **S-73 (manual-edit)** with the specific change. Do not
apply ad hoc fixes outside the skill chain — S-73 is the only sanctioned path for
operator-directed targeted edits.

### Step 6: Re-run gap-eval to verify

```bash
python scripts/gap-eval/run.py {family} {platform}
```

The delta section must show prior Wave 1/2 findings as `fixed` with 0 regressions. If
regressions appear, investigate before marking the run complete.

## Post-conditions

- Wave 1 fixes applied via batch scripts; audit passes
- Wave 2 substitutions applied; each substitution traceable to fix_specs.json entry
- Wave 3 missing pages generated via page-draft
- Wave 4 escalation list written to `reports/agents/remediation/{family}-{platform}/wave4-escalation.md`
- Gap-eval delta confirms: prior findings `fixed`, no new regressions
- Execution report written to `reports/gap-apply/{family}-{platform}-{timestamp}.json`

## Failure handling

| Failure | Action |
|---------|--------|
| Plan not found | Halt; run S-44 first |
| Wave 1 script errors | Log and continue with other Wave 1 fixes; add failed files to Wave 4 escalation |
| Wave 2 `old` text not found | Skip (log as `SKIP - source changed`); do not fabricate |
| Wave 2 audit FAIL after apply | Revert that file's change; add to Wave 4 escalation |
| Wave 3 page-draft STOP | Halt page generation for that item; add to Wave 4 escalation |
| Knowledge bootstrap stale | Halt all waves; run S-12 → S-14 first |

## Output artifacts

```
reports/gap-apply/{family}-{platform}-{timestamp}.json    # execution log
reports/agents/remediation/{family}-{platform}/wave4-escalation.md  # Wave 4 items
```

The execution log format:
```json
{
  "family": "{family}",
  "platform": "{platform}",
  "executed_at": "ISO timestamp",
  "waves_attempted": [1, 2, 3],
  "wave1_fixes_applied": 0,
  "wave2_substitutions_applied": 0,
  "wave2_skipped": 0,
  "wave3_pages_generated": 0,
  "wave4_escalated": 0,
  "gap_eval_delta": "PASS | REGRESSIONS"
}
```

---
name: gap-plan
id: S-63
description: >
  Convert gap-eval findings into an exact, wave-ordered remediation plan. Uses LLM
  to generate precise old→new substitutions for each finding, grounded in clone cache
  evidence. Produces a machine-applicable plan ready for gap-apply (S-65).
args: "{family} {platform} [--dry-run]"
---

# S-63: Gap Plan — Wave-Ordered Remediation Planning

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--dry-run]`

## Purpose

Convert S-62 (gap-eval) findings into an exact, wave-ordered remediation plan. Uses LLM
to generate precise old→new substitutions for each finding, grounded in clone cache evidence.
Produces a machine-applicable plan ready for S-65 (gap-apply).

## Pre-conditions

1. `reports/gap-analysis/{family}-{platform}.json` must exist (run `/gap-eval {family} {platform}` first)
2. Clone cache at `runs/.clone_cache/aspose_{family}_{platform}/` (for evidence retrieval)
3. `LLM_API_KEY` env var recommended for best fix quality (falls back to Ollama llama3.2)

## Steps

1. **Load gap-eval report**:
   ```bash
   python scripts/gap-eval/gap_plan.py {family} {platform} [--dry-run]
   ```

2. **Wave assignment**: Findings are assigned to waves by severity and fix complexity:

   | Wave | Finding type | Mechanism |
   |---|---|---|
   | 1 | Deterministic fixes (wrong API names, format strings) | batch scripts |
   | 2 | LLM substitutions (prose accuracy, evidence gaps) | fix_specs.json |
   | 3 | Page generation (missing pages identified by gap-eval) | S-19 page-draft |
   | 4 | Human-required fixes (ambiguous or high-risk changes) | escalate |

3. **Output files**:
   - `reports/agents/remediation/{family}-{platform}/plan.md` — human-readable plan
   - `reports/agents/remediation/{family}-{platform}/fix_specs.json` — machine-applicable specs

4. **Review plan** before executing:
   - Wave 1 count (safe to auto-apply)
   - Wave 2 count (LLM-generated; verify spot-check)
   - Wave 3 count (new pages to generate)
   - Wave 4 count (escalated to human)

5. **Proceed to apply**:
   ```bash
   /gap-apply {family} {platform}
   ```

## Post-conditions

- `plan.md` written with wave-ordered remediation steps
- `fix_specs.json` written with machine-applicable old→new substitutions
- All M-severity findings addressed in waves 1–3 or escalated to wave 4

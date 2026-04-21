---
name: gap-eval
id: S-62
description: >
  Evaluate content against clone cache ground truth using a three-tier
  verification architecture (deterministic → vector → LLM). Produces a
  structured findings report with verdict: PUBLICATION READY / CONDITIONAL /
  NOT PUBLISHABLE.
args: "{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--dry-run]"
---

# S-62: Gap Eval — Content Verification Against Clone Cache

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--dry-run]`

## Purpose

Evaluate all content for a family/platform against clone cache ground truth using a three-tier
verification architecture (deterministic → vector → LLM). Produces a structured findings report
and updates the per-product state file for delta tracking.

**Parallel to the evidence pipeline** (S-43–S-46): gap-eval uses clone cache ground truth;
the evidence pipeline uses knowledge model artifacts. Both pipelines coexist and complement each other.

## Pre-conditions

1. Clone cache must exist at `runs/.clone_cache/aspose_{family}_{platform}/`
2. Profile must exist at `scripts/gap-eval/profiles/{family}/{platform}.yaml`
   - If missing, run will create a minimal auto-detected profile
3. Optional (Tier 2): API vectors at `knowledge/_vectors/{family}/{platform}/api.vectors.json`
   - Build with: `python scripts/pipeline/embed.py gap-index {family} {platform}`
4. Optional (Tier 3 LLM): `LLM_API_KEY` env var set (falls back to Ollama)

## Steps

1. **Validate profile**:
   ```bash
   python scripts/gap-eval/validate_profile.py {family} {platform}
   ```

2. **(Optional) Build API surface vectors** for Tier 2:
   ```bash
   python scripts/pipeline/embed.py gap-index {family} {platform}
   ```
   Skip if vectors already exist.

3. **Run evaluation**:
   ```bash
   # All tiers:
   python scripts/gap-eval/run.py {family} {platform} --scope all

   # Tier 1+2 only (faster, no LLM):
   python scripts/gap-eval/run.py {family} {platform} --no-llm

   # Specific scope:
   python scripts/gap-eval/run.py {family} {platform} --scope {scope}
   ```

4. **Review output**:
   - Report: `reports/gap-analysis/{family}-{platform}.md`
   - Findings JSON: `reports/gap-analysis/{family}-{platform}.json`
   - State file: `reports/gap-analysis/state/{family}-{platform}.json`

5. **Interpret verdict**:

   | Verdict | Meaning | Next step |
   |---|---|---|
   | `PUBLICATION READY` | No M or S findings | Ship content |
   | `CONDITIONAL` | S-findings only or M in blog | Fix S-findings or accept conditionally |
   | `NOT PUBLISHABLE` | M-findings in core content | Run `/gap-plan {family} {platform}` |

6. **If NOT PUBLISHABLE** — generate fix plan:
   ```bash
   /gap-plan {family} {platform}
   ```

## Finding Severity Levels

| Severity | Meaning |
|---|---|
| M (Major) | Content contradicts clone cache; blocks publication |
| S (Standard) | Content gap or inaccuracy; conditional on site type |
| I (Informational) | Observation; no action required |

## Post-conditions

- `reports/gap-analysis/{family}-{platform}.json` written with structured findings
- Verdict rendered: PUBLICATION READY / CONDITIONAL / NOT PUBLISHABLE
- State file updated for delta tracking

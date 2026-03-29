# S-43: Gap Eval — Content Verification Against Clone Cache

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--dry-run]`

## Purpose
Evaluate all content for a family/platform against clone cache ground truth using a three-tier verification architecture (deterministic → vector → LLM). Produces a structured findings report and updates the per-product state file for delta tracking.

## Pre-conditions
1. Clone cache must exist at `{FOSS_LAUNCHER_PATH}/runs/.clone_cache/aspose_{family}_{platform}/`
2. Profile must exist at `scripts/gap-eval/profiles/{family}/{platform}.yaml`
   - If missing, run will create a minimal auto-detected profile
3. Optional (Tier 2): API vectors at `knowledge/_vectors/{family}/{platform}/api.vectors.json`
   - Build with: `python scripts/pipeline/embed.py gap-index {family} {platform}`
4. Optional (Tier 3 LLM): `LLM_API_KEY` env var set for professionalize.com (falls back to Ollama)

## Steps

### Step 1: Validate profile

```bash
python scripts/gap-eval/validate_profile.py {family} {platform}
```

If profile validation fails on clone cache path → check `FOSS_LAUNCHER_PATH` env var.

### Step 2: (Optional) Build API surface vectors for Tier 2

```bash
python scripts/pipeline/embed.py gap-index {family} {platform}
```

Skip if `knowledge/_vectors/{family}/{platform}/api.vectors.json` already exists.

### Step 3: Run evaluation

```bash
python scripts/gap-eval/run.py {family} {platform} [--scope {scope}]
```

With all tiers active:
```bash
python scripts/gap-eval/run.py {family} {platform} --scope all
```

Skip LLM (Tier 1+2 only, faster):
```bash
python scripts/gap-eval/run.py {family} {platform} --no-llm
```

### Step 4: Review output

- **Report**: `reports/gap-analysis/{family}-{platform}.md`
- **Findings JSON**: `reports/gap-analysis/{family}-{platform}.json`
- **State file**: `reports/gap-analysis/state/{family}-{platform}.json`

### Step 5: Interpret verdict

| Verdict | Meaning | Next step |
|---------|---------|-----------|
| PUBLICATION READY | No M or S findings | Ship content |
| CONDITIONAL | S-findings only or M in blog | Fix S-findings or accept conditionally |
| NOT PUBLISHABLE | M-findings in core content | Run `/gap-plan {family} {platform}` |

### Step 6: If NOT PUBLISHABLE — generate fix plan

```bash
/gap-plan {family} {platform}
```

## Post-conditions
- `reports/gap-analysis/{family}-{platform}.md` written with 8-section report
- `reports/gap-analysis/{family}-{platform}.json` written with machine-readable findings
- `reports/gap-analysis/state/{family}-{platform}.json` updated (enables delta on next run)
- Profile `discovered_actuals.last_baseline_sha` updated to clone cache HEAD SHA
- Exit code 2 if verdict = NOT PUBLISHABLE (enables CI blocking)

## Repeatability
- Same content + same clone cache SHA → same findings (except `run_date`)
- Rerun after fixes → delta section shows prior findings as `fixed`, new findings listed
- Finding IDs are stable: `F-{family}-{platform}-{type}-{sha8(file+line+old_value[:20])}`

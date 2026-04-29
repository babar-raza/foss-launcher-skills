<!-- CONTRACT: scripts/gap-eval/src/run.py
     purpose: verify content against clone cache ground truth using three-tier architecture
     preconditions: clone cache exists; profile at scripts/gap-eval/profiles/{family}/{platform}.yaml
     postcondition: gap-eval report with verdict (PUBLICATION READY / CONDITIONAL / NOT PUBLISHABLE)
     idempotent: yes — same inputs and clone cache SHA produce same Tier 1/2 results
     verified: 2026-04-11
-->
# S-43: Gap Eval — Content Verification Against Clone Cache

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--dry-run]`

## Purpose
Evaluate all content for a family/platform against clone cache ground truth using a three-tier verification architecture (deterministic → vector → LLM). Produces a structured findings report and updates the per-product state file for delta tracking.

## Pre-conditions
1. Clone cache must exist at `runs/.clone_cache/aspose_{family}_{platform}/`
2. Profile must exist at `scripts/gap-eval/profiles/{family}/{platform}.yaml`
   - If missing, run will create a minimal auto-detected profile
3. Optional (Tier 2): API vectors at `knowledge/_vectors/{family}/{platform}/api.vectors.json`
   - Build with: `python scripts/pipeline/commands/knowledge/embed.py gap-index {family} {platform}`
4. Optional (Tier 3 LLM): `LLM_API_KEY` env var set for professionalize.com (falls back to Ollama)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-43 --scope "*"
> ```


### Step 1: Validate profile

```bash
.venv/Scripts/python scripts/gap-eval/src/validate_profile.py {family} {platform}
```

If profile validation fails on clone cache path → check `ASPOSE_CLONE_CACHE` env var or verify clone cache exists.

### Step 2: (Optional) Build API surface vectors for Tier 2

```bash
.venv/Scripts/python scripts/pipeline/commands/knowledge/embed.py gap-index {family} {platform}
```

Skip if `knowledge/_vectors/{family}/{platform}/api.vectors.json` already exists.

### Step 3: Run evaluation

```bash
.venv/Scripts/python scripts/gap-eval/src/run.py {family} {platform} [--scope {scope}]
```

With all tiers active:
```bash
.venv/Scripts/python scripts/gap-eval/src/run.py {family} {platform} --scope all
```

Skip LLM (Tier 1+2 only, faster):
```bash
.venv/Scripts/python scripts/gap-eval/src/run.py {family} {platform} --no-llm
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

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-43 --status completed
> ```

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

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `PRECONDITION FAILED: api_surface.json not found` | Knowledge not bootstrapped | Run `/knowledge-bootstrap {family} {platform}` |
| `PREREQUISITE FAILED: Clone cache not found` | Clone cache absent at `runs/.clone_cache/` | Run `/getting-started` step 4, or set `ASPOSE_CLONE_CACHE` env var |
| `Profile validation failed` | Missing or malformed profile YAML | Check `scripts/gap-eval/profiles/{family}/{platform}.yaml`; delete and re-run to auto-detect |
| Exit code 2 (NOT PUBLISHABLE) | Mandatory findings in core content | Run `/gap-plan {family} {platform}` to generate fix specs |
| `LLM endpoint unreachable` (Tier 3) | LLM API key missing or endpoint down | Set `LLM_API_KEY` env var, or use `--no-llm` to skip Tier 3 |
| `api.vectors.json not found` (Tier 2) | Vectors not built | Run `python scripts/pipeline/commands/knowledge/embed.py gap-index {family} {platform}` |

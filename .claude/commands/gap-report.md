# S-45: Gap Report — Cross-Product Synthesis

**Arguments**: $ARGUMENTS
Expected format: `[--products all|{family/platform},{family/platform},...] [--k {cluster_count}] [--dry-run]`

## Purpose
Synthesize findings across all products into a MASTER-SYNTHESIS update. Uses vector-based clustering and LLM pattern naming to identify systemic error patterns and root causes. Fully automated — no manual pattern identification required.

## Pre-conditions
1. At least 2 `reports/gap-analysis/{family}-{platform}.json` files must exist
   - Run `/gap-eval {family} {platform}` for each product first
2. `LLM_API_KEY` env var recommended for pattern naming and root cause analysis
3. Optional: `PROFESSIONALIZE_API_KEY` for high-quality embeddings (falls back to Ollama, then TF-IDF)

## Steps

### Step 1: Build findings index (optional, for dense vectors)

```bash
python scripts/pipeline/embed.py findings-index
```

Embeds all findings for high-quality clustering. Skip if running in offline mode (TF-IDF fallback).

### Step 2: Run synthesis

For all products:
```bash
python scripts/gap-eval/synthesize.py --products all
```

For specific products:
```bash
python scripts/gap-eval/synthesize.py --products slides/java,slides/python,slides/net
```

Dry run (no file writes, prints synthesis update):
```bash
python scripts/gap-eval/synthesize.py --products all --dry-run
```

Override cluster count:
```bash
python scripts/gap-eval/synthesize.py --k 8
```

### Step 3: Review output

- **Synthesis result JSON**: `reports/gap-analysis/synthesis_result.json`
- **MASTER-SYNTHESIS.md**: Updated with a new `## Synthesis Update — {date}` section
- **Finding vectors**: `knowledge/_vectors/_synthesis/findings.vectors.json`

### Step 4: Review pattern names

LLM-generated pattern names are in `synthesis_result.json`. If pattern descriptions are unclear:
1. Re-run with different k: `--k {smaller_or_larger}`
2. Or edit `MASTER-SYNTHESIS.md` pattern names manually (the update section is clearly delimited)

## Post-conditions
- `reports/gap-analysis/synthesis_result.json` written with clusters, patterns, root causes
- `reports/gap-analysis/MASTER-SYNTHESIS.md` updated with new synthesis section
- `knowledge/_vectors/_synthesis/findings.vectors.json` written if embedding succeeded
- Publish sequence derived deterministically from state files (no LLM for ordering)

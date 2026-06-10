---
name: gap-report
id: S-64
description: >
  Synthesize gap-eval findings across all products into a MASTER-SYNTHESIS update.
  Uses vector-based clustering and LLM pattern naming to identify systemic error
  patterns and root causes.
args: "[--products all|{family/platform},...] [--k {cluster_count}] [--dry-run]"
---

# S-64: Gap Report — Cross-Product Synthesis

**Arguments**: $ARGUMENTS
Expected format: `[--products all|{family/platform},{family/platform},...] [--k {cluster_count}] [--dry-run]`

## Purpose

Synthesize findings across all products into a MASTER-SYNTHESIS update. Uses vector-based
clustering and LLM pattern naming to identify systemic error patterns and root causes.
Fully automated — no manual pattern identification required.

## Pre-conditions

1. At least 2 `reports/gap-analysis/{family}-{platform}.json` files must exist
   - Run `/gap-eval {family} {platform}` for each product first
2. `LLM_API_KEY` env var recommended for pattern naming and root cause analysis
3. Optional: `PROFESSIONALIZE_API_KEY` for high-quality embeddings (falls back to Ollama, then TF-IDF)

## Steps

1. **Run the cross-product synthesis** with `/gap-report`, using existing `reports/gap-analysis/*.json` inputs.

2. **Output**: `reports/gap-analysis/MASTER-SYNTHESIS.md`

3. **Interpret the synthesis**:
   - **Systemic patterns**: Error patterns appearing across multiple products
   - **Root causes**: Pipeline defects that produce recurring findings
   - **Cluster names**: LLM-generated names for finding clusters
   - **Fix priority**: Clusters sorted by frequency × severity

4. **Action on systemic patterns**:
   - Pipeline defects → investigate `scripts/pipeline/` and fix at source
   - Knowledge model gaps → identify missing knowledge extraction steps
   - Template defects → update generation skill templates

## Post-conditions

- `reports/gap-analysis/MASTER-SYNTHESIS.md` updated with cross-product pattern analysis
- Systemic patterns identified with root cause classification
- Fix priorities established for pipeline-level corrections

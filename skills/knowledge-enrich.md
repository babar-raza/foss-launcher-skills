---
name: knowledge-enrich
id: S-61
description: >
  Generate LLM-enriched semantic claims from scout artifacts. Reads verified API
  facts from scout/api_surface.json and writes scout/enriched_claims.json.
  Current replacement for the removed FL enrichment layer.
args: "{family} {platform}"
---

# S-61: Knowledge Enrich — LLM Semantic Enrichment from Scout Artifacts

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Generate LLM-enriched semantic claims from `knowledge/{family}/{platform}/scout/`
artifacts. The enrichment step reads verified API facts from `scout/api_surface.json`,
uses the clone cache for bounded context, and writes `scout/enriched_claims.json`.

## Pre-conditions

1. `knowledge/{family}/{platform}/scout/api_surface.json` must exist (run S-34 repo-scout first)
2. Clone cache accessible at `runs/.clone_cache/aspose_{family}_{platform}/`
3. `LLM_API_KEY` recommended for best claim quality (falls back to TF-IDF)

## Steps

1. **Run enrich**:
   ```bash
   python scripts/pipeline/commands/knowledge/enrich.py {family} {platform}
   ```

2. **Expected output**: `knowledge/{family}/{platform}/scout/enriched_claims.json`
   - Format: JSON array of claim objects
   - Claim ID format: `ERC-{family}-{platform}-{8-char-hash}`
   - Fields: `claim_id`, `text`, `kind`, `confidence`, `claim_source`, `evidence`
   - Claims with confidence < 0.60 are dropped before write

3. **Verify output**:
   ```bash
   python -c "import json; d=json.load(open('knowledge/{family}/{platform}/scout/enriched_claims.json')); print(f'{len(d)} claims, min confidence: {min(c[\"confidence\"] for c in d):.2f}')"
   ```

4. **Proceed to promote**: After enrichment, run S-35 (truth-merge) to promote claims to `merged/`.

## Post-conditions

- `knowledge/{family}/{platform}/scout/enriched_claims.json` exists as a JSON array
- All claims have `confidence >= 0.60`
- Claim IDs follow the `ERC-{family}-{platform}-{hash}` format

## Error handling

| Error | Action |
|-------|--------|
| `api_surface.json` missing | Run S-34 (repo-scout) first |
| LLM API unavailable | Falls back to TF-IDF — output will have lower-confidence claims |
| Clone cache missing | WARN; enrichment continues with reduced context |

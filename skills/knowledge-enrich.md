# S-37: Knowledge Enrich - LLM Semantic Enrichment from Scout Artifacts

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Generate LLM-enriched semantic claims from `knowledge/{family}/{platform}/scout/`
artifacts. The enrichment step reads verified API facts from `scout/api_surface.json`,
uses the clone cache for bounded context, and writes `scout/enriched_claims.json`.
This is the current replacement for the removed FL enrichment layer.

## Pre-conditions

1. `knowledge/{family}/{platform}/scout/api_surface.json` must exist.
2. `runs/.clone_cache/aspose_{family}_{platform}/` should exist for richer context.
3. `scripts/pipeline/enrich.py` must exist.

## Steps

1. Parse `{family}` and `{platform}` from `$ARGUMENTS`.
2. Verify `knowledge/{family}/{platform}/scout/api_surface.json` exists.
3. Run:
   ```bash
   python scripts/pipeline/enrich.py {family} {platform}
   ```
   Optional flags:
   - `--knowledge-root <path>` to override the knowledge root
   - `--no-llm` to skip the LLM call and write an empty enrichment file
4. Verify `knowledge/{family}/{platform}/scout/enriched_claims.json` exists and is valid JSON.
5. Report the number of enriched claims written.

## Post-conditions

- `scout/enriched_claims.json` exists.
- `claims` is a JSON array and all `claim_id` values are deterministic.
- The enrichment is grounded in `api_surface.json`, not in fabricated API names.

## Chain

```
S-34 (repo-scout) -> S-37 (knowledge-enrich) -> S-35 (truth-merge) -> S-31 (truth-index)
```

## Error handling

- Missing scout artifacts: abort and ask for S-34 first.
- LLM unavailable: write an empty `enriched_claims.json` and continue.
- Invalid hallucinated claims: reject them and write only validated enrichment.

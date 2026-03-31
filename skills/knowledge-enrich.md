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

## Output Schema

`scout/enriched_claims.json` must conform to this schema:

```json
{
  "claims": [
    {
      "claim_id": "ENRICH-001",
      "subject": "ClassName",
      "predicate": "supports | can | has | implements | raises",
      "object": "human-readable description of the capability or fact",
      "kind": "capability | format | api | limitation",
      "confidence": 0.0–1.0,
      "source_ref": "api_surface.json class or method that grounded this claim",
      "enrichment_method": "llm | rule"
    }
  ]
}
```

**Field rules**:
- `claim_id`: Must be unique within the file. Use sequential `ENRICH-NNN` format.
- `subject`: Must be a class name that exists in `scout/api_surface.json`. If no matching class
  exists, the claim is hallucinated and must be excluded.
- `confidence`: LLM-assigned confidence. Claims with `confidence < 0.5` are written but
  flagged; S-35 (truth-merge) will set them as `validated: false`.
- `source_ref`: The specific API surface entry that this claim is derived from (e.g.,
  `"Scene.open"` or `"PolygonModifier"`). Never empty — if no grounding exists, reject the claim.
- `enrichment_method`: `"llm"` for LLM-generated claims, `"rule"` for deterministically
  derived claims (e.g., format support inferred from method signatures).

## Post-conditions

- `scout/enriched_claims.json` exists.
- `claims` is a JSON array (may be empty `[]` if `--no-llm` was used or LLM was unavailable).
- All `claim_id` values are deterministic and unique within the file.
- All `subject` values appear in `scout/api_surface.json` (hallucinated subjects are excluded).
- The enrichment is grounded in `api_surface.json`, not in fabricated API names.

## LLM Fallback Sequence

If the primary LLM endpoint is unavailable:

1. **Retry once** (transient network failure).
2. **Fall back to `--no-llm` mode**: Write `enriched_claims.json` with `claims: []`.
   - Downstream impact: S-35 (truth-merge) will proceed as `scout_only`.
   - Content generation proceeds with scout claims only — no enrichment. This is safe but
     produces less semantically rich content.
3. **Do NOT abort** — empty enrichment is a valid output. Log: "LLM unavailable; proceeding
   with empty enrichment. Run S-37 again with LLM access to improve claim quality."

If the LLM returns claims that fail hallucination detection (subject not in api_surface.json):
- Exclude those claims.
- If ALL claims are hallucinated (100% rejection), write `claims: []` and log the rejection.
- Do NOT write the hallucinated claims under any circumstances.

## Chain

```
S-34 (repo-scout) -> S-37 (knowledge-enrich) -> S-35 (truth-merge) -> S-31 (truth-index)
```

## Error handling

- Missing scout artifacts: abort and run S-34 (repo-scout) first.
- LLM unavailable: follow the fallback sequence above; write `claims: []` and continue.
- Invalid hallucinated claims: reject them individually; write only validated claims.
- `enrich.py` script error (non-zero exit): do not write partial output; leave any existing
  `enriched_claims.json` intact; print the script error.
- `enriched_claims.json` already exists from a prior run: the script overwrites it; this is safe.

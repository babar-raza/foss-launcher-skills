# S-35: Truth Merge — Dual-Source Verification

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Merge `knowledge/{family}/{platform}/scout/` and `knowledge/{family}/{platform}/fl/` into `knowledge/{family}/{platform}/merged/`, applying dual-source verification with provenance tagging.

## Pre-conditions
1. `scout/claims.json` must exist (`fl/` is optional — gracefully skipped if absent)
2. If both exist, both should refer to the same product (family/platform)

## Automated Script

Run the merge engine first, then review:
```
python scripts/pipeline/commands/knowledge/promote.py {family} {platform}
```
Review `knowledge/{family}/{platform}/merged/merge_report.md` for dual/scout_only/fl_only counts.

The script matches claims using: **same `kind`** AND **Jaccard token overlap ≥ 0.8**.

**Note on dual-confirmed rate**: In practice, FL LLM-generated claims (`claim_source: "llm"`)
use natural-language text (e.g. "The Scene class enables...") while scout claims use terse API
signatures (e.g. "Scene.open(file) -> Scene"). These rarely meet the 0.8 overlap threshold, so
`dual` count is typically 0. FL claims appear in the merged output as `fl_only` with their
confidence penalised (×0.6 for llm, ×0.8 for deterministic). This is correct — FL claims
still add value as contextual/explanatory knowledge even when they cannot be cross-confirmed.
If PASS is shown in the script output, the manual steps below can be skipped.

## Post-conditions
- `merged/` directory has all required files
- All claims have a `provenance` field
- `model.yaml` has `source: "dual"` (or `"scout_only"` when FL absent) and `has_conflicts: false`
- `api_surface.md` generated for LLM prompt grounding

## Provenance rules
| Scout | FL | Result |
|-------|-----|--------|
| Present | Present (same kind, overlap ≥ 0.8) | `dual`, confidence = max |
| Present | Absent / no match | `scout_only` |
| Absent | Present (deterministic) | `fl_only`, conf × 0.8 |
| Absent | Present (llm/llm_fallback) | `fl_only`, conf × 0.6 |

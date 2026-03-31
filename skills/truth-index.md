---
name: truth-index
id: S-31
description: >
  Generate per-product index.json from merged knowledge and cross-product
  _index.json summary at the knowledge root.
args: "{family} {platform} | all"
---

# S-31: Truth Index — Generate Knowledge Index

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `all`

## Purpose
Generate `index.json` per product from `knowledge/{family}/{platform}/merged/` and `_index.json` cross-product summary at `knowledge/_index.json`.

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/` must exist with at minimum `claims.json` and `model.yaml`
2. If `all`, scan `knowledge/` for all family/platform combinations

## Automated Script

```
python scripts/pipeline/index.py {family} {platform}   # Single product
python scripts/pipeline/index.py all                     # All discovered products
```

The script:
- Reads merged knowledge artifacts
- Sets `api_confidence: "high"` (scout claims are deterministic code analysis)
- Sets `provenance: "scout_only"` and `has_conflicts: false`
- Computes API coverage metrics (surface_tier 1/2/3)
- Builds forbidden_claims from limitations.md
- Writes per-product index.json and cross-product _index.json

## Post-conditions
- `index.json` exists for each processed product
- `_index.json` exists at `knowledge/` root
- All JSON files are valid and parseable
- `api_confidence` is `"high"` for all scout-sourced products

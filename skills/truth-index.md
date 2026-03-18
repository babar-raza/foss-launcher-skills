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

Run the index generator:
```
python scripts/index.py {family} {platform}   # Single product
python scripts/index.py all                     # All discovered products
```
The script auto-discovers products, computes api_confidence thresholds, generates platform-appropriate install commands, and writes both per-product `index.json` and cross-product `_index.json`.

## Manual Steps (fallback)

1. **Scan merged knowledge**: Read all artifacts from `merged/`
2. **Build index.json** with schema:
   ```json
   {
     "schema_version": 2,
     "family": "{family}",
     "platform": "{platform}",
     "display_name": "Aspose.{Family}",
     "provenance": "dual|scout_only|external_only",
     "stale": false,
     "has_conflicts": false,
     "api_confidence": "high|medium|low",
     "repo_sha": "...",
     "last_merged": "...",
     "vectors_available": true|false,
     "stats": { ... },
     "classes": [...],
     "class_graph": { ... },
     "formats": { "import": [...], "export": [...], "caveats": { ... } },
     "install": { ... },
     "not_implemented": [...],
     "forbidden_claims": [...],
     "truth_gaps": []
   }
   ```
3. **Write** `knowledge/{family}/{platform}/merged/index.json`
4. **Build _index.json**: Aggregate all products into cross-product summary
5. **Write** `knowledge/_index.json`

## Post-conditions
- `index.json` exists for each processed product
- `_index.json` exists at `knowledge/` root
- All JSON files are valid and parseable

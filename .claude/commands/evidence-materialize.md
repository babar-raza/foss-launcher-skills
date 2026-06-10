# S-44: Evidence Materialize — Build Canonical Product Evidence File

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `all`

## Purpose
Aggregate all knowledge artifacts from `knowledge/{family}/{platform}/merged/` into a single canonical Product Evidence File (PEF) at `evidence/{family}/{platform}/pef.json`. The PEF is the single source of truth for content operations — it contains claims, API surface, formats, limitations, install info, snippets, provenance summary, and freshness metadata.

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/` must exist with at minimum `model.yaml` and `claims.json`
2. S-35 (truth-merge) and S-31 (truth-index) should have been run first

## Automated Script

Run the materializer:
```
python scripts/materialize.py {family} {platform}   # Single product
python scripts/materialize.py all                     # All discovered products
```
The script:
- Reads all merged knowledge artifacts (claims, api_surface, formats, class_graph, coverage_matrix, constants, limitations, install, index, snippets)
- Computes provenance summary and api_confidence
- Rotates previous PEF to `pef_previous.json` for diffing
- Appends to `changelog.json` with delta summary
- Validates output against `configs/schemas/pef.schema.json`

## Output
- `evidence/{family}/{platform}/pef.json` — canonical PEF
- `evidence/{family}/{platform}/pef_previous.json` — previous snapshot (auto-rotated)
- `evidence/{family}/{platform}/changelog.json` — append-only evidence change log

## Post-conditions
- `pef.json` exists and passes schema validation
- All claims have provenance annotations
- Provenance summary is accurate
- If re-run, previous PEF is preserved and changelog is appended

# S-35: Truth Merge - Scout-Only Promotion with Enrichment

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Promote `knowledge/{family}/{platform}/scout/` plus any `scout/enriched_claims.json`
enrichment into `knowledge/{family}/{platform}/merged/`, applying provenance tagging and
current runtime rules. The FL layer has been removed.

## Pre-conditions

1. `scout/claims.json` must exist
2. `scout/enriched_claims.json` is optional but should be used when present
3. If both exist, both should refer to the same product (family/platform)

## Automated Script

Run the promotion engine first, then review:
```bash
python scripts/pipeline/promote.py {family} {platform}
```
Review `knowledge/{family}/{platform}/merged/merge_report.md` for scout/enriched promotion counts.

## Post-conditions

- `merged/` directory has all required files
- All claims have a `provenance` field
- `model.yaml` has `source: "scout_only"` or `source: "scout_plus_enriched"` depending on
  enrichment availability and `has_conflicts: false`
- `api_surface.md` generated for LLM prompt grounding

## Provenance rules

| Scout | Enriched claim | Result |
|-------|-----------------|--------|
| Present | Present and validated | `scout_plus_enriched`, confidence = max |
| Present | Absent / rejected | `scout_only` |
| Present | Present but hallucinated / invalid | `scout_only` with the invalid enrichment excluded |

---
name: truth-merge
id: S-35
description: >
  Promote scout/ knowledge (plus optional enriched/supplemental claims) into
  merged/ with provenance tagging. Replaces dual-source merge — no FL dependency.
args: "{family} {platform}"
---

> Cross-skill references like `/evidence-cite` refer to sibling skills in this directory.

# S-35: Truth Merge — Knowledge Promotion

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Promote `knowledge/{family}/{platform}/scout/` artifacts into `knowledge/{family}/{platform}/merged/`,
appending LLM-enriched claims from `scout/enriched_claims.json` (S-37) when present.

## Pre-conditions
1. `scout/claims.json` must exist (run S-34 first)
2. `fl/` directory must NOT exist — promote.py will exit 1 if it does

## Automated Script

```
python scripts/pipeline/promote.py {family} {platform}
```
Review `knowledge/{family}/{platform}/merged/merge_report.md` for scout/enriched/supplemental counts.

## Post-conditions
- `merged/` directory has all required files
- All claims have a `provenance` field (`scout` | `enriched` | `supplemental`)
- `model.yaml` has `source: scout_only` and `has_conflicts: false`
- `api_surface.md` and `formats.md` generated for LLM prompt grounding

## Provenance rules
| Source | Condition | Result |
|--------|-----------|--------|
| `scout/claims.json` | Always | `provenance: "scout"` |
| `scout/enriched_claims.json` | Present (from S-37) | `provenance: "enriched"` |
| `scout/supplemental_claims.json` | Present (bridge only) | `provenance: "supplemental"` |

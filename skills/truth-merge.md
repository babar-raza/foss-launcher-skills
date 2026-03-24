---
name: truth-merge
id: S-35
description: >
  Copy scout knowledge to merged/ with provenance tagging.
  Scout-only pipeline — no FL merge.
args: "{family} {platform}"
---

# S-35: Truth Merge — Scout-Only Knowledge Merge

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Copy `knowledge/{family}/{platform}/scout/` to `knowledge/{family}/{platform}/merged/`, tagging all claims with `provenance: "scout_only"`. This is a deterministic passthrough — no LLM or FL involvement.

## Pre-conditions
1. `knowledge/{family}/{platform}/scout/claims.json` must exist (run S-34 repo-scout first)

## Automated Script

```
python scripts/pipeline/merge.py {family} {platform}
```

The script:
- Validates scout claims
- Tags all claims with `provenance: "scout_only"`
- Copies api_surface.json, formats.json, class_graph.json, limitations.md, etc. to merged/
- Generates api_surface.md (human-readable API reference)
- Writes model.yaml with `source: "scout_only"` and `has_conflicts: false`
- Writes merge_report.md with statistics

## Post-conditions
- `merged/` directory has all required files
- All claims have `provenance: "scout_only"`
- `model.yaml` has `source: "scout_only"` and `has_conflicts: false`
- `api_surface.md` generated for LLM prompt grounding
- No merge_conflicts.md (legacy files are cleaned up)

## Output artifacts
| File | Purpose |
|------|---------|
| `merged/claims.json` | All claims with provenance tags |
| `merged/api_surface.json` | API surface (classes, methods, properties) |
| `merged/api_surface.md` | Human-readable API reference |
| `merged/model.yaml` | Metadata (repo_sha, stats, source) |
| `merged/formats.json` | Format support matrix |
| `merged/formats.md` | Human-readable format table |
| `merged/limitations.md` | NotImplementedError methods |
| `merged/merge_report.md` | Merge statistics |

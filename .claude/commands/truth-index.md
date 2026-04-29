<!-- CONTRACT: scripts/pipeline/commands/knowledge/index.py
     postcondition: merged/index.json exists (schema_version 2, api_confidence always "high")
     postcondition: knowledge/_index.json exists (products array)
     postcondition: install field is {"command": "...", "version": "..."} not pip/npm/maven object
     postcondition: forbidden_claims format is ["supports ClassName.method"] strings
     verified: 2026-04-01
-->
# S-31: Truth Index - Generate Knowledge Index

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `all`

## Purpose

Generate `index.json` per product from `knowledge/{family}/{platform}/merged/` and
`_index.json` cross-product summary at `knowledge/_index.json`.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/` must exist with at minimum `claims.json` and `model.yaml`.
2. `merged/api_surface.json` must exist — used to compute `api_confidence` and `classes` list.
3. If `all`, scan `knowledge/` for all family/platform combinations that have a `merged/` directory.

## Automated Script

Run the index generator:
```bash
.venv/Scripts/python scripts/pipeline/commands/knowledge/index.py {family} {platform}   # Single product
.venv/Scripts/python scripts/pipeline/commands/knowledge/index.py all                   # All discovered products
```
The script auto-discovers products, generates platform-appropriate install commands, and
writes both per-product `index.json` and cross-product `_index.json`.

## Manual Steps (fallback)

1. **Scan merged knowledge**: Read all artifacts from `merged/`.

2. **Build index.json** with the following schema (all fields required unless noted):

   ```json
   {
     "schema_version": 2,
     "family": "{family}",
     "platform": "{platform}",
     "display_name": "Aspose.{Family}",
     "provenance": "scout_only",
     "stale": false,
     "has_conflicts": false,
     "api_confidence": "high",
     "repo_sha": "...",
     "last_merged": "...",
     "vectors_available": true | false,
     "stats": { ... },
     "classes": ["ClassName", ...],
     "class_graph": { "ClassName": ["ParentClass"] },
     "formats": {
       "import": ["ext", ...],
       "export": ["ext", ...],
       "caveats": {}
     },
     "install": {
       "command": "pip install aspose-{family}-foss",
       "version": "..."
     },
     "not_implemented": ["ClassName.method"],
     "forbidden_claims": ["supports ClassName.method", ...],
     "truth_gaps": [],
     "api_coverage": {
       "total_classes": N,
       "with_methods": N,
       "with_properties": N,
       "with_enums": N,
       "method_pct": 75.0,
       "property_pct": 50.0,
       "surface_tier": 1
     },
     "snippets_coverage": {
       "total_snippets": N,
       "classes_with_snippet": N,
       "classes_total": N,
       "coverage_ratio": 0.45
     }
   }
   ```

   **Field semantics**:
   - `api_confidence`: Always `"high"` in the current implementation — deterministic code
     analysis (tree-sitter) is considered high-confidence. Threshold-based calculation
     (high/medium/low by class count) is a planned enhancement.
   - `classes`: Public API class names only — excludes functions, private names (`_`-prefixed),
     test-file classes, and internal implementation paths.
   - `class_graph`: From `merged/class_graph.json` if present; empty object otherwise.
   - `forbidden_claims`: Derived from `merged/limitations.md` parsed entries, formatted as
     `"supports ClassName.method"` strings. NOT `[FORBIDDEN]`-tagged sentences.
   - `not_implemented`: `"ClassName.method"` strings from parsed `merged/limitations.md` table rows.
   - `install`: Single command for the platform: `{"command": ".venv/Scripts/pip install ...", "version": "..."}`.
     All platforms use this same two-field structure.
   - `stats`: Copied directly from `merged/model.yaml` → `stats` object (promote.py stats).
   - `api_coverage`: Computed class coverage metrics — method/property/enum percentages and
     `surface_tier` (1: ≥70% methods, 2: 40-69%, 3: <40%).
   - `snippets_coverage`: Snippet coverage ratio across public classes.
   - `stale`: Always `false` — `index.py` does not currently read `stale_since` from model.yaml.
   - `has_conflicts`: Always `false` — mirrors `promote.py` output.

3. **Write** `knowledge/{family}/{platform}/merged/index.json`.

4. **Build _index.json**: Aggregate all processed products into cross-product summary:
   ```json
   {
     "products": [
       {
         "family": "3d", "platform": "python",
         "display_name": "Aspose.3D for Python",
         "api_confidence": "high",
         "stale": false,
         "class_count": N,
         "claim_count": N
       }
     ]
   }
   ```

5. **Write** `knowledge/_index.json`.

## Validation Rules

After writing, verify:
- `index.json` is valid JSON (parseable).
- `classes` list is non-empty (abort if empty — indicates scout failure or no public API).
- `api_confidence` is `"high"` (current implementation hardcodes this for scout-only).
- `forbidden_claims` is an array (may be empty `[]`).
- `install` has both `command` and `version` fields.
- `api_coverage.surface_tier` is 1, 2, or 3; if 3, a WARNING is logged.

## Post-conditions

- `index.json` exists for each processed product and passes all validation rules above.
- `_index.json` exists at `knowledge/` root with an entry for each processed product.
- All JSON files are valid and parseable.
- No product with `api_confidence: "low"` proceeds to content generation (hard stop — §7).

## Error handling

- `merged/claims.json` missing: abort; run S-35 (truth-merge) first.
- `merged/api_surface.json` missing: abort; run S-35 (truth-merge) first.
- `classes` list is empty after parsing `api_surface.json`: abort with message
  "api_surface.json contains no classes — re-run S-34 (repo-scout) to re-extract."
- `index.py` script fails: do not write partial `index.json`; leave existing file intact.
- `all` mode: skip products where `merged/` is incomplete; log skipped products; continue with the rest.

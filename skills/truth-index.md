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
python scripts/pipeline/index.py {family} {platform}   # Single product
python scripts/pipeline/index.py all                   # All discovered products
```
The script auto-discovers products, computes api_confidence thresholds, generates
platform-appropriate install commands, and writes both per-product `index.json` and
cross-product `_index.json`.

## Manual Steps (fallback)

1. **Scan merged knowledge**: Read all artifacts from `merged/`.

2. **Build index.json** with the following schema (all fields required unless noted):

   ```json
   {
     "schema_version": 2,
     "family": "{family}",
     "platform": "{platform}",
     "display_name": "Aspose.{Family}",
     "provenance": "dual | scout_only | fl_only",
     "stale": false,
     "has_conflicts": false,
     "api_confidence": "high | medium | low",
     "repo_sha": "...",
     "last_merged": "...",
     "vectors_available": true | false,
     "stats": {
       "total_claims": 0,
       "capability_claims": 0,
       "format_claims": 0,
       "api_claims": 0,
       "limitation_claims": 0
     },
     "classes": ["ClassName", ...],
     "class_graph": { "ClassName": ["ParentClass"] },
     "formats": {
       "import": ["ext", ...],
       "export": ["ext", ...],
       "caveats": { "ext": "description of caveat" }
     },
     "install": {
       "pip": "pip install {package}",
       "npm": null,
       "maven": null,
       "dotnet": null,
       "cmake": null
     },
     "not_implemented": ["ClassName.method — reason"],
     "forbidden_claims": ["Do not claim X because Y", ...],
     "truth_gaps": []
   }
   ```

   **Field semantics**:
   - `api_confidence`: Set to `"high"` when total classes ≥ 10 AND all class methods are documented;
     `"medium"` when 5–9 classes or some methods undocumented; `"low"` when <5 classes or
     `api_surface.json` is sparse. A value of `"low"` triggers a hard stop in all content skills.
   - `classes`: Exact list of class names from `merged/api_surface.json` top-level keys.
   - `class_graph`: Inheritance map — keys are class names, values are arrays of parent class names.
     Empty array `[]` means no parent. Use data from `merged/class_graph.json` if present.
   - `forbidden_claims`: Statements that must NEVER appear in generated content. Populate from
     `merged/limitations.md` entries tagged as `[FORBIDDEN]`, and any claims with `confidence < 0.4`.
   - `not_implemented`: List of `"ClassName.method — reason"` strings from `merged/limitations.md`
     entries where the feature is documented as `NotImplementedError` or explicitly unimplemented.
   - `truth_gaps`: Leave as `[]` for initial generation; populated by S-43 (gap-eval) findings.
   - `install`: Only populate the field relevant to `{platform}` (e.g., `pip` for Python,
     `npm` for TypeScript). Set all other install fields to `null`.
   - `stale`: Copy from `merged/model.yaml` → `stale_since != null ? true : false`.
   - `has_conflicts`: Copy from `merged/model.yaml` → `has_conflicts`.

3. **Write** `knowledge/{family}/{platform}/merged/index.json`.

4. **Build _index.json**: Aggregate all processed products into cross-product summary:
   ```json
   {
     "schema_version": 1,
     "generated": "{ISO timestamp}",
     "products": [
       { "family": "3d", "platform": "python", "display_name": "Aspose.3D", "api_confidence": "high", "stale": false }
     ]
   }
   ```

5. **Write** `knowledge/_index.json`.

## Validation Rules

After writing, verify:
- `index.json` is valid JSON (parseable).
- `classes` list is non-empty (abort if empty — indicates scout failure).
- `api_confidence` is one of `"high"`, `"medium"`, `"low"` — never absent.
- `forbidden_claims` is an array (may be empty `[]`).
- `stale` and `has_conflicts` are boolean, not null.
- `install` has exactly one non-null field (the platform-appropriate one).

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

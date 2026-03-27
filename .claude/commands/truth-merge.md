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
python scripts/pipeline/merge.py {family} {platform}
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

## Manual Steps (fallback)

1. **Load sources**:
   - Read `scout/claims.json`, `scout/api_surface.json`, `scout/model.yaml`
   - Read `fl/claims.json`, `fl/api_surface.json`, `fl/model.yaml`
   - Either can be absent — proceed with single-source if needed

2. **Merge claims** with provenance tagging:
   - For each scout claim, find matching FL claims (same kind + similar text)
   - Matching strategy:
     - Exact text match → `provenance: "dual"`, confidence = max(both)
     - Similar text (>80% token overlap) → `provenance: "dual_fuzzy"`, flag for review
     - Scout only → `provenance: "scout_only"`
     - FL only (deterministic source) → `provenance: "fl_only"`, confidence × 0.8
     - FL only (llm/llm_fallback source) → `provenance: "fl_only"`, confidence × 0.6
     - Contradicting claims → `provenance: "conflict"`, add to merge_conflicts.md

3. **Merge API surface**:
   - Class in both with same methods → `dual`
   - Class in both with different methods → take union, flag discrepancies
   - Class in one only → single-source provenance

4. **Merge format matrix**:
   - Same format, same flags → `dual`
   - Different flags → `conflict`

5. **Build forbidden_claims**: From limitations (NotImplementedError items) build list of claims that must NOT appear in content

6. **Build truth_gaps**: Facts that couldn't be extracted or verified

7. **Write merged artifacts**:
   - `merged/model.yaml` — combined metadata
   - `merged/claims.json` — all claims with provenance
   - `merged/claims.md` — human-readable claim summary
   - `merged/api_surface.json` — merged API surface
   - `merged/api_surface.md` — human-readable API reference
   - `merged/formats.json` — merged format matrix
   - `merged/formats.md` — human-readable format table
   - `merged/install.md` — install instructions (prefer scout, fall back to fl)
   - `merged/limitations.md` — combined limitations
   - `merged/class_graph.json` — from scout (or fl if scout absent)
   - `merged/merge_report.md` — statistics on merge (dual/single/conflict counts)
   - `merged/merge_conflicts.md` — only if conflicts exist

## Post-conditions
- `merged/` directory has all required files
- `merge_report.md` shows merge statistics
- All claims have a `provenance` field
- Conflicting claims are documented in `merge_conflicts.md`

## Provenance rules
| Scout | FL | Result |
|-------|-----|--------|
| Present | Present (same kind, overlap ≥ 0.8) | `dual`, confidence = max |
| Present | Absent / no match | `scout_only` |
| Absent | Present (deterministic) | `fl_only`, conf × 0.8 |
| Absent | Present (llm/llm_fallback) | `fl_only`, conf × 0.6 |

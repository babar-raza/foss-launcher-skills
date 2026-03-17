# S-35: Truth Merge — Dual-Source Verification

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Merge `knowledge/{family}/{platform}/scout/` and `knowledge/{family}/{platform}/fl/` into `knowledge/{family}/{platform}/merged/`, applying dual-source verification with provenance tagging.

## Pre-conditions
1. At least ONE source must exist: `scout/` or `fl/` (both preferred)
2. If both exist, verify they refer to the same product (compare family/platform in model.yaml)

## Automated Script

Run the merge engine first, then review:
```
python scripts/merge.py {family} {platform}
```
Review `knowledge/{family}/{platform}/merged/merge_report.md` for dual/fuzzy/conflict counts.

The script implements claim-type-aware matching (KIND_MAP) that bridges the vocabulary gap between scout API signatures and FL natural-language claims. If the script output shows PASS and dual-confirmed > 20%, the manual steps below can be skipped.

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
| Present | Present (matching) | `dual`, confidence = max |
| Present | Present (fuzzy match) | `dual_fuzzy`, flag review |
| Present | Absent | `scout_only` |
| Absent | Present (deterministic) | `fl_only`, conf × 0.8 |
| Absent | Present (llm source) | `fl_only`, conf × 0.6 |
| Present | Present (contradicting) | `conflict` |

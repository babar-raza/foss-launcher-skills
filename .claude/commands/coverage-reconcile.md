# S-85: Coverage Reconcile — Knowledge Unit Disposition Report

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `cells net` or `slides python`

## Purpose

Produce a full disposition table for every knowledge unit (claim from claims.json,
API member from api_surface.json) for the given product, showing whether it is:
- **Used**: cited in a content page's `evidence.claims` or `evidence.apis`
- **Stored**: in the knowledge store but not cited anywhere
- **Orphaned**: no page covers the relevant topic
- **Excluded**: cluster excluded from site plan

This enables the operator to verify knowledge coverage and identify gaps before
trusting a product launch as complete.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/claims.json` exists
2. `knowledge/{family}/{platform}/merged/api_surface.json` exists
3. Content pages exist under `$CONTENT_REPO_PATH/content/` for the product

## Steps

1. **Load all knowledge units**:
   - Claims: read `knowledge/{family}/{platform}/merged/claims.json`
   - API members: read `knowledge/{family}/{platform}/merged/api_surface.json`

2. **Index all content evidence blocks**:
   - Scan all `$CONTENT_REPO_PATH/content/**/{family}/{platform}/**/*.md` frontmatter
   - Extract `evidence.claims` and `evidence.apis` from each file
   - Build a reverse map: claim_id → [pages that cite it]

3. **Classify each knowledge unit**:

   | Disposition | Criteria |
   |---|---|
   | `USED` | Cited in at least one page's evidence block |
   | `STORED` | In knowledge store, not cited in any page |
   | `ORPHANED` | Not cited; no content page covers its topic |
   | `EXCLUDED` | Marked `excluded: true` in site plan |

4. **Compute coverage metrics**:
   ```
   Claims:
     Total:    N
     Used:     N (X%)
     Stored:   N (Y%)
     Orphaned: N (Z%)

   API members:
     Total:    N
     Used:     N (X%)
     Stored:   N (Y%)
     Orphaned: N (Z%)
   ```

5. **Write report** to `reports/coverage/{family}/{platform}/coverage-reconcile.md`:
   - Summary table with counts by disposition
   - Full disposition table listing each knowledge unit, its disposition, and which pages cite it

6. **Flag critical gaps**: Any ORPHANED claim with `confidence >= 0.8` should be flagged as `HIGH_PRIORITY_GAP` — these are high-confidence capabilities with no content coverage.

## Post-conditions

- Report written to `reports/coverage/{family}/{platform}/coverage-reconcile.md`
- Coverage metrics printed to output
- HIGH_PRIORITY_GAP items listed for operator review
- No content modified (read-only)

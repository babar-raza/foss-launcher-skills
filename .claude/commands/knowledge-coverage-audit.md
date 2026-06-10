# S-86: Knowledge Coverage Audit — Per-Claim Disposition Table

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `cells net` or `email java`

## Purpose

Build a per-claim, per-API-class disposition table showing which knowledge units
are used, evidence-cited, surface-only, excluded (by threshold/tier/skip), or
orphaned. This is the foundational observability instrument for "no silent knowledge loss."

**Why existing skills are insufficient**: S-43 (gap-eval) verifies content accuracy
against source. S-32 (content-audit) audits semantic prose quality. Neither computes
the reverse mapping: which claims in `knowledge/` appear in NO content page evidence block.

**Relationship to coverage-reconcile (S-85)**: S-86 focuses on claim-level detail and
script-driven computation; S-85 provides a broader product-level disposition view including
API members and site plan exclusions.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/claims.json` exists
2. `knowledge/{family}/{platform}/merged/api_surface.json` exists
3. Knowledge bootstrap must have been run (S-14 / knowledge-update)

## Steps

1. **Run the coverage script**:
   ```bash
   python scripts/pipeline/commands/knowledge/knowledge_coverage.py {family} {platform}
   ```
   This produces:
   - `reports/coverage/{family}/{platform}/knowledge_coverage.json`
   - `reports/coverage/{family}/{platform}/knowledge_coverage.md`

2. **Interpret dispositions**:

   | Disposition | Meaning |
   |---|---|
   | `CITED` | Claim ID appears in at least one page's `evidence.claims` |
   | `SURFACE_ONLY` | Claim exists in knowledge but never cited in content |
   | `EXCLUDED_THRESHOLD` | Claim confidence below citation threshold |
   | `EXCLUDED_TIER` | Claim excluded by product tier/platform filter |
   | `EXCLUDED_SKIP` | Claim explicitly skipped by operator |
   | `ORPHANED` | Claim not cited and no content page covers its topic |

3. **Review ORPHANED count**: This is the primary metric to review. ORPHANED claims represent
   capability knowledge that exists in the knowledge store but has no coverage in any content page.
   Operator must decide for each ORPHANED claim:
   - Create a new content page (use S-19 or appropriate generation skill)
   - Add the claim to an existing page (use S-21 page-enhance)
   - Accept as intentionally uncovered (mark `excluded_skip: true`)

4. **Generate summary**:
   ```
   KNOWLEDGE COVERAGE AUDIT — {family}/{platform}
   Total claims:           N
   Cited:                  N (X%)
   Surface only:           N (Y%)
   Excluded (threshold):   N
   Excluded (tier/skip):   N
   Orphaned:               N  ← must be reviewed

   HIGH-PRIORITY ORPHANS (confidence >= 0.8): N
   ```

## Post-conditions

- `reports/coverage/{family}/{platform}/knowledge_coverage.json` written with per-claim dispositions
- `reports/coverage/{family}/{platform}/knowledge_coverage.md` written with human-readable table
- ORPHANED count must be reviewed and actioned before product launch sign-off
- No content modified (read-only)

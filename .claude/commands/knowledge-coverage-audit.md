# S-81: Knowledge Coverage Audit — Per-Claim Disposition Table

<!-- CONTRACT: scripts/pipeline/knowledge_coverage.py (per-claim disposition table)
postcondition: every claim in merged/claims.json has exactly one disposition
postcondition: ORPHANED count is reported and must be reviewed by operator
postcondition: reports/coverage/{family}/{platform}/knowledge_coverage.json written
postcondition: reports/coverage/{family}/{platform}/knowledge_coverage.md written
verified: 2026-04-07
-->

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `cells net` or `email java`

## Purpose

Build a per-claim, per-API-class disposition table showing which knowledge units
are used, evidence-cited, surface-only, excluded (by threshold/tier/skip), or
orphaned. This is the foundational observability instrument for "no silent
knowledge loss."

**Why existing skills are insufficient**: S-43 (gap-eval) verifies content
accuracy against source. S-32 (content-audit) audits semantic prose quality.
Neither computes the reverse mapping: which claims in `knowledge/` appear in NO
content page evidence block.

**Output location**: `reports/coverage/{family}/{platform}/`

## Disposition Taxonomy (9 terminal states)

| Disposition | Meaning |
|-------------|---------|
| `USED_EVIDENCE` | Claim cited in `evidence.claims` on a content page |
| `SURFACE_ONLY` | Structural API fact expressed in reference page tables (api_method, api_class, api_field) |
| `EXCLUDED_THRESHOLD` | Content section blocked by snippet/claim threshold in site plan (e.g. blog `snippet_count < 10`) |
| `EXCLUDED_TIER` | Content section blocked by tier/precondition (e.g. KB tier bug) |
| `EXCLUDED_SKIP` | Cluster in KB_SKIP_CLUSTERS |
| `EXCLUDED_LIMITATION` | Intentionally excluded limitation fact |
| `DUPLICATE` | Derived from or overlaps with another claim (Jaccard dedup) |
| `INTENTIONAL` | Operator-marked as not needed |
| `ORPHANED` | No traceable use — requires operator review |

**Invariant**: sum of all dispositions = total_claims in model.yaml.
No claim may be absent from the output.

## Pre-conditions (halt immediately on any failure)

1. Parse `{family}` and `{platform}` from `$ARGUMENTS`.
2. `knowledge/{family}/{platform}/merged/claims.json` must exist.
3. `knowledge/{family}/{platform}/merged/api_surface.json` must exist.
4. `knowledge/{family}/{platform}/merged/model.yaml` must exist with `stale_since: null`.
   If stale, HALT:
   ```
   REFUSED: Knowledge is stale for {family}/{platform}.
   Run S-12 (knowledge-diff) then S-14 (knowledge-update) before proceeding.
   ```
5. At least one content page must exist under any site for `{family}/{platform}`.
   If no pages found, WARN but continue (partial coverage only).

## Steps

1. **Run backing script**:
   ```bash
   .venv/Scripts/python scripts/pipeline/knowledge_coverage.py {family} {platform}
   ```

2. **Read output** from `reports/coverage/{family}/{platform}/knowledge_coverage.json`.

3. **Check orphaned count** from summary:
   - If `orphaned_count == 0`: report CLEAN
   - If `orphaned_count > 0`: list orphaned claim IDs and kinds; report ORPHANED_FOUND

4. **Report** using the standard format (see §Output Format).

## Output Format

```
KNOWLEDGE COVERAGE AUDIT — {family}/{platform}

Total claims:     {N}
Total classes:    {N}
Pages scanned:    {N}
Cited claim IDs:  {N}
Blog blocked:     {true|false}
KB blocked:       {true|false}

Claim dispositions:
  USED_EVIDENCE            {N}  ({X}%)
  SURFACE_ONLY             {N}  ({X}%)
  EXCLUDED_THRESHOLD       {N}  ({X}%)
  EXCLUDED_TIER            {N}  ({X}%)
  EXCLUDED_SKIP            {N}  ({X}%)
  EXCLUDED_LIMITATION      {N}  ({X}%)
  DUPLICATE                {N}  ({X}%)
  INTENTIONAL              {N}  ({X}%)
  ORPHANED                 {N}  ({X}%)

Result: CLEAN | ORPHANED_FOUND

Reports:
  reports/coverage/{family}/{platform}/knowledge_coverage.json
  reports/coverage/{family}/{platform}/knowledge_coverage.md
```

If `ORPHANED_FOUND`, list each orphaned claim ID and its text (max 20 lines; rest in JSON).

## Post-conditions

- `reports/coverage/{family}/{platform}/knowledge_coverage.json` written
- `reports/coverage/{family}/{platform}/knowledge_coverage.md` written
- Every claim in `merged/claims.json` has exactly one disposition in output
- ORPHANED count is reported (may be non-zero; operator decides action)

## Integration Points

- **S-47 (site-plan)**: site_plan.yaml is read for EXCLUDED_THRESHOLD/EXCLUDED_TIER
  classification. Run S-47 before this skill for accurate exclusion mapping.
- **S-49 (launch-product)**: invoke this skill after Stage 6 (truth-audit) as a
  coverage gate. Operators should review ORPHANED claims before closing a launch.
- **launch_gate.py**: Add Check L-03 — `orphaned_claim_count == 0 OR operator-classified`

## Error Handling

| Condition | Action |
|-----------|--------|
| `merged/claims.json` missing | HALT — run S-14 (knowledge-update) first |
| Knowledge stale | HALT — run S-12 then S-14 first |
| No content pages found | WARN and continue with partial coverage |
| `reports/plans/` site_plan.yaml missing | WARN — EXCLUDED_THRESHOLD/TIER may be wrong; continue |
| Script error | HALT and report the traceback |

## Never Do

- Modify any content page or knowledge file
- Mark claims as INTENTIONAL without explicit operator instruction
- Invent or infer dispositions without code evidence
- Skip the orphaned count check
- Suppress ORPHANED findings

## Relationship to Other Skills

- **S-43 (gap-eval)**: verifies content accuracy against source (forward). S-79 maps
  knowledge to content (reverse). Complementary, not overlapping.
- **S-32 (content-audit)**: checks semantic prose quality. S-79 checks coverage accounting.
- **S-62 (batch-reference)**: generates reference pages from api_surface.json. After S-79
  reports high ORPHANED count in ERC-* claims, extend S-62 to use ERC-* claims when
  `doc=""`, delete stubs, re-run `/batch-reference`.

---
name: knowledge-coverage-audit
id: S-81
description: >
  Build a per-claim, per-API-class disposition table showing which knowledge units are
  used, evidence-cited, excluded, or orphaned. The foundational observability instrument
  for detecting silent knowledge loss.
args: "{family} {platform}"
---

# S-81: Knowledge Coverage Audit — Per-Claim Disposition Table

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `cells net` or `email java`

## Purpose

Build a per-claim, per-API-class disposition table showing which knowledge units
are used, evidence-cited, excluded (by threshold/tier/skip), or orphaned. This is
the foundational observability instrument for "no silent knowledge loss."

**Why existing skills are insufficient**: S-23 (ground-check) verifies structure.
S-90 (truth-audit) verifies API accuracy against knowledge. Neither computes the
reverse mapping: which claims in `knowledge/` appear in NO content page evidence block.

**Output location**: `reports/coverage/{family}/{platform}/`

## Disposition Taxonomy

| Disposition | Meaning |
|-------------|---------|
| `USED_EVIDENCE` | Claim cited in `evidence.claims` on a content page |
| `SURFACE_ONLY` | Structural API fact expressed in reference page tables |
| `EXCLUDED_THRESHOLD` | Content section blocked by snippet/claim threshold in site plan |
| `EXCLUDED_TIER` | Content section blocked by tier/precondition |
| `EXCLUDED_SKIP` | Cluster explicitly skipped in site plan configuration |
| `EXCLUDED_LIMITATION` | Intentionally excluded limitation fact |
| `DUPLICATE` | Derived from or overlaps with another claim |
| `INTENTIONAL` | Operator-marked as not needed |
| `ORPHANED` | No traceable use — requires operator review |

**Invariant**: sum of all dispositions = total_claims in model.yaml.
No claim may be absent from the output.

Note: `EXCLUDED_*` dispositions require a site plan file (`reports/plans/{family}/{platform}/site_plan.yaml`)
or equivalent plan configuration. If no site plan exists, all uncited claims are classified as `ORPHANED`.

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
   If no pages found, WARN but continue (coverage = 0% partial result only).

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-81 --scope "*"
> ```

## Steps

### Step 1: Run backing script (if available)

If `scripts/knowledge_coverage.py` exists:
```bash
python scripts/knowledge_coverage.py {family} {platform}
```

Read output from `reports/coverage/{family}/{platform}/knowledge_coverage.json`.
Proceed to Step 3.

If the script is absent, execute Step 2 manually.

### Step 2: Manual agent-executed audit (when script absent)

1. Load `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
2. Walk all content files for `{family}/{platform}` (from `config.yaml sites` section)
3. For each file, extract `evidence.claims` and `evidence.apis` from frontmatter
4. For each claim in claims.json:
   - If claim ID appears in any file's `evidence.claims` → `USED_EVIDENCE`
   - If claim is about a structural API fact with a reference page → `SURFACE_ONLY`
   - If no match found → `ORPHANED`
5. For each API class/member in api_surface.json:
   - If cited in any file's `evidence.apis` → `USED_EVIDENCE`
   - If no match found → `ORPHANED`
6. Write the disposition table to `reports/coverage/{family}/{platform}/knowledge_coverage.json`

### Step 3: Check orphaned count

- If `orphaned_count == 0`: report **CLEAN**
- If `orphaned_count > 0`: list orphaned claim IDs and kinds; report **ORPHANED_FOUND**

### Step 4: Report

```
KNOWLEDGE COVERAGE AUDIT — {family}/{platform}

Total claims:     {N}
Total classes:    {N}
Pages scanned:    {N}
Cited claim IDs:  {N}

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

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-81 --status completed
> ```

## Post-conditions

- `reports/coverage/{family}/{platform}/knowledge_coverage.json` written
- `reports/coverage/{family}/{platform}/knowledge_coverage.md` written
- Every claim in `merged/claims.json` has exactly one disposition in output
- ORPHANED count is reported (may be non-zero; operator decides action)

## Integration Points

- **S-49 (launch-product)**: invoke this skill as a coverage gate before closing a launch.
  Operators should review ORPHANED claims before declaring launch complete.
- **S-80 (coverage-reconcile)**: simpler 3-state disposition; use S-80 for quick coverage
  ratios and S-81 for detailed per-claim accountability.

## Error Handling

| Condition | Action |
|-----------|--------|
| `merged/claims.json` missing | HALT — run S-14 (knowledge-update) first |
| Knowledge stale | HALT — run knowledge-diff then knowledge-update first |
| No content pages found | WARN and continue with partial coverage |
| Site plan missing | WARN — EXCLUDED_* dispositions may be wrong; continue |
| Script error | HALT and report the traceback |

## Never Do

- Modify any content page or knowledge file
- Mark claims as INTENTIONAL without explicit operator instruction
- Invent or infer dispositions without evidence
- Skip the orphaned count check
- Suppress ORPHANED findings

## Relationship to Other Skills

- **S-90 (truth-audit)**: verifies content accuracy (forward check). S-81 maps knowledge to
  content (reverse check). Complementary, not overlapping.
- **S-80 (coverage-reconcile)**: quick 3-state coverage ratio. S-81 provides the full
  9-state per-claim accountability needed for launch sign-off.
- **S-32 (content-audit)**: checks semantic prose quality. S-81 checks coverage accounting.

---
name: coverage-reconcile
id: S-80
description: >
  Trace every knowledge unit (claim, API member) to a page disposition. Identifies which
  claims are used in content, which are orphaned, and whether coverage is adequate for launch.
args: "{family} {platform}"
---

# S-80: Coverage Reconcile — Knowledge Unit Disposition Report

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `cells net` or `slides python`

## Purpose

Produce a full disposition table for every knowledge unit (claim from claims.json,
API member from api_surface.json) for the given product, showing whether it is:
- Used in a content page (cited in evidence.claims or evidence.apis)
- Stored but not used (in knowledge store, not cited anywhere)
- Orphaned (no page covers the relevant topic)
- Excluded by a site plan or threshold rule (if applicable)

This enables the operator to verify knowledge coverage and identify gaps before
trusting a product launch as complete.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/claims.json` must exist
2. `knowledge/{family}/{platform}/merged/api_surface.json` must exist
3. `knowledge/{family}/{platform}/merged/model.yaml` must have `stale_since: null`
4. At least one content page must exist under any configured site for `{family}/{platform}`

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-80 --scope "{family} {platform}"
> ```

## Inputs

- `knowledge/{family}/{platform}/merged/claims.json` — all knowledge claims
- `knowledge/{family}/{platform}/merged/api_surface.json` — all API members
- Content files at paths from `config.yaml sites` section for `{family}/{platform}` — evidence frontmatter
- `reports/plans/{family}/{platform}/site_plan.yaml` — planner exclusions *(optional; see below)*

## Execution Steps

### Step 1: Run backing script (if available)

If `scripts/knowledge_coverage.py` exists:
```bash
python scripts/knowledge_coverage.py {family} {platform}
```

Proceed to Step 4 to read and interpret the output.
If the script is absent, execute Steps 2–3 manually.

### Step 2: Load knowledge

```python
claims = load_json("knowledge/{family}/{platform}/merged/claims.json")
api_surface = load_json("knowledge/{family}/{platform}/merged/api_surface.json")
site_plan = load_yaml("reports/plans/{family}/{platform}/site_plan.yaml")  # optional
```

If `site_plan.yaml` does not exist: continue without exclusion mapping; all uncited units
will be classified as `orphaned` rather than `excluded`.

### Step 3: Walk content pages and classify

For each content file matching the configured content paths for `{family}/{platform}`:
- Extract `evidence.claims` from frontmatter → set of claim IDs cited
- Extract `evidence.apis` from frontmatter → set of API member references cited

Accumulate: `used_claims = all cited claim IDs`, `used_apis = all cited API members`

**For each claim in claims.json**:
- `claim.id` in `used_claims` → **used_in_content**
- Claim's topic in site_plan excluded_topics (if site_plan available) → **excluded_by_planner**
- Otherwise → **orphaned**

**For each API member in api_surface.json** (format: `{ClassName}.{memberName}`):
- Member reference in `used_apis` → **used_in_content**
- Class has no page in site_plan (if site_plan available) → **excluded_by_planner**
- Otherwise → **orphaned**

### Step 4: Write reconciliation report

Write `reports/coverage/{family}/{platform}/{date}-coverage-report.md` with:

1. **Summary table**

   | Disposition | Claims | API Members | % of total |
   |-------------|--------|-------------|-----------|
   | used_in_content | N | N | X% |
   | orphaned | N | N | X% |
   | excluded_by_planner | N | N | X% |

2. **Orphaned clusters** — groups of orphaned claims/members by topic/class

3. **Exclusion justification** — which topics were excluded by site planner and why
   (omit this section if site_plan.yaml was not available)

4. **Coverage ratio** — `used / (used + orphaned)` as a percentage; flag if < 90%

### Step 5: Return verdict

- Coverage ≥ 90%: **PASS** — "Knowledge coverage is adequate"
- Coverage 70–89%: **WARN** — "Knowledge coverage below 90%; review orphaned clusters"
- Coverage < 70%: **FAIL** — "Significant knowledge orphaning detected; launch quality is impaired"

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-80 --status completed
> ```

## Acceptance Criteria

- Every claim in claims.json has exactly one disposition
- Every public API member in api_surface.json has exactly one disposition
- Report written to `reports/coverage/{family}/{platform}/{date}-coverage-report.md`
- Verdict returned to operator

## Failure Modes

| Condition | Action |
|-----------|--------|
| `claims.json` missing | STOP — run `/knowledge-update {family} {platform}` first |
| No content files found | Report coverage = 0%; return FAIL |
| Evidence frontmatter malformed | Log as WARN; skip file; continue |
| `site_plan.yaml` missing | WARN; continue without exclusion mapping |
| Knowledge stale | HALT — run knowledge-update first |

## Related Skills

- `/knowledge-update {family} {platform}` — refreshes the knowledge store
- `/content-eval {family} {platform}` — per-page quality evaluation
- S-81 (knowledge-coverage-audit) — deeper per-claim disposition with 9-state taxonomy
- S-90 (truth-audit) — member-level API claim verification

---
name: coverage-reconcile
description: >
  Trace every knowledge unit (claim, API member) to a page disposition
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-80: Coverage Reconcile — Knowledge Unit Disposition Report

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `cells net` or `slides python`

## Purpose

Produce a full disposition table for every knowledge unit (claim from claims.json,
API member from api_surface.json) for the given product, showing whether it is:
- Used in a content page (cited in evidence.claims or evidence.apis)
- Stored but not used (in knowledge store, not cited anywhere)
- Orphaned (no page covers the relevant topic)
- Excluded by the site planner (cluster excluded from site plan)

This enables the operator to verify knowledge coverage and identify gaps before
trusting a product launch as complete.

## Inputs

- `knowledge/{family}/{platform}/merged/claims.json` — all knowledge claims
- `knowledge/{family}/{platform}/merged/api_surface.json` — all API members
- `reports/plans/{family}/{platform}/site_plan.yaml` — planner exclusions
- `content/*/en/{family}/{platform}/` — all generated content files (evidence frontmatter)

## Execution Steps

### Step 1 — Load knowledge

```python
claims = load_json("knowledge/{family}/{platform}/merged/claims.json")
api_surface = load_json("knowledge/{family}/{platform}/merged/api_surface.json")
site_plan = load_yaml("reports/plans/{family}/{platform}/site_plan.yaml")
```

### Step 2 — Walk content pages

For each content file matching `content/*/en/{family}/{platform}/**/*.md`:
- Extract `evidence.claims` from frontmatter → set of ERC IDs cited
- Extract `evidence.apis` from frontmatter → set of API member references cited

Accumulate: `used_claims = all cited ERC IDs`, `used_apis = all cited API members`

### Step 3 — Classify each knowledge unit

For each claim in claims.json:
- `claim.id` in `used_claims` → **used_in_content**
- Claim's topic in planner excluded_topics → **excluded_by_planner**
- Otherwise → **orphaned**

For each API member in api_surface.json (format: `{ClassName}.{memberName}`):
- Member reference in `used_apis` → **used_in_content**
- Class has no page in site_plan → **excluded_by_planner** (if site_plan excluded it)
- Otherwise → **orphaned**

### Step 4 — Write reconciliation report

Write `reports/coverage/{family}/{platform}/{date}-coverage-report.md` with:

1. **Summary table**
   | Disposition | Claims | API Members | % of total |

2. **Orphaned clusters** — groups of orphaned claims/members by topic/class

3. **Exclusion justification** — which topics were excluded by site planner and why

4. **Coverage ratio** — `used / (used + orphaned)` as a percentage; flag if < 90%

### Step 5 — Return verdict

- Coverage ≥ 90%: PASS — "Knowledge coverage is adequate"
- Coverage 70–89%: WARN — "Knowledge coverage below 90%; review orphaned clusters"
- Coverage < 70%: FAIL — "Significant knowledge orphaning detected; launch quality is impaired"

## Acceptance Criteria

- Every claim in claims.json has exactly one disposition
- Every public API member in api_surface.json has exactly one disposition
- Report written to `reports/coverage/{family}/{platform}/{date}-coverage-report.md`
- Verdict returned to operator

## Failure Modes

| Condition | Action |
|-----------|--------|
| claims.json missing | STOP — run `/knowledge-update {family} {platform}` first |
| No content files found | Report coverage = 0%; return FAIL |
| Evidence frontmatter malformed | Log as WARN; skip file; continue |

## Related Skills

- `/knowledge-update {family} {platform}` — refreshes the knowledge store
- `/launch-rollback {family} {platform}` — S-79, revert flawed launch
- `/content-eval {family} {platform}` — per-page quality evaluation

## Registry

**Skill code**: S-80
**Status**: REGISTERED — AGENTS.md §12 entry added 2026-04-07
**Script**: `scripts/pipeline/knowledge_coverage.py` (existing — check if compatible)
**Test**: `scripts/pipeline/tests/test_coverage_reconcile.py` (to be created)

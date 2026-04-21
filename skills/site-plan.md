---
name: site-plan
id: S-57
description: >
  Produce a deterministic, evidence-bound manifest of all pages a product needs
  across all 5 subdomains. Consumed by launch-product, new-blog-post,
  new-docs-page, new-kb-howto, new-products-page, and gap-eval.
args: "{family} {platform} [--mode launch|update|section] [--section products|docs|blog|kb|reference] [--dry-run]"
---

# S-57: Site Plan — Production-Grade Pre-Generation Site Manifest

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform} [--mode launch|update|section] [--section products|docs|blog|kb|reference] [--dry-run]`

## Purpose

Produce `reports/plans/{family}/{platform}/site_plan.yaml` — a deterministic, evidence-bound manifest
of all pages a product needs across all 5 subdomains. Consumed by `launch-product`, `new-blog-post`,
`new-docs-page`, `new-kb-howto`, `new-products-page`, and `gap-eval`.

## Pre-conditions

1. Run `/knowledge-bootstrap {family} {platform}` first — halt on `STOP:partial`; halt and review on `REFRESHED`
2. `knowledge/{family}/{platform}/merged/` must have: `claims.json`, `api_surface.json`, `formats.json`, `limitations.md`, `model.yaml`

## Modes

| Mode | When to use |
|---|---|
| `launch` | First time planning a product launch |
| `update` | After a knowledge refresh — produces delta |
| `section` | Plan a single subdomain (e.g. only `kb`) |

## Steps

1. **Run the site planner**:
   ```bash
   python scripts/pipeline/site_planner.py {family} {platform} \
     [--mode {mode}] [--section {section}] [--dry-run]
   ```

2. **Inspect the site plan** at `reports/plans/{family}/{platform}/site_plan.yaml`:
   - `pages` — all pages planned for generation
   - `clusters` — content clusters grouped by topic
   - `delta` (update mode) — `pages_to_add`, `pages_to_update`, `pages_to_remove`
   - `evidence` — knowledge model SHA and confidence scores

3. **Review excluded clusters**: Check `excluded_clusters` for topics that were below
   confidence threshold. Confirm exclusions are intentional.

4. **Dry-run validation** (if `--dry-run`): No files written; plan printed to stdout for review.

5. **Confirm plan**: Report plan totals:
   ```
   SITE PLAN — {family}/{platform}
   Mode: {mode}
   Pages planned:
     products.aspose.org:  N
     docs.aspose.org:      N
     blog.aspose.org:      N
     kb.aspose.org:        N
     reference.aspose.org: N
   Total: N
   Excluded clusters: N
   Plan written to: reports/plans/{family}/{platform}/site_plan.yaml
   ```

## Post-conditions

- `reports/plans/{family}/{platform}/site_plan.yaml` written
- All planned pages have evidence-justified entries
- Downstream skills (launch-product, gap-eval) can consume the plan

## Error handling

| Error | Action |
|-------|--------|
| `claims.json` missing | Halt: run knowledge-bootstrap first |
| Knowledge stale | Halt: run S-12 + S-14 first |
| `--mode update` but no `knowledge_delta.json` | WARN; fall back to full plan mode |

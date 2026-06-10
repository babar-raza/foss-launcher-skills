---
name: delta-site-plan
id: S-87
description: >
  Incremental site planning after a knowledge update. Compares updated knowledge
  against the existing site_plan.yaml to produce a delta: pages to add, update,
  remove, or rename.
args: "{family} {platform}"
---

# S-87: Delta Site Plan — Incremental Site Planning After Knowledge Update

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

After a knowledge refresh (S-14), compute which pages need to be added, updated, removed,
or renamed. Uses `site_planner.py --mode update` which compares the updated knowledge
artifacts against the existing `site_plan.yaml` to produce a delta section.

This skill must run before content execution (S-20, S-88) so the downstream skills have
a complete picture of what changes are needed.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/knowledge_delta.json` exists (S-14 must have run)
2. `reports/plans/{family}/{platform}/site_plan.yaml` exists (initial site plan from S-57)
3. `knowledge/{family}/{platform}/merged/api_surface.json` and `claims.json` are current

## Steps

1. **Run the site planner in update mode**:
   ```bash
   python scripts/pipeline/commands/launch/site_planner.py {family} {platform} --mode update
   ```

2. **Review the delta output**:
   - `delta.pages_to_add` — new pages to generate
   - `delta.pages_to_update` — existing pages to refresh via S-20 (page-update)
   - `delta.pages_to_remove` — obsolete pages to retire via S-88 (page-retire)
   - `delta.pages_renamed` — slugs that changed (require redirect management)

3. **If `knowledge_delta.json` is absent**: WARN: "knowledge_delta.json not found; falling back to full plan mode."
   Run `site_planner.py` without `--mode update` to regenerate the full plan.

4. **Write updated site plan**: The planner writes the delta into the existing `site_plan.yaml`.

5. **Report delta summary**:
   ```
   DELTA SITE PLAN — {family}/{platform}
   Pages to add:    N
   Pages to update: N
   Pages to remove: N
   Pages renamed:   N

   Updated plan: reports/plans/{family}/{platform}/site_plan.yaml
   ```

## Post-conditions

- `reports/plans/{family}/{platform}/site_plan.yaml` updated with delta section
- Downstream skills (page-update, batch-reference --update, page-retire) can consume delta
- `pages_to_remove` must be reviewed before passing to page-retire

## Error handling

| Error | Action |
|-------|--------|
| No existing site plan | Run S-57 (site-plan) in launch mode first |
| `knowledge_delta.json` missing | WARN; fall back to full plan mode |
| `api_surface.json` stale | Halt: run S-12 + S-14 first |

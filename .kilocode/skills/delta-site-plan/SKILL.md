---
name: delta-site-plan
id: S-82
description: >
  Run incremental site planning after a knowledge update to determine which pages
  to add, update, remove, or rename.
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-82: Delta Site Plan — Incremental Site Planning After Knowledge Update

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

After a knowledge refresh (S-14), compute which pages need to be added, updated, removed,
or renamed. Uses `site_planner.py --mode update` which compares the updated knowledge
artifacts against the existing `site_plan.yaml` to produce a delta section.

This skill must run before content execution (S-20, S-83) so the downstream skills have
a complete picture of what changes are needed.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/knowledge_delta.json` exists (S-14 must have run)
2. `reports/plans/{family}/{platform}/site_plan.yaml` exists (initial site plan from S-47)
3. `knowledge/{family}/{platform}/merged/api_surface.json` and `claims.json` are current

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-82 --scope "*"
> ```


1. **Parse arguments**: Extract `{family}` and `{platform}` from $ARGUMENTS.

2. **Verify pre-conditions**:
   - Confirm `knowledge_delta.json` exists. If absent, print:
     `STOP: knowledge_delta.json not found. Run /knowledge-update {family} {platform} first.`
     and exit.
   - Confirm `site_plan.yaml` exists. If absent, print:
     `STOP: site_plan.yaml not found. Run /site-plan {family} {platform} first.`
     and exit.

3. **Run delta planning**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/launch/site_planner.py {family} {platform} --mode update
   ```
   This reads the current `api_surface.json`, `claims.json`, and `knowledge_delta.json`,
   compares them against the existing `site_plan.yaml`, and writes a `delta:` section to
   `reports/plans/{family}/{platform}/site_plan.yaml`.

4. **Report delta summary**: Print what was found:
   ```
   Delta Site Plan: {family}/{platform}
   pages_to_add:    {N}  (new pages required by knowledge additions)
   pages_to_update: {N}  (existing pages with changed claims/APIs)
   pages_to_remove: {N}  (pages whose claim/API coverage is now absent)
   pages_renamed:   {N}  (pages whose slug changed)
   ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-82 --status completed
> ```

## Output

The `delta:` section in `site_plan.yaml` contains:

```yaml
delta:
  generated_at: "2026-04-07T..."
  based_on_delta: "knowledge_delta.json"
  pages_to_add:
    - slug: "new-feature-guide"
      kind: "docs"
      reason: "new_claim CLM-xxx covers feature not in any existing page"
  pages_to_update:
    - path: "content/docs.aspose.org/en/{family}/{platform}/existing-page/index.md"
      reason: "modified_claim CLM-yyy"
  pages_to_remove:
    - path: "content/docs.aspose.org/en/{family}/{platform}/old-page/index.md"
      reason: "all cited claims removed"
  pages_renamed: []
```

## Post-conditions

- `reports/plans/{family}/{platform}/site_plan.yaml` has a current `delta:` section
- `pages_to_add` lists pages that must be generated (feed to S-84 Step 5 delta dispatch)
- `pages_to_remove` lists candidates for retirement (feed to S-83 page-retire)
- `pages_to_update` lists pages for S-20 (page-update) to process

## Error handling

- If `knowledge_delta.json` is absent: halt with instruction to run S-14
- If `site_plan.yaml` is absent: halt with instruction to run S-47
- If `site_planner.py --mode update` fails: print error and exit without modifying site_plan.yaml

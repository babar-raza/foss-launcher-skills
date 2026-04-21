---
name: refresh-product
id: S-84
description: >
  Orchestrate the full post-launch product refresh cycle: detect changes, update
  knowledge, plan delta, update content, retire obsolete pages, validate, and commit.
  14-step chain with checkpoint-based resume.
args: "{family} {platform}"
---

# S-84: Refresh Product — Full Post-Launch Refresh Orchestration

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Orchestrate the complete post-launch refresh cycle for a single product. Detects upstream
changes, refreshes knowledge, plans what content needs to change, updates stale pages,
generates new pages, retires obsolete pages, validates quality, and commits the result.

This skill is the entry point for the maintenance chain (AGENTS.md §6).

## Pre-conditions

- `knowledge/{family}/{platform}/merged/model.yaml` must exist
- Clone cache reachable at `runs/.clone_cache/` or `ASPOSE_CLONE_CACHE`

## Early Exit (No Change)

If Step 1 finds no SHA change, exit cleanly:
```
No upstream change detected for {family}/{platform}. No content update needed.
```

## Steps

1. **Detect change** (S-12: knowledge-diff):
   ```bash
   /knowledge-diff {family} {platform} {repo-path}
   ```
   - If SHAs match: exit cleanly
   - If HIGH/MEDIUM: `stale_since` auto-set; proceed to Step 2

2. **Refresh knowledge** (S-14: knowledge-update):
   ```bash
   /knowledge-update {family} {platform}
   ```
   - Runs full scout → enrich → promote → index pipeline
   - Writes `knowledge_delta.json` with semantic diff

3. **Delta site planning** (S-87: delta-site-plan):
   ```bash
   /delta-site-plan {family} {platform}
   ```
   - Produces `delta.pages_to_add`, `pages_to_update`, `pages_to_remove`

4. **Update stale existing pages** (S-20: page-update):
   ```bash
   /page-update {family} {platform}
   ```

5. **Delta dispatch — generate new pages**:
   For each page in `delta.pages_to_add`:
   - `docs/` → `/new-docs-page {family} {platform} {slug}`
   - `blog/` → `/new-blog-post {family} {platform} {slug}`
   - `kb/faq` → `/new-kb-faq {family} {platform}`
   - `kb/howto` → `/new-kb-howto {family} {platform} {slug}`
   - `reference/` → `python scripts/pipeline/batch_reference.py {family} {platform} --update`

6. **Retire obsolete pages** (S-88: page-retire):
   ```bash
   /page-retire --from-plan reports/plans/{family}/{platform}/site_plan.yaml
   ```
   Always run `--dry-run` first; confirm before executing.

7. **Update reference pages for modified APIs** (S-67: batch-reference --update):
   ```bash
   python scripts/pipeline/batch_reference.py {family} {platform} --update
   ```

8. **Family page sync** (S-58: family-sync):
   ```bash
   /family-sync {family}
   ```

9. **Verification gate** — run before commit:
   ```bash
   python scripts/pipeline/post_refresh_verify.py {family} {platform} --full-check
   ```
   Must return `PASS` on all checks. If any FAIL → route to S-93 (system-heal).

10. **Link validation** (S-70: link-validate):
    ```bash
    /link-validate {family} {platform}
    ```

11. **Content eval spot-check**:
    ```bash
    python -m scripts.pipeline.content_eval evaluate \
      --family {family} --platform {platform} --grade-filter D,F --format json
    ```
    Any new grade D/F pages → route to S-26 (heal-page).

12. **Commit** (S-81: commit):
    ```bash
    /commit --scope {family}/{platform} \
      --hint "post-launch refresh: {N} pages updated, {M} added, {K} retired"
    ```

## Post-conditions

- Knowledge model fresh (`stale_since: null`)
- All content pages reflect current knowledge
- Obsolete pages marked `draft: true`
- Verification gate PASS
- Changes committed with `Skills invoked:` provenance

## Error handling

| Error | Action |
|-------|--------|
| Step 2 (knowledge-update) fails | Halt; run S-72 (diagnose-skill-failure) |
| Verification gate FAIL | Run S-93 (system-heal) before committing |
| No upstream change | Exit cleanly with early-exit message |

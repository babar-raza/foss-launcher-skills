<!-- CONTRACT: agent-executed
     purpose: orchestrate full post-launch product refresh cycle (14-step chain)
     preconditions: product already launched; knowledge model accessible; clone cache reachable
     postcondition: content updated from knowledge delta; verification gate passed; changes committed
     idempotent: yes — checkpoint-based resume; completed steps produce no-ops on re-run
     verified: 2026-04-11
-->
---
name: refresh-product
id: S-84
description: >
  Orchestrate the full post-launch product refresh cycle: detect changes, update
  knowledge, plan delta, update content, retire obsolete pages, validate, and commit.
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-84: Refresh Product — Full Post-Launch Refresh Orchestration

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Orchestrate the complete post-launch refresh cycle for a single product. Detects upstream
changes, refreshes knowledge, plans what content needs to change, updates stale pages,
generates new pages, retires obsolete pages, validates quality, translates changed pages,
and commits the result.

This skill is the entry point for the maintenance chain (AGENTS.md §6). Running it ensures
the full cycle executes in the correct order with progress tracking and a verification gate
before any commit.

## Pre-conditions

- Knowledge model must be accessible: `knowledge/{family}/{platform}/merged/model.yaml` must exist.
- Clone cache must be reachable or previously populated at `runs/.clone_cache/` (or `ASPOSE_CLONE_CACHE`).
- **S-12 (knowledge-diff) is auto-invoked as Step 1** — no separate pre-activation required.
  If S-12 reports no SHA change, the skill exits cleanly without further steps.

## Early Exit (No Change)

If Step 1 finds no SHA change (upstream repo unchanged), exit cleanly:
```
No upstream change detected for {family}/{platform}.
SHA: {sha} (unchanged)
No content update needed.
```
Do not run any subsequent steps. Exit 0.

## Steps

1. **Detect change** (S-12: knowledge-diff):
   ```
   /knowledge-diff {family} {platform} {repo-path}
   ```
   - Calls `update_clone()` to fetch upstream before SHA comparison
   - If SHAs match: exit cleanly with "no upstream change" message
   - If HIGH/MEDIUM: `stale_since` auto-set; proceed to Step 2
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step knowledge_diff`

2. **Refresh knowledge** (S-14: knowledge-update):
   ```
   /knowledge-update {family} {platform}
   ```
   - Runs full scout → enrich → promote → index pipeline
   - Writes `knowledge_delta.json` with semantic diff
   - Clears `stale_since` on success
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step knowledge_update`

3. **Delta site planning** (S-82: delta-site-plan):
   ```
   /delta-site-plan {family} {platform}
   ```
   - Runs `site_planner.py --mode update`
   - Produces `delta.pages_to_add`, `pages_to_update`, `pages_to_remove`, `pages_renamed`
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step delta_site_plan`

4. **Update stale existing pages** (S-20: page-update):
   ```
   /page-update {family} {platform}
   ```
   - Reads `knowledge_delta.json` to find affected pages
   - Updates stale paragraphs; uses blog regeneration rule for blog posts
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step page_update`

5. **Delta dispatch — generate new pages**:
   For each page in `delta.pages_to_add` from the site_plan.yaml delta section:
   - `docs/` prefix → `/new-docs-page {family} {platform} {slug}`
   - `blog/` prefix → `/new-blog-post {family} {platform} {slug}`
   - `kb/faq` → `/new-kb-faq {family} {platform}`
   - `kb/howto` → `/new-kb-howto {family} {platform} {slug}`
   - `reference/` → `python scripts/pipeline/batch_reference.py {family} {platform} --update`
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step delta_dispatch`

6. **Retire obsolete pages** (S-83: page-retire):
   ```
   /page-retire --from-plan reports/plans/{family}/{platform}/site_plan.yaml
   ```
   - Always run `--dry-run` first; confirm before executing
   - Retires pages from `delta.pages_to_remove` (dual-signal rule applies)
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step page_retire`

6.5. **Un-retire resurrected API pages** (retire_page.py --un-retire):
   ```bash
   .venv/Scripts/python scripts/pipeline/retire_page.py --un-retire --from-delta {family} {platform}
   ```
   - Reads `resurrected_apis` from `knowledge_delta.json`
   - Removes `draft: true` and `retired_at` from reference pages whose class was re-added
   - Idempotent: pages without `draft: true` are skipped
   - Must run BEFORE batch-reference --update so un-retired pages get regenerated

7. **Update reference pages for modified/new/resurrected APIs** (S-62: batch-reference --update):
   ```
   .venv/Scripts/python scripts/pipeline/batch_reference.py {family} {platform} --update
   ```
   - Regenerates reference pages for classes in `knowledge_delta.json` (modified + new + resurrected APIs)
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step reference_update`

8. **Family page sync** (S-48: family-sync):
   ```
   /family-sync {family}
   ```
   Updates `products.aspose.org` family landing page with any version/status changes.
   - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step family_sync`

9. **Content check** on all changed files (S-23: content-check):
   ```
   /content-check {family} {platform}
   ```
   Run on all pages updated, generated, or modified in Steps 4-7.

10. **Link validation** (S-65: link-validate):
    ```
    /link-validate {family} {platform}
    ```
    Verify no broken cross-subdomain links were introduced.

11. **Translate changed pages** (S-53: translate-batch):
    ```
    /translate {family} {platform}
    ```
    **Filter**: Only translate pages where body `content_hash` changed (not just frontmatter/evidence updates).
    Compare `provenance.content_hash` before and after to identify pages with real content changes.
    Translating metadata-only changes wastes LLM budget.
    **LLM_API_KEY absent**: If `LLM_API_KEY` is not set in the environment, this step emits
    a SKIP-WITH-WARNING and the chain continues. Translation can be re-run separately via
    `/translate {family} {platform}` once the key is available. This is not a chain-abort condition.
    - Record progress: `python scripts/pipeline/post_refresh_verify.py {family} {platform} --step translate`

12. **Record step completions**: After each step above, call:
    ```bash
    .venv/Scripts/python scripts/pipeline/post_refresh_verify.py {family} {platform} --step {step_name}
    ```
    Progress is tracked at `reports/refresh_state/{family}/{platform}/progress.json` (local-only, not committed).

13. **Verification gate** (post_refresh_verify.py --verify):
    ```bash
    .venv/Scripts/python scripts/pipeline/post_refresh_verify.py {family} {platform} --verify
    ```
    Runs post-refresh checklist:
    - `stale_since` is null in `merged/model.yaml`
    - No content pages cite claim IDs absent from `merged/claims.json`
    - No reference pages exist for classes absent from `merged/api_surface.json`
    - No reference pages are incorrectly retired (draft: true) for classes that exist in api_surface (Check 3b)
    - `stale_detect.py` reports 0 stale pages (end-state proxy for page freshness)

    Note: `audit.py` is NOT re-run per-page during `--verify`; it is already enforced
    by S-20 and S-23 during the chain. `stale_detect.py` is the correct end-state proxy:
    pages with audit failures leave their `model_sha` stale (Check 4) or produce orphaned
    claim citations (Check 2), both of which are caught above.

    **If verification fails**: do NOT proceed to Step 14. Fix the reported issues and re-run
    the failing sub-steps, then re-run `--verify`. Commit only after verification passes.

14. **Commit** (S-76: commit):
    ```
    /commit
    ```
    Include in the commit message:
    - Knowledge delta summary (new/removed claims and APIs)
    - Step list from `progress.json`
    - `Skills invoked: [refresh-product, S-12, S-14, S-82, S-20, S-83, S-62, S-48]`

## Progress Tracking

Progress is stored at `reports/refresh_state/{family}/{platform}/progress.json` (local-only, gitignored).
Check current progress at any time:
```bash
.venv/Scripts/python scripts/pipeline/post_refresh_verify.py {family} {platform} --status
```

If the refresh cycle is interrupted, re-run this skill — completed steps are idempotent and
will be skipped or produce no-ops on re-run.

## Post-conditions

- All stale content pages have been updated or retired
- All new pages required by knowledge additions have been generated
- No orphaned claim citations remain
- Verification gate (`--verify`) exited 0
- All changes committed with structured commit message

## Error handling

- Step 1 (detect): if `update_clone()` fails, log warning and compare against cached local SHA; continue
- Step 2 (knowledge-update): if scout fails, abort entire cycle; do not write partial delta
- Step 13 (verify): if fails, list specific issues; do not commit; fix and re-verify
- Any step failure: check `--status` to see which steps completed; resume from the failing step

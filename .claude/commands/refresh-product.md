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
  Re-generate content for a single product after knowledge update: detect upstream
  changes, refresh knowledge model, plan delta, update stale pages, generate new pages,
  retire obsolete pages, validate quality, and commit. Translation runs via separate
  cadence (AREA9-TRANS-001) and is not part of this chain.
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-84: Refresh Product — Full Post-Launch Refresh Orchestration

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Re-generate content for a single product after a knowledge update. Detects upstream
changes, refreshes the knowledge model, plans what content needs to change, updates stale
pages, generates new pages, retires obsolete pages, validates quality, and commits the
result.

**Translation is not part of this chain** — it was decoupled in AREA9-TRANS-001 and runs
via a separate cadence. After refresh, run `translation_coverage.py` to detect locale
staleness and trigger translation independently.

This skill is the entry point for the maintenance chain (AGENTS.md §6; full detail: [docs/workflows/skill-chains.md](../docs/workflows/skill-chains.md)). Running it ensures
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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-84 --scope "*"
> ```


1. **Detect change** (S-12: knowledge-diff):
   ```
   /knowledge-diff {family} {platform} {repo-path}
   ```
   - Calls `update_clone()` to fetch upstream before SHA comparison
   - If SHAs match: exit cleanly with "no upstream change" message
   - If HIGH/MEDIUM: `stale_since` auto-set; proceed to Step 2
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step knowledge_diff`

2. **Refresh knowledge** (S-14: knowledge-update):
   ```
   /knowledge-update {family} {platform}
   ```
   - Runs full scout → enrich → promote → index pipeline
   - Writes `knowledge_delta.json` with semantic diff
   - Clears `stale_since` on success
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step knowledge_update`

3. **Delta site planning** (S-82: delta-site-plan):
   ```
   /delta-site-plan {family} {platform}
   ```
   - Runs `site_planner.py --mode update`
   - Produces `delta.pages_to_add`, `pages_to_update`, `pages_to_remove`, `pages_renamed`
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step delta_site_plan`

3.5. **Page Impact Assessment**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/page_impact_assess.py {family} {platform}
   ```
   - Scores every English page HIGH_IMPACT / MEDIUM_IMPACT / LOW_IMPACT / NOT_AFFECTED
     based on body text signals vs `knowledge_delta.json` (class names, method names, claim keywords)
   - Writes `reports/refresh_review/{family}/{platform}/page_impact.json`
   - **If `knowledge_delta.json` absent**: step is skipped with WARNING; chain continues
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step page_impact_assess`

4. **Update stale existing pages** (S-20: page-update):
   ```
   /page-update {family} {platform}
   ```
   - Reads `knowledge_delta.json` to find affected pages
   - Updates stale paragraphs; uses blog regeneration rule for blog posts
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step page_update`

5. **Delta dispatch — generate new pages**:
   For each page in `delta.pages_to_add` from the site_plan.yaml delta section:
   - `docs/` prefix → `/new-docs-page {family} {platform} {slug}`
   - `blog/` prefix → `/new-blog-post {family} {platform} {slug}`
   - `kb/faq` → `/new-kb-faq {family} {platform}`
   - `kb/howto` → `/new-kb-howto {family} {platform} {slug}`
   - `reference/` → `python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --update`
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step delta_dispatch`

6. **Retire obsolete pages** (S-83: page-retire):
   ```
   /page-retire --from-plan reports/plans/{family}/{platform}/site_plan.yaml
   ```
   - Always run `--dry-run` first; confirm before executing
   - Retires pages from `delta.pages_to_remove` (dual-signal rule applies)
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step page_retire`

7. **Update reference pages for modified APIs** (S-62: batch-reference --update):
   ```
   .venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --update
   ```
   - Regenerates only reference pages for classes in `knowledge_delta.json modified_apis`
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step reference_update`
   - **Write execution reconciliation** (after all content steps complete):
     ```bash
     .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --reconcile
     ```

8. **Family page sync** (S-48: family-sync):
   ```
   /family-sync {family}
   ```
   Updates `products.aspose.org` family landing page with any version/status changes.
   - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step family_sync`

9. **Content check** on all changed files (S-23: content-check):
   ```
   /content-check {family} {platform}
   ```
   Run on all pages updated, generated, or modified in Steps 4-7.

9.5. **Re-grade changed pages** (TC-P3-03: post-refresh re-grading):
    ```bash
    .venv/Scripts/python -m content_eval evaluate {family} {platform} --write-grade
    ```
    Recalculates grades against the updated knowledge model and persists them to frontmatter.
    Compare before/after grades: any page regressing to D or F should be flagged for healing
    before commit. Pass `--skip-regrade` to bypass for fast refresh runs.

10. **Link validation** (S-65: link-validate):
    ```
    /link-validate {family} {platform}
    ```
    Verify no broken cross-subdomain links were introduced.

11. **Record step completions**: After each step above, call:
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step {step_name}
    ```
    Progress is tracked at `reports/refresh_state/{family}/{platform}/progress.json` (local-only, not committed).

12. **Verification gate** (post_refresh_verify.py --verify):
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --verify
    ```
    Runs post-refresh checklist:
    - `stale_since` is null in `merged/model.yaml`
    - No content pages cite claim IDs absent from `merged/claims.json`
    - No reference pages exist for classes absent from `merged/api_surface.json`
    - `stale_detect.py` reports 0 stale pages (end-state proxy for page freshness)

    Note: `audit.py` is NOT re-run per-page during `--verify`; it is already enforced
    by S-20 and S-23 during the chain. `stale_detect.py` is the correct end-state proxy:
    pages with audit failures leave their `model_sha` stale (Check 4) or produce orphaned
    claim citations (Check 2), both of which are caught above.

    **If verification fails**: do NOT proceed to Step 13. Fix the reported issues and re-run
    the failing sub-steps, then re-run `--verify`. Commit only after verification passes.

12.5. **Hugo build check** (VVR-TC09-001):
    ```bash
    bash scripts/ci/hooks/check_hugo_build.sh
    ```
    Builds all 5 sites (`products.aspose.org docs.aspose.org kb.aspose.org reference.aspose.org blog.aspose.org`).
    - If any site FAIL: abort; do not proceed to Step 13.5 or Step 13 (commit).
    - Invoke S-67 (diagnose-skill-failure) if build fails before retrying.
    - A passing build does NOT prove rendering completeness (Hugo silently skips missing frontmatter
      sections via `{{ with }}` guards); use the verification gate (Step 12) for semantic checks.
    - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step hugo_build`

13.5. **Coverage report**:
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/refresh_review.py {family} {platform} --report
    ```
    Writes `reports/refresh_review/{family}/{platform}/coverage_report.md` with per-subdomain
    counts (total, body_updated, evidence_only, not_affected, retired).
    - If coverage < 100%: emits WARNING and includes gap in commit message; does NOT abort commit
    - Record progress: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step coverage_report`


13a. **Two-layer triage gate** (S-92: triage-confirm):

    Before committing, confirm that all updated and generated pages pass the
    Layer 2 body-prose scanner. This catches residual staleness signals not
    caught by the SHA-based Layer 1 check.

    For each page in the updated/generated set, run:
    ```python
    from triage_confirm import triage_confirm
    result = triage_confirm(page_path, knowledge)
    # knowledge must include: api_surface, claims, delta
    ```
    Or invoke the skill:
    ```
    /triage-confirm {family} {platform}
    ```
    - If `result['stale']` is True for any page: log the reasons and re-run
      the relevant content update step before continuing.
    - If all pages return `stale: False`: proceed to Step 13.
    - Record step: `.venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step triage_gate`

13. **Commit** (S-76: commit):
    ```
    /commit
    ```
    Include in the commit message:
    - Knowledge delta summary (new/removed claims and APIs)
    - Step list from `progress.json`
    - `Skills invoked: [refresh-product, S-12, S-14, S-82, S-20, S-83, S-62, S-48]`

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-84 --status completed
> ```

## Progress Tracking

Progress is stored at `reports/refresh_state/{family}/{platform}/progress.json` (local-only, gitignored).
Check current progress at any time:
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --status
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
- Step 12 (verify): if fails, list specific issues; do not commit; fix and re-verify
- Any step failure: check `--status` to see which steps completed; resume from the failing step

---
name: page-retire
id: S-88
description: >
  Retire obsolete content pages by setting draft: true in frontmatter. Uses Hugo's
  draft mechanism to suppress pages without deleting them, preserving history and
  allowing rollback.
args: "{file-path} | --from-plan {site_plan_path}"
---

# S-88: Page Retire — Retire Obsolete Content Pages

**Arguments**: $ARGUMENTS
Expected format:
- `{file-path}` — retire a single specific page
- `--from-plan {site_plan_path}` — retire all pages in `delta.pages_to_remove`

## Purpose

Retire content pages that are no longer valid because the knowledge they cover has been removed
or significantly changed. Uses Hugo's standard `draft: true` mechanism to suppress pages from
production builds without deleting them (preserving history and allowing rollback).

## Retirement Signals

Before retiring any page, confirm at least one of these signals:

**(a) Cluster-level signal**: The page appears in `site_plan.yaml delta.pages_to_remove`
(produced by S-87 delta-site-plan).

**(b) Claim-level signal**: `stale_detect.py` reports `orphaned_claims` for the page
(claims cited in evidence frontmatter that no longer exist in `merged/claims.json`).

**Retire only when BOTH signals agree**, OR when the operator explicitly names a path.
Retiring on a single signal without operator confirmation risks premature retirement.

## Pre-conditions

1. File exists at the target path under `$CONTENT_REPO_PATH/content/`
2. `knowledge/{family}/{platform}/merged/model.yaml` must exist

## Steps

1. **Parse arguments**: Determine single-file mode or plan-driven mode.

2. **In plan-driven mode** (`--from-plan`):
   - Read `{site_plan_path}` and extract `delta.pages_to_remove`
   - Confirm the list with the operator before proceeding

3. **For each target file**:

   a. **Verify retirement signal**: Check both (a) and (b) above. If neither is confirmed and
      the operator did not explicitly name the path, SKIP with a warning.

   b. **Check current state**:
      - If `draft: true` already in frontmatter → SKIP: "already retired"
      - If file does not exist → SKIP: "not found"

   c. **Set draft: true** in frontmatter:
      ```bash
      python scripts/pipeline/commands/healing/retire_page.py --files {path}
      ```
      Or manually: add `draft: true` to YAML frontmatter.

   d. **Update provenance**:
      - Set `provenance.content_origin: retired`
      - Set `provenance.last_mechanism: skill`
      - Set `provenance.auto_updatable: false`

   e. **Run audit** (should now be skipped by draft status in production):
      ```bash
      python scripts/pipeline/commands/content/audit.py --files {path}
      ```

4. **Summary report**:
   ```
   PAGE RETIRE
   Targets: N
   Retired: N
   Skipped (already retired): N
   Skipped (no retirement signal): N
   ```

## Post-conditions

- `draft: true` set in frontmatter of all retired pages
- `provenance.content_origin: retired` in all retired pages
- Pages remain on disk (not deleted)
- Rollback: remove `draft: true` to restore visibility

## Never Do

- Never delete files — retirement is draft-only
- Never retire a page without a confirmed retirement signal
- Never retire pages that are still referenced by active pages (check inbound links first)

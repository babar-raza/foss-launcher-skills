---
name: page-retire
id: S-83
description: >
  Retire obsolete content pages by setting draft: true in frontmatter.
  Does not delete files — uses Hugo's standard draft mechanism.
args: "{file-path} | --from-plan {site_plan_path}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-83: Page Retire — Retire Obsolete Content Pages

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
(produced by S-82 delta-site-plan).

**(b) Claim-level signal**: `stale_detect.py` reports `orphaned_claims` for the page
(claims cited in evidence frontmatter that no longer exist in `merged/claims.json`).

**Retire only when BOTH signals agree**, OR when the operator explicitly names a path.
Retiring on a single signal without operator confirmation risks premature retirement of
pages that still have valid coverage.

## Pre-conditions

1. `scripts/pipeline/retire_page.py` exists
2. Target page(s) exist under `content/`
3. For `--from-plan`: `site_plan.yaml` with `delta.pages_to_remove` exists

## Steps

1. **Parse arguments**: Determine mode — single file or from-plan batch.

2. **Always run --dry-run first**:
   ```bash
   .venv/Scripts/python scripts/pipeline/retire_page.py {file-path} --dry-run
   # or
   .venv/Scripts/python scripts/pipeline/retire_page.py --from-plan reports/plans/{family}/{platform}/site_plan.yaml --dry-run
   ```
   Review the list of pages that would be retired. Confirm before proceeding.

3. **Verify retirement signals** (if not operator-directed):
   For each candidate page, check that BOTH signals are present:
   - Check `site_plan.yaml delta.pages_to_remove` includes the path
   - Check `stale_detect.py` output for `orphaned_claims` on the page
   If only one signal is present, flag for operator confirmation before retiring.

4. **Execute retirement**:
   ```bash
   .venv/Scripts/python scripts/pipeline/retire_page.py {file-path}
   # or
   .venv/Scripts/python scripts/pipeline/retire_page.py --from-plan reports/plans/{family}/{platform}/site_plan.yaml
   ```
   Each retired page receives:
   - `draft: true` in frontmatter (Hugo standard — suppresses from production builds)
   - `retired_at: YYYY-MM-DD` in frontmatter (date of retirement)
   The file is NOT deleted. All other frontmatter fields are preserved.

5. **Report retirement**:
   ```
   Page Retirement Report: {family}/{platform}
   Retired:  {N} pages
   Skipped:  {N} pages (already retired)
   Errors:   {N} pages (path not found, etc.)

   Retired pages:
     - content/docs.aspose.org/en/{family}/{platform}/old-page/index.md
   ```

## Post-conditions

- Retired pages have `draft: true` and `retired_at: YYYY-MM-DD` in frontmatter
- No files are deleted
- Already-retired pages (draft: true) are idempotently skipped
- Pages NOT in the retirement list are unchanged

## Error handling

- If page path does not exist: exit with error code; no partial writes
- If `--from-plan` path not found: halt with clear message
- If frontmatter parse fails: skip that page; log as error; continue batch
- If operator provides a path not confirmed by both signals: warn but proceed (operator override)

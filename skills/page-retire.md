---
name: page-retire
id: S-83
description: >
  Retire obsolete content pages by setting draft: true in frontmatter.
  Does not delete files — uses Hugo's standard draft mechanism to suppress
  pages from production builds while preserving history.
args: "{content-file-path} | --from-plan {site-plan-path}"
---

# S-83: Page Retire — Retire Obsolete Content Pages

**Arguments**: $ARGUMENTS
Expected format:
- `{content-file-path}` — retire a single specific page
- `--from-plan {site-plan-path}` — retire all pages listed in the plan's `pages_to_remove`

## Purpose

Retire content pages that are no longer valid because the knowledge they cover
has been removed or significantly changed. Uses Hugo's standard `draft: true`
mechanism to suppress pages from production builds without deleting them —
preserving history and allowing rollback.

## Retirement signals

Before retiring any page, confirm at least one of these signals:

**(a) Explicit operator request**: The operator names a specific path to retire.

**(b) Plan signal**: The page appears in `pages_to_remove` in a site plan file
produced by a site-planning skill.

**(c) Claim-level signal**: S-13 (stale-detect) reports orphaned claims for the page
(claims cited in evidence frontmatter that no longer exist in `merged/claims.json`).

**Best practice**: Retire only when BOTH signals (b) + (c) agree, OR when the
operator explicitly names a path (a). Retiring on a single automated signal
without operator confirmation risks premature retirement of pages that still
have valid coverage.

## Pre-conditions

1. Target page(s) exist under the content directory
2. For `--from-plan`: a site plan YAML/JSON file with a `pages_to_remove` list exists

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-83 --scope "{target}"
> ```

## Steps

### Step 1: Parse arguments

Determine mode:
- Single file: extract `{content-file-path}`
- From plan: load `pages_to_remove` list from `{site-plan-path}`

### Step 2: Always preview first (dry-run)

Before making changes, list all pages that would be retired and confirm:

```
Pages to retire (dry-run):
  - {content-file-path-1}
  - {content-file-path-2}

Proceed with retirement? [Y/N]
```

Halt if the operator responds N.

### Step 3: Verify retirement signals (if not operator-directed)

For each candidate page, check that at least two signals are present.
If only one automated signal is present: flag for operator confirmation before retiring.

### Step 4: Execute retirement

For each page to retire:

1. Read the file's current frontmatter
2. Set `draft: true`
3. Add `retired_at: YYYY-MM-DD` (today's date in ISO 8601)
4. Write the updated frontmatter back to the file
5. Leave all other frontmatter fields and the body unchanged

If `scripts/retire_page.py` exists in the repo, use it instead:

```bash
# Single file:
python scripts/retire_page.py {content-file-path}

# From plan:
python scripts/retire_page.py --from-plan {site-plan-path}
```

The script and the manual approach produce identical results.

### Step 5: Report retirement

```
Page Retirement Report
Retired:  {N} pages
Skipped:  {N} pages (already retired)
Errors:   {N} pages (path not found, etc.)

Retired pages:
  - {path-1} (retired_at: YYYY-MM-DD)
  - {path-2} (retired_at: YYYY-MM-DD)
```

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-83 --status completed
> ```

## Post-conditions

- Retired pages have `draft: true` and `retired_at: YYYY-MM-DD` in frontmatter
- No files are deleted
- Already-retired pages (draft: true) are idempotently skipped
- Pages NOT in the retirement list are unchanged

## Error handling

| Error | Action |
|---|---|
| Page path does not exist | Exit with error; no partial writes |
| `--from-plan` path not found | Halt with clear message |
| Frontmatter parse fails | Skip that page; log as error; continue batch |
| Operator declines confirmation | Halt; no files modified |

---
name: refresh-product-page
id: S-85
description: >
  Re-generate a single products.aspose.org landing page through the full S-61
  pipeline with no-downgrade-guard protection. Use when the generation template
  (S-61) has been improved and existing pages should benefit.
args: "{family} {platform}"
---

> Cross-skill references like `/new-products-page` refer to sibling skills in this directory.

# S-85: Refresh Product Page — Re-generate Product Landing Page

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `words python` or `slides java`

## Purpose

Re-generate a single `products.aspose.org` landing page when the generation template
(S-61) has been improved. Unlike S-49 Stage 1 (which skips if the page exists and passes
audit), this skill always regenerates and uses the no-downgrade-guard to prevent regressions.

**When to use**:
- S-61 template was updated (new steps, better constraints, structural improvements)
- Product page has `graded_evaluators: audit` and needs full evaluation
- Product page is missing sections that the updated S-61 would produce
- Manual quality review identified content issues that regeneration would fix

**When NOT to use**:
- Upstream FOSS repo changed → use `/refresh-product` (S-84) instead
- Page needs minor edits → use `/manual-edit` (S-73) instead
- Page needs healing from grade D/F → use `/heal-page` (S-26) instead

## Pre-conditions

1. Existing product page must exist at `content/products.aspose.org/en/{family}/{platform}/_index.md`
2. Knowledge model must be available: `knowledge/{family}/{platform}/merged/` exists
3. S-61 (`/new-products-page`) must be available

## Steps

1. **Parse arguments**: Extract `{family}` and `{platform}` from $ARGUMENTS.

2. **Verify existing page**: Confirm the product page exists. If not, abort:
   "No existing product page found. Use `/new-products-page {family} {platform}` for first generation,
   or `/launch-product {family} {platform}` for full 5-subdomain launch."

3. **Snapshot existing page**: Read and store the current page content for comparison:
   ```bash
   cp content/products.aspose.org/en/{family}/{platform}/_index.md content/products.aspose.org/en/{family}/{platform}/_index.md.bak
   ```

4. **Record existing grade**: Read the current `grade`, `graded_evaluators`, and
   `graded_at` from frontmatter. Print:
   ```
   Existing page: grade {grade}, evaluators: {graded_evaluators}, graded: {graded_at}
   ```

5. **Regenerate via S-61**: Run the full generation pipeline:
   ```
   /new-products-page {family} {platform}
   ```
   S-61 Step 9 (no-downgrade-guard) will compare proposed vs existing content.
   - If BLOCK: S-61 will halt. Print the blocking reason and restore backup:
     ```bash
     mv content/products.aspose.org/en/{family}/{platform}/_index.md.bak content/products.aspose.org/en/{family}/{platform}/_index.md
     ```
     Abort with: "Regeneration blocked by no-downgrade-guard: {reason}. Existing page preserved."
   - If WARN: Print the warning. Ask for confirmation before proceeding.
   - If ALLOW: Continue.

6. **Compare results**: After S-61 completes successfully, diff the backup against the new page:
   ```bash
   diff content/products.aspose.org/en/{family}/{platform}/_index.md.bak content/products.aspose.org/en/{family}/{platform}/_index.md
   ```
   Print a summary of what changed (sections added/removed/modified, grade change).

7. **Clean up backup**:
   ```bash
   rm content/products.aspose.org/en/{family}/{platform}/_index.md.bak
   ```

8. **Print result**:
   ```
   REFRESH PRODUCT PAGE — {family}/{platform}
   Previous: grade {old_grade}, evaluators: {old_evaluators}
   Current:  grade {new_grade}, evaluators: {new_evaluators}
   Status: {REGENERATED | BLOCKED | NO_CHANGE}
   ```

## Post-conditions

- Product page has been regenerated through the current S-61 pipeline
- No-downgrade-guard verified no regression occurred
- `graded_evaluators` reflects the evaluation tier used (should be `full` per S-61 Step 15)
- Backup file removed
- No other files modified (family page, blog, docs, etc. are NOT touched)

## Error handling

- If S-61 fails for any reason other than no-downgrade-guard BLOCK, restore the backup
  and report the failure. Do not leave the page in a partially-generated state.
- If the backup file already exists (interrupted previous run), warn and ask before overwriting.

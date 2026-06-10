---
name: refresh-product-page
id: S-59
description: >
  Re-generate a single products.aspose.org landing page through the full
  new-products-page (S-66) pipeline with no-downgrade-guard protection. Use when
  the generation template has been improved and existing pages should benefit.
args: "{family} {platform}"
---

# S-59: Refresh Product Page — Re-generate Product Landing Page

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `words python` or `slides java`

## Purpose

Re-generate a single `products.aspose.org` landing page when the generation template
(S-66) has been improved and existing pages should benefit from the improvement.

This is distinct from S-84 (refresh-product) which refreshes content after upstream
knowledge changes. S-59 refreshes the layout and template quality of an existing page
without a knowledge change trigger.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/model.yaml` with `stale_since: null`
2. Existing products page at `$CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/{platform}/_index.md`

## Steps

1. **Parse arguments**: Extract `{family}` and `{platform}`.

2. **Knowledge bootstrap check**:
   ```bash
   /knowledge-bootstrap {family} {platform}
   ```
   Proceed only on `READY`, `BOOTSTRAPPED`, or `WARN:conflicts`.

3. **Read the existing page** and record its current grade:
   ```bash
   python -m scripts.pipeline.content_eval evaluate \
     --files $CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/{platform}/_index.md \
     --format json
   ```

4. **Invoke no-downgrade-guard** (S-56) in strict mode:
   The existing page grade is the baseline. If the re-generated page would score lower,
   BLOCK the write and report the regression.

5. **Re-generate** by invoking S-66 (new-products-page):
   ```bash
   /new-products-page {family} {platform}
   ```
   This runs the full generation pipeline including structural completion, evidence attach,
   structural validation, audit, content eval, and smoke test.

6. **Compare before/after**:
   ```
   REFRESH PRODUCT PAGE — {family}/{platform}
   Grade before: {grade}
   Grade after:  {grade}
   Result: IMPROVED | UNCHANGED | BLOCKED (no-downgrade-guard)
   ```

## Post-conditions

- Products page regenerated with latest template
- Grade same or improved
- Audit passes; evidence attached

## When NOT to use

- After an upstream knowledge change — use S-84 (refresh-product) instead
- When the page content is wrong — use S-26 (heal-page) or S-78 (manual-edit) instead

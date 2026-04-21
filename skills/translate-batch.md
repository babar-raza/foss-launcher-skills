---
name: translate-batch
id: S-100
description: >
  Translate all English content pages for a product family and platform to one
  or more target locales. Supports all translator backends and incremental
  translation with caching.
args: "{family} {platform} [{site}] [{locales}]"
---

# S-100: Translate Batch — Batch Translation for Family/Platform

> **Backend requirement:** This skill requires the `scripts/translator/` backend package, which is
> **not included** in this repository. Install the backend separately before invoking this skill.
> Run `python -m translator preflight` to verify availability. Without the backend, commands in
> the Steps section will fail with `ModuleNotFoundError`.

Translate all English content pages for a product family and platform to one or more target locales.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} [{site}] [{locales}]` — e.g. `slides net docs.aspose.org fr,de` or `3d python all all`

Omit `{site}` or use `all` to process all supported sites. Omit `{locales}` or use `all` to translate to all 36 supported locales.

## Pre-conditions

1. At least one translation backend must be available. Run `python -m translator preflight` to check.
2. English source files must exist under `$CONTENT_REPO_PATH/content/{site}/en/{family}/{platform}/`
3. The knowledge model for the family/platform should be current

## Steps

1. **Parse** `$ARGUMENTS` into `family`, `platform`, `site` (default: `all`), `locales` (default: `all`).

2. **Run preflight** (mandatory):
   ```bash
   python -m translator preflight
   ```

3. **Run the batch translator**:
   ```bash
   python -m translator batch {family} {platform} \
     [--site {site}] \
     [--locales {locales}] \
     [--provider {auto,llm,ollama,m2m}] \
     [--workers N] \
     [--dry-run]
   ```
   Options:
   - `--workers N`: parallel worker count (default: 4; reduce for Ollama)
   - `--resume`: skip files already translated (use after interrupted run)
   - `--force`: re-translate even if cached output exists

4. **Monitor progress**: The translator prints per-file progress:
   ```
   [1/N] [OK]   filename -> fr
   [2/N] [OK]   filename -> de
   [3/N] [SKIP] filename -> ar: already translated
   [4/N] [FAIL] filename -> zh: backend error
   ```

5. **Print batch summary**:
   ```
   TRANSLATE BATCH — {family}/{platform}
   Site: {site}
   Locales: {locales}
   Backend: {backend} ({model})

   Files processed: N
     OK: N
     Skipped: N (already translated)
     Failed: N

   OVERALL: PASS | PARTIAL | FAIL
   ```

6. **Post-batch verification** (spot-check):
   Run content-check on 5 random translated files:
   ```bash
   /content-check {sample-output-path}
   ```

## Post-conditions

- All translatable English pages for the product have locale variants
- `evidence:` frontmatter preserved byte-for-byte
- Hugo shortcodes, code blocks, and API names unchanged
- Batch translation report written to `reports/translations/{family}-{platform}-{date}.json`

## Resuming Interrupted Batches

If a batch run is interrupted, resume without re-translating cached files:
```bash
python -m translator batch {family} {platform} --resume [--locales {remaining-locales}]
```

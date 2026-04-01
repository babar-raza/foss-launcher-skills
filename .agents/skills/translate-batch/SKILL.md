---
name: translate-batch
description: >
  Translate all English content pages for a product family and platform
args: "{family} {platform} [locales]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-53: Translate Batch — Batch Translation for Family/Platform

Translate all English content pages for a product family and platform to one or more target locales.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} [{site}] [{locales}]` — e.g. `slides net docs.aspose.org fr,de` or `3d python all all`

Omit `{site}` or use `all` to process all supported sites. Omit `{locales}` or use `all` to translate to all 36 supported locales.

## Pre-conditions

1. `LLM_API_KEY` environment variable must be set (or `--offline` flag used with M2M100 installed).
2. English source files must exist under `content/{site}/en/{family}/{platform}/`.
3. The knowledge model for the family/platform should be current. If `knowledge/{family}/{platform}/merged/index.json` shows `stale: true`, run `/stale-detect` first.

## Steps

1. **Parse** `$ARGUMENTS` into:
   - `family` — product family (e.g. `slides`, `3d`, `cells`)
   - `platform` — platform identifier (e.g. `net`, `python`, `java`, `cpp`)
   - `site` — site name or `all` (default: `all`)
   - `locales` — comma-separated locale codes or `all` (default: `all`)

2. **Estimate scope** before running:
   - Count English `.md` files under `content/{site}/en/{family}/{platform}/` (across all specified sites).
   - Multiply by the number of target locales.
   - Print: `Scope: {file_count} files x {locale_count} locales = {total} translation jobs`
   - If total exceeds 500, warn the user and ask for confirmation before proceeding.

3. **Run the batch translator**:
   ```bash
   python -m translator batch --family {family} --platform {platform} --site {site} --locales {locales}
   ```
   Add `--dry-run` to validate without writing output.
   Add `--force` to re-translate files whose translated copies are already up to date.
   Add `--offline` to use the M2M100 local backend.

4. **Monitor progress**: The translator prints progress every 10 jobs and a final summary line:
   ```
   Batch complete: N ok, N skipped, N failed
   ```

5. **On completion**, run cache-stats to confirm cache utilisation:
   ```bash
   python -m translator cache-stats
   ```
   Print the cache statistics.

6. **Spot-check translated output**: For a representative sample (up to 3 files), run `/content-check` on the translated output:
   ```
   /content-check content/{site}/{lang}/{family}/{platform}/{filename}
   ```
   Report any FAIL results.

7. **Report results** in this format:
   ```
   TRANSLATE BATCH — {family}/{platform}
   Site(s): {site}   Locales: {locales}
   Source files found: N
   Total jobs: N

   BATCH RESULT
   OK: N   SKIPPED: N   FAILED: N

   CACHE STATS
   Total entries: N   Total hits: N

   SPOT-CHECK (sample)
     {path}: PASS | WARN | FAIL
     ...

   OVERALL: PASS | PARTIAL | FAIL
   ```
   OVERALL is FAIL if the translator exited non-zero. OVERALL is PARTIAL if some files failed. OVERALL is PASS if all jobs succeeded or were legitimately skipped.

## Post-conditions

- All English source files for the family/platform have translated counterparts in each locale directory.
- Translated files are stamped with the current date so subsequent `sync` runs will skip them unless the source is updated.
- Cache entries are populated, making incremental re-runs significantly faster.

## Acceptance Criteria

- [ ] Translator CLI exits 0 (or only with expected validation failures reported).
- [ ] All `[OK]` locales have files on disk at the correct paths.
- [ ] No `[FAIL]` entries in the batch output.
- [ ] Cache hit rate is reasonable for repeated runs (should be near 100% for unchanged source).

---
name: ht-translate-batch
id: S-HT-02
description: >
  Skill description pending
---

# S-HT-02: HT-Translate-Batch — Batch Translation via Hugo-Translator

Translate all English content pages for a product family/platform to one or more target locales
using the external `hugo-translator` tool with an explicit site profile.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {site} {locales}` — e.g.:
`slides net docs.aspose.org fr,de,ar`
`cells java kb.aspose.org all`

- `{family}` — product family (e.g. `slides`, `cells`, `pdf`, `3d`)
- `{platform}` — platform (e.g. `net`, `java`, `python`, `cpp`, `typescript`)
- `{site}` — explicit site profile ID (required — no guessing, no default, no `all`)
- `{locales}` — comma-separated list (e.g. `fr,de`) or `all` for all 36 target languages

## Mandatory Pre-Conditions

1. `{site}` argument is one of the valid profile IDs — stop if missing or not recognized
2. Profile exists at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/config/site_profiles/{site}.yaml`
3. Content exists at `content/{site}/en/{family}/{platform}/`
4. Output temp directory pre-created (hugo-translator silently exits if parent missing)
5. hugo-translator venv activated at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/.venv/`

## Valid Site Profile IDs

- `docs.aspose.org` — Documentation site
- `kb.aspose.org` — Knowledge base
- `products.aspose.org` — Product landing pages (note: `max_parallel_files=1`)
- `reference.aspose.org` — API reference
- `blog.aspose.org` — Blog (confirm scope before first batch run)
- `www.aspose.org` — Main website (requires special flags — see Step 5)

## Hard Stops

**STOP** and fail with an error if:
- `{site}` is missing, empty, `all`, or not in the valid profile list above
- `{site}` is `all` — this is NOT allowed. One site per invocation.
- Profile file does not exist in the hugo-translator repo
- Content directory for `{family}/{platform}` does not exist

Do NOT fall back to any other translation mechanism. Do NOT loop over sites automatically.

## Scope Estimation

Before running: estimate scope.
```
file_count = count of .md files under content/{site}/en/{family}/{platform}/
locale_count = count of target locales
total_jobs = file_count × locale_count
```
If `total_jobs > 500`, warn the operator and request explicit confirmation before proceeding.

## Execution Steps

### Step 1 — Validate arguments
Parse `$ARGUMENTS`: extract `{family}`, `{platform}`, `{site}`, `{locales}`.
- If `{site}` is missing, `all`, or invalid: output error and stop.
- If content path does not exist: output error and stop.

### Step 2 — Pre-create output temp directory
```bash
OUTPUT_TMP="C:/Users/prora/AppData/Local/Temp/ht-batch/{site}/{family}-{platform}/"
mkdir -p "${OUTPUT_TMP}"
```

### Step 3 — Run dry-run
```bash
cd "C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator"
.venv/Scripts/python -m src.cli \
  --site {site} \
  --input "d:/onedrive/Documents/GitHub/aspose.org/content/{site}/en/{family}/{platform}/" \
  --output "${OUTPUT_TMP}" \
  --target-langs {locales_space_separated} \
  --validation-mode normal \
  --force-accept \
  --no-commit \
  --dry-run
```
Review dry-run output. Stop if validation errors are reported.

### Step 4 — Run live batch translation
```bash
cd "C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator"
.venv/Scripts/python -m src.cli \
  --site {site} \
  --input "d:/onedrive/Documents/GitHub/aspose.org/content/{site}/en/{family}/{platform}/" \
  --output "${OUTPUT_TMP}" \
  --target-langs {locales_space_separated} \
  --validation-mode normal \
  --force-accept \
  --no-commit
```

**Note for CJK/RTL locales:** `--force-accept` handles `FrontmatterLanguageCheck` false-positives.
**Note for products.aspose.org:** `max_parallel_files=1` is set in the profile — do not override.

### Step 5 — www.aspose.org special handling
If `{site}` is `www.aspose.org`, add `--force-retranslate --force-restart`:
```bash
.venv/Scripts/python -m src.cli \
  --site www.aspose.org \
  --input "d:/onedrive/Documents/GitHub/aspose.org/content/www.aspose.org/" \
  --output "${OUTPUT_TMP}" \
  --target-langs {locales_space_separated} \
  --validation-mode normal \
  --force-accept \
  --force-retranslate \
  --force-restart \
  --no-commit
```
(www uses `_index.{lang}.md` pattern; existing locale files cause false "already translated" skips.)

### Step 6 — blog.aspose.org model note
If `{site}` is `blog.aspose.org`, verify the profile uses `m2m100_418m` (NOT `m2m100_1.2b`).
The 1.2B model causes OOM crash (exit 0xC0000005) on this machine.

### Step 7 — Spot-check output
Review 3–5 representative translated files in `${OUTPUT_TMP}`. Verify:
- Evidence block unchanged
- Shortcodes preserved
- No placeholder leakage
- Product names not transliterated in m2m100 output

### Step 8 — Copy reviewed files to repository
After review:
```bash
for lang in {locales_list}; do
  cp -r "${OUTPUT_TMP}/${lang}/" \
     "d:/onedrive/Documents/GitHub/aspose.org/content/{site}/${lang}/"
done
```
Match the repository's content directory structure.

### Step 9 — Record evidence
Record in skill run evidence:
- `site_profile: {site}`
- `family: {family}`, `platform: {platform}`
- `target_locales: [{locales}]`
- `file_count: {actual_count}`
- `hugo_translator_revision: {git describe}`
- `output_tmp: ${OUTPUT_TMP}`

### Step 10 — Commit via /commit
Do not commit directly. Use `/commit` (S-76) with appropriate skill run record.

## Push Coordination

If multiple batches run concurrently (e.g., different families):
- Each batch agent MUST NOT commit or push independently.
- A single coordinator or the human operator performs the final commit+push after all batches complete.

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` through the hugo-translator LLM backend,
the run carries a metrics obligation per AGENTS.md §15.

## Retirement Note

This skill replaces the retired S-53 (`translate-batch`). The internal `scripts/translator/`
package has been deleted. Do not recreate it.

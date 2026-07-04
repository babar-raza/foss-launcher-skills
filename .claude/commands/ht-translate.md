---
name: ht-translate
id: S-HT-01
description: >
  Skill description pending
---

# S-HT-01: HT-Translate — Single Page Translation via Hugo-Translator

Translate a single English content page to one or more target locales using the external
`hugo-translator` tool with an explicit site profile.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{src_path} {site} {locales}` — e.g.:
`content/docs.aspose.org/en/slides/net/getting-started/_index.md docs.aspose.org fr,de,ar`

- `{src_path}` — path relative to repo root, must contain `/en/`
- `{site}` — explicit site profile ID (required — no guessing, no default)
- `{locales}` — comma-separated list (e.g. `fr,de`) or `all` for all 36 target languages

## Mandatory Pre-Conditions

1. Source file exists and contains `/en/` in path
2. `{site}` argument is one of the valid profile IDs listed below — stop if not provided
3. Profile exists at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/config/site_profiles/{site}.yaml`
4. Output temp directory pre-created (hugo-translator silently exits if parent missing)
5. hugo-translator venv is activated at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/.venv/`

## Valid Site Profile IDs

- `docs.aspose.org` — Documentation site
- `kb.aspose.org` — Knowledge base
- `products.aspose.org` — Product landing pages
- `reference.aspose.org` — API reference
- `blog.aspose.org` — Blog (was English-only in retired system; confirm scope before running)
- `www.aspose.org` — Main website

## Hard Stops

**STOP** and fail with an error if:
- `{site}` argument is missing, empty, or not in the valid profile list above
- The profile file does not exist in the hugo-translator repo
- Source file does not exist or does not contain `/en/`
- You are about to guess a site profile based on path heuristics

Do NOT fall back to any other translation mechanism.

## Execution Steps

### Step 1 — Validate arguments
Parse `$ARGUMENTS`: extract `{src_path}`, `{site}`, `{locales}`.
- If `{site}` is missing or invalid: output error and stop.
- If `{src_path}` does not exist: output error and stop.

### Step 2 — Resolve content root and derive input path
The hugo-translator operates on the parent directory of the source file.
```
input_dir = dirname({src_path})
```

### Step 3 — Pre-create output temp directory
```bash
OUTPUT_TMP="C:/Users/prora/AppData/Local/Temp/ht-single/{site}/"
mkdir -p "${OUTPUT_TMP}"
```

### Step 4 — Run dry-run first
```bash
cd "C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator"
.venv/Scripts/python -m src.cli \
  --site {site} \
  --input "d:/onedrive/Documents/GitHub/aspose.org/{input_dir}/" \
  --output "${OUTPUT_TMP}" \
  --target-langs {locales_space_separated} \
  --validation-mode normal \
  --force-accept \
  --no-commit \
  --dry-run
```
Review dry-run output. If validation errors are reported, stop and report them.

### Step 5 — Run live translation
After dry-run passes:
```bash
cd "C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator"
.venv/Scripts/python -m src.cli \
  --site {site} \
  --input "d:/onedrive/Documents/GitHub/aspose.org/{input_dir}/" \
  --output "${OUTPUT_TMP}" \
  --target-langs {locales_space_separated} \
  --validation-mode normal \
  --force-accept \
  --no-commit
```

**Note for CJK/RTL locales (zh, ar, he, fa, hi, ko, ja, th, vi):** `--force-accept` is required.
`FrontmatterLanguageCheck` false-positives on English product names (Aspose.Words, etc.) are expected
and are NOT real translation errors.

### Step 6 — Review output files
Inspect translated files in `${OUTPUT_TMP}`. Verify:
- Evidence block is unchanged (byte-for-byte identical to source)
- Shortcodes are preserved
- No placeholder leakage (`⟦PH_xxxx⟧` literals not present in output)
- Product names are not transliterated (e.g., "Aspose.Cells" not "Апсоц.Клетки")

### Step 7 — Copy reviewed files to repository
After review:
```bash
# Example for docs.aspose.org, fr locale:
cp "${OUTPUT_TMP}/fr/{filename}" \
   "d:/onedrive/Documents/GitHub/aspose.org/content/{site}/{lang}/{relative_path}"
```
Match the repository's content structure for the target site.

### Step 8 — Record evidence
Record in the commit message or evidence:
- `site_profile: {site}`
- `profile_path: C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/config/site_profiles/{site}.yaml`
- `source_file: {src_path}`
- `target_locales: [{locales}]`
- `hugo_translator_revision: {git describe in hugo-translator repo}`

### Step 9 — Commit via /commit
Do not commit directly. Use `/commit` (S-76) with appropriate skill run record.

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` through the hugo-translator LLM backend,
the run carries a metrics obligation per AGENTS.md §15.

## Retirement Note

This skill replaces the retired S-52 (`translate-page`). The internal `scripts/translator/`
package has been deleted. Do not recreate it.

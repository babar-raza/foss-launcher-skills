# S-HT-01: HT-Translate — Single Page Translation via Hugo-Translator

Translate a single English content page to one or more of the **25 approved target locales**
using the external `hugo-translator` tool's **governed zero-defect campaign path**.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{src_path} {site} {locales}` — e.g.:
`content/docs.aspose.org/en/slides/net/getting-started/_index.md docs.aspose.org fr,de,ar`

- `{src_path}` — path relative to repo root, must contain `/en/` (blog: a leaf `index.md` / `_index.md` with no locale suffix)
- `{site}` — explicit site profile ID (required — no guessing, no default)
- `{locales}` — comma-separated subset of the approved set, or `all` for **all 25 approved locales**
  (`ar cs de el es fa fr he hi hu id it ja ko nl pl pt ro ru sv th tr uk vi zh`).
  The 11 codes `bg ca da fi hr lt lv ms no sk sr` are disabled in every site's Hugo config and
  rejected by every profile's `strict_locale_allowlist` — they are never generated.

> **Governed path only (2026-09-02, TC-APT-025 of mission aspose-org-full-portfolio-translation-20260901).**
> The former plain-CLI invocation (`src.cli … --validation-mode normal --force-accept`) is
> retired: it bypassed the zero-defect write-gate promotion and the receipt ledger. The only
> sanctioned translation execution path is `src/workers/campaign_runner.py` under
> `validation_policy: zero-defect`, driven through a campaign manifest as below. Do not fall back
> to the plain CLI, to `.local/*.py` scripts, or to any `--force-accept` / validator-skip flag.

## Mandatory Pre-Conditions

1. Source file exists and is an English source (contains `/en/`, or is a blog leaf `index.md`/`_index.md`)
2. `{site}` argument is one of the valid profile IDs listed below — stop if not provided
3. Profile exists at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/config/site_profiles/{site}.yaml`
4. hugo-translator venv exists at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/.venv/`
   (always invoke it as `.venv/Scripts/python` — never bare `python`)
5. The content-repo session ledger is active (`/session-start`), because the runner writes
   receipt-backed files directly into `content/{site}/{lang}/…` and those files must be adopted
   into THIS session before `/commit`

## Valid Site Profile IDs

- `docs.aspose.org` — Documentation site
- `kb.aspose.org` — Knowledge base
- `products.aspose.org` — Product landing pages (`max_parallel_files=1` in profile — do not override)
- `reference.aspose.org` — API reference
- `blog.aspose.org` — Blog (file-suffix layout: `index.md` → `index.{lang}.md`; profile pins `m2m100_418m`, never `m2m100_1.2b`)
- `websites.aspose.org` — Corporate site pages (`content/websites.aspose.org/` is NOT in `path_guard.py`'s
  allowlist: every commit touching it needs an `override_manager.py create` token first — see Step 7)
- ~~`www.aspose.org`~~ — **out of scope** of the governed portfolio mission (operator decision 2026-09-01);
  not a valid target for this skill

## Hard Stops

**STOP** and fail with an error if:
- `{site}` argument is missing, empty, or not in the valid profile list above
- The profile file does not exist in the hugo-translator repo
- Source file does not exist or is not an English source
- Any requested locale is outside the 25 approved codes
- You are about to guess a site profile based on path heuristics
- The manifest verify step (Step 4) reports drift, an unreceipted existing output, or a dirty source

Do NOT fall back to any other translation mechanism. Do NOT pass `--force-accept`, `--validation-mode`,
or any bypass environment variable.

## Execution Steps

### Step 1 — Validate arguments
Parse `$ARGUMENTS`: extract `{src_path}`, `{site}`, `{locales}`.
- If `{site}` is missing or invalid: output error and stop.
- If `{src_path}` does not exist: output error and stop.
- Expand `all` to the 25 approved codes; reject anything outside them.

### Step 2 — Build a one-source campaign manifest
```bash
cd "C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator"
printf '%s\n' "{src_path}" > "$TEMP/ht-single-sources.txt"
.venv/Scripts/python scripts/campaign/build_campaign_manifest.py \
  --content-repo "D:/onedrive/Documents/GitHub/aspose.org" \
  --site {site} \
  --source-list "$TEMP/ht-single-sources.txt" \
  --locale {locale_1} --locale {locale_2} ... \
  --campaign-id "ht-single-{site}-{YYYYMMDD-HHMMSS}" \
  --manifest-output "data/campaigns/manifests/ht-single-{site}-{YYYYMMDD-HHMMSS}.yaml"
```
The builder uses the profile's own discovery filter and the engine's own output-path logic; the
manifest is `validation_policy: zero-defect` by construction and lists exactly one source.

### Step 3 — Pre-existing targets
The runner refuses to overwrite an existing target that is not declared in the manifest. If a
target already exists for a requested locale, it must be declared for governed replacement
(`replace_existing` with the current file's SHA256 — TC-APT-031) or the locale must be dropped.
Never delete the existing file to get around this.

### Step 4 — Verify (read-only) before translating
```bash
.venv/Scripts/python -m src.workers.autonomous_content_translation_worker \
  --mode oneshot \
  --campaign-manifest "data/campaigns/manifests/ht-single-{site}-{stamp}.yaml" \
  --validation-policy zero-defect \
  --verify-only
```
Any drift, unreceipted existing output, or dirty-source finding is a hard stop.

### Step 5 — Run the governed translation
```bash
.venv/Scripts/python -m src.workers.autonomous_content_translation_worker \
  --mode oneshot \
  --campaign-manifest "data/campaigns/manifests/ht-single-{site}-{stamp}.yaml" \
  --validation-policy zero-defect
```
Every output passes all 44 write gates (the 13 warn-tier gates are promoted to block under
zero-defect) or it is not written at all. Accepted files are written **directly** into
`content/{site}/{lang}/…` (blog: beside the source as `index.{lang}.md`) and receipted in
`data/campaigns/{campaign-id}/acceptance_receipts.jsonl`; rejected candidates are recorded
content-free in `failures.jsonl`. There is no temp directory and no copy step.
After a crash or a qualified pipeline fix, add `--resume`.

### Step 6 — Review
- Read the receipt: all 44 gates `passed`, none with action `warn`.
- Inspect the written file: evidence block byte-identical to source, shortcodes preserved, no
  placeholder leakage, product names not transliterated.
- A blocked output is reviewed as a **Block-Queue** item (batch size 1) — never force-accepted.

### Step 7 — Adopt and record
```bash
cd "D:/onedrive/Documents/GitHub/aspose.org"
.venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py adopt --files <exactly the receipt-listed paths>
.venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py candidates --format json   # must equal the receipt set
```
For `websites.aspose.org` paths, create the override token before staging:
```bash
.venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py create \
  --paths <the content/websites.aspose.org/... paths> \
  --reason "S-HT-01 governed locale output" --plan "<plan or taskcard reference>"
```
Record in the skill run evidence: `site_profile`, `profile_path`, `source_file`,
`target_locales`, `campaign_manifest`, `receipt_sha256` per output,
`hugo_translator_revision` (`git describe` in the hugo-translator repo).

### Step 8 — Commit via /commit
Do not commit directly. Use `/commit` (S-76) with a skill run record declaring `S-HT-01`;
the commit body must carry `Skills invoked: [S-HT-01]` and exactly one `Co-Authored-By` trailer.
Never push.

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` through the hugo-translator LLM backend,
the run carries a metrics obligation per AGENTS.md §15.

## Retirement Note

This skill replaces the retired S-52 (`translate-page`). The internal `scripts/translator/`
package has been deleted. Do not recreate it. The plain-CLI `--force-accept` invocation this
skill used until 2026-09-02 is likewise retired (hugo-translator plan G-16).

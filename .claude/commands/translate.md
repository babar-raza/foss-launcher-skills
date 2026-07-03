# /translate — PERMANENTLY RETIRED

**This command is permanently retired. No translation will occur. Stop immediately.**

The internal `scripts/translator/` package has been deleted. `translate-page` (S-52) and
`translate-batch` (S-53) skill files have been deleted. This dispatcher has no valid target.

---

## Authorized Translation Mechanism

The **only** authorized translation mechanism is the external `hugo-translator` tool with an
**explicit site profile**. There is no fallback, no alias, and no wrapper.

**Required invocation pattern:**

```bash
cd "C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator"

# Pre-create output directory (required — CLI silently exits if parent missing)
mkdir -p "C:/Users/prora/AppData/Local/Temp/ht-out/{site_id}"

.venv/Scripts/python -m src.cli \
  --site {site_profile_id} \
  --input "d:/onedrive/Documents/GitHub/aspose.org/content/{site_id}/" \
  --output "C:/Users/prora/AppData/Local/Temp/ht-out/{site_id}/" \
  --target-langs {lang1} {lang2} ... \
  --validation-mode normal \
  --force-accept \
  --no-commit
```

**Site profiles available** (at `config/site_profiles/` in the hugo-translator repo):
- `docs.aspose.org`
- `kb.aspose.org`
- `products.aspose.org`
- `reference.aspose.org`
- `blog.aspose.org`
- `www.aspose.org`

**Skills that wrap the authorized mechanism:**
- `/ht-translate {src_path} {site} {locales}` — single page (S-HT-01)
- `/ht-translate-batch {family} {platform} {site} {locales}` — batch (S-HT-02)

---

## What You Must NOT Do

- Do not recreate `/translate` as a command or skill.
- Do not wrap `hugo-translator` in a new aspose.org repository script.
- Do not call an LLM directly for translation.
- Do not invoke the internal translator package (`scripts/translator/`) — it has been deleted.
- Do not select a site profile by guessing.
- Do not proceed without an explicit `--site {profile_id}` argument.

---

## Retirement Record

- Mission: `translate-retirement-001`
- Date: 2026-07-02
- Deleted: `scripts/translator/` (27 files), `skills/translate-page.md`, `skills/translate-batch.md`
- Gap ledger: `reports/translation/translation-retirement-gap-ledger.yaml`

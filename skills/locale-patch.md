---
name: locale-patch
id: S-101
description: >
  Propagate targeted text fixes from a fixed English source file to all locale
  translation copies of that file, without re-translating the entire page.
  Use after fixing a content bug in English that has locale translations.
args: "{family} {platform} {site} {source_file} --patches [{old_text: ..., new_text: ...}] [--dry-run]"
---

# S-101: Locale Patch — Propagate Targeted Text Fixes to Locale Files

Propagate targeted text fixes from a fixed English source content file to all locale translation copies of that file, without re-translating the entire page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {site} {source_file}` plus patches specification

## When to use

After fixing a content bug in an English source file that has locale translations (e.g., `index.zh.md`,
`index.de.md`, or locale directory variants), use this skill to apply the same fix to all locale copies.

Use for:
- Correcting a wrong API name that appears in both English and locale files
- Updating an install command that changed
- Fixing a factual error propagated during initial batch translation

Do **not** use for:
- Full page re-translations (use S-100 translate-batch with `--force` instead)
- Adding new content that doesn't exist in locales yet (use translate-page S-99)

## Inputs

| Parameter | Description |
|---|---|
| `family` | Product family (e.g. `3d`, `slides`, `email`) |
| `platform` | Language platform (e.g. `python`, `net`, `java`) |
| `site` | Site name (e.g. `blog`, `kb`, `docs`) |
| `source_file` | Path to the fixed English source file (relative to `$CONTENT_REPO_PATH/content/`) |
| `patches` | List of patch objects: `{old_text, new_text, context?}` |
| `dry_run` | `true`/`false` (default: `true` for safety) |

## Steps

1. **Parse arguments**.

2. **Locate locale files**: Find all locale variants of `{source_file}`:
   - Directory-based: `content/{site}/{lang}/{family}/{platform}/{same-path}`
   - File-based: `content/{site}/en/{family}/{platform}/{name}.{lang}.md`

3. **Dry-run preview** (always run first):
   ```
   LOCALE PATCH — DRY RUN
   Source: {source_file}
   Patches: N
   Locale files found: N

   Patch 1: "{old_text}" → "{new_text}"
     Would apply to: {lang1}, {lang2}, ...
     Would skip: {lang3} (old_text not found)
   ```
   Exit after dry-run unless `--dry-run false` is specified.

4. **Apply patches** (when `--dry-run false`):
   For each locale file × each patch:
   - Search for `old_text` (exact match)
   - If found: replace with `new_text`
   - If `context` provided: only match when `context` line is adjacent
   - Log each application: `[PATCHED] {lang}: {old_text} → {new_text}`

5. **Run content-check** on each modified locale file:
   ```bash
   /content-check {locale_file}
   ```
   WARN is acceptable; FAIL must be investigated.

6. **Summary**:
   ```
   LOCALE PATCH — {source_file}
   Patches applied: N
   Locale files modified: N
   Locale files skipped (text not found): N
   ```

## Post-conditions

- All locale files updated with the same textual fix as the English source
- `evidence:` frontmatter blocks preserved (locale patches only update prose/code text)
- Content-check passing on all modified files

## Never Do

- Never patch locale files without first confirming on the English source
- Never patch `evidence:` frontmatter blocks via locale-patch (use evidence-repair S-77)
- Never apply patches without a dry-run preview first

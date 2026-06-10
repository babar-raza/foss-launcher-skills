---
name: translate-page
id: S-99
description: >
  Translate a single English content page to one or more target locales using
  the translator system (LLM / Ollama / M2M100 backends). Preserves evidence
  frontmatter, code blocks, and Hugo shortcodes unchanged.
args: "{src_path} {locales}"
---

# S-99: Translate Page — Single Page Translation

> **Backend requirement:** This skill requires the `scripts/translator/` backend package, which is
> **not included** in this repository. The backend provides three adapters: `llm.py` (LLM API),
> `ollama.py` (local Ollama), and `m2m100.py` (offline HuggingFace M2M100). Install the backend
> separately before invoking this skill. Run `python -m translator preflight` to verify availability.
> Without the backend, commands in the Steps section will fail with `ModuleNotFoundError`.

Translate a single English content page to one or more target locales.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{src_path} {locales}` — e.g. `content/docs.aspose.org/en/slides/net/getting-started/_index.md fr,de,ar`

Locales may be a comma-separated list (e.g. `fr,de,ar`) or the literal string `all` to translate to all 36 supported locales.

## Pre-conditions

1. At least one translation backend must be available. Run `python -m translator preflight` to check:
   - **llm.professionalize.com**: requires `LLM_API_KEY` to be set
   - **Ollama**: requires Ollama running locally with a suitable model installed
   - **M2M100 offline**: requires `pip install transformers torch` and the model downloaded (~2 GB)
2. The source file must exist under `content/{site}/en/` — blog content is skipped automatically
3. The knowledge model for the page's family/platform should be current

## Steps

1. **Parse** `$ARGUMENTS` into `src_path` and `locales`.

2. **Validate source path**:
   - Confirm the file exists
   - Confirm the path contains `/en/` — required to derive the output path
   - If path is under `content/blog.aspose.org/`, STOP: blog content is English-only

3. **Run preflight** (mandatory before translation):
   ```bash
   python -m translator preflight [--provider {auto,llm,ollama,m2m}]
   ```
   If preflight fails, resolve the issue before proceeding.

4. **Run the translator**:
   ```bash
   python -m translator page {src_path} --locales {locales} [--provider {auto,llm,ollama,m2m}]
   ```
   Options:
   - `--provider auto` (default): system selects best available backend
   - `--provider llm`: force llm.professionalize.com
   - `--provider ollama`: force local Ollama
   - `--provider m2m`: force offline M2M100 backend
   - `--dry-run`: validate without writing output files

5. **Interpret output**:
   - `[OK]   filename -> lang (translated=N, cached=N)` — success
   - `[SKIP] filename -> lang: reason` — skipped
   - `[FAIL] filename -> lang: reason` — failure

6. **Verify translated files**: For each `[OK]` output, run content-check:
   ```bash
   /content-check {output_path}
   ```
   PASS or WARN is acceptable; FAIL requires investigation.

7. **Report results**:
   ```
   TRANSLATE PAGE — {src_path}
   Locales requested: {locales}
   Backend used: {backend} ({model})

   RESULTS
     [OK/SKIP/FAIL] {lang}: {output_path or reason}

   SUMMARY
   OK: N   SKIPPED: N   FAILED: N
   OVERALL: PASS | PARTIAL | FAIL
   ```

## Post-conditions

- Translated files written to `content/{site}/{lang}/` mirroring the English path structure
- `evidence:` frontmatter block preserved byte-for-byte from the source
- Hugo shortcodes, code blocks, and API names unchanged in translated output

## Never Do

- Never translate blog content (English-only)
- Never modify the `evidence:` frontmatter block during translation
- Never translate locale variant files (only translate from `/en/` source)

---
name: translate-page
description: >
  Translate a single English content page to one or more target locales
argument-hint: "{file-path} {locales}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-52: Translate Page — Single Page Translation

Translate a single English content page to one or more target locales.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{src_path} {locales}` — e.g. `content/docs.aspose.org/en/slides/net/getting-started/_index.md fr,de,ar`

Locales may be a comma-separated list (e.g. `fr,de,ar`) or the literal string `all` to translate to all 36 supported locales.

## Pre-conditions

1. At least one translation backend must be available. Run `python -m translator preflight` to check.
   - **llm.professionalize.com**: requires `LLM_API_KEY` to be set.
   - **Ollama**: requires Ollama running locally with a suitable model installed.
   - **M2M100 offline**: requires `pip install transformers torch` and the model downloaded (~2 GB).
2. The source file must exist under `content/{site}/en/` — blog content is skipped automatically.
3. The knowledge model for the page's family/platform should be current. If `knowledge/{family}/{platform}/merged/index.json` shows `stale: true`, run `/stale-detect` before translating.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-52 --scope "*"
> ```


1. **Parse** `$ARGUMENTS` into:
   - `src_path` — path to the English source `.md` file
   - `locales` — comma-separated locale codes or `all`

2. **Validate source path**:
   - Confirm the file exists.
   - Confirm the path contains `/en/` — this is required to derive the output path.
   - If the path is under `content/blog.aspose.org/`, STOP: blog content is English-only and must not be translated.

3. **Run preflight** (mandatory before translation):
   ```bash
   .venv/Scripts/python -m translator preflight [--provider {auto,llm,ollama,m2m}]
   ```
   Review the preflight report. Confirm that:
   - A valid backend is selected (no `ERROR` lines in output).
   - The selected model is a non-thinking translation-suitable model.
   - Any `WARNING` lines are understood and acceptable.
   If preflight fails, resolve the issue before proceeding.

4. **Run the translator**:
   ```bash
   .venv/Scripts/python -m translator page {src_path} --locales {locales} [--provider {auto,llm,ollama,m2m}]
   ```
   - `--provider auto` (default): system selects best available backend automatically.
   - `--provider llm`: force llm.professionalize.com.
   - `--provider ollama`: force local Ollama.
   - `--provider m2m`: force offline M2M100 backend.
   - `--model MODEL`: override translation model (LLM and Ollama backends).
   - `--dry-run`: validate without writing output files.
   - `--offline`: alias for `--provider m2m` (backward compat).

5. **Interpret output**: The translator prints one line per locale:
   - `[OK]   filename -> lang (translated=N, cached=N)` — success
   - `[SKIP] filename -> lang: reason` — skipped (e.g. blog content, unknown content type)
   - `[FAIL] filename -> lang: reason` — validation or backend failure

6. **For each `[OK]` output**, verify the translated file:
   - Confirm the output file was written at `content/{site}/{lang}/{family}/{platform}/{filename}`.
   - Run `/content-check {output_path}` on the translated file to verify structural integrity.
   - A translated file should PASS all frontmatter and file path checks. WARN on content-structure checks is acceptable (translated content may differ in structure).

7. **Report results** in this format:
   ```
   TRANSLATE PAGE — {src_path}
   Locales requested: {locales}
   Backend used: {backend} ({model})

   RESULTS
     [OK/SKIP/FAIL] {lang}: {output_path or reason}
     ...

   SUMMARY
   OK: N   SKIPPED: N   FAILED: N
   OVERALL: PASS | PARTIAL | FAIL
   ```
   OVERALL is FAIL if any locale produced `[FAIL]`. OVERALL is PARTIAL if some succeeded and some failed or were skipped. OVERALL is PASS if all requested locales produced `[OK]`.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-52 --status completed
> ```

## Post-conditions

- Translated files are written to `content/{site}/{lang}/` mirroring the English path structure.
- Each translated file preserves the original `evidence:` frontmatter block unchanged.
- Hugo shortcodes, code blocks, and API names are unchanged in the translated output.

## Acceptance Criteria

- [ ] Preflight completed without errors before translation started.
- [ ] Translator CLI exits 0 for all requested locales (or exits 1 only on actual failures, not skips).
- [ ] Every `[OK]` locale has a corresponding file on disk at the correct path.
- [ ] `/content-check` on each output file returns OVERALL PASS or WARN (not FAIL).
- [ ] The `evidence:` frontmatter block in each output file is byte-for-byte identical to the source.

# S-22: FAQ Generate — Generate FAQ Section from Knowledge

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `3d python`

## Purpose
Generate a FAQ page for a product by extracting common patterns, limitations, and capabilities from the knowledge model. Produces Q&A pairs grounded in verified claims.

## Note

For KB FAQ pages specifically, prefer S-59 (new-kb-faq) which includes the full KB site template, evidence citations, and Hugo frontmatter. This skill (S-22) generates FAQ content sections that can be embedded in any page type.

## Pre-conditions
1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
2. `knowledge/{family}/{platform}/merged/` must have after bootstrap:
   - `claims.json` — structured claims
   - `api_surface.json` — API surface
   - `formats.json` — format support matrix
   - `limitations.md` — known limitations

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-22 --scope "*"
> ```


1. **Parse arguments**: Extract `{family}` and `{platform}` from $ARGUMENTS.

2. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/formats.json`
   - Read `knowledge/{family}/{platform}/merged/limitations.md`
   - Read `knowledge/{family}/{platform}/merged/install.md`

3. **Extract FAQ categories** from knowledge:

   **Getting Started** (from install.md + api_surface.json):
   - Installation questions
   - Basic setup / import questions
   - Supported platforms/runtimes

   **Format Support** (from formats.json + claims):
   - "What formats are supported for import/export?"
   - Format-specific questions (derived from format matrix)
   - Conversion questions (format A → format B)

   **Capabilities** (from claims.json, kind=capability):
   - "Can I do X?" questions derived from capability claims
   - Feature availability questions

   **Limitations** (from limitations.md):
   - "Why does X not work?" questions from NotImplementedError items
   - Known restriction questions
   - Workaround suggestions where available

   **API Usage** (from api_surface.json + claims):
   - Common class/method usage questions
   - Parameter questions for frequently-used methods

4. **Generate Q&A pairs**: For each extracted question:
   - Write a clear, concise question
   - Write an answer grounded in specific claims (reference claim IDs)
   - Include a short code snippet from `snippets/` if applicable
   - Use hedging language for claims with confidence < 0.7

5. **Format as FAQ page**:

   **IMPORTANT**: FAQ Q&A pairs must appear as `### Question?` headings in the markdown body.
   Never write a `faq:` or `faq.list` frontmatter block — it is invisible to the Hugo renderer
   and will trigger `_check_faq` Rule 3 FAIL on the next evaluation.

   ```markdown
   ---
   title: "Frequently Asked Questions — Aspose.{Family} for {Platform}"
   description: "Common questions about Aspose.{Family} FOSS for {Platform}"
   type: topic
   date: '{today}'
   lastmod: '{today}'
   keywords: [{family}, {platform}, faq, ...]
   evidence:
     model_sha: "{repo_sha}"
     model_version: "{version}"
     claims: [CLM-xxx, ...]
     apis: []
     formats: []
   ---

   ## Getting Started

   ### Q: How do I install Aspose.{Family} for {Platform}?
   A: ...

   ---

   ## Format Support

   ### Q: What file formats are supported?
   A: ...

   ---
   ...
   ```

6. **Write the file** to `content/kb.aspose.org/en/{family}/{platform}/faq.md`.

7. **Run ground-check**:
   ```bash
   python scripts/pipeline/audit.py --files content/kb.aspose.org/en/{family}/{platform}/faq.md
   ```

8. **Report**: Print summary — number of Q&A pairs generated, categories covered, claims referenced.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-22 --status completed
> ```

## Post-conditions
- FAQ page is written to `content/kb.aspose.org/en/{family}/{platform}/faq.md`
- Every answer is grounded in at least one claim from `claims.json`
- No fabricated API names or format claims
- Ground-check passes
- Evidence frontmatter lists all referenced claim IDs

## Error handling
- If knowledge model is stale, the pre-condition bootstrap handles refresh automatically.
- **Insufficient claims (< 3 claims total)**: Return `STOP:insufficient_knowledge` immediately.
  Do NOT generate a partial FAQ. Print: "FAQ generation halted: fewer than 3 claims available
  in merged/claims.json. Run S-34 (repo-scout) → S-37 (knowledge-enrich) → S-35 (truth-merge)
  to populate the knowledge model before retrying."
- **Sparse claims (3–4 claims)**: Log a WARN that the FAQ will be sparse. Continue generation
  but limit output to the categories that have at least one grounded claim. Omit empty categories.
- If no limitations found, skip the Limitations category entirely.

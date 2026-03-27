# S-22: FAQ Generate — Generate FAQ Section from Knowledge

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `3d python`

## Purpose
Generate a FAQ page for a product by extracting common patterns, limitations, and capabilities from the knowledge model. Produces Q&A pairs grounded in verified claims.

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

## Post-conditions
- FAQ page is written to `content/kb.aspose.org/en/{family}/{platform}/faq.md`
- Every answer is grounded in at least one claim from `claims.json`
- No fabricated API names or format claims
- Ground-check passes
- Evidence frontmatter lists all referenced claim IDs

## Error handling
- If knowledge model is stale, the pre-condition bootstrap handles refresh automatically
- If very few claims available (< 5), warn that FAQ will be sparse and suggest running S-34/S-35 for richer knowledge
- If no limitations found, skip the Limitations category

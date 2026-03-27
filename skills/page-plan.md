# S-18: Page Plan — Plan Page Structure Before Generation

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {section} {slug}` — e.g. `3d python developer-guide rendering`

## Purpose
Plan a page's structure before drafting. Compiles relevant claims from knowledge, determines page structure based on the section type, and outputs a structured plan that S-19 (page-draft) will consume.

## Pre-conditions
1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
2. `knowledge/{family}/{platform}/merged/` must have `claims.json`, `api_surface.json`, `formats.json` after bootstrap
3. Determine target site from `{section}`:
   - `developer-guide`, `getting-started` → docs.aspose.org
   - `how-to-*`, `faq`, `troubleshooting`, `use-cases` → kb.aspose.org
   - Blog topic → blog.aspose.org
   - API reference → reference.aspose.org

## Steps

1. **Parse arguments**: Extract `{family}`, `{platform}`, `{section}`, and `{slug}` from $ARGUMENTS.

2. **Load knowledge**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/formats.json`
   - Read `knowledge/{family}/{platform}/merged/limitations.md`
   - Read `knowledge/{family}/{platform}/snippets/` directory listing

3. **Select relevant claims**: Filter claims from `claims.json` that are relevant to the `{slug}` topic:
   - Match by claim `kind` (e.g., `format_rw`, `api_method`, `capability`)
   - Match by keyword overlap with `{slug}`
   - Include all claims with confidence >= 0.5
   - Flag claims with confidence < 0.7 as needing careful wording

4. **Select relevant API surface**: From `api_surface.json`, identify classes and methods related to the topic.

5. **Select snippets**: From `knowledge/{family}/{platform}/snippets/`, find code examples matching the topic.

6. **Determine page structure** based on section type:

   **developer-guide** page:
   - Introduction paragraph (what + why)
   - Key concepts section
   - Code example sections (one per relevant snippet)
   - API reference links
   - Limitations/notes section

   **how-to** KB article:
   - Brief intro
   - Prerequisites
   - Steps (3-7 numbered steps with code)
   - Expected output
   - Troubleshooting tips

   **faq** KB article:
   - Q&A pairs grouped by subtopic
   - Code snippets where applicable
   - Links to detailed docs

   **blog post**:
   - Hook paragraph
   - Feature walkthrough
   - Code demonstration
   - Conclusion + links

7. **Output the plan** as structured YAML:
   ```yaml
   plan:
     family: {family}
     platform: {platform}
     section: {section}
     slug: {slug}
     target_path: content/{site}/en/{family}/{platform}/{section}/{slug}.md
     page_type: {docs|topic|blog}

     claims_used:
       - id: CLM-xxx
         text: "..."
         confidence: 0.9
         provenance: dual
       ...

     api_surface:
       - class: ClassName
         methods: [method1, method2]
       ...

     snippets:
       - file: snippet_name.py
         purpose: "demonstrates X"
       ...

     structure:
       - heading: "Introduction"
         content_brief: "..."
         claims: [CLM-xxx]
       - heading: "..."
         content_brief: "..."
         claims: [CLM-yyy]
         code: snippet_name.py
       ...

     limitations:
       - "..."

     low_confidence_claims:
       - id: CLM-zzz
         note: "confidence 0.6 — use hedging language"
   ```

## Post-conditions
- Plan is output as valid YAML
- Every claim referenced exists in `claims.json`
- Every API member referenced exists in `api_surface.json`
- Every snippet referenced exists in `snippets/`
- No fabricated API names or format claims
- Plan is ready for consumption by S-19 (page-draft)

## Error handling
- If no relevant claims found for the topic, warn and suggest checking the slug or running S-14
- If no snippets available, note that code blocks will need manual creation
- If knowledge is stale, the pre-condition bootstrap handles refresh automatically

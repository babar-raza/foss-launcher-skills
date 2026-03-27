Generate a new blog post for blog.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {slug}` — e.g. `3d python working-with-3d-formats`

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
2. **Load verified facts**: Read `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
3. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never include these in content
4. **Load format matrix**: Read `formats.json` — only reference formats confirmed here
5. **Load snippets**: Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples.
   Load `snippets_index.json` and keep it in memory for all code block decisions.
   - Check `index.json` → `snippets_coverage.total_snippets` to know how many are available
   - If `snippets_coverage.total_snippets == 0`, note this: you will need `<!-- MISSING_SNIPPET -->` placeholders throughout

## Platform Resolution

Read `knowledge/{family}/{platform}/scout/model.yaml` to determine:
- `install_command` — use this verbatim instead of hardcoding any install command
- `canonical_import` — use this for import statements
- `product_name` — use for package registry references

Determine the **code fence language** from the platform:
- python → `python`
- dotnet → `csharp`
- java → `java`
- cpp → `cpp`
- typescript → `typescript`
- javascript → `javascript`
- nodejs → `javascript`

Determine the **package manager context** from the platform:
- python → pip / PyPI
- dotnet → NuGet / `dotnet add package`
- java → Maven / Gradle
- cpp → CMake / vcpkg
- typescript / javascript / nodejs → npm / yarn

Use these resolved values (`{platform_lang}`, `{install_command}`, `{package_manager}`, `{package_registry}`) throughout the generated content. Never hardcode a platform-specific tool or language fence.

## Steps

1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `slug` (slug becomes the directory name and title source).

   **Slug hygiene gates (STOP if violated):**
   - If `slug` starts with `test` (case-insensitive): STOP — "Slug '{slug}' looks like an internal test method name. Derive the slug from the content title instead (e.g. `create-hyperlinks-excel-python`)."
   - If `content/blog.aspose.org/{family}/{platform}/{slug}.md` exists: STOP — "A flat file at that path already exists. Delete it first or choose a different slug to avoid a Hugo URL collision."
   - If `content/blog.aspose.org/{family}/{platform}/{slug}/index.md` already exists: STOP — "A blog post at that slug already exists. Use `/page-update` to modify it instead."

2. **Read existing blog posts for reference** (read only — do not copy):
   - List files in `content/blog.aspose.org/{family}/{platform}/`
   - Read one existing post's `index.md` to confirm frontmatter fields and tone
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` for class names, format support, and package name

3. **Generate frontmatter**:
   ```yaml
   ---
   title: {Natural title derived from slug — written for humans, not SEO}
   seoTitle: Aspose.{Family} FOSS for {Platform} — {keyword-rich subtitle, 60–70 chars}
   description: >
     {2–3 sentences: what the library does for this use case, key formats, key classes.
     Written as meta description copy.}
   date: '{today as YYYY-MM-DD}'
   draft: false
   author: Aspose
   summary: >
     {Same or shorter version of description — displayed in post listings}
   tags: []
   categories:
   - Aspose.{Family}
   ---
   ```

4. **Generate body** in this exact section order:

   `## Introduction`
   - 2–3 paragraphs: announce or introduce the topic; what problem this solves; who it's for
   - Mention the package name (from `product_name` in model.yaml), MIT license, and zero-dependency nature
   - Reference the package registry appropriate to the platform ({package_registry} from Platform Resolution)

   `---`

   `## What's Included` (or `## Key Features` — pick one that fits the slug topic)
   - One `###` subsection per major feature area (3–6 subsections)
   - Each subsection: 2–4 sentences of prose + a code block using ```{platform_lang} fence demonstrating the feature
   - Base subsections on what you read in the reference content — use only confirmed class/method names
   - **Code blocks must use snippets**: Search `snippets_index.json` for entries where
     `classes_used` or `methods_used` overlaps with the API you are demonstrating.
     - If a match exists: paste the snippet file's content verbatim (or trim to relevant lines)
     - If no match exists: write `<!-- MISSING_SNIPPET: {ClassName.method} -->` and omit the code block
     - Never invent code when no snippet is available

   `---`

   `## Quick Start`
   - Install snippet: use `{install_command}` from model.yaml in the appropriate block format:
     - python: ```bash block
     - dotnet: ```bash block
     - java: ```xml block (Maven POM dependency)
     - cpp: ```bash or ```cmake block
     - typescript/javascript/nodejs: ```bash block
   - A 10–20 line code example in ```{platform_lang} fence covering the core task described by the slug.
     Search `snippets_index.json` for an entry covering the slug's core class or operation.
     Use that snippet verbatim (or trimmed); if no match exists, write
     `<!-- MISSING_SNIPPET: {core_class.core_method} -->` and omit the code block.

   `---`

   `## Supported Formats`
   - Markdown table: Format | Extension | Read | Write
   - Rows cover only formats confirmed in the reference or existing content — do not add speculative rows
   - Use ✓ / — for Read/Write cells

   `---`

   `## Open Source & Licensing`
   - 2–3 sentences: MIT license, link to repo or package registry, commercial use allowed
   - Do not include pricing or comparison with paid products

   `---`

   `## Getting Started`
   - Bullet list of 4–6 links to docs, KB, and reference pages using absolute internal paths:
     - `[Getting Started](/docs.aspose.org/en/{family}/{platform}/getting-started/)`
     - `[Developer Guide](/docs.aspose.org/en/{family}/{platform}/developer-guide/)`
     - `[KB Articles](/kb.aspose.org/en/{family}/{platform}/)`
     - `[API Reference](/reference.aspose.org/en/{family}/{platform}/)`

5. **Constraints**:
   - `author` is always exactly `Aspose`
   - `tags` is always `[]`
   - `categories` uses the format `Aspose.{Family}` with a capital F and correct family name casing (e.g. `Aspose.3D`, `Aspose.Cells`, `Aspose.Slides`)
   - Every code block uses ```{platform_lang} (resolved from Platform Resolution above) or ```bash / ```xml / ```cmake as appropriate for shell and config blocks
   - All class names and method names must match what you read from reference content — no invented API

6. **Create directory and write** the file to `content/blog.aspose.org/{family}/{platform}/{slug}/index.md`
   - The slug is a directory name, not just a filename — create `{slug}/index.md`

## Knowledge Post-conditions

After generating the post:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/blog.aspose.org/{family}/{platform}/{slug}/index.md` to generate the `evidence:` YAML frontmatter block with claims, APIs, and per-section binding
2. **Run content check**: Execute `/content-check content/blog.aspose.org/{family}/{platform}/{slug}/index.md` to validate structure and knowledge alignment
3. **Run change guard**: Run `python scripts/pipeline/change_guard.py {family} {platform} --file content/blog.aspose.org/{family}/{platform}/{slug}/index.md` to verify no contradictions with known facts

7. **Confirm** with the output path.

# S-57: New Blog Post — Generate Blog Post for blog.aspose.org

Generate a new blog post for blog.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {slug}` — e.g. `3d python working-with-3d-formats`

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Bootstrap knowledge**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `KNOWLEDGE: STOP:partial` → halt (see printed message)
   - `KNOWLEDGE: REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run
     `/knowledge-diff` to review what changed before generating content, then re-run this command."
   - `KNOWLEDGE: READY`, `KNOWLEDGE: BOOTSTRAPPED`, or `KNOWLEDGE: WARN:conflicts` → continue

2. **Load verified artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.md` — the human-readable API reference.
     Every class name, method, property, and enum value in your generated content MUST appear in
     this file. If a name is not in api_surface.md, do not use it.
   - Read `knowledge/{family}/{platform}/merged/formats.json` — only reference formats confirmed here
   - Read `forbidden_claims` from `knowledge/{family}/{platform}/merged/index.json` — never include these
   - Read `knowledge/{family}/{platform}/scout/model.yaml` → `canonical_import` (package name for install)
   - Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples

## Steps

1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `slug` (slug becomes the directory name and title source).

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
   evidence:
     model_sha: ""
     model_version: ""
     claims: []
     apis: []
   ---
   ```

4. **Generate body** in this exact section order:

   `## Introduction`
   - 2–3 paragraphs: announce or introduce the topic; what problem this solves; who it's for
   - Mention the package name (PyPI name), MIT license, and zero-dependency nature

   `---`

   `## What's Included` (or `## Key Features` — pick one that fits the slug topic)
   - One `###` subsection per major feature area (3–6 subsections)
   - Each subsection: 2–4 sentences of prose + a working Python code block demonstrating the feature
   - Base subsections on what you read in the reference content — use only confirmed class/method names

   `---`

   `## Quick Start`
   - Install snippet in ` ```bash ` block: `pip install {package-name}`
   - A 10–20 line Python example covering the core task described by the slug

   `---`

   `## Supported Formats`
   - Markdown table: Format | Extension | Read | Write
   - Rows cover only formats confirmed in the reference or existing content — do not add speculative rows
   - Use ✓ / — for Read/Write cells

   `---`

   `## Open Source & Licensing`
   - 2–3 sentences: MIT license, link to repo or PyPI, commercial use allowed
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
   - **Code fence language** — resolve from `{platform}` argument (never hardcode `python`):
     - `python` → `python`, install via `pip`
     - `net` → `csharp`, install via `dotnet add package`
     - `java` → `java`, install via Maven `<dependency>`
     - `cpp` → `cpp`, install via CMake FetchContent or vcpkg (see install.md)
     - `typescript` → `typescript`, install via `npm install`
   - **Package name** always comes from `knowledge/{family}/{platform}/scout/model.yaml` →
     `canonical_import`. Never use the commercial Aspose package name. If `canonical_import`
     is empty, STOP and run `/repo-scout {family} {platform}` first.
   - All class names and method names must match what you read from reference content — no invented API

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/blog.aspose.org/{family}/{platform}/{slug}/index.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Create directory and write** the file to `content/blog.aspose.org/{family}/{platform}/{slug}/index.md`
   - The slug is a directory name, not just a filename — create `{slug}/index.md`

## Knowledge Post-conditions

After generating the post:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/blog.aspose.org/{family}/{platform}/{slug}/index.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/blog.aspose.org/{family}/{platform}/{slug}/index.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Run audit**: `python scripts/pipeline/audit.py --files content/blog.aspose.org/{family}/{platform}/{slug}/index.md`
   — must exit with 0 FAIL before committing.

7. **Confirm** with the output path.

---
name: new-blog-post
description: >
  Generate a new blog post for blog.aspose.org with knowledge pre-conditions,
  evidence grounding, and post-condition skill chain.
args: "{family} {platform} {slug}"
---
Generate a new blog post for blog.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {slug}` — e.g. `3d python working-with-3d-formats`

## Knowledge Pre-conditions

Before generating any content, you MUST:

0. **Validate setup**: Run `python scripts/check_setup.py --family {family} --platform {platform}`
   - If exit code 2 (ERROR): STOP and report the error to the user before proceeding.
   - If exit code 1 (WARN): proceed but surface all warnings.

1. **Read knowledge model**: Load `knowledge/{family}/{platform}/merged/index.json`
   - If it does not exist, STOP and instruct the user to run `/repo-scout` and `/truth-merge` first
   - If `stale: true`, STOP and instruct the user to run `/knowledge-diff` first
   - If `has_conflicts: true`, WARN and list unresolved conflicts from `merge_conflicts.md`
2. **Load verified facts**: Read `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
2b. **Read API surface summary**: Read `knowledge/{family}/{platform}/merged/api_surface.md`
    - This is the concise, human-readable API reference
    - Every class name, method, property, and enum value in your generated content MUST appear in this file
    - If a name is not in api_surface.md, do not use it
3. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never include these in content
4. **Load format matrix**: Read `formats.json` — only reference formats confirmed here
5. **Load snippets**: Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples

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
   - Every code block uses ` ```python ` or ` ```bash ` language identifier
   - All class names and method names must match what you read from reference content — no invented API

6. **Create directory and write** the file to `content/blog.aspose.org/{family}/{platform}/{slug}/index.md`
   - The slug is a directory name, not just a filename — create `{slug}/index.md`

## Knowledge Post-conditions

After generating the post:

1. **Run evidence citation**: Execute `/evidence-cite content/blog.aspose.org/{family}/{platform}/{slug}/index.md` to write the YAML `evidence:` frontmatter block
2. **Run content check**: Execute `/content-check content/blog.aspose.org/{family}/{platform}/{slug}/index.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Pre-write gate**: Run `python scripts/pre_write.py {output-file}` before committing
   - Exit 0 (PASS/WARN): proceed
   - Exit 1 (FAIL): do NOT commit — report findings to user and offer to fix

7. **Confirm** with the output path.

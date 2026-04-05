---
name: new-docs-page
description: >
  Generate a new documentation page for docs.aspose.org
argument-hint: "{family} {platform} {section} {slug} [--bypass-plan]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-56: New Docs Page — Generate Documentation Page for docs.aspose.org

Generate a new documentation page for docs.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {section} {slug}` — e.g. `3d python developer-guide mesh-operations`
Valid sections: `getting-started` | `developer-guide`

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
   - Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples

## Steps

1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `section`, `slug`.

2. **Read existing docs for reference** (read only — do not copy text):
   - List files in `content/docs.aspose.org/en/{family}/{platform}/{section}/` to see what already exists
   - Read the `_index.md` for that section to understand the section's scope and tone
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` for available API classes and methods

3. **Determine the next `weight`** by reading existing pages in the section and using the next available multiple of 10 (e.g. if highest existing weight is 20, use 30).

4. **Generate frontmatter**:
   ```yaml
   ---
   page_role: howto_article
   title: {Human-readable title from slug}
   description: >-
     {1–2 sentences: what the reader learns and which classes/methods are covered}
   weight: {next weight}
   type: docs
   provenance:
     content_origin: skill-generated
     last_mechanism: skill
     auto_updatable: true
   evidence:
     model_sha: ""
     model_version: ""
     claims: []
     apis: []
   ---
   ```

5. **Generate body** — structure differs by section:

   ### For `getting-started` pages:
   - `## {Title}`
   - Opening paragraph: one-sentence purpose statement
   - `---`
   - `### Prerequisites` — markdown table: Requirement | Detail rows (Python version, OS, compiler, system packages)
   - `---`
   - Numbered steps for the task (install, configure, verify)
   - Each step: prose explanation + code block (bash or python)
   - `---`
   - `### Next Steps` — 3–5 links to related getting-started or developer-guide pages using `[Title](../slug/)`

   ### For `developer-guide` pages:
   - `## {Title}`
   - Opening paragraph: what feature/capability this covers and which class is the entry point
   - `---`
   - `### {Feature subsection}` blocks — one per major capability or concept, each with:
     - 1–2 prose sentences
     - Working Python code block
   - `---`
   - `### Tips and Best Practices` — 3–5 bullet points
   - `---`
   - `### Common Issues` — markdown table: Issue | Cause | Fix
   - `---`
   - `### FAQ` — 3–5 `#### Question?` + answer pairs
   - `---`
   - `### API Reference Summary` — markdown table: Class/Method | Description, limited to what you confirmed exists in reference content

6. **Constraints**:
   - Every code block uses ` ```python ` or ` ```bash ` language identifier
   - `---` divider between every major section
   - Class names, method names, package paths must exactly match what you read from reference content — no invented API
   - **Internal links within docs.aspose.org**: use relative paths (`../slug/`)
   - **Cross-subdomain links** (to kb, blog, reference): use absolute `https://` URLs without `/en/` — e.g. `https://kb.aspose.org/{family}/{platform}/slug/`
   - Do not add a `sidebar:` key unless the section `_index.md` uses it

7. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

8. **Write** to `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`

## Knowledge Post-conditions

After generating the page:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Run audit**: `python scripts/pipeline/audit.py --files content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`
   — must exit with 0 FAIL before committing.

8. **Confirm** with the output path and a list of the H2 sections written.

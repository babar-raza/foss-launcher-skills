Generate a new documentation page for docs.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {section} {slug}` — e.g. `3d python developer-guide mesh-operations`
Valid sections: `getting-started` | `developer-guide`

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
2. **Load verified facts**: Read `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
3. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never include these in content
4. **Load format matrix**: Read `formats.json` — only reference formats confirmed here
5. **Load snippets**: Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples

## Platform Resolution

Read `knowledge/{family}/{platform}/scout/model.yaml` to determine:
- `install_command` — use this verbatim instead of hardcoding any install command
- `canonical_import` — use this for import statements

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

Use these resolved values (`{platform_lang}`, `{install_command}`, `{package_manager}`) throughout the generated content. Never hardcode a platform-specific tool or language fence.

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
   ---
   ```

5. **Generate body** — structure differs by section:

   ### For `getting-started` pages:
   - `## {Title}`
   - Opening paragraph: one-sentence purpose statement
   - `---`
   - `### Prerequisites` — markdown table: Requirement | Detail rows (runtime version, OS, compiler, system packages — adjust for platform)
   - `---`
   - Numbered steps for the task (install, configure, verify)
   - Each step: prose explanation + code block using `{install_command}` from model.yaml for install steps
   - Platform-specific install verification:
     - python: `{install_command}` in a ```bash block, then a ```python block with import verification
     - dotnet: `{install_command}` in a ```bash block, then a ```csharp block with `using` statement
     - java: `{install_command}` in a ```xml block (Maven POM), then a ```java block with `import` statement
     - cpp: `{install_command}` in a ```bash or ```cmake block, then a ```cpp block with `#include` directive
     - typescript/javascript/nodejs: `{install_command}` in a ```bash block, then a ```typescript or ```javascript block with `import` statement
   - `---`
   - `### Next Steps` — 3–5 links to related getting-started or developer-guide pages using `[Title](../slug/)`

   ### For `developer-guide` pages:
   - `## {Title}`
   - Opening paragraph: what feature/capability this covers and which class is the entry point
   - `---`
   - `### {Feature subsection}` blocks — one per major capability or concept, each with:
     - 1–2 prose sentences
     - Working code block using ```{platform_lang} fence
   - `---`
   - `### Tips and Best Practices` — 3–5 bullet points
   - `---`
   - `### Common Issues` — markdown table: Issue | Cause | Fix
   - `---`
   - `### FAQ` — 3–5 `#### Question?` + answer pairs
   - `---`
   - `### API Reference Summary` — markdown table: Class/Method | Description, limited to what you confirmed exists in reference content

6. **Constraints**:
   - Every code block uses ```{platform_lang} (resolved from Platform Resolution above) or ```bash / ```xml / ```cmake as appropriate for shell and config blocks
   - `---` divider between every major section
   - Class names, method names, package paths must exactly match what you read from reference content — no invented API
   - Internal links: relative paths within same section (`../slug/`) or absolute starting with `/docs.aspose.org/`
   - Do not add a `sidebar:` key unless the section `_index.md` uses it

7. **Write** to `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`

## Knowledge Post-conditions

After generating the page:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to generate the `evidence:` YAML frontmatter block with claims, APIs, and per-section binding
2. **Run content check**: Execute `/content-check content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Run `python scripts/pipeline/change_guard.py {family} {platform} --file content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to verify no contradictions with known facts

8. **Confirm** with the output path and a list of the H2 sections written.

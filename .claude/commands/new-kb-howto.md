Generate a new KB how-to article.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {slug}` — e.g. `3d python how-to-convert-fbx-to-gltf`

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
- `product_name` — use for package references

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

1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `slug` (slug becomes the filename and title source).

2. **Read existing KB content for reference** (do not copy text — read only to confirm patterns):
   - Read one existing how-to file from `content/kb.aspose.org/en/{family}/{platform}/` to confirm exact frontmatter fields
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` to identify available classes, methods, and package names you may reference

3. **Generate frontmatter** using this exact structure (fill in placeholders):
   ```yaml
   ---
   title: {Human-readable title — convert slug hyphens to words, capitalise naturally}
   description: >
     {2 sentences: what the reader learns + which classes/methods are involved}
   date: '{today as YYYY-MM-DD}'
   lastmod: '{today as YYYY-MM-DD}'
   weight: 10
   draft: false
   type: topic
   keywords:
   - {action verb + noun + platform — e.g. "convert fbx to gltf python"}
   - {6–10 more SEO-oriented phrases, each on its own line}
   ---
   ```

4. **Generate body** using this exact section order:
   - Opening paragraph: what the library does for this task; state install prerequisites using the platform's package manager (from Platform Resolution)
   - `## Step-by-Step Guide`
   - `{{% steps %}}`
   - `### Step 1: Install the Package` — use `{install_command}` from model.yaml in the appropriate block format:
     - python: ```bash block with pip command
     - dotnet: ```bash block with dotnet CLI command
     - java: ```xml block with Maven POM dependency
     - cpp: ```bash or ```cmake block
     - typescript/javascript/nodejs: ```bash block with npm command
     Then add a version/install check snippet in ```{platform_lang} fence
   - `### Step 2: Import Required Classes` — exact import statements matching the package, in ```{platform_lang} fence
   - `### Step 3–N:` — one step per logical task action, each with a prose explanation followed by a working code block in ```{platform_lang} fence
   - `{{% /steps %}}`
   - `## Common Issues and Fixes` — 3–5 bold-question + answer-paragraph pairs for likely errors
   - `## Frequently Asked Questions` — 3–5 `### Question?` + answer-paragraph pairs
   - `## See Also` — 3–5 links using pattern `[Article Title](/kb.aspose.org/en/{family}/{platform}/slug/)`

5. **Constraints** (hard rules — never violate):
   - Every code block must use ```{platform_lang} (resolved from Platform Resolution above) or ```bash / ```xml / ```cmake as appropriate for shell and config blocks
   - Use `---` horizontal divider between each step inside `{{% steps %}}`
   - Class names, method names, and import paths must exactly match what appears in the reference content you read — do not invent new API names
   - All internal links must begin with `/kb.aspose.org/`, `/docs.aspose.org/`, or `/reference.aspose.org/`
   - All claims must be backed by entries in `knowledge/{family}/{platform}/merged/claims.json`

6. **Write** the file to `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`

## Knowledge Post-conditions

After generating the article:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to generate the `evidence:` YAML frontmatter block with claims, APIs, and per-section binding
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Run `python scripts/pipeline/change_guard.py {family} {platform} --file content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to verify no contradictions with known facts

7. **Confirm** by printing the output file path and a short summary of steps covered.

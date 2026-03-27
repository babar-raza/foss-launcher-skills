Generate or update the FAQ page for a product platform.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `cells python`

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
2. **Load verified facts**: Read `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
3. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never include these in content
4. **Load format matrix**: Read `formats.json` — only reference formats confirmed here
5. **Load limitations**: Read `limitations.md` for known NotImplementedError items

## Platform Resolution

Read `knowledge/{family}/{platform}/scout/model.yaml` to determine:
- `install_command` — use this verbatim instead of hardcoding any install command
- `canonical_import` — use this for import statements
- `product_name` — use for package references
- `version` — use for version-specific answers

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

1. **Parse** `$ARGUMENTS` into `family` and `platform`.

2. **Check if an FAQ exists** at `content/kb.aspose.org/en/{family}/{platform}/faq.md`:
   - If it exists: read the full file, identify what questions are already covered, then add new questions at the end (do not duplicate)
   - If it does not exist: create from scratch following the full template below

3. **Read for context** (read only — do not copy):
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` to understand available classes, limitations, and format support
   - Read one existing how-to article from `content/kb.aspose.org/en/{family}/{platform}/` to see keyword style

4. **Frontmatter** (for new files — preserve existing frontmatter when updating):
   ```yaml
   ---
   title: Frequently Asked Questions
   description: >
     FAQ about Aspose.{Family} FOSS for {Platform} — licensing, known limitations,
     format support, and common usage questions.
   date: '{today as YYYY-MM-DD}'
   lastmod: '{today as YYYY-MM-DD}'
   weight: 1
   draft: false
   type: topic
   keywords:
   - {product name} {platform} faq
   - {product name} {platform} licensing
   - {product name} open source
   - {6–10 more question-oriented keywords}
   ---
   ```
   When updating an existing file: update only `lastmod` to today's date; leave all other frontmatter unchanged.

5. **Content structure** — write or append these FAQ categories (skip categories that are already fully covered):

   **Licensing & Open Source** (2–3 questions):
   - What is the licensing model?
   - Can I use it in commercial products?

   **Installation & Requirements** (2–3 questions):
   - How do I install? — answer using `{install_command}` from model.yaml and reference the appropriate package manager ({package_manager})
   - What runtime versions are supported? (e.g. Python versions, .NET versions, JDK versions, C++ standard — adjust for platform)
   - Are there any native dependencies?

   **Format Support** (2–4 questions):
   - Which formats can be read / written?
   - Known limitations per format (FBX exporter, animation stubs, etc. — based on what you read)

   **API Usage** (3–5 questions):
   - Typical pattern for the main entry-point class (e.g. `Scene`, `Workbook`, `Presentation`)
   - How to traverse/iterate the data model
   - Saving in different formats
   - Code examples in ```{platform_lang} fence

   **Known Limitations** (2–3 questions):
   - Features that are stubbed or not yet implemented (base answers on what you observed in reference content)

   Each question uses `### Question text?` as the heading followed by one or more answer paragraphs.

6. **Constraints**:
   - All class names, method names, and package import paths must match what you read from the reference content — do not invent API surface
   - Code examples use ```{platform_lang} (resolved from Platform Resolution above) or ```bash / ```xml / ```cmake for shell and config blocks
   - `weight: 1` ensures FAQ appears first in the KB listing — never change this value

7. **Write** to `content/kb.aspose.org/en/{family}/{platform}/faq.md`

## Knowledge Post-conditions

After generating or updating the FAQ:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/kb.aspose.org/en/{family}/{platform}/faq.md` to generate the `evidence:` YAML frontmatter block with claims, APIs, and per-section binding
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/faq.md` to validate structure and knowledge alignment
3. **Run change guard**: Run `python scripts/pipeline/change_guard.py {family} {platform} --file content/kb.aspose.org/en/{family}/{platform}/faq.md` to verify no contradictions with known facts

8. **Confirm** by printing the output path and a count of FAQ items written or added.

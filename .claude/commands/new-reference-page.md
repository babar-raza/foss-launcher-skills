Generate a new API reference page for reference.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {classname}` — e.g. `3d python polygon-modifier`
The classname argument is used as both the slug (filename) and the class display name (PascalCase the slug for title).

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
2. **Load API surface**: Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - The class being documented MUST exist in api_surface.json — do not document classes that aren't verified
   - Use method signatures, property types, and docstrings from api_surface.json as the authoritative source
3. **Load class graph**: Read `knowledge/{family}/{platform}/merged/class_graph.json` for inheritance chain
4. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never reference capabilities that are not implemented

## Platform Resolution

Read `knowledge/{family}/{platform}/scout/model.yaml` to determine:
- `install_command` — use this for install references
- `canonical_import` — use this for import path references
- `product_name` — use for package name references
- `version` — use for version display

Determine the **code fence language** from the platform:
- python → `python`
- dotnet → `csharp`
- java → `java`
- cpp → `cpp`
- typescript → `typescript`
- javascript → `javascript`
- nodejs → `javascript`

Determine the **class declaration syntax** from the platform:
- python → `class {ClassName}({ParentClass}):`
- dotnet → `public class {ClassName} : {ParentClass}`
- java → `public class {ClassName} extends {ParentClass}`
- cpp → `class {ClassName} : public {ParentClass}`
- typescript/javascript → `class {ClassName} extends {ParentClass}`

Use these resolved values (`{platform_lang}`, `{class_declaration_syntax}`) throughout the generated content. Never hardcode a platform-specific syntax.

## Steps

1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `classname-slug`.
   - Derive `ClassName` (PascalCase) from the slug: e.g. `polygon-modifier` → `PolygonModifier`

2. **Read reference content for context** (read only — do not copy):
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` to understand:
     - The package name (e.g. `aspose.threed.entities`, `Aspose.Slides.Foss`, `org.aspose.slides.foss`, etc.)
     - The library version
     - What other classes exist and how the class you're documenting relates to them
   - Read one or two existing class reference pages in the same platform to confirm exact formatting style

3. **Generate frontmatter**:
   ```yaml
   ---
   linkTitle: {ClassName}
   title: {ClassName}
   description: >
     {2 sentences: what this class does, what it stores/manages, and its key properties or methods.
     Include inheritance parent if known.}
   summary: >
     {Same 2 sentences as description — used in listing cards}
   categories:
   - {Class | Enum | Interface — pick the correct one}
   layout: reference-single
   ---
   ```
   Note: no `date`, `lastmod`, `draft`, `type`, or `weight` fields on reference pages.

4. **Generate body** in this exact structure:

   ```
   Package: `{package.name}` ({product_name} {version})
   ```

   Short paragraph (2–4 sentences) describing what the class does, its relationship to other classes, and typical usage pattern.

   ```{platform_lang}
   {class_declaration_syntax for this ClassName and ParentClass}
   ```

   `#### Inheritance`
   `{RootClass} → {…} → {ParentClass} → {ClassName}`

   `---`

   `## Examples`

   Provide 2–3 labelled code examples:
   - **Bold label** followed by a working code snippet in ```{platform_lang} fence
   - Examples must demonstrate the most common real-world uses
   - All imports, class names, method calls must match what you confirmed exists in the reference index

   `---`

   `## Properties`

   Markdown table:
   | Property | Type | Access | Description |
   |----------|------|--------|-------------|
   *(one row per property)*

   Access values: `read` | `read/write`

   `---`

   `## Methods` (omit if the class has no public methods beyond inherited ones)

   For each method:
   - `### {method_name}(params) → ReturnType`
   - 1-sentence description
   - Parameter table: | Parameter | Type | Description |
   - Short code example in ```{platform_lang} fence

   `---`

   `## See Also`
   - 3–5 links to related class pages using `[ClassName](/reference.aspose.org/en/{family}/{platform}/classname-slug/)`

5. **Constraints**:
   - `layout: reference-single` must always be present — this triggers the custom Hugo template
   - Class name, parent class, package name, and property names must match what you read from the reference index — do not invent API surface
   - Code examples use ```{platform_lang} (resolved from Platform Resolution above)
   - The `---` divider separates Examples, Properties, Methods, and See Also blocks

6. **Write** to `content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md`

## Knowledge Post-conditions

After generating the reference page:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md` to generate the `evidence:` YAML frontmatter block with claims, APIs, and per-section binding
2. **Run content check**: Execute `/content-check content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md` to validate structure and knowledge alignment

7. **Confirm** with the output path and a count of properties and methods documented.

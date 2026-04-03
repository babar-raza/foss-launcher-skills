---
name: new-reference-page
description: >
  Generate a new API reference page for reference.aspose.org
args: "{family} {platform} {ClassName}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-60: New Reference Page — Generate API Reference Page

Generate a new API reference page for reference.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {ClassName}` — e.g. `3d python PolygonModifier`
The ClassName argument is the exact class name as it appears in the repo (PascalCase). It is used directly as the filename stem.

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Bootstrap knowledge**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `KNOWLEDGE: STOP:partial` → halt (see printed message)
   - `KNOWLEDGE: REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run
     `/knowledge-diff` to review what changed before generating content, then re-run this command."
   - `KNOWLEDGE: READY`, `KNOWLEDGE: BOOTSTRAPPED`, or `KNOWLEDGE: WARN:conflicts` → continue
2. **Load API surface**: Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - The class being documented MUST exist in api_surface.json — do not document classes that aren't verified
   - Use method signatures, property types, and docstrings from api_surface.json as the authoritative source
2b. **Read API surface summary**: Read `knowledge/{family}/{platform}/merged/api_surface.md`
    - This is the concise, human-readable API reference
    - Every class name, method, property, and enum value in your generated content MUST appear in this file
    - If a name is not in api_surface.md, do not use it
3. **Load class graph**: Read `knowledge/{family}/{platform}/merged/class_graph.json` for inheritance chain
4. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never reference capabilities that are not implemented

## Steps

0b. **Package name validation** (run before any content generation):
   - Read `knowledge/{family}/{platform}/scout/model.yaml` → `canonical_import`
   - This is the ground-truth package identifier (e.g. `aspose.slides_foss`, `org.aspose.slides.foss`)
   - If `canonical_import` is empty or missing:
     **STOP**: "canonical_import not set in scout/model.yaml. Run `/repo-scout {family} {platform}` first."
   - Store as `{CANONICAL_IMPORT}` for use in frontmatter and throughout the page body.
   - **Validation**: If `{CANONICAL_IMPORT}` contains `aspose.` without `_foss` suffix (Python),
     or `com.aspose.` without `.foss` (Java), or `Aspose.` without `.Foss` (.NET):
     WARN: "Package name `{CANONICAL_IMPORT}` does not look like a FOSS package. Verify against clone:
     `python scripts/pipeline/core/clone_cache.py resolve {family} {platform}` then check
     setup.py/pom.xml/package.json for the correct package identifier."

1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `ClassName`.
   - `ClassName` is already PascalCase — use it as-is for both the filename and display name.

2. **Read reference content for context** (read only — do not copy):
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` to understand:
     - The package name (e.g. `aspose.threed.entities`, `aspose.cells`, etc.)
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
   Package: `{package.name}` ({pypi-package-name} {version})
   ```

   Short paragraph (2–4 sentences) describing what the class does, its relationship to other classes, and typical usage pattern.

   ` ```python `
   `class {ClassName}({ParentClass}):`
   ` ``` `

   `#### Inheritance`
   `{RootClass} → {…} → {ParentClass} → {ClassName}`

   `---`

   `## Examples`

   Provide 2–3 labelled code examples:
   - **Bold label** followed by a working Python snippet
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
   - Short code example

   `---`

   `## See Also`
   - 3–5 links to related class pages — template: `[ClassName](/reference.aspose.org/en/{family}/{platform}/{ClassName}/)`
   - Example: `[PolygonModifier](/reference.aspose.org/en/3d/python/PolygonModifier/)`

5. **Constraints**:
   - `layout: reference-single` must always be present — this triggers the custom Hugo template
   - Class name, parent class, package name, and property names must match what you read from the reference index — do not invent API surface
   - Code examples use the platform's code fence language: `python` (Python), `csharp` (.NET), `java` (Java), `cpp` (C++), `typescript` (TypeScript)
   - The `---` divider separates Examples, Properties, Methods, and See Also blocks

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Write** to `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`

## Platform-Specific Rendering Rules

### TypeScript: Property vs. Method Rendering (FR-14)

When generating TypeScript reference pages, check the `kind` field for each member in api_surface.json:

- If `kind: property` → render as a **Property** row in the Properties table:
  - Columns: `Property | Type | Access | Description`
  - Use `access_mode` field: `readonly` → `Read`, `readwrite` → `Read/Write`, `writeonly` → `Write`
  - Do NOT append `()` to the property name — properties are accessed without parentheses in TypeScript
  - Example: `binaryMode` property of type `boolean`, access `Read/Write`
- If `kind: method` (or no `kind` field) → render as a **Method** section with `methodName(params)` heading (including `()`)
- This rule is critical: TypeScript getter/setter accessors are properties, not callable methods. Rendering `binaryMode()` as a method will produce incorrect documentation.

### class_import Usage (FR-15)

When generating the import/package line at the top of a reference page:
- Check api_surface.json for the `class_import` field on the class entry
- If `class_import` is present, use it as the authoritative import path
- Example: `class_import: "com.aspose.threed.shading.PbrMaterial"` → render `import com.aspose.threed.shading.PbrMaterial;`
- If `class_import` is absent, fall back to `canonical_import` from `scout/model.yaml`
- Do NOT guess or construct the import path from the class name alone

### C++ canonical_namespace (FR-15)

For C++ reference pages, the namespace label must use the full qualified namespace:
- Check api_surface.json for the `canonical_namespace` field on the class entry
- If `canonical_namespace` is present (e.g. `Aspose::Slides::Foss::Drawing`), use it as the namespace label
- Do NOT use a shortened or root-only namespace (e.g. do not use `Aspose::Slides` when the canonical is `Aspose::Slides::Foss`)
- Example: `canonical_namespace: "Aspose::Slides::Foss::Drawing"` → `**Namespace**: Aspose::Slides::Foss::Drawing`

### Stub Method Callout (FR-16)

When a method has `stub: true` in api_surface.json, emit the following callout block immediately **above** the method description (before the parameter table):

```
> **Not implemented**: This method raises NotImplementedException in the current release.
```

Do not omit stub methods from the reference page — document them with the callout so developers know the method signature exists but is not yet functional. This is especially important for Aspose FOSS libraries where many methods are scaffolded but not yet implemented.

## Knowledge Post-conditions

After generating the reference page:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md` to validate structure and knowledge alignment
3. **Run audit**: `python scripts/pipeline/audit.py --files content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
   — must exit with 0 FAIL before committing.

7. **Confirm** with the output path and a count of properties and methods documented.

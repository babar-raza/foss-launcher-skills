---
name: new-reference-page
description: >
  Generate a new API reference page for reference.aspose.org documenting a
  single class with properties, methods, examples, and inheritance chain.
args: "{family} {platform} {classname}"
---
Generate a new API reference page for reference.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {classname}` — e.g. `3d python polygon-modifier`
The classname argument is used as both the slug (filename) and the class display name (PascalCase the slug for title).

## Knowledge Pre-conditions

Before generating any content, you MUST:

0. **Validate setup**: Run `python scripts/check_setup.py --family {family} --platform {platform}`
   - If exit code 2 (ERROR): STOP and report the error to the user before proceeding.
   - If exit code 1 (WARN): proceed but surface all warnings.

1. **Read knowledge model**: Load `knowledge/{family}/{platform}/merged/index.json`
   - If it does not exist, STOP and instruct the user to run `/repo-scout` and `/truth-merge` first
   - If `stale: true`, STOP and instruct the user to run `/knowledge-diff` first
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

1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `classname-slug`.
   - Derive `ClassName` (PascalCase) from the slug: e.g. `polygon-modifier` → `PolygonModifier`

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
   - 3–5 links to related class pages using `[ClassName](/reference.aspose.org/en/{family}/{platform}/classname-slug/)`

5. **Constraints**:
   - `layout: reference-single` must always be present — this triggers the custom Hugo template
   - Class name, parent class, package name, and property names must match what you read from the reference index — do not invent API surface
   - Code examples use ` ```python ` language identifier
   - The `---` divider separates Examples, Properties, Methods, and See Also blocks

6. **Write** to `content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md`

## Knowledge Post-conditions

After generating the reference page:

1. **Run evidence citation**: Execute `/evidence-cite content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md` to write the YAML `evidence:` frontmatter block
2. **Run content check**: Execute `/content-check content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md` to validate structure and knowledge alignment
3. **Pre-write gate**: Run `python scripts/pre_write.py {output-file}` before committing
   - Exit 0 (PASS/WARN): proceed
   - Exit 1 (FAIL): do NOT commit — report findings to user and offer to fix

7. **Confirm** with the output path and a count of properties and methods documented.

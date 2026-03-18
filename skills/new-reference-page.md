---
name: new-reference-page
description: >
  Generate a new API reference page for reference.aspose.org documenting a
  single class with properties, methods, examples, and inheritance chain.
args: "{family} {platform} {classname}"
---
Generate a new API reference page for reference.aspose.org.

> **Configuration**: Output paths below are defaults for the aspose.org repo. See `config.yaml` `sites.reference` for your project's reference content path.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {classname}` — e.g. `3d python polygon-modifier`
The classname argument is used as both the slug (filename) and the class display name (PascalCase the slug for title).

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Read knowledge model**: Load `knowledge/{family}/{platform}/merged/index.json`
   - If it does not exist, STOP and instruct the user to run `/repo-scout` and `/truth-merge` first
   - If `stale: true`, STOP and instruct the user to run `/knowledge-diff` first
2. **Load API surface**: Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - The class being documented MUST exist in api_surface.json — do not document classes that aren't verified
   - Use method signatures, property types, and docstrings from api_surface.json as the authoritative source
3. **Load class graph**: Read `knowledge/{family}/{platform}/merged/class_graph.json` for inheritance chain
4. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never reference capabilities that are not implemented

## Golden Corpus Pre-conditions

1. **Load corpus profile**: Read `knowledge/{family}/{platform}/_corpus/reference_profile.json`
   - If not found → WARN and suggest running `/corpus-scan {family} {platform} reference`; proceed with default template

2. **Load golden index**: Read `golden/_index.json`
   - If not found → WARN and suggest running `python scripts/golden_index.py`; proceed with default template

3. **Determine variant**: Read `selected_variant` from the corpus profile
   - If `richness_tier: C` → use "minimal" variant (class definition + properties table only)
   - If `richness_tier: A` or `B` → use "standard" variant (full with examples, methods, see also)

4. **Select golden page**: From `golden/_index.json`, find the page where `page_role` is `api_reference` and `variant` matches the selected variant
   - If no match → fall back to "standard" variant

5. **Read the golden file**: Read the actual golden `.md` file at the `source_path` from the index entry

6. **Apply STRUCTURAL CONTRACTS**: For EACH section you generate, find the matching section in the golden page (by heading) and follow its structural contract:
   - Required block types (paragraph, code, list, table) at minimum counts
   - Target prose word count and code block count

7. **Apply STYLE ANCHOR**: Use the first 600 chars of the matching golden section as a style reference — match its voice and depth. Do NOT copy its actual content.

8. **Apply STYLE RUBRIC** from the golden page's `style_rubric`:
   - If `prose_before_code: true` → every code block must be preceded by a prose paragraph
   - If `code_completeness_required: true` → code must show import + usage + verification pattern
   - Include at least `min_code_variety` distinct code examples

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
   - {Class | Enum | Interface — pick based on api_surface.json: if class has `enum_members` → Enum}
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
   *(one row per property from api_surface.json `properties` array)*

   Access values — map from the `read_write` field in api_surface.json:
   - `read_write: true` → "read/write"
   - `read_write: false` or absent → "read"

   `---`

   `## Enum Members` *(only if the class has `enum_members` in api_surface.json — omit for non-enum classes)*

   Markdown table:
   | Member | Value | Description |
   |--------|-------|-------------|
   *(one row per entry from api_surface.json `enum_members` array)*

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

1. **Run evidence citation**: Execute `/evidence-cite content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md` to attach `<!-- evidence: api=... -->` comments
2. **Run content check**: Execute `/content-check content/reference.aspose.org/en/{family}/{platform}/{classname-slug}.md` to validate structure and knowledge alignment

7. **Confirm** with the output path and a count of properties and methods documented.

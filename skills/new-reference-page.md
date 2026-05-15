<!-- CONTRACT: agent-executed
     purpose: generate an API reference page for reference.aspose.org with class/member docs
     preconditions: api_surface.json exists; class must be present in api_surface.json
     postcondition: new reference page with properties, methods, inheritance, and evidence attached
     idempotent: no — LLM-generated descriptions and examples vary between invocations
     verified: 2026-04-11
-->
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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-60 --scope "*"
> ```


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
     {2 sentences derived from the class `doc` field in api_surface.json.
     If `doc` is empty or absent, write exactly: [No documentation available — class summary not captured by scout]
     Include inheritance parent if known.}
   summary: >
     {Same 2 sentences as description — used in listing cards}
   categories:
   - {Class | Enum | Interface — pick the correct one}
   layout: single
   provenance:
     content_origin: skill-generated
     last_mechanism: skill
     auto_updatable: true
   ---
   ```
   Note: no `date`, `lastmod`, `draft`, `type`, or `weight` fields on reference pages.

   **D-1 enforcement**: The `description:` value MUST come from `api_surface.json → class.doc`.
   If the doc string is absent or empty, write `[No documentation available — class summary not captured by scout]`.
   Do NOT invent a description. This causes the structure evaluator to flag the page for human review.

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

   **D-3 enforcement**: The `Access` column value MUST be derived from `api_surface.json → property.writable`:
   - `writable: true` → `Read/Write`
   - `writable: false` or absent → `Read`
   Do NOT default all properties to `Read`. Check each property individually.

   `---`

   `## Methods` (omit if the class has no public methods beyond inherited ones)

   For each method:
   - `### {method_name}(params) → ReturnType`
   - 1-sentence description
   - Parameter table: | Parameter | Type | Description |
   - Short code example

   **D-2 enforcement**: The `ReturnType` in the method heading MUST come from `api_surface.json → method.return_type`.
   - If `return_type` is non-empty and not `void`/`None`: write `→ {return_type}`
   - If `return_type` is empty, `void`, or `None`: omit the `→ ReturnType` part or write `→ None`
   Do NOT default all methods to `void` or leave ReturnType blank.

   `---`

   `## See Also`
   - 3–5 links to related class pages — template: `[ClassName](/reference.aspose.org/en/{family}/{platform}/{ClassName}/)`
   - Example: `[PolygonModifier](/reference.aspose.org/en/3d/python/PolygonModifier/)`

5. **Constraints**:
   - `layout: single` must always be present — bypasses `layouts/_default/section.html` and uses `themes/docs/layouts/_default/single.html`
   - Class name, parent class, package name, and property names must match what you read from the reference index — do not invent API surface
   - Code examples use the platform's code fence language: `python` (Python), `csharp` (.NET), `java` (Java), `cpp` (C++), `typescript` (TypeScript)
   - The `---` divider separates Examples, Properties, Methods, and See Also blocks

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Write** to `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`

7b. **Backlink injection**: After writing, inject the reciprocal aspose.com backlink into
    the `## See Also` section (idempotent — skips if already present):
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py \n      --family {family} --platform {platform} --subdomain reference.aspose.org --write
    ```
    If BLOCKED_TARGET: log WARN and continue.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-60 --status completed
> ```

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

1. **Attach evidence**: Run `python scripts/pipeline/commands/healing/attach_evidence.py --files content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md` to validate structure and knowledge alignment
3. **Run audit**: `python scripts/pipeline/commands/content/audit.py --files content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
   — must exit with 0 FAIL before committing.

7. **Confirm** with the output path and a count of properties and methods documented.

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
